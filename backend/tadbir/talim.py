"""Ta'lim (تعليم, teaching): an administrator teaches MIZAN new examples.

MIZAN understands by evidence (Tamyiz): Qasd reads what a message asks, its
facets read yes/no questions about it, and Lughah reads its language. Each is
fitted on seed examples that ship with the code. Ta'lim lets an administrator
add examples, typed in or imported from a Hugging Face dataset, and add a
language Lughah did not know (Tamil, Bengali, …).

A batch is kept only if it does not make MIZAN worse at what it already knew:

- the model is refitted with the batch, and every existing seed (up to 1,500,
  every k-th) is scored by exact leave-one-out, before and after;
- a paired bootstrap over those seeds (2,000 resamples, a fixed seed so the
  verdict is reproducible) gives P(after < before);
- the batch is refused when that probability is at least 0.95, the same
  standard Tajdid uses to replace its incumbent. Otherwise it is kept, with
  how well the refitted model reads the new examples themselves.

Nothing else decides: no hand-set accuracy floor. Every batch, kept or
refused, is reported with the per-class change, and a kept batch is a Sakk
receipt. Undo removes a batch. Batches live in ``$MIZAN_DATA_DIR/talim.db``;
the kept ones are part of each model's corpus, so its fit (cached by the
corpus SHA-256) follows them.
"""

from __future__ import annotations

import json
import math
import os
import random
import re
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

MAX_EXAMPLES = 5000  # one batch
MAX_TEXT = 500  # one example
LOO_SAMPLE = 1500  # existing seeds scored before and after, as Tamyiz.fit does
RESAMPLES = 2000
REFUSE_AT = 0.95  # P(worse) at which a batch is refused (Tajdid's standard)
_CODE = re.compile(r"^[a-z]{2,3}(?:-[a-z]{2,4})?$")
_LOCK = threading.Lock()


# ── storage ──────────────────────────────────────────────────────────────


def _path() -> Path:
    return Path(os.getenv("MIZAN_DATA_DIR", "/data/mizan")) / "talim.db"


def _connect() -> sqlite3.Connection:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS batches (
            id TEXT PRIMARY KEY, model TEXT NOT NULL, source TEXT NOT NULL,
            licence TEXT NOT NULL, by TEXT NOT NULL, created REAL NOT NULL,
            status TEXT NOT NULL, report TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS examples (
            batch TEXT NOT NULL, position INTEGER NOT NULL, text TEXT NOT NULL,
            label TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS examples_batch ON examples(batch);
        CREATE TABLE IF NOT EXISTS languages (code TEXT PRIMARY KEY, name TEXT NOT NULL);
        """
    )
    return conn


def enabled() -> bool:
    """MIZAN_TALIM=off sets every taught batch aside (and the shipped refit,
    ``python -m core.tamyiz_cache``, never includes them)."""
    return os.getenv("MIZAN_TALIM", "on").strip().lower() not in {"off", "0", "false", "no"}


def rows(model: str) -> list[tuple[str, str, str]]:
    """(text, label, batch) of every kept example for a model, in teaching order."""
    if not enabled() or not _path().exists():
        return []
    try:
        with _connect() as conn:
            found = conn.execute(
                "SELECT e.text, e.label, e.batch FROM examples e JOIN batches b ON b.id = e.batch "
                "WHERE b.model = ? AND b.status = 'kept' ORDER BY b.created, e.position",
                (model,),
            ).fetchall()
    except sqlite3.Error:
        return []
    return [(row["text"], row["label"], row["batch"]) for row in found]


def languages() -> dict[str, str]:
    """Languages an administrator taught Lughah: code -> name."""
    if not _path().exists():
        return {}
    try:
        with _connect() as conn:
            found = conn.execute("SELECT code, name FROM languages").fetchall()
    except sqlite3.Error:
        return {}
    taught = {label for _text, label, _batch in rows("lughah")}
    return {row["code"]: row["name"] for row in found if row["code"] in taught}


def batches() -> list[dict]:
    if not _path().exists():
        return []
    with _connect() as conn:
        found = conn.execute(
            "SELECT b.*, COUNT(e.batch) AS size FROM batches b "
            "LEFT JOIN examples e ON e.batch = b.id GROUP BY b.id ORDER BY b.created DESC"
        ).fetchall()
    return [{**dict(row), "report": json.loads(row["report"])} for row in found]


# ── the models that can be taught ────────────────────────────────────────


def models() -> dict[str, list[str]]:
    """Each teachable model and the labels it takes."""
    from . import lughah, qasd

    found: dict[str, list[str]] = {
        "qasd": sorted({label for label, _text in qasd._rows("intents.tsv")}),
        "lughah": sorted(set(lughah.LABELS) | set(languages())),
    }
    for facet in sorted({row[0] for row in qasd._rows("facets.tsv")}):
        found[f"qasd.{facet}"] = ["no", "yes"]
    return found


def _model(name: str) -> tuple[Callable, Callable[[], list[tuple[str, ...]]], Callable]:
    """(featurize, current corpus, shape of new rows) for a model."""
    from . import lughah, qasd

    if name == "qasd":

        def shape(examples: list[tuple[str, str]], batch: str) -> list[tuple[str, ...]]:
            return qasd.shaped(examples, batch)

        return qasd._features, qasd.examples, shape
    if name.startswith("qasd."):
        facet = name.partition(".")[2]
        return (
            qasd._features,
            lambda: qasd.facet_examples(facet),
            lambda examples, batch: list(examples),
        )
    if name == "lughah":
        return lughah._features, lughah.corpus, lambda examples, batch: list(examples)
    raise KeyError(name)


def _clear(name: str) -> None:
    """Forget the cached fits so the next read refits on the new corpus."""
    from . import lughah, qasd

    if name == "lughah":
        lughah.model.cache_clear()
        lughah._word.cache_clear()
    elif name == "qasd":
        qasd.model.cache_clear()
    else:
        qasd.facet_model.cache_clear()


def check(
    name: str, examples: Sequence[tuple[str, str]], language_name: str = ""
) -> list[tuple[str, str]]:
    """The batch, cleaned and checked against the model's labels."""
    labels = models().get(name)
    if labels is None:
        raise ValueError(f"No model named {name!r}")
    cleaned: list[tuple[str, str]] = []
    for text, label in examples:
        text = " ".join(str(text).split())[:MAX_TEXT]
        label = str(label).strip()
        if not text:
            continue
        if label not in labels:
            if name == "lughah" and _CODE.match(label) and language_name.strip():
                labels = [*labels, label]  # a new language, named by the teacher
            else:
                raise ValueError(f"{label!r} is not a label of {name}")
        cleaned.append((text, label))
    if not cleaned:
        raise ValueError("The batch has no examples")
    if len(cleaned) > MAX_EXAMPLES:
        raise ValueError(f"A batch holds at most {MAX_EXAMPLES} examples")
    return cleaned


# ── the gate ─────────────────────────────────────────────────────────────


def p_worse(before: Sequence[bool], after: Sequence[bool], resamples: int = RESAMPLES) -> float:
    """P(after is less accurate than before) by a paired bootstrap."""
    differences = [int(b) - int(a) for a, b in zip(before, after, strict=True)]
    if not differences or not any(differences):
        return 0.0
    rng = random.Random(0)
    size = len(differences)
    worse = 0
    for _ in range(resamples):
        if sum(differences[rng.randrange(size)] for _ in range(size)) < 0:
            worse += 1
    return worse / resamples


def judge(name: str, examples: Sequence[tuple[str, str]], batch: str = "candidate") -> dict:
    """Refit with the batch and weigh it against what the model already knew."""
    from core.tamyiz import Tamyiz

    featurize, corpus, shape = _model(name)
    existing = corpus()
    added = shape(list(examples), batch)
    old = Tamyiz(featurize).fit(existing)
    new = Tamyiz(featurize).fit([*existing, *added])
    step = max(1, math.ceil(len(existing) / LOO_SAMPLE))
    sample = existing[::step]
    before = old.held_out_correct(sample)
    after = new.held_out_correct(sample)
    learned = new.held_out_correct(added)
    risk = p_worse(before, after)
    per_class: dict[str, dict[str, float | int]] = {}
    for row, was, now in zip(sample, before, after, strict=True):
        entry = per_class.setdefault(row[1], {"n": 0, "before": 0, "after": 0})
        entry["n"] += 1
        entry["before"] += int(was)
        entry["after"] += int(now)
    changed = {
        label: {
            "n": int(entry["n"]),
            "before": round(entry["before"] / entry["n"], 4),
            "after": round(entry["after"] / entry["n"], 4),
        }
        for label, entry in sorted(per_class.items())
        if entry["before"] != entry["after"]
    }
    return {
        "examples": len(examples),
        "seeds_scored": len(sample),
        "before": round(sum(before) / max(1, len(before)), 4),
        "after": round(sum(after) / max(1, len(after)), 4),
        "p_worse": round(risk, 4),
        "kept": risk < REFUSE_AT,
        "learned": round(sum(learned) / max(1, len(learned)), 4),
        "changed_classes": changed,
    }


def teach(
    name: str,
    examples: Sequence[tuple[str, str]],
    *,
    source: str,
    licence: str,
    by: str,
    language_name: str = "",
) -> dict:
    """Judge a batch and keep it if it passes; every batch is recorded."""
    cleaned = check(name, examples, language_name)
    batch = uuid.uuid4().hex
    with _LOCK:
        report = judge(name, cleaned, batch)
        status = "kept" if report["kept"] else "refused"
        with _connect() as conn:
            conn.execute(
                "INSERT INTO batches VALUES (?,?,?,?,?,?,?,?)",
                (batch, name, source[:300], licence[:120], by, time.time(), status,
                 json.dumps(report)),
            )  # fmt: skip
            if status == "kept":
                conn.executemany(
                    "INSERT INTO examples VALUES (?,?,?,?)",
                    [(batch, i, text, label) for i, (text, label) in enumerate(cleaned)],
                )
                if name == "lughah" and language_name.strip():
                    for _text, label in cleaned:
                        if _CODE.match(label):
                            conn.execute(
                                "INSERT OR IGNORE INTO languages VALUES (?, ?)",
                                (label, language_name.strip()[:60]),
                            )
        if status == "kept":
            _clear(name)
    _receipt(by, "taught" if status == "kept" else "refused", batch, name, len(cleaned), report)
    return {"batch": batch, "status": status, "model": name, **report}


def undo(batch: str, by: str) -> bool:
    with _LOCK:
        with _connect() as conn:
            row = conn.execute(
                "SELECT model, status FROM batches WHERE id = ?", (batch,)
            ).fetchone()
            if row is None or row["status"] != "kept":
                return False
            conn.execute("UPDATE batches SET status = 'undone' WHERE id = ?", (batch,))
        _clear(row["model"])
    _receipt(by, "undone", batch, row["model"], 0, {})
    return True


def _receipt(by: str, action: str, batch: str, model: str, size: int, report: dict) -> None:
    try:
        from security import sakk

        sakk.record(
            "system",
            "talim",
            {
                "action": action,
                "batch": batch,
                "model": model,
                "examples": size,
                "by": by,
                "p_worse": report.get("p_worse"),
            },
            f"Ta'lim · {model} · {action} ({size})"[:120],
        )
    except Exception:  # noqa: BLE001 - the batch is recorded; the receipt is best effort
        pass


def from_rows(
    records: Sequence[dict[str, Any]],
    text_column: str,
    label_column: str,
    label_map: dict[str, str] | None = None,
) -> list[tuple[str, str]]:
    """Examples from dataset rows: the text and label columns, labels mapped;
    rows whose label maps to nothing are left out."""
    found = []
    for record in records:
        text, label = record.get(text_column), record.get(label_column)
        if text is None or label is None:
            continue
        mapped = (label_map or {}).get(str(label), str(label) if label_map is None else None)
        if mapped:
            found.append((str(text), mapped))
    return found
