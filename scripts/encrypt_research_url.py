#!/usr/bin/env python3
"""Encrypt a one-use research URL read only from stdin; never print the URL."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from research_transfer_key import (
    BUNDLE_BYTES,
    BUNDLE_SHA256,
    KEY_TTL,
    TransferError,
    protected_write,
    require,
    run,
)

MAX_URL_BYTES = 8192
MAX_ENVELOPE_BYTES = 32768
DOWNLOAD_HOST = "sdmntprcentralus.oaiusercontent.com"


def target_digest(target: dict) -> str:
    return hashlib.sha256(
        json.dumps(target, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_key(document: dict, *, now: int | None = None) -> None:
    now = int(time.time()) if now is None else now
    require(document.get("schema") == "mizan-research-key-v1", "Unsupported key metadata")
    require(bool(re.fullmatch(r"[0-9a-f]{32}", document.get("key_id", ""))), "Invalid key identity")
    require(
        bool(re.fullmatch(r"[0-9a-f]{64}", document.get("public_key_sha256", ""))),
        "Invalid public-key digest",
    )
    created, expires = document.get("created_unix"), document.get("expires_unix")
    require(isinstance(created, int) and isinstance(expires, int), "Invalid key validity interval")
    require(
        0 < expires - created <= KEY_TTL and created - 60 <= now < expires - 60,
        "Key is expired or outside its validity interval",
    )
    require(
        document.get("bundle_sha256") == BUNDLE_SHA256
        and document.get("bundle_bytes") == BUNDLE_BYTES,
        "Unexpected bundle identity",
    )
    require(
        isinstance(document.get("target"), dict) and document["target"].get("persistent") is True,
        "Key has no persistent target",
    )
    require(
        document["target"].get("target", {}).get("exists") is False,
        "Only a new research target is authorized",
    )


def validate_url(url: str, *, now: int | None = None) -> int:
    now = int(time.time()) if now is None else now
    require(isinstance(url, str) and 1 <= len(url) <= MAX_URL_BYTES, "Invalid download URL size")
    require(all(33 <= ord(char) <= 126 for char in url), "Download URL contains invalid characters")
    try:
        parsed = urlsplit(url)
        require(
            parsed.scheme == "https" and parsed.hostname == DOWNLOAD_HOST,
            "Download URL is outside the reviewed HTTPS host",
        )
        require(
            parsed.netloc == DOWNLOAD_HOST
            and parsed.port is None
            and parsed.username is None
            and parsed.password is None
            and not parsed.fragment,
            "Download URL must use the exact HTTPS origin without credentials or fragment",
        )
        query = parse_qs(parsed.query, strict_parsing=True)
        require(
            len(query.get("se", [])) == 1 and query.get("sp") == ["r"],
            "Expected a single expiry and read-only signed URL",
        )
        expiry = dt.datetime.fromisoformat(query["se"][0].replace("Z", "+00:00"))
        require(expiry.tzinfo is not None, "Download expiry needs a timezone")
        expires = int(expiry.timestamp())
        require(
            now + 60 < expires <= now + KEY_TTL + 60,
            "Download URL is expired or exceeds the one-hour transfer window",
        )
        return expires
    except TransferError:
        raise
    except Exception as exc:
        raise TransferError("Download URL metadata is malformed") from exc


def read_public_metadata(path: Path) -> dict:
    with path.open("rb") as handle:
        raw = handle.read(65537)
    require(len(raw) <= 65536, "Public metadata exceeds size limit")
    decoder = json.JSONDecoder()
    remaining = raw.decode().strip()
    documents = []
    while remaining:
        value, index = decoder.raw_decode(remaining)
        documents.append(value)
        remaining = remaining[index:].lstrip()
    candidates = [item["public"] for item in documents if item.get("status") == "key_ready"]
    if len(documents) == 1 and documents[0].get("schema") == "mizan-research-key-v1":
        candidates = documents
    require(len(candidates) == 1, "Expected exactly one prepared public key")
    validate_key(candidates[0])
    return candidates[0]


def encrypted_envelope(document: dict, url: str) -> dict:
    validate_key(document)
    expiry = min(document["expires_unix"], validate_url(url))
    payload = {
        "schema": "mizan-research-transfer-v1",
        "key_id": document["key_id"],
        "public_key_sha256": document["public_key_sha256"],
        "bundle_sha256": BUNDLE_SHA256,
        "bundle_bytes": BUNDLE_BYTES,
        "expires_unix": expiry,
        "target_sha256": target_digest(document["target"]),
        "url": url,
    }
    with tempfile.TemporaryDirectory(prefix="mizan-public-certificate-") as temporary:
        certificate = Path(temporary) / "certificate.pem"
        protected_write(certificate, document["certificate_pem"].encode())
        public_pem = run(["openssl", "x509", "-in", str(certificate), "-pubkey", "-noout"])
        public_der = run(["openssl", "pkey", "-pubin", "-outform", "DER"], data=public_pem)
        require(
            hashlib.sha256(public_der).hexdigest() == document["public_key_sha256"],
            "Certificate public key does not match the prepared key",
        )
        ciphertext = run(
            [
                "openssl",
                "cms",
                "-encrypt",
                "-binary",
                "-aes-256-gcm",
                "-recip",
                str(certificate),
                "-keyopt",
                "rsa_padding_mode:oaep",
                "-keyopt",
                "rsa_oaep_md:sha256",
                "-keyopt",
                "rsa_mgf1_md:sha256",
                "-outform",
                "DER",
            ],
            data=json.dumps(payload, separators=(",", ":")).encode(),
        )
    result = {
        "schema": "mizan-research-cms-v1",
        "key_id": document["key_id"],
        "ciphertext_b64": base64.b64encode(ciphertext).decode(),
    }
    require(len(json.dumps(result)) <= MAX_ENVELOPE_BYTES, "Encrypted envelope exceeds size limit")
    return result


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        raw_url = sys.stdin.buffer.read(MAX_URL_BYTES + 1)
        require(len(raw_url) <= MAX_URL_BYTES, "Download URL exceeds size limit")
        document = read_public_metadata(args.public_key)
        envelope = encrypted_envelope(document, raw_url.decode("ascii").rstrip("\r\n"))
        protected_write(args.output, (json.dumps(envelope) + "\n").encode())
        print(
            json.dumps(
                {
                    "status": "encrypted",
                    "key_id": document["key_id"],
                    "bundle_sha256": BUNDLE_SHA256,
                }
            )
        )
        return 0
    except TransferError as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 1
    except Exception:
        print(
            json.dumps(
                {"status": "failed", "reason": "URL encryption failed; private details withheld"}
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
