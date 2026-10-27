"""docs/api-reference.md lists every route the backend serves (scripts/api_reference.py)."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import api_reference  # noqa: E402


def test_the_reference_lists_every_route():
    from api import main

    served = {(item["method"], item["path"]) for item in api_reference.routes(main)}
    written = (ROOT / "docs" / "api-reference.md").read_text(encoding="utf-8")
    listed = set(re.findall(r"^\| (\w+) \| `([^`]+)`", written, re.M))
    assert served - listed == set(), "run: python scripts/api_reference.py"
    assert listed - served == set(), "run: python scripts/api_reference.py"


def test_access_follows_the_apps_own_tables():
    from api import main

    who = {(item["method"], item["path"]): item["access"] for item in api_reference.routes(main)}
    assert who[("GET", "/api/health")] == "public"
    assert who[("POST", "/api/chat/stream")] == "user"
    assert who[("POST", "/api/imtihan/run")] == "admin"
    assert who[("GET", "/api/public/reliability")] == "public"
    assert who[("POST", "/api/debug/compare")].startswith("debug mode")
