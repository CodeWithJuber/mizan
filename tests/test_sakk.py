"""Sakk: a tamper-evident, content-free receipt for every action, signed daily."""

import json
import sqlite3

import pytest

from security import sakk
from security.sakk import Sakk, merkle_proof, merkle_root, proof_root, verify_export


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    sakk._STORES.clear()
    return sakk.store()


def tamper(store: Sakk, owner: str, seq: int, **changes) -> None:
    with sqlite3.connect(store.path) as conn:
        body = json.loads(
            conn.execute(
                "SELECT body FROM receipts WHERE owner = ? AND seq = ?", (owner, seq)
            ).fetchone()[0]
        )
        body.update(changes)
        conn.execute(
            "UPDATE receipts SET body = ? WHERE owner = ? AND seq = ?",
            (json.dumps(body), owner, seq),
        )


def test_each_receipt_links_to_the_one_before(store):
    for tool in ("web_search", "bash", "write_file"):
        store.record_tool("alice", tool, {"q": tool}, {"ok": True})
    chain = list(reversed(store.receipts("alice")))
    assert [r["seq"] for r in chain] == [1, 2, 3]
    assert chain[0]["prev"] == sakk.GENESIS
    assert chain[1]["prev"] == chain[0]["hash"] and chain[2]["prev"] == chain[1]["hash"]
    assert store.verify("alice") == {"ok": True, "receipts": 3, "head": chain[2]["hash"]}
    assert store.verify("bob") == {"ok": True, "receipts": 0, "head": None}


def test_a_changed_receipt_is_found(store):
    for tool in ("web_search", "bash", "write_file"):
        store.record_tool("alice", tool, {}, {"ok": True})
    tamper(store, "alice", 2, outcome="declined")  # rewrite history: "I never ran bash"
    found = store.verify("alice")
    assert not found["ok"] and found["broken_at"] == 2 and found["problem"] == "receipt was changed"


def test_a_removed_or_reordered_receipt_is_found(store):
    for tool in ("a", "b", "c"):
        store.record_tool("alice", tool, {}, {})
    with sqlite3.connect(store.path) as conn:
        conn.execute("DELETE FROM receipts WHERE owner = 'alice' AND seq = 2")
    assert store.verify("alice")["problem"] == "missing or reordered receipt"


def test_a_rehashed_forgery_still_breaks_the_next_link(store):
    for tool in ("a", "b", "c"):
        store.record_tool("alice", tool, {}, {})
    tamper(store, "alice", 2, tool="harmless")
    with sqlite3.connect(store.path) as conn:  # even with its own hash recomputed
        body = json.loads(conn.execute("SELECT body FROM receipts WHERE seq = 2").fetchone()[0])
        conn.execute("UPDATE receipts SET hash = ? WHERE seq = 2", (sakk.digest(body),))
    found = store.verify("alice")
    assert found["broken_at"] == 3 and found["problem"] == "link to the previous receipt is broken"


def test_the_display_line_can_be_redacted_without_breaking_the_chain(store):
    store.record_tool("alice", "bash", {"command": "ls"}, {"ok": True})
    with sqlite3.connect(store.path) as conn:
        conn.execute("UPDATE receipts SET display = ''")
    assert store.verify("alice")["ok"]


def test_no_content_is_kept_only_keyed_digests(store):
    secret = "my private note about my health"
    store.record_tool("alice", "remember", {"note": secret}, {"saved": secret})
    with open(store.path, "rb") as handle:
        assert secret.encode() not in handle.read()
    receipt = store.receipts("alice")[0]
    assert receipt["params"] == store.mac("alice", {"note": secret})
    assert receipt["params"] != store.mac("bob", {"note": secret})  # each owner has a key
    import hashlib

    plain = hashlib.sha256(sakk.canonical({"note": secret})).hexdigest()
    assert receipt["params"] != plain  # a guess cannot be checked without the key


@pytest.mark.parametrize(
    "result,state",
    [
        ({"held_for_approval": "a" * 32}, "held"),
        ({"error": "The user declined this action", "declined": True}, "declined"),
        ({"error": "Permission denied"}, "error"),
        ({"stdout": "ok"}, "done"),
        ("plain text", "done"),
    ],
)
def test_outcomes(result, state):
    assert sakk.outcome(result) == state


def test_values_json_cannot_hold_still_get_a_digest(store):
    store.record_tool("alice", "x", {"blob": b"\x00\x01", "big": 2**70}, float("nan"))
    assert store.verify("alice")["ok"]


@pytest.mark.parametrize("count", [1, 2, 3, 5, 8])
def test_every_leaf_proves_its_way_to_the_root(count):
    leaves = [f"leaf-{i}".encode() for i in range(count)]
    root = merkle_root(leaves).hex()
    for index, leaf in enumerate(leaves):
        assert proof_root(leaf, merkle_proof(leaves, index)) == root
    assert proof_root(b"not a leaf", merkle_proof(leaves, 0)) != root


def test_the_signed_daily_root_proves_a_chain_offline(store):
    for owner in ("alice", "bob", "carol"):
        store.record_tool(owner, "web_search", {}, {})
    root = store.sign_day("2026-10-27")
    assert root["leaves"] == 3 and store.sign_day("2026-10-27") == root  # once per day
    exported = store.export("bob")
    found = verify_export(json.loads(json.dumps(exported)))
    assert found == {"ok": True, "receipts": 1, "included": True, "signed": True, "problems": []}

    forged = json.loads(json.dumps(exported))
    forged["receipts"][0]["body"]["tool"] = "something else"
    assert not verify_export(forged)["ok"]
    other_key = json.loads(json.dumps(exported))
    other_key["public_key"] = Sakk(str(store.path) + ".other").public_key()
    assert verify_export(other_key)["signed"] is False


async def test_a_tool_call_writes_its_receipt_whatever_happens(store, monkeypatch):
    from agents.base import BaseAgent
    from security.auth import TokenPayload, bind_principal, reset_principal

    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    agent = BaseAgent(name="Sakk test")

    async def refused(tool_name, params):
        return {"error": "Permission denied: not allowed"}

    async def raises(tool_name, params):
        raise RuntimeError("boom")

    binding = bind_principal(TokenPayload("alice", "alice", ["user"], 0, 0, "t"))
    try:
        monkeypatch.setattr(agent, "_execute_tool_checked", refused)
        assert (await agent._execute_tool_safe("bash", {"command": "rm -rf /"}))["error"]
        monkeypatch.setattr(agent, "_execute_tool_checked", raises)
        with pytest.raises(RuntimeError):
            await agent._execute_tool_safe("bash", {})
    finally:
        reset_principal(binding)
    chain = store.receipts("alice")
    assert [(r["tool"], r["outcome"]) for r in reversed(chain)] == [
        ("bash", "error"),
        ("bash", "error"),
    ]


# ── the public scorecard ────────────────────────────────────────────────


def finished_run():
    return {
        "id": "run-1",
        "status": "complete",
        "created_at": 1793100000.0,
        "model": "test-model",
        "repeats": 1,
        "blocks": ["arithmetic"],
        "result": {
            "results": [{"prompt": "SECRET PROMPT", "answer": "SECRET ANSWER", "pass": True}],
            "report": {
                "blocks": {
                    "arithmetic": {"tasks": 6, "base": {"rate": 0.5}, "mizan": {"rate": 1.0}}
                },
                "index": {"base": {"score": 0.5}, "mizan": {"score": 1.0}},
                "cost": {"mizan": {"cost_usd": 0.01}},
            },
        },
    }


def test_publishing_keeps_only_aggregates_and_chains_the_report(store):
    from imtihan import scorecard

    entry = scorecard.publish(finished_run())
    published = json.dumps(scorecard.view())
    assert "SECRET" not in published and "results" not in entry["report"]
    assert entry["report_sha256"] == scorecard.report_digest(entry["report"])
    receipt = store.receipts("system")[0]
    assert receipt["kind"] == "scorecard" and receipt["report"] == entry["report_sha256"]
    with pytest.raises(ValueError):
        scorecard.publish({**finished_run(), "status": "running"})
    assert scorecard.unpublish("run-1") and scorecard.view()["latest"] is None


def test_public_routes_need_no_login_and_private_ones_do(tmp_path, monkeypatch, store):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("DB_PATH", str(tmp_path / "chat.db"))
    monkeypatch.setenv("MIZAN_OWNED_DB", str(tmp_path / "owned.sqlite3"))
    import api.main as main
    from imtihan import scorecard
    from security.auth import MizanAuth

    scorecard.publish(finished_run())
    auth = MizanAuth("sakk-test-signing-key-" * 4, data_dir=str(tmp_path / "users"))
    alice = auth.create_user("alice", "test-password", roles=["user"])
    monkeypatch.setattr(main, "auth", auth)
    client = TestClient(main.app)

    public = client.get("/api/public/reliability")
    assert public.status_code == 200 and "SECRET" not in public.text
    assert public.json()["latest"]["run_id"] == "run-1"
    assert client.get("/api/public/reliability/run-1").json()["model"] == "test-model"
    assert client.get("/api/public/reliability/nope").status_code == 404
    assert len(client.get("/api/public/sakk").json()["public_key"]) == 43
    assert client.get("/api/sakk").status_code == 401

    headers = {"Authorization": "Bearer " + auth.create_token(alice)}
    store.record_tool(alice.id, "web_search", {"q": "Asr"}, {"ok": True})
    mine = client.get("/api/sakk", headers=headers).json()["receipts"]
    assert [r["display"] for r in mine] == ["web_search · done"]
    assert client.get("/api/sakk/verify", headers=headers).json()["ok"] is True
    export = client.get("/api/sakk/export", headers=headers)
    assert "attachment" in export.headers["content-disposition"]
    assert export.json()["format"] == "mizan-sakk/1"
    assert client.get("/api/sakk/verify/all", headers=headers).status_code == 403
    assert client.post("/api/imtihan/runs/run-1/publish", headers=headers).status_code == 403


def test_a_new_checkpoint_is_signed_when_a_chain_moves(tmp_path):
    from security import sakk

    store = sakk.Sakk(str(tmp_path / "moving.db"))
    empty = store.sign_day("2026-10-27")
    assert empty["leaves"] == 0
    store.append("alice", "tool", {"tool": "web_search"}, "searched")
    moved = store.sign_day("2026-10-27")  # the same day, but alice's chain moved
    assert moved["leaves"] == 1 and moved["root"] != empty["root"]
    assert store.sign_day("2026-10-27") == moved  # nothing moved: nothing new signed
    assert [root["root"] for root in store.roots()] == [moved["root"], empty["root"]]
    proof = store.proof("alice")
    assert proof is not None and proof["root"] == moved["root"] and proof["leaf"]
    assert sakk.verify_export(store.export("alice"))["ok"]
