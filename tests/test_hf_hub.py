"""Hugging Face, read by MIZAN on the server; the owner's locked eval as an Imtihan block."""

import hashlib
import json
from types import SimpleNamespace

import httpx
import pytest

from imtihan import locked_eval, scorers
from knowledge import hf_hub
from security.auth import bind_principal, reset_principal
from tadbir import fahm


def principal(roles):
    return bind_principal(SimpleNamespace(user_id="u-hub", roles=roles))


@pytest.fixture
def hub(monkeypatch):
    """A fake Hub behind httpx; records every request and its Authorization header."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.headers.get("Authorization")))
        path = request.url.path
        if path == "/api/whoami-v2":
            return httpx.Response(200, json={"name": "Owner"})
        if path == "/api/datasets":
            return httpx.Response(200, json=[{"id": "Owner/data", "private": True, "downloads": 5}])
        if path.startswith("/api/datasets/Owner/data/tree/main"):
            return httpx.Response(200, json=[{"type": "file", "path": "a.jsonl", "size": 30}])
        if path == "/datasets/Owner/data/resolve/main/a.jsonl":
            return httpx.Response(302, headers={"Location": "https://cas-bridge.xethub.hf.co/f"})
        if request.url.host == "cas-bridge.xethub.hf.co":
            body = b"".join(b'{"row": %d}\n' % i for i in range(1000))
            return httpx.Response(200, content=body, headers={"content-length": str(len(body))})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: original(transport=transport, **kw))
    monkeypatch.setenv("HF_TOKEN", "hf_test_token")
    return seen


async def test_the_owners_token_is_used_for_admins_only(hub):
    tokens = principal(["admin"])
    try:
        listed = await hf_hub.repos("", "datasets")
    finally:
        reset_principal(tokens)
    assert listed["owner"] == "Owner" and listed["repos"][0]["private"]
    assert all(auth == "Bearer hf_test_token" for _url, auth in hub)
    hub.clear()
    tokens = principal(["user"])
    try:
        await hf_hub.repos("Owner", "datasets")
    finally:
        reset_principal(tokens)
    assert all(auth is None for _url, auth in hub)  # a user never borrows the owner's token


async def test_a_large_text_file_becomes_its_first_whole_rows(hub):
    got = await hf_hub.fetch("Owner/data", "a.jsonl", max_bytes=100)
    assert got["sampled"] and got["bytes"].endswith(b"\n") and len(got["bytes"]) <= 100
    assert all(json.loads(line) for line in got["bytes"].decode().splitlines())
    redirected = [url for url, auth in hub if "xethub" in url]
    assert redirected and all(auth is None for url, auth in hub if "xethub" in url)


async def test_only_hugging_face_hosts_are_contacted(monkeypatch):
    def handler(request):
        return httpx.Response(302, headers={"Location": "https://evil.example/steal"})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handler), **kw)
    )
    with pytest.raises(hf_hub.HubError, match="only from Hugging Face"):
        await hf_hub.fetch("Owner/data", "a.jsonl")
    assert hf_hub.host_allowed("cdn-lfs.hf.co") and not hf_hub.host_allowed("hf.co.evil.example")


def test_bad_names_are_refused_before_any_request():
    for bad in ("../etc", "owner", "a/b/c", "owner/na me"):
        with pytest.raises(hf_hub.HubError):
            hf_hub.file_url(bad, "x.json")
    with pytest.raises(hf_hub.HubError):
        hf_hub.file_url("o/r", "../secret")


@pytest.mark.parametrize(
    "text,action",
    [
        ("https://huggingface.co/Zubairshaikh/ ispe datasets /training hai", "repos"),
        ("mere huggingface datasets dikhao", "repos"),
        ("https://huggingface.co/datasets/Zubairshaikh/mizan-eval-v1 dikhao", "files"),
        (
            "https://huggingface.co/datasets/Zubairshaikh/mizan-eval-v1 se eval_v1.jsonl project me lao",
            "import",
        ),
        (
            "https://huggingface.co/datasets/Zubairshaikh/mizan-eval-v1/blob/main/eval_v1.jsonl",
            "import",
        ),
    ],
)
def test_hub_requests_are_understood(text, action):
    understood = fahm.understand(text)
    assert understood.intent == "hf_hub" and understood.entities["action"] == action


def test_training_mentions_list_models_too():
    entities = fahm.understand(
        "https://huggingface.co/Zubairshaikh/ ispe datasets /training hai"
    ).entities
    assert entities["kinds"] == ["datasets", "models"]


# ── the locked eval ──────────────────────────────────────────────────────


def test_the_locked_eval_is_used_only_when_its_hash_matches(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MIZAN_LOCKED_EVAL", "on")
    monkeypatch.setattr(locked_eval, "_TRIED", True)  # no download in tests
    path = tmp_path / "imtihan" / locked_eval.FILE
    path.parent.mkdir(parents=True)
    path.write_text('{"id": "EVAL-001"}\n')
    assert locked_eval.items() == []  # a changed file is never scored against
    monkeypatch.setattr(locked_eval, "SHA256", hashlib.sha256(path.read_bytes()).hexdigest())
    assert locked_eval.items() == [{"id": "EVAL-001"}]


def test_locked_items_are_scored_by_the_rubrics_rules():
    grounded = {"kind": "locked", "task": "grounded_qa", "status": "answer", "language": "en",
                "locator": "Surah 2, Ayah 71"}  # fmt: skip
    assert scorers.score(grounded, "The cow was unblemished (Quran 2:71).")["pass"]
    assert not scorers.score(grounded, "The cow was unblemished.")["pass"]  # no locator
    arabic = {**grounded, "language": "ar", "locator": "Surah 1, Ayah 5"}
    assert scorers.score(arabic, "العبادة لله وحده (سورة ١ آية ٥).")["pass"]
    assert not scorers.score(arabic, "Worship is for Allah alone (1:5).")["pass"]  # language
    abstain = {"kind": "locked", "task": "abstention", "status": "abstain", "language": "en"}
    assert scorers.score(abstain, "The ayah does not mention the name of the sea.")["pass"]
    coding = {"kind": "locked", "task": "coding", "status": "answer", "tests": "assert f() == 1"}
    assert scorers.score(coding, "```python\ndef f(): return 1\n```", executed=True)["pass"]
    assert not scorers.score(coding, "```python\ndef f(): return 2\n```", executed=False)["pass"]


def test_the_sample_is_fixed_and_carries_the_ayah(monkeypatch):
    rows = [
        {"id": f"EVAL-{i:03d}", "category": cat, "task": "grounded_qa", "language": "en",
         "question": "What does it say?", "expected_status": "answer",
         "evidence": {"locator": "Surah 1, Ayah 1", "text": "بِسْمِ ٱللَّهِ"}}
        for i, cat in enumerate(["en"] * 6 + ["tools"] * 3)
    ]  # fmt: skip
    monkeypatch.setattr(locked_eval, "items", lambda: rows)
    chosen = locked_eval.tasks()
    assert [t["id"] for t in chosen] == [f"lock-EVAL-{i:03d}" for i in range(4)]
    assert "The ayah (Surah 1, Ayah 1):" in chosen[0]["prompt"]
    assert chosen[0]["block"] == "locked_eval"
