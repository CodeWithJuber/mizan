"""Send an immutable ZIP directly to the compute server using GitHub's short-lived OIDC."""

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ORIGIN = "https://artifacts.invalid/ci-artifacts"
ARTIFACTS = {
    "dist": ("python-package", 512 * 1024 * 1024),
    "playwright-report": ("browser-report", 512 * 1024 * 1024),
    "research-import-public-key": ("public-key", 1024 * 1024),
    "research-import-receipt": ("receipt", 4 * 1024 * 1024),
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def pack(archive, base, sources, limit):
    base = base.resolve()
    paths = set()
    for source in sources:
        relative = Path(source)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("artifact source must stay within its base directory")
        root = base / relative
        if root.is_symlink() or not root.exists():
            continue
        candidates = root.rglob("*") if root.is_dir() else [root]
        for path in candidates:
            name = path.relative_to(base)
            if any(part.startswith(".") for part in name.parts) or path.is_symlink():
                continue
            if stat.S_ISREG(path.stat().st_mode):
                paths.add(path)
    total = 0
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for path in sorted(paths):
            total += path.stat().st_size
            if total > limit:
                raise ValueError("artifact exceeds the permitted size")
            output.write(path, str(path.relative_to(base)))
    if archive.stat().st_size > limit:
        raise ValueError("compressed artifact exceeds the permitted size")
    return len(paths)


def read_json(response):
    data = response.read(65537)
    if len(data) > 65536:
        raise ValueError("oversized service response")
    return json.loads(data)


def oidc_token(opener):
    url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"]
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("OIDC endpoint requires HTTPS")
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(key, value) for key, value in query if key != "audience"]
    query.append(("audience", ORIGIN))
    url = urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))
    request = urllib.request.Request(  # noqa: S310 - HTTPS checked above, redirects refused.
        url, headers={"Authorization": "Bearer " + os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]}
    )
    with opener.open(request, timeout=30) as response:
        token = read_json(response)["value"]
    if not isinstance(token, str) or not token:
        raise ValueError("GitHub returned no OIDC identity")
    return token


def verify_receipt(receipt, family, slot, digest, size):
    if family not in ARTIFACTS or slot != ARTIFACTS[family][0]:
        raise ValueError("unexpected artifact family or slot")
    expected = {
        "repository": "CodeWithJuber/mizan",
        "repository_id": "1166364542",
        "run_id": os.environ["GITHUB_RUN_ID"],
        "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "family": family,
        "slot": slot,
        "sha256": digest,
        "size_bytes": size,
    }
    if not isinstance(receipt, dict) or any(
        type(receipt.get(key)) is not type(value) or receipt.get(key) != value
        for key, value in expected.items()
    ):
        raise ValueError("server receipt does not match this run and artifact")
    identity = [expected[key] for key in ("repository_id", "run_id", "run_attempt")]
    if any(not re.fullmatch(r"[1-9][0-9]{0,20}", value) for value in identity):
        raise ValueError("invalid artifact run identity")
    path = "/".join([*identity, family, slot, "artifact.zip"])
    if receipt.get("path") != path:
        raise ValueError("invalid private artifact path")
    if not isinstance(receipt.get("retained_until"), str):
        raise ValueError("server receipt has no valid retention deadline")
    expires = datetime.fromisoformat(receipt["retained_until"].replace("Z", "+00:00"))
    if expires.tzinfo is None or expires <= datetime.now(UTC):
        raise ValueError("server receipt has no valid retention deadline")
    return path


def retry_delay(error, fallback):
    """Allow the receiver's signing-key refresh, with a bounded numeric delay."""
    value = error.headers.get("Retry-After", "") if error.headers else ""
    if error.code in {429, 503} and re.fullmatch(r"[0-9]{1,6}", value):
        return max(fallback, min(int(value), 60))
    return fallback


def upload(archive, family, opener):
    slot, _ = ARTIFACTS[family]
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    size = archive.stat().st_size
    for attempt in range(3):
        delay = 2 ** (attempt + 1)
        try:
            token = oidc_token(opener)
            with archive.open("rb") as data:
                request = urllib.request.Request(  # noqa: S310 - Fixed HTTPS origin, redirects refused.
                    f"{ORIGIN}/v1/artifacts/{family}/{slot}",
                    method="PUT",
                    data=data,
                    headers={
                        "Authorization": "Bearer " + token,
                        "Content-Type": "application/octet-stream",
                        "Content-Length": str(size),
                        "X-Artifact-SHA256": digest,
                        "X-Artifact-Format": "zip",
                    },
                )
                with opener.open(request, timeout=600) as response:
                    receipt = read_json(response)
            path = verify_receipt(receipt, family, slot, digest, size)
            return path, digest, size, receipt["retained_until"]
        except urllib.error.HTTPError as error:
            if attempt == 2 or error.code not in {429, 502, 503, 504}:
                raise RuntimeError(f"compute artifact service returned HTTP {error.code}") from None
            delay = retry_delay(error, delay)
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == 2:
                raise RuntimeError("compute artifact service could not be reached") from None
        time.sleep(delay)
    raise RuntimeError("artifact upload did not complete")


def restricted_pull_request():
    if os.environ.get("GITHUB_EVENT_NAME") != "pull_request":
        return False
    if os.environ.get("GITHUB_ACTOR") == "dependabot[bot]":
        return True
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    return event["pull_request"]["head"]["repo"]["full_name"] != os.environ["GITHUB_REPOSITORY"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("family", choices=ARTIFACTS)
    parser.add_argument("--base", type=Path, default=Path("."))
    parser.add_argument("--optional", action="store_true")
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()
    if os.environ["GITHUB_REPOSITORY"] != "CodeWithJuber/mizan":
        raise ValueError("unexpected repository")
    token_environment = ("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_URL")
    if not all(os.environ.get(key) for key in token_environment):
        if restricted_pull_request():
            message = (
                f"{args.family} was generated during a fork or Dependabot PR. "
                "GitHub withheld OIDC permission, so its downloadable archive is unavailable."
            )
            print("::notice::" + message)
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as summary:
                print(message, file=summary)
            return
        raise ValueError("artifact upload requires the job's id-token: write permission")
    with tempfile.TemporaryDirectory() as directory:
        archive = Path(directory) / "artifact.zip"
        _, limit = ARTIFACTS[args.family]
        if not pack(archive, args.base, args.paths, limit):
            if args.optional:
                print(f"::notice::No files were produced for {args.family}.")
                return
            raise ValueError("no artifact files were produced")
        opener = urllib.request.build_opener(NoRedirect())
        path, digest, size, expires = upload(archive, args.family, opener)
    message = f"{args.family} stored on compute ({size} bytes). SHA-256 `{digest}`. Retained until {expires}. Private relative path `{path}` (see docs/ci-artifacts.md for SSH retrieval)."
    print(message)
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as summary:
        print(message, file=summary)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, KeyError, zipfile.BadZipFile) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        sys.exit(1)
