"""Satr (Muslim 2699): a secret in a tool's output is covered before anything keeps it.

Known credential formats, credentials in a URL, a secret assigned to a key, and long
random-looking tokens are replaced by ``[redacted:<kind>]``; what MIZAN itself prints
(SHA-256 digests, UUIDs, git SHAs, links), Quran and hadith text, code and images are not.
Fake values are built at run time so no credential-shaped literal sits in this file.
"""

from unittest.mock import MagicMock

import pytest

from agents.specialized import create_agent
from security import satr

# Built here, never written whole in the source (the secret scanners read this file).
GITHUB = "gh" + "p_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
OPENAI = "s" + "k-" + "proj-Zq8Rt3Lm9Xc2Vb7Nw4Ks1Pd6"
AWS = "AK" + "IA" + "Q7XK2M9P4R6T8V3W"
SLACK = "xo" + "xb-" + "1234567890-abcdefABCDEF"
JWT = "ey" + "JhbGciOiJIUzI1NiJ9." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0." + "abc123DEF456ghi789"
RANDOM = "Qm9x" + "T7kLp2Vr8Zs4Wn6Yc1Hd3Jf5"  # mixed case, scattered digits, near-random
PEM = "-----BEGIN " + "RSA PRIVATE KEY-----\nMIIEow\nabc\n-----END RSA PRIVATE KEY-----"


@pytest.mark.parametrize(
    ("text", "kind", "kept"),
    [
        (f"token {GITHUB} done", "github_token", "done"),
        (f"OPENAI_API_KEY={OPENAI}", "api_key", "OPENAI_API_KEY="),
        ("export DB_PASSWORD=" + "hunter2hunter2", "assigned", "export DB_PASSWORD="),
        (f"key {OPENAI} here", "api_key", "here"),
        (f"aws {AWS}", "aws_key", "aws"),
        (f"slack {SLACK}", "slack_token", "slack"),
        (f"jwt {JWT}", "jwt", "jwt"),
        (f"{PEM}\nafter", "private_key", "after"),
        ("postgres://app:" + "hunter2pw" + "@db.local:5432/x", "url_password", "postgres://app:"),
        ("DB_PASSWORD=" + "s3cr3t!pw", "assigned", "DB_PASSWORD="),
        ('password: "' + "correct horse" + '"', "assigned", "password: "),
        ("Authorization: Bearer " + RANDOM, "authorization", "Authorization: Bearer "),
        (f"value {RANDOM} end", "high_entropy", "end"),
    ],
)
def test_secrets_are_covered_by_kind(text, kind, kept):
    covered = satr.cover(text)
    assert f"[redacted:{kind}]" in covered, covered
    assert kept in covered
    assert satr.holds(text)


@pytest.mark.parametrize(
    "text",
    [
        # What MIZAN prints about its own work.
        "receipt sha256 " + "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
        "params_sha256: " + "E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855",
        "id 3f2a9b1c-4d5e-4f60-8a7b-9c0d1e2f3a4b and commit 431b875a9c0e",
        "/api/workspaces/preview/" + "a" * 32 + "0123456789abcdef" * 2 + "/5173/",
        # Scripture and ordinary words.
        "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ",
        "Actions are judged by intentions (Bukhari 1). The secret of success is patience.",
        "Remember to implement password hashing and token refresh in the auth module.",
        # Code: expressions, not literals.
        "const token = jwt.sign(payload, key)",
        "secret_key = settings.SECRET_KEY",
        "api_key: str | None = None\npassword = getpass()",
        '{"max_tokens": 4096, "tokens": 12}',
        "class UserProfileCard2 extends convertBase64ToUtf8Helper {}",
        "/home/user/projects/mizan/backend/security/satr.py",
        # Public digests and links.
        "integrity sha512-" + "Zm9vYmFyQmF6UXV4MTIzNDU2Nzg5MEFCQ0RFRkdISUpLTE1OT1BRUlNUVVZXWFla",
        "https://docs.google.com/document/d/1aBcD3fGhIjK4lMnOp5QrStU6vWxYz7AbCd/edit",
        "Run in 12 ms; 3 tests passed.",
    ],
)
def test_what_is_not_a_secret_is_left_alone(text):
    assert satr.cover(text) == text
    assert not satr.holds(text)


def test_images_are_never_touched():
    image = "data:image/png;base64," + (RANDOM * 40)
    assert satr.cover(image) == image
    assert satr.cover({"preview": image}) == {"preview": image}


def test_structures_are_walked_and_keyed_values_covered():
    value = {
        "stdout": f"export TOKEN={GITHUB}\nok",
        "files": [{"path": ".env", "content": f"API_KEY={OPENAI}"}],
        "client_secret": "plainwords",
        "next_page_token": "CAESBggDEAEYAQ",  # a cursor, not a credential
        "exit_code": 0,
        "nested": ({"password": "letmein99"},),
    }
    covered = satr.cover(value)
    assert GITHUB not in str(covered) and OPENAI not in str(covered)
    assert covered["client_secret"] == "[redacted:key]"
    assert covered["next_page_token"] == "CAESBggDEAEYAQ"
    assert covered["exit_code"] == 0
    assert covered["nested"][0]["password"] == "[redacted:key]"
    assert isinstance(covered["nested"], tuple)
    assert value["client_secret"] == "plainwords"  # the original is not changed


@pytest.mark.parametrize(
    ("key", "credential"),
    [
        ("password", True),
        ("client_secret", True),
        ("x-api-key", True),
        ("apiKey", True),
        ("accessToken", True),
        ("refresh_token", True),
        ("Authorization", True),
        ("next_page_token", False),
        ("nextPageToken", False),
        ("max_tokens", False),
        ("tokens", False),
        ("token_count", False),
        ("secret_dir", False),
        ("author", False),
    ],
)
def test_credential_keys(key, credential):
    assert satr.credential_key(key) is credential


def test_cover_is_idempotent():
    once = satr.cover(f"a {GITHUB} b DB_PASSWORD=x9y8z7w6 {RANDOM}")
    assert satr.cover(once) == once


def test_connector_logs_use_the_same_patterns():
    from connectors.manager import redact

    assert GITHUB not in redact(f"[stderr] using {GITHUB}")
    assert redact("token=" + "abcd1234efgh&q=1").startswith("token=[redacted]&q=1")


# ── One place for tool results: _execute_tool_safe ─────────────────────────


async def test_tool_results_are_covered_before_the_model_and_the_receipt(monkeypatch):
    from security import sakk

    seen = []
    monkeypatch.setattr(
        sakk, "record_tool", lambda owner, tool, params, result: seen.append(result)
    )
    izn = MagicMock()
    izn.check_permission.return_value = {"allowed": True, "reason": "", "requires_approval": False}
    agent = create_agent("general", name="Satr", wali=MagicMock(), izn=izn)
    agent._chat_tool_allowed = lambda name: True

    async def cat_env(**params):
        return {"stdout": f"GITHUB_TOKEN={GITHUB}\n", "exit_code": 0}

    agent.tools["bash"] = cat_env
    result = await agent._execute_tool_safe("bash", {"command": "cat .env"})
    assert GITHUB not in str(result) and "[redacted:" in result["stdout"]
    assert seen and GITHUB not in str(seen[0])


# ── Memory never keeps a secret ────────────────────────────────────────────


async def test_a_note_is_kept_without_its_secret(tmp_path):
    from memory.dhikr import DhikrMemorySystem

    memory = DhikrMemorySystem(str(tmp_path / "memory.db"))
    mem_id = await memory.remember(f"my deploy key is {GITHUB}", memory_type="semantic")
    stored = (
        memory._get_conn()
        .execute("SELECT content FROM memories WHERE id = ?", (mem_id,))
        .fetchone()[0]
    )
    assert GITHUB not in stored and "[redacted:github_token]" in stored


def test_a_daftar_edit_is_kept_without_its_secret(tmp_path):
    import asyncio

    from memory import daftar
    from memory.dhikr import DhikrMemorySystem

    memory = DhikrMemorySystem(str(tmp_path / "memory.db"))
    mem_id = asyncio.run(memory.remember("my note", memory_type="semantic"))
    assert daftar.edit_note(memory, mem_id, content=f"key {OPENAI}", tags=None, expires=None)
    stored = (
        memory._get_conn()
        .execute("SELECT content FROM memories WHERE id = ?", (mem_id,))
        .fetchone()[0]
    )
    assert OPENAI not in stored and "[redacted:api_key]" in stored


def test_talaqqi_keeps_no_answer_that_holds_a_secret(monkeypatch):
    from tadbir import talaqqi

    saved = []
    monkeypatch.setattr(talaqqi, "_load", lambda store, user: [])
    monkeypatch.setattr(talaqqi, "_save", lambda store, user, items: saved.append(items))
    monkeypatch.setattr(talaqqi, "about", lambda question, answer: True)

    passage = MagicMock(
        text="source", title="T", url="https://en.wikipedia.org/wiki/X", source="wikipedia", at=""
    )
    finding = MagicMock(
        verdict="supported",
        passage=passage,
        context=None,
        claim=f"The key is {GITHUB}",
        probability=0.9,
    )
    assert not talaqqi.keep(None, "u", "what is the key of the project", "en", [finding])
    assert saved == []
