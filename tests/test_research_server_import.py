"""Bounded private research transfer, without external downloads or server changes."""

import base64
import contextlib
import copy
import datetime as dt
import hashlib
import importlib
import io
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    sender = importlib.import_module("encrypt_research_url")
    receiver = importlib.import_module("research_server_import")
    stage = importlib.import_module("research_backend_stage")
finally:
    sys.path.pop(0)


def sample_url():
    expiry = (
        dt.datetime.fromtimestamp(time.time() + 1800, dt.UTC).isoformat().replace("+00:00", "Z")
    )
    return f"https://{sender.DOWNLOAD_HOST}/research.zip?se={expiry}&sp=r&sig=PRIVATE_FIXTURE_TOKEN"


@pytest.fixture(scope="module")
def prepared_key(tmp_path_factory):
    directory = tmp_path_factory.mktemp("research-key")
    private, certificate = directory / "private.pem", directory / "certificate.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:3072",
            "-nodes",
            "-sha256",
            "-days",
            "1",
            "-subj",
            "/CN=local-test",
            "-keyout",
            str(private),
            "-out",
            str(certificate),
        ],
        capture_output=True,
        check=True,
    )
    private.chmod(0o600)
    certificate.chmod(0o600)
    public = subprocess.run(
        ["openssl", "pkey", "-in", str(private), "-pubout", "-outform", "DER"],
        capture_output=True,
        check=True,
    ).stdout
    now = int(time.time())
    document = {
        "schema": "mizan-research-key-v1",
        "key_id": "a" * 32,
        "created_unix": now,
        "expires_unix": now + 3600,
        "public_key_sha256": hashlib.sha256(public).hexdigest(),
        "certificate_pem": certificate.read_text(),
        "bundle_sha256": sender.BUNDLE_SHA256,
        "bundle_bytes": sender.BUNDLE_BYTES,
        "target": {"persistent": True, "target": {"exists": False}, "image_id": "sha256:expected"},
    }
    return directory, document


def decrypt(monkeypatch, envelope, document, directory):
    monkeypatch.setattr(receiver, "private_file", lambda path, maximum: path.read_bytes())
    return receiver.decrypt_envelope(envelope, document, directory)


def test_real_authenticated_envelope_roundtrip_and_no_plaintext_ciphertext_artifact(
    monkeypatch, prepared_key
):
    directory, document = prepared_key
    url = sample_url()
    envelope = sender.encrypted_envelope(document, url)
    assert set(envelope) == {"schema", "key_id", "ciphertext_b64"}
    assert "PRIVATE_FIXTURE_TOKEN" not in json.dumps(envelope)
    assert sender.DOWNLOAD_HOST not in json.dumps(envelope)
    payload = decrypt(monkeypatch, envelope, document, directory)
    assert payload["url"] == url
    assert payload["target_sha256"] == sender.target_digest(document["target"])


def test_tampered_tag_never_releases_or_parses_provisional_plaintext(monkeypatch, prepared_key):
    directory, document = prepared_key
    envelope = sender.encrypted_envelope(document, sample_url())
    ciphertext = bytearray(base64.b64decode(envelope["ciphertext_b64"]))
    ciphertext[-1] ^= 1
    envelope["ciphertext_b64"] = base64.b64encode(ciphertext).decode()
    with pytest.raises(receiver.TransferError) as error:
        decrypt(monkeypatch, envelope, document, directory)
    assert "PRIVATE_FIXTURE_TOKEN" not in str(error.value)
    assert sender.DOWNLOAD_HOST not in str(error.value)


@pytest.mark.parametrize(
    "flags",
    [
        ["-aes-256-cbc"],
        ["-aes-256-gcm"],
        ["-aes-256-gcm", "-keyopt", "rsa_padding_mode:oaep"],
        [
            "-aes-128-gcm",
            "-keyopt",
            "rsa_padding_mode:oaep",
            "-keyopt",
            "rsa_oaep_md:sha256",
            "-keyopt",
            "rsa_mgf1_md:sha256",
        ],
    ],
)
def test_receiver_refuses_cbc_pkcs1_sha1_and_short_cipher_downgrades(prepared_key, flags):
    directory, _ = prepared_key
    result = subprocess.run(
        [
            "openssl",
            "cms",
            "-encrypt",
            "-binary",
            "-recip",
            str(directory / "certificate.pem"),
            *flags,
            "-outform",
            "DER",
        ],
        input=b"untrusted data",
        capture_output=True,
        check=True,
    )
    with pytest.raises(receiver.TransferError):
        receiver.validate_cms(result.stdout)


def test_authenticated_target_binding_is_mandatory(monkeypatch, prepared_key):
    directory, document = prepared_key
    changed = copy.deepcopy(document)
    changed["target"]["image_id"] = "sha256:different"
    envelope = sender.encrypted_envelope(changed, sample_url())
    with pytest.raises(receiver.TransferError, match="binding"):
        decrypt(monkeypatch, envelope, document, directory)


@pytest.mark.parametrize(
    "replace",
    [
        ("https://", "http://"),
        (sender.DOWNLOAD_HOST, "example.com"),
        (sender.DOWNLOAD_HOST, sender.DOWNLOAD_HOST + ".example.com"),
        (sender.DOWNLOAD_HOST, "user:password@" + sender.DOWNLOAD_HOST),
        (sender.DOWNLOAD_HOST, sender.DOWNLOAD_HOST + ":443"),
        ("sp=r", "sp=rw"),
        ("sp=r", "sp=r&se=2000-01-01T00:00:00Z"),
        ("research.zip", "research.zip\nprivate"),
    ],
)
def test_url_origin_permissions_and_metadata_are_strict(replace):
    with pytest.raises(receiver.TransferError):
        sender.validate_url(sample_url().replace(*replace))


def test_expired_and_overlong_key_or_url_validity_are_refused(prepared_key):
    _, document = prepared_key
    with pytest.raises(receiver.TransferError):
        sender.validate_key(document, now=document["expires_unix"])
    with pytest.raises(receiver.TransferError):
        sender.validate_key({**document, "expires_unix": document["created_unix"] + 3601})
    for timestamp in (time.time() - 1, time.time() + 7200):
        expiry = dt.datetime.fromtimestamp(timestamp, dt.UTC).isoformat()
        with pytest.raises(receiver.TransferError):
            sender.validate_url(f"https://{sender.DOWNLOAD_HOST}/x?sp=r&se={expiry}")


class Download:
    def __init__(self, content=b"known", status=200, declared="5"):
        self.body = io.BytesIO(content)
        self.status = status
        self.declared = declared
        self.requests = []
        self.closed = False

    def getheader(self, name):
        return self.declared if name == "Content-Length" else None

    def read1(self, count):
        return self.body.read(count)

    def request(self, *args, **kwargs):
        self.requests.append((args, kwargs))

    def getresponse(self):
        return self

    def close(self):
        self.closed = True


def mocked_download(monkeypatch, connection):
    monkeypatch.setattr(receiver, "BUNDLE_BYTES", 5)
    monkeypatch.setattr(receiver, "BUNDLE_SHA256", hashlib.sha256(b"known").hexdigest())
    monkeypatch.setattr(receiver.http.client, "HTTPSConnection", lambda host, timeout: connection)


def test_streamed_download_verifies_exact_bytes_and_hash_without_auth_header(monkeypatch, tmp_path):
    connection = Download()
    mocked_download(monkeypatch, connection)
    path = tmp_path / "bundle.zip"
    receiver.download_bundle(sample_url(), path)
    assert path.read_bytes() == b"known"
    assert path.stat().st_mode & 0o777 == 0o600
    assert connection.closed
    assert len(connection.requests) == 1
    assert "Authorization" not in connection.requests[0][1]["headers"]


@pytest.mark.parametrize(
    "connection",
    [
        Download(status=302),
        Download(declared="6"),
        Download(content=b"known!"),
        Download(content=b"kn"),
        Download(content=b"other"),
    ],
)
def test_redirect_length_overflow_truncation_and_wrong_hash_stop_before_import(
    monkeypatch, tmp_path, connection
):
    mocked_download(monkeypatch, connection)
    with pytest.raises(receiver.TransferError):
        receiver.download_bundle(sample_url(), tmp_path / "bundle.zip")
    assert len(connection.requests) == 1
    assert connection.closed


def test_downloader_error_never_leaks_url(monkeypatch, tmp_path):
    connection = Download()
    mocked_download(monkeypatch, connection)

    def failure(*args, **kwargs):
        raise OSError(sample_url())

    monkeypatch.setattr(connection, "getresponse", failure)
    with pytest.raises(receiver.TransferError) as error:
        receiver.download_bundle(sample_url(), tmp_path / "bundle.zip")
    assert "PRIVATE_FIXTURE_TOKEN" not in str(error.value)


def stage_fixture(monkeypatch, tmp_path):
    target = tmp_path / "research"
    temporary, release = tmp_path / "private-stage", tmp_path / "release"
    monkeypatch.setattr(stage, "validate_target", lambda config: (target, temporary, release))
    monkeypatch.setattr(stage, "BUNDLE_BYTES", 5)
    monkeypatch.setattr(stage, "BUNDLE_SHA256", hashlib.sha256(b"known").hexdigest())
    monkeypatch.setattr(stage, "process_start", lambda pid: "123456")
    receipt = {
        "bundle_sha256": stage.BUNDLE_SHA256,
        "archive_members": 21486,
        "indexed_text_files": 7665,
        "training_gold": False,
        "fts_search_verified": True,
    }

    def import_bundle(bundle, destination):
        destination.mkdir(mode=0o700)
        (destination / "IMPORT.json").write_text(json.dumps(receipt))

    fake = SimpleNamespace(BUNDLE_SHA256=stage.BUNDLE_SHA256, import_bundle=import_bundle)
    monkeypatch.setitem(sys.modules, "mizan_owned.research", fake)
    monkeypatch.setattr(stage, "verify_collection", lambda root, **kwargs: receipt)
    return target, temporary, release


def install_config():
    return {"key_id": "a" * 32, "operation_deadline_unix": int(time.time()) + 840}


def test_backend_user_stage_preserves_original_and_activates_only_complete_release(
    monkeypatch, tmp_path
):
    target, temporary, release = stage_fixture(monkeypatch, tmp_path)
    result = stage.install(install_config(), io.BytesIO(b"known"))
    assert result["status"] == "active"
    assert target.is_symlink() and target.resolve() == release
    assert (target / "BUNDLE.source.zip").read_bytes() == b"known"
    assert json.loads((target / "FULL_IMPORT.json").read_text())["training_gold"] is False
    assert not temporary.exists()


def test_concurrent_existing_target_is_never_overwritten(monkeypatch, tmp_path):
    target, temporary, release = stage_fixture(monkeypatch, tmp_path)
    target.mkdir()
    (target / "existing.txt").write_text("preserve")
    with pytest.raises(FileExistsError):
        stage.install(install_config(), io.BytesIO(b"known"))
    assert (target / "existing.txt").read_text() == "preserve"
    assert not temporary.exists() and not release.exists()


def test_post_activation_failure_removes_only_own_new_link_and_stage(monkeypatch, tmp_path):
    target, temporary, release = stage_fixture(monkeypatch, tmp_path)
    original = stage.verify_collection

    def verify(root, **kwargs):
        if kwargs.get("use_default"):
            raise ValueError("query failed")
        return original(root, **kwargs)

    monkeypatch.setattr(stage, "verify_collection", verify)
    with pytest.raises(ValueError):
        stage.install(install_config(), io.BytesIO(b"known"))
    assert not os.path.lexists(target) and not temporary.exists() and not release.exists()


def test_invalid_transfer_bytes_are_not_passed_to_archive_importer(monkeypatch, tmp_path):
    target, temporary, release = stage_fixture(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="identity"):
        stage.install(install_config(), io.BytesIO(b"other"))
    assert not os.path.lexists(target) and not temporary.exists() and not release.exists()


def test_metadata_reader_has_a_real_read_bound(tmp_path):
    oversized = tmp_path / "metadata.json"
    oversized.write_bytes(b" " * 65537)
    with pytest.raises(receiver.TransferError, match="size"):
        sender.read_public_metadata(oversized)


def test_aggregate_deadline_also_covers_slow_headers(monkeypatch, tmp_path):
    connection = Download()
    mocked_download(monkeypatch, connection)
    previous = signal.getsignal(signal.SIGALRM)

    def blocked_headers():
        signal.getsignal(signal.SIGALRM)(signal.SIGALRM, None)

    monkeypatch.setattr(connection, "getresponse", blocked_headers)
    with pytest.raises(receiver.TransferError, match="aggregate"):
        receiver.download_bundle(sample_url(), tmp_path / "bundle.zip")
    assert signal.getsignal(signal.SIGALRM) == previous
    assert connection.closed


def test_backend_completion_is_awaited_on_handled_disconnect(monkeypatch, tmp_path):
    bundle = tmp_path / "bundle.zip"
    bundle.write_bytes(b"fixture")
    previous = signal.getsignal(signal.SIGHUP)
    events = []

    def process(*args, **kwargs):
        events.append("started")
        signal.getsignal(signal.SIGHUP)(signal.SIGHUP, None)
        events.append("completed")
        return SimpleNamespace(returncode=0, stdout=b'{"status":"active"}')

    monkeypatch.setattr(receiver.subprocess, "run", process)
    assert receiver.backend_stage("install", {}, bundle) == {
        "status": "active",
        "interruption_requested": True,
    }
    assert events == ["started", "completed"]
    assert signal.getsignal(signal.SIGHUP) == previous


@pytest.mark.parametrize(
    "status,expected",
    [
        ({"status": "active"}, "active"),
        ({"status": "failed", "target_absent": True}, "absent"),
        (None, "unknown"),
    ],
)
def test_client_failure_reconciles_exact_operation_without_retrying_install(
    monkeypatch, tmp_path, status, expected
):
    bundle = tmp_path / "bundle.zip"
    bundle.write_bytes(b"fixture")
    calls = []

    def process(*args, **kwargs):
        calls.append("install")
        raise subprocess.TimeoutExpired("docker", 900)

    def control(args, **kwargs):
        calls.append(args[-2])
        assert kwargs["timeout"] == 10
        if status is None:
            raise receiver.TransferError("Docker unreachable")
        return json.dumps(status).encode()

    monkeypatch.setattr(receiver.subprocess, "run", process)
    monkeypatch.setattr(receiver, "run", control)
    clock = [0]
    monkeypatch.setattr(receiver.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        receiver.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + 300)
    )
    if expected == "active":
        assert receiver.backend_stage("install", {}, bundle)["reconciled_after_client_failure"]
    elif expected == "absent":
        with pytest.raises(receiver.TransferError, match="target confirmed absent"):
            receiver.backend_stage("install", {}, bundle)
    else:
        with pytest.raises(receiver.OutcomeUnknown, match="outcome unknown"):
            receiver.backend_stage("install", {}, bundle)
        assert calls.count("status") == 6
        assert clock[0] >= 900
        assert "cancel" not in calls
    assert calls.count("install") == 1


@pytest.mark.parametrize("changed", ["target", "authentication"])
def test_failed_binding_or_authentication_consumes_private_key(
    monkeypatch, tmp_path, prepared_key, changed
):
    _, original = prepared_key
    document = copy.deepcopy(original)
    directory = tmp_path / document["key_id"]
    directory.mkdir()
    (directory / "key.json").write_text(json.dumps(document))
    (directory / "private.pem").write_text("fixture private")
    monkeypatch.setattr(receiver, "KEYS", tmp_path)
    monkeypatch.setattr(receiver, "deployment_lock", contextlib.nullcontext)
    monkeypatch.setattr(receiver, "secure_directory", lambda *args, **kwargs: None)
    monkeypatch.setattr(receiver, "private_file", lambda path, maximum: path.read_bytes())
    monkeypatch.setattr(receiver.os, "geteuid", lambda: 0)
    observed = copy.deepcopy(document["target"])
    if changed == "target":
        observed["image_id"] = "different"
    monkeypatch.setattr(receiver, "inspect_target", lambda: observed)

    def reject(*args):
        raise receiver.TransferError("Authentication failed")

    monkeypatch.setattr(receiver, "decrypt_envelope", reject)
    with pytest.raises(receiver.TransferError):
        receiver.import_transfer(json.dumps({"key_id": document["key_id"]}).encode())
    assert not directory.exists()


@pytest.mark.parametrize("same_process", [True, False])
def test_cancel_checks_pid_start_time_and_exact_request_identity(
    monkeypatch, tmp_path, same_process
):
    config = {"key_id": "a" * 32}
    target, temporary, release = tmp_path / "target", tmp_path / "stage", tmp_path / "release"
    temporary.mkdir()
    (temporary / "PROCESS.json").write_text(
        json.dumps({"pid": 1234, "start_ticks": "100", "key_id": config["key_id"]})
    )
    monkeypatch.setattr(stage, "operation_paths", lambda value: (target, temporary, release))
    monkeypatch.setattr(stage, "process_start", lambda pid: "100" if same_process else "other")
    old_read, old_stat = Path.read_bytes, Path.stat
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda path: (
            b"python\0-c\0reviewed-code\0install\0" + json.dumps(config).encode() + b"\0"
            if str(path) == "/proc/1234/cmdline"
            else old_read(path)
        ),
    )
    monkeypatch.setattr(
        Path,
        "stat",
        lambda path, **kwargs: (
            SimpleNamespace(st_uid=os.geteuid())
            if str(path) == "/proc/1234"
            else old_stat(path, **kwargs)
        ),
    )
    killed = []
    closed = []
    old_close = os.close
    monkeypatch.setattr(stage.os, "pidfd_open", lambda pid: 9999)
    monkeypatch.setattr(
        stage.signal, "pidfd_send_signal", lambda fd, signum: killed.append((fd, signum))
    )
    monkeypatch.setattr(
        stage.os, "close", lambda fd: closed.append(fd) if fd == 9999 else old_close(fd)
    )
    if same_process:
        assert stage.operation_status(config, cancel=True)["status"] == "running"
        assert killed == [(9999, signal.SIGTERM)]
    else:
        with pytest.raises(ValueError, match="identity"):
            stage.operation_status(config, cancel=True)
        assert killed == []
    assert closed == [9999]


def test_missing_process_marker_is_unknown_until_terminal_receipt_exists(monkeypatch, tmp_path):
    config = {"key_id": "a" * 32}
    target, temporary, release = tmp_path / "target", tmp_path / "stage", tmp_path / "release"
    monkeypatch.setattr(stage, "operation_paths", lambda value: (target, temporary, release))
    assert stage.operation_status(config)["status"] == "outcome_unknown"
    stage.write_operation_receipt(target, config, {"status": "failed", "target_absent": True})
    assert stage.operation_status(config)["status"] == "failed"


def test_reconciliation_cancels_at_most_once_and_uses_cached_helper(monkeypatch, tmp_path):
    bundle = tmp_path / "bundle.zip"
    bundle.write_bytes(b"fixture")
    calls, status_count = [], [0]

    def process(*args, **kwargs):
        def removed_helper(path, *args, **kwargs):
            raise FileNotFoundError("SSH cleanup already removed uploaded helper")

        monkeypatch.setattr(Path, "read_text", removed_helper)
        raise subprocess.TimeoutExpired("docker", 900)

    def control(args, **kwargs):
        calls.append(args[-2])
        assert args[6] == receiver.BACKEND_CODE
        if args[-2] == "status":
            status_count[0] += 1
        status = (
            {"status": "running"}
            if status_count[0] < 3
            else {"status": "failed", "target_absent": True}
        )
        return json.dumps(status).encode()

    monkeypatch.setattr(receiver.subprocess, "run", process)
    monkeypatch.setattr(receiver, "run", control)
    monkeypatch.setattr(receiver.time, "sleep", lambda seconds: None)
    with pytest.raises(receiver.TransferError, match="target confirmed absent"):
        receiver.backend_stage("install", {}, bundle)
    assert calls.count("cancel") == 1
    assert calls.count("status") == 3


def test_delayed_backend_start_and_late_activation_cannot_outlive_host_deadline(
    monkeypatch, tmp_path
):
    target, temporary, release = stage_fixture(monkeypatch, tmp_path)
    config = install_config()
    with pytest.raises(ValueError, match="deadline"):
        stage.install(
            {**config, "operation_deadline_unix": int(time.time()) - 1}, io.BytesIO(b"known")
        )
    assert not temporary.exists() and not release.exists()

    def slow_verification(root, **kwargs):
        monkeypatch.setattr(stage.time, "time", lambda: config["operation_deadline_unix"] + 1)
        return {"training_gold": False}

    monkeypatch.setattr(stage, "verify_collection", slow_verification)
    with pytest.raises(ValueError, match="deadline"):
        stage.install(config, io.BytesIO(b"known"))
    assert not os.path.lexists(target) and not temporary.exists() and not release.exists()
