"""The owner's locked evaluation set (mizan-eval-v1) as an Imtihan block.

The set is published on Hugging Face (``Zubairshaikh/mizan-eval-v1``, CC-BY-4.0)
and anchored by its SHA-256, not by secrecy. Its lock rules: it never becomes
training data, and only aggregate scores are reported. So it is not copied into
this repository: MIZAN downloads it once into ``$MIZAN_DATA_DIR/imtihan/`` and
uses it only if the hash matches.

A fixed sample per category runs through both arms (the first items by id, so
every run sees the same ones). Scored by rule, following the lock's rubric:

- **grounded questions**: the answer cites the ayah's locator, is in the
  question's language, and does not refuse
- **general and dialogue**: in the question's language, and not refused
- **abstention**: the answer declines or says the ayah does not tell
- **coding**: the answer's code passes the item's assert tests in the sandbox

The rubric's key points and ``must_not`` claims need a reader, not a rule, so
they are not scored here. The 25 tool items ask about the owner's own
workspace and are left out.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

REPO = "Zubairshaikh/mizan-eval-v1"
FILE = "eval_v1.jsonl"
SHA256 = "14844d6f0e2b0885013ad2dbf6deeb990aeb44b3141832aa8f0df6da217b504b"
URL = f"https://huggingface.co/datasets/{REPO}/resolve/main/{FILE}"
PER_CATEGORY = 4
CATEGORIES = ("ar", "en", "hi", "ru", "ur", "abstain", "coding")
_LANGUAGES = {"ar": {"ar"}, "en": {"en"}, "hi-hinglish": {"hi-latn"}, "ur-roman": {"hi-latn"},
              "ur": {"ur"}}  # fmt: skip
_TRIED = False


def _cache() -> Path:
    return Path(os.getenv("MIZAN_DATA_DIR", "data")) / "imtihan" / FILE


def _verified(data: bytes) -> bool:
    return hashlib.sha256(data).hexdigest() == SHA256


def enabled() -> bool:
    return os.getenv("MIZAN_LOCKED_EVAL", "on").strip().lower() not in {"off", "false", "0"}


def items() -> list[dict]:
    """The locked items, downloaded once and used only when the hash matches."""
    global _TRIED
    if not enabled():
        return []
    path = _cache()
    if path.exists() and _verified(path.read_bytes()):
        data = path.read_bytes()
    else:
        if _TRIED:
            return []
        _TRIED = True
        try:
            import httpx

            from knowledge.hf_hub import host_allowed

            def guard(request: httpx.Request) -> None:
                if not host_allowed(request.url.host):
                    raise httpx.HTTPError(f"refused host {request.url.host}")

            with httpx.Client(
                follow_redirects=True, timeout=20, event_hooks={"request": [guard]}
            ) as client:
                response = client.get(URL)
                response.raise_for_status()
                data = response.content
        except Exception:  # noqa: BLE001 - no network: the block is simply absent
            return []
        if not _verified(data):
            return []  # never score against a changed set
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]


def tasks() -> list[dict]:
    chosen: list[dict] = []
    rows = sorted(items(), key=lambda row: row["id"])
    for category in CATEGORIES:
        chosen += [row for row in rows if row["category"] == category][:PER_CATEGORY]
    return [_task(row) for row in chosen]


def _task(row: dict) -> dict:
    prompt = row["question"]
    evidence = row.get("evidence")
    if evidence:
        prompt += f"\n\nThe ayah ({evidence['locator']}):\n{evidence['text']}"
    return {
        "id": f"lock-{row['id']}",
        "block": "locked_eval",
        "prompt": prompt,
        "source": f"{REPO} ({row['id']}, sha256 {SHA256[:12]}…)",
        "score": {
            "kind": "locked",
            "task": row["task"],
            "status": row["expected_status"],
            "language": row.get("language"),
            "locator": (evidence or {}).get("locator"),
            "tests": row.get("tests"),
        },
    }


_LOCATOR = re.compile(r"(\d+)\D+(\d+)")
# "The ayah does not mention it": declining because the evidence does not say.
ABSTAIN = re.compile(
    r"\b(?:does\s*n[o']?t|do\s*n[o']?t|is\s*n[o']?t|are\s*n[o']?t)\s+(?:\w+\s+)?(?:mention|say|state|name|"
    r"specify|tell|give|identify|reveal)|\bnot\s+(?:mentioned|stated|specified|named|given|"
    r"identified|known)|\bno\s+mention\b|cannot\s+be\s+(?:known|determined|answered)|"
    r"\bnahi?n?\s+(?:bataya|batata|diya|likha|kaha)|\bzikr\s+nahi|\bmention\s+nahi|"
    r"لا\s+(?:تذكر|يذكر|تحدد)|لم\s+(?:تذكر|يذكر|تحدد)|نہیں\s+(?:بتایا|بتاتی|بتاتا)|ذکر\s+نہیں",
    re.IGNORECASE,
)
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def cites(answer: str, locator: str | None) -> bool:
    """The answer names the ayah: surah and ayah numbers (1:5, Surah 1 Ayah 5, ١:٥)."""
    match = _LOCATOR.search(locator or "")
    if not match:
        return True
    surah, ayah = match.groups()
    text = (answer or "").translate(_DIGITS)
    if re.search(rf"(?<!\d){surah}\s*[:：/.]\s*{ayah}(?!\d)", text):
        return True
    return bool(
        re.search(rf"(?<!\d){surah}(?!\d)", text) and re.search(rf"(?<!\d){ayah}(?!\d)", text)
    )


def language_ok(answer: str, expected: str | None) -> bool:
    from tadbir.fahm import detect_language

    wanted = _LANGUAGES.get(expected or "")
    if not wanted:
        return True
    prose = re.sub(r"```.*?```|^>.*$", " ", answer or "", flags=re.DOTALL | re.MULTILINE)
    return detect_language(prose) in wanted


def code_of(answer: str) -> str:
    blocks = re.findall(r"```(?:python|py)?[^\n]*\n(.*?)```", answer or "", re.DOTALL)
    return max(blocks, key=len) if blocks else ""


async def passes_tests(answer: str, tests: str) -> bool:
    """The answer's code with the item's asserts, run in a fresh sandboxed project."""
    code = code_of(answer)
    if not code or not tests:
        return False
    from security.auth import current_user_id
    from workspace.execution import run_project
    from workspace.store import WorkspaceStore

    owner = current_user_id()
    if not owner:
        return False
    store = WorkspaceStore(owner)
    project = store.create("imtihan-locked-coding", reserved=True)["id"]
    try:
        store.write(project, "check.py", f"{code}\n\n{tests}\nprint('LOCKED-TESTS-PASSED')\n")
        run = await run_project(store, project, "python check.py", "shell", 30)
        return run.get("exit_code") == 0 and "LOCKED-TESTS-PASSED" in str(run.get("stdout", ""))
    except Exception:  # noqa: BLE001 - the sandbox is part of the test
        return False
    finally:
        try:
            store.remove(project)
        except Exception:  # noqa: BLE001
            pass
