#!/usr/bin/env python3
"""Consume one encrypted, short-lived URL; pin and import a full research bundle."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import http.client
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

from encrypt_research_url import (
    DOWNLOAD_HOST,
    MAX_ENVELOPE_BYTES,
    target_digest,
    validate_key,
    validate_url,
)
from research_transfer_key import (
    BUNDLE_BYTES,
    BUNDLE_SHA256,
    CONTAINER,
    KEYS,
    SAFE_ENV,
    STATE,
    TransferError,
    deployment_lock,
    inspect_target,
    require,
    run,
    secure_directory,
)


class OutcomeUnknown(TransferError):
    """Remote execution could not be reconciled; never imply rollback or retry."""


BACKEND_CODE = Path(__file__).with_name("research_backend_stage.py").read_text()


def private_file(path: Path, maximum: int) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        require(
            stat.S_ISREG(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o600,
            "Unsafe private transfer file",
        )
        require(info.st_size <= maximum, "Private transfer metadata exceeds size limit")
        result = handle.read(maximum + 1)
    require(len(result) <= maximum, "Private transfer metadata exceeds size limit")
    return result


def der_children(data: bytes) -> list[tuple[int, bytes]]:
    result, offset = [], 0
    while offset < len(data):
        require(offset + 2 <= len(data), "Invalid authenticated envelope")
        tag, length = data[offset], data[offset + 1]
        offset += 2
        if length & 128:
            count = length & 127
            require(
                0 < count <= 3 and offset + count <= len(data), "Invalid authenticated envelope"
            )
            encoded = data[offset : offset + count]
            require(encoded[0] != 0, "Noncanonical authenticated envelope")
            length = int.from_bytes(encoded, "big")
            require(length >= 128, "Noncanonical authenticated envelope")
            offset += count
        require(offset + length <= len(data), "Invalid authenticated envelope")
        result.append((tag, data[offset : offset + length]))
        offset += length
    return result


def sequence(item: tuple[int, bytes], tag: int = 0x30) -> list[tuple[int, bytes]]:
    require(item[0] == tag, "Unexpected authenticated envelope structure")
    return der_children(item[1])


def sha256_algorithm(item: tuple[int, bytes]) -> bool:
    values = sequence(item)
    return values in [
        [(6, bytes.fromhex("608648016503040201"))],
        [(6, bytes.fromhex("608648016503040201")), (5, b"")],
    ]


def validate_cms(ciphertext: bytes) -> None:
    """Accept exactly the DER AEAD/OAEP shape emitted by our reviewed sender."""
    try:
        outer = der_children(ciphertext)
        require(len(outer) == 1, "Unexpected authenticated envelope structure")
        info = sequence(outer[0])
        require(
            len(info) == 2 and info[0] == (6, bytes.fromhex("2a864886f70d0109100117")),
            "CMS must use AuthEnvelopedData",
        )
        wrapped = sequence(info[1], 0xA0)
        require(len(wrapped) == 1, "Unexpected authenticated envelope structure")
        body = sequence(wrapped[0])
        require(len(body) == 4 and body[0] == (2, b"\0"), "Unsupported CMS attributes")
        recipients = sequence(body[1], 0x31)
        require(len(recipients) == 1, "CMS must have exactly one recipient")
        recipient = sequence(recipients[0])
        require(
            len(recipient) == 4
            and recipient[0] == (2, b"\0")
            and recipient[1][0] == 0x30
            and recipient[3][0] == 4
            and len(recipient[3][1]) == 384,
            "Expected one RSA-3072 recipient",
        )
        algorithm = sequence(recipient[2])
        require(
            len(algorithm) == 2 and algorithm[0] == (6, bytes.fromhex("2a864886f70d010107")),
            "CMS key wrapping must use RSA-OAEP",
        )
        params = sequence(algorithm[1])
        require(len(params) == 2, "CMS OAEP parameters differ")
        hash_params, mgf_params = sequence(params[0], 0xA0), sequence(params[1], 0xA1)
        require(
            len(hash_params) == len(mgf_params) == 1 and sha256_algorithm(hash_params[0]),
            "OAEP must use SHA256",
        )
        mgf = sequence(mgf_params[0])
        require(
            len(mgf) == 2
            and mgf[0] == (6, bytes.fromhex("2a864886f70d010108"))
            and sha256_algorithm(mgf[1]),
            "OAEP MGF1 must use SHA256",
        )
        content = sequence(body[2])
        require(
            len(content) == 3
            and content[0] == (6, bytes.fromhex("2a864886f70d010701"))
            and content[2][0] == 0x80,
            "Unexpected CMS content",
        )
        cipher = sequence(content[1])
        require(
            len(cipher) == 2 and cipher[0] == (6, bytes.fromhex("60864801650304012e")),
            "CMS content must use AES-256-GCM",
        )
        gcm = sequence(cipher[1])
        require(
            len(gcm) == 2
            and gcm[0][0] == 4
            and len(gcm[0][1]) == 12
            and gcm[1] == (2, b"\x10")
            and body[3][0] == 4
            and len(body[3][1]) == 16,
            "CMS GCM nonce or tag differs",
        )
    except TransferError:
        raise
    except Exception as exc:
        raise TransferError("Invalid authenticated envelope") from exc


def decrypt_envelope(envelope: dict, document: dict, directory: Path) -> dict:
    require(
        envelope.get("schema") == "mizan-research-cms-v1"
        and envelope.get("key_id") == document["key_id"],
        "Encrypted transfer identity differs",
    )
    try:
        ciphertext = base64.b64decode(envelope["ciphertext_b64"], validate=True)
    except Exception as exc:
        raise TransferError("Invalid encrypted transfer") from exc
    require(len(ciphertext) <= MAX_ENVELOPE_BYTES, "Encrypted transfer exceeds size limit")
    validate_cms(ciphertext)
    private_file(directory / "private.pem", 8192)
    private_file(directory / "certificate.pem", 8192)
    # run() returns nothing unless OpenSSL successfully authenticates the GCM
    # tag. Never parse any provisional plaintext from a failing decryption.
    plaintext = run(
        [
            "openssl",
            "cms",
            "-decrypt",
            "-binary",
            "-inform",
            "DER",
            "-inkey",
            str(directory / "private.pem"),
            "-recip",
            str(directory / "certificate.pem"),
        ],
        data=ciphertext,
    )
    require(len(plaintext) <= 16384, "Decrypted transfer exceeds size limit")
    try:
        payload = json.loads(plaintext)
    except Exception as exc:
        raise TransferError("Invalid authenticated payload") from exc
    expected = {
        "schema": "mizan-research-transfer-v1",
        "key_id": document["key_id"],
        "public_key_sha256": document["public_key_sha256"],
        "bundle_sha256": BUNDLE_SHA256,
        "bundle_bytes": BUNDLE_BYTES,
        "target_sha256": target_digest(document["target"]),
    }
    require(
        all(payload.get(name) == value for name, value in expected.items()),
        "Authenticated transfer binding differs",
    )
    expiry = payload.get("expires_unix")
    require(
        isinstance(expiry, int) and int(time.time()) + 60 < expiry <= document["expires_unix"],
        "Authenticated transfer is expired",
    )
    require(expiry <= validate_url(payload.get("url")), "Authenticated transfer exceeds URL expiry")
    return payload


def download_bundle(url: str, path: Path) -> None:
    validate_url(url)
    parsed = urlsplit(url)
    connection = http.client.HTTPSConnection(DOWNLOAD_HOST, timeout=30)
    deadline = time.monotonic() + 600

    def deadline_expired(signum, frame):
        raise TransferError("Research download exceeded its aggregate time limit")

    previous_handler = signal.signal(signal.SIGALRM, deadline_expired)
    signal.alarm(600)
    try:
        connection.request(
            "GET",
            parsed.path + "?" + parsed.query,
            headers={"User-Agent": "Mizan-Research-Import/1"},
        )
        response = connection.getresponse()
        require(
            response.status == 200, "Research download was refused; redirects are never followed"
        )
        require(
            response.getheader("Content-Length") == str(BUNDLE_BYTES),
            "Research download size header differs",
        )
        require(
            response.getheader("Content-Encoding") in (None, "identity"),
            "Encoded research response is not accepted",
        )
        digest, total = hashlib.sha256(), 0
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            while block := response.read1(min(1024 * 1024, BUNDLE_BYTES + 1 - total)):
                require(time.monotonic() < deadline, "Research download exceeded its time limit")
                total += len(block)
                require(total <= BUNDLE_BYTES, "Research download exceeded its size limit")
                digest.update(block)
                handle.write(block)
            handle.flush()
            os.fsync(handle.fileno())
        require(
            total == BUNDLE_BYTES and digest.hexdigest() == BUNDLE_SHA256,
            "Downloaded research bundle identity differs",
        )
    except TransferError:
        raise
    except Exception as exc:
        raise TransferError("Research download failed; private details withheld") from exc
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)
        connection.close()


@contextlib.contextmanager
def deferred_cancellation():
    """Keep the production lock until the bounded backend process is reconciled."""
    requested = []

    def remember(signum, frame):
        requested.append(signum)

    previous = {
        number: signal.signal(number, remember)
        for number in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)
    }
    try:
        yield requested
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def backend_stage(action: str, config: dict, bundle: Path | None = None) -> dict:
    if bundle is not None:
        config = {**config, "operation_deadline_unix": int(time.time()) + 840}
    args = [
        "docker",
        "exec",
        "-i",
        CONTAINER,
        "python",
        "-c",
        BACKEND_CODE,
        action,
        json.dumps(config),
    ]
    if bundle is None:
        raw = run(args, timeout=10 if action in {"cancel", "status"} else 60)
    else:
        with deferred_cancellation() as requested:
            launch_deadline = time.monotonic() + 900
            try:
                with bundle.open("rb") as source:
                    process = subprocess.run(
                        args,
                        stdin=source,
                        capture_output=True,
                        env=SAFE_ENV,
                        timeout=900,
                        check=False,
                    )
                if process.returncode == 0:
                    receipt = json.loads(process.stdout)
                    receipt["interruption_requested"] = bool(requested)
                    return receipt
            except (OSError, subprocess.TimeoutExpired, ValueError):
                pass
            # A Docker client failure does not prove its in-container process
            # stopped. Cancel only the recorded PID/start-time/config identity,
            # then reconcile the outcome while still holding deploy.lock.
            attempts, cancel_sent = 0, False
            while attempts < 6 or time.monotonic() < launch_deadline:
                attempts += 1
                try:
                    status = backend_stage("status", config)
                    if status.get("status") == "active":
                        status["reconciled_after_client_failure"] = True
                        return status
                    if status.get("status") == "failed" and status.get("target_absent"):
                        raise TransferError("Backend import failed; target confirmed absent")
                    if status.get("status") == "running" and not cancel_sent:
                        cancel_sent = True
                        backend_stage("cancel", config)
                except TransferError as exc:
                    if "target confirmed absent" in str(exc):
                        raise
                time.sleep(5)
            raise OutcomeUnknown(
                "Backend import outcome unknown; inspect target before deployment or retry"
            )
    try:
        return json.loads(raw)
    except Exception as exc:
        raise TransferError("Backend research receipt is invalid") from exc


def import_transfer(raw: bytes) -> dict:
    require(os.geteuid() == 0, "Research import requires the existing root deployment account")
    require(len(raw) <= MAX_ENVELOPE_BYTES, "Encrypted transfer exceeds size limit")
    envelope = json.loads(raw)
    key_id = envelope.get("key_id", "")
    require(bool(re.fullmatch(r"[0-9a-f]{32}", key_id)), "Invalid transfer key identity")
    with deployment_lock():
        secure_directory(KEYS)
        directory = KEYS / key_id
        secure_directory(directory)
        try:
            document = json.loads(private_file(directory / "key.json", 65536))
            validate_key(document)
            require(document["key_id"] == key_id, "Prepared transfer identity differs")
            current = inspect_target()
            require(
                target_digest(current) == target_digest(document["target"]),
                "Backend target changed since key preparation; prepare a new key",
            )
            payload = decrypt_envelope(envelope, document, directory)
            config = {
                name: current[name] for name in ("research_dir", "backend_uid", "backend_gid")
            }
            config["key_id"] = key_id
            require(
                backend_stage("check", config).get("status") == "ready",
                "Backend research preflight failed",
            )
            require(
                shutil.disk_usage(STATE).free >= BUNDLE_BYTES + 100_000_000,
                "Server needs additional temporary download space",
            )
            with tempfile.TemporaryDirectory(prefix="research-download-", dir=STATE) as temporary:
                bundle = Path(temporary) / "bundle.zip"
                download_bundle(payload["url"], bundle)
                require(
                    time.time() < payload["expires_unix"],
                    "Transfer expired before research activation",
                )
                require(
                    target_digest(inspect_target()) == target_digest(current),
                    "Backend target changed during download",
                )
                receipt = backend_stage("install", config, bundle)
                require(
                    receipt.get("status") == "active"
                    and receipt.get("bundle_sha256") == BUNDLE_SHA256
                    and receipt.get("bundle_bytes") == BUNDLE_BYTES
                    and receipt.get("fts_search_verified") is True,
                    "Backend did not confirm verified research activation",
                )
                return receipt
        finally:
            # One attempt consumes the key, including authentication failures.
            # The /run timer also removes unused keys and reboot clears /run.
            shutil.rmtree(directory, ignore_errors=True)


def main() -> int:
    os.umask(0o077)

    def interrupted(signum, frame):
        raise TransferError("Research transfer interrupted")

    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, interrupted)
    try:
        receipt = import_transfer(sys.stdin.buffer.read(MAX_ENVELOPE_BYTES + 1))
        print(json.dumps(receipt))
        return 0
    except OutcomeUnknown as exc:
        print(json.dumps({"status": "outcome_unknown", "reason": str(exc)}))
        return 1
    except TransferError as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 1
    except Exception:
        print(
            json.dumps(
                {"status": "failed", "reason": "Research import failed; private details withheld"}
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
