"""Private research-transfer preflight, with no server or key-creation operations."""

import contextlib
import importlib.util
import json
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    "research_transfer_key",
    Path(__file__).resolve().parents[1] / "scripts/research_transfer_key.py",
)
key = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(key)


def target(**changed):
    return {
        "research_dir": "/data/research",
        "backend_uid": 1000,
        "backend_gid": 1000,
        "parent": {"exists": True, "uid": 1000, "gid": 1000, "mode": "0o700"},
        "target": {"exists": False},
        "parent_writable_by_backend": True,
        "importer_bundle_sha256": key.BUNDLE_SHA256,
        **changed,
    }


def inspect(monkeypatch, observation, mounts):
    container = {"container_id": "c", "image_id": "sha256:i", "image_ref": "sha", "mounts": mounts}
    outputs = iter((container, observation))
    monkeypatch.setattr(key, "run", lambda *args, **kwargs: json.dumps(next(outputs)).encode())
    return key.inspect_target()


def mount(destination="/data", **changed):
    return {
        "Destination": destination,
        "Source": "/volume",
        "Type": "volume",
        "RW": True,
        **changed,
    }


def test_actual_effective_user_and_deepest_persistent_mount_are_recorded(monkeypatch):
    found = inspect(
        monkeypatch,
        target(research_dir="/data/project/research"),
        [mount(), mount("/data/project", Name="project")],
    )
    assert found["persistent"]
    assert found["mount"]["Name"] == "project"
    assert found["backend_uid"] == found["backend_gid"] == 1000
    assert "mounts" not in found


@pytest.mark.parametrize(
    "directory,mounts",
    [
        ("/app/data/research", [mount()]),
        ("/data", [mount()]),
        ("/data/research", [mount(RW=False)]),
        ("/data/research", [mount(Type="tmpfs")]),
        ("/data/research", [mount(), mount("/data/research", Type="tmpfs")]),
        ("/data/project/research", [mount(), mount("/data/project", Type="tmpfs")]),
    ],
)
def test_ephemeral_read_only_or_mount_root_target_is_refused(monkeypatch, directory, mounts):
    assert not inspect(monkeypatch, target(research_dir=directory), mounts)["persistent"]


@pytest.mark.parametrize(
    "changed",
    [
        {"persistent": False},
        {"parent_writable_by_backend": False},
        {"target": {"exists": True, "symlink": False}},
        {"target": {"exists": True, "symlink": True}},
    ],
)
def test_failed_preflight_creates_no_keys(monkeypatch, changed):
    monkeypatch.setattr(key.os, "geteuid", lambda: 0)
    monkeypatch.setattr(key, "deployment_lock", contextlib.nullcontext)
    monkeypatch.setattr(key, "inspect_target", lambda: {**target(), "persistent": True, **changed})
    monkeypatch.setattr(
        key, "run", lambda *a, **k: pytest.fail("No key operations before successful preflight")
    )
    monkeypatch.setattr(
        key, "secure_directory", lambda *a, **k: pytest.fail("No transfer state creation")
    )
    with pytest.raises(key.TransferError):
        key.prepare_key()


@pytest.mark.parametrize(
    "mode,uid", [(stat.S_IFLNK | 0o700, 0), (stat.S_IFDIR | 0o777, 0), (stat.S_IFDIR | 0o700, 1000)]
)
def test_state_rejects_symlinks_untrusted_ownership_and_writable_directories(
    monkeypatch, mode, uid
):
    monkeypatch.setattr(Path, "lstat", lambda self: SimpleNamespace(st_mode=mode, st_uid=uid))
    with pytest.raises(key.TransferError):
        key.secure_directory(Path("/not-accessed"))


def test_protected_file_is_private_exclusive_and_never_follows_link(tmp_path):
    path = tmp_path / "key.json"
    key.protected_write(path, b"private")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        key.protected_write(path, b"replacement")
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(FileExistsError):
        key.protected_write(link, b"replacement")
    assert path.read_bytes() == b"private"


def test_key_cleanup_timer_precedes_private_generation(monkeypatch, tmp_path):
    monkeypatch.setattr(key.os, "geteuid", lambda: 0)
    monkeypatch.setattr(key, "KEYS", tmp_path / "keys")
    monkeypatch.setattr(key, "deployment_lock", contextlib.nullcontext)
    monkeypatch.setattr(key, "inspect_target", lambda: {**target(), "persistent": True})
    monkeypatch.setattr(
        key, "secure_directory", lambda path, **kw: path.mkdir(mode=0o700, exist_ok=True)
    )
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if args[0] == "openssl" and args[1] == "req":
            Path(args[args.index("-keyout") + 1]).write_bytes(b"fake private key")
            Path(args[args.index("-out") + 1]).write_text("fake certificate")
        return b"fake public key"

    monkeypatch.setattr(key, "run", fake_run)
    result = key.prepare_key()
    assert calls[0][0] == "systemd-run"
    assert calls[1][:2] == ["openssl", "req"]
    assert result["expires_unix"] - result["created_unix"] == 3600
    for name in ("key.json", "private.pem", "certificate.pem"):
        assert stat.S_IMODE((key.KEYS / result["key_id"] / name).stat().st_mode) == 0o600


def test_public_receipt_is_single_line_without_private_material(monkeypatch, capsys):
    monkeypatch.setattr(
        key, "prepare_key", lambda: {"key_id": "test", "certificate_pem": "line1\nline2\n"}
    )
    assert key.main() == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["status"] == "key_ready"
