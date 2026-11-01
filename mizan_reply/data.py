"""Strict, original-data input contract and length-framed byte serialization.

No corpora are created here. Hashes prove byte identity, not truth, authorship,
religious authenticity, source alignment or a reviewer's competence.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Iterator
from urllib.parse import urlsplit

import torch

SCHEMA_VERSION = "mizan.reply.v1"
EOS_ID, BOS_ID, USER_ID, ASSISTANT_ID, SYSTEM_ID, EVIDENCE_ID, END_ID = range(256, 263)
IGNORE_INDEX = -100
ROOT_ALPHABET = "ءبتثجحخدذرزسشصضطظعغفقكلمنهوي"
ROOT_TO_ID = {letter: i + 1 for i, letter in enumerate(ROOT_ALPHABET)}
ROLE_IDS = {"user": USER_ID, "assistant": ASSISTANT_ID, "system": SYSTEM_ID}
SPLITS = {"train", "dev", "test"}
TASKS = {"dialogue", "grounded_qa", "clarification", "abstention", "correction"}
SOURCE_KINDS = {"quran", "tafsir", "hadith", "lexicon", "human_dialogue", "other"}
# The owner's decision of 30 Oct 2026 (docs/consent.md): a teacher model's output
# may be a training target when MIZAN verified it and the teacher's licence allows
# training on its output. Anthropic's and OpenAI's terms forbid that, so their
# output is never a target; scripture is never a target whoever wrote it.
TEACHER_LICENCES = {"apache-2.0", "mit", "deepseek-terms-of-use", "deepseek-model-license"}
FORBIDDEN_TEACHERS = {"anthropic", "openai"}
MIZAN_VERIFIERS = {"tathabbut", "sandbox", "sidq", "ahl_dhikr", "fihris", "calc", "hifz", "qiyas"}
SCRIPTURE_KINDS = {"quran", "hadith"}
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_LANG = re.compile(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*\Z")
_IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/@+~-]{0,255}\Z")


class DataValidationError(ValueError):
    """A record, source asset or partition violates the data contract."""


def _fail(where: str, message: str) -> None:
    raise DataValidationError(f"{where}: {message}")


def _keys(obj: Any, required: set[str], optional: set[str], where: str) -> None:
    if not isinstance(obj, dict):
        _fail(where, "must be an object")
    missing = required - obj.keys()
    extra = obj.keys() - required - optional
    if missing:
        _fail(where, f"missing fields {sorted(missing)}")
    if extra:
        _fail(where, f"unsupported fields {sorted(extra)}")


def _text(value: Any, where: str, *, identifier: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(where, "must be a non-empty string")
    if "__REPLACE_" in value:
        _fail(where, "placeholder is not training data")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        _fail(where, "contains invalid Unicode")
    if "\x00" in value:
        _fail(where, "NUL is unsupported in textual source records")
    if identifier and not _IDENT.fullmatch(value):
        _fail(where, "must be an ASCII identifier (letters/digits and _ . : / @ + ~ -)")
    return value


def _strings(value: Any, where: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        _fail(where, "must be a list" + (" with at least one item" if nonempty else ""))
    for i, item in enumerate(value):
        _text(item, f"{where}[{i}]", identifier=True)
    if len(value) != len(set(value)):
        _fail(where, "duplicate identifiers")
    return value


def _sha(value: Any, where: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        _fail(where, "must be a lowercase SHA256 hexadecimal digest")
    return value


def sha256_text(text: str) -> str:
    """Hash exact UTF-8 bytes, without NFC, whitespace or punctuation changes."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _validate_messages(messages: Any) -> None:
    if not isinstance(messages, list) or not messages:
        _fail("messages", "must contain at least one user message")
    expected = "user"
    for i, message in enumerate(messages):
        where = f"messages[{i}]"
        _keys(message, {"role", "content"}, set(), where)
        role = message["role"]
        if i == 0 and role == "system":
            _text(message["content"], where + ".content")
            continue
        if role != expected:
            _fail(where + ".role", f"expected {expected}; optional system is first only")
        _text(message["content"], where + ".content")
        expected = "assistant" if role == "user" else "user"
    if messages[-1]["role"] != "user":
        _fail("messages", "last message must be user; target is kept separately")


def _validate_evidence(evidence: Any) -> None:
    if not isinstance(evidence, list):
        _fail("evidence", "must be a list")
    seen: set[str] = set()
    for i, item in enumerate(evidence):
        where = f"evidence[{i}]"
        _keys(item, {"id", "source_id", "locator", "text", "sha256"}, set(), where)
        eid = _text(item["id"], where + ".id", identifier=True)
        if eid in seen:
            _fail(where + ".id", "duplicate evidence id")
        seen.add(eid)
        _text(item["source_id"], where + ".source_id", identifier=True)
        _text(item["locator"], where + ".locator")
        text = _text(item["text"], where + ".text")
        _sha(item["sha256"], where + ".sha256")
        if sha256_text(text) != item["sha256"]:
            _fail(where + ".sha256", "does not match exact evidence UTF-8 bytes")


def _validate_roots(roots: Any, messages: list[dict[str, str]], *, allow_pending: bool) -> None:
    if not isinstance(roots, list):
        _fail("roots", "must be a list")
    used: dict[int, list[tuple[int, int]]] = {}
    for i, annotation in enumerate(roots):
        where = f"roots[{i}]"
        _keys(annotation, {"message_index", "start", "end", "root", "source_id", "review_status"}, set(), where)
        mi, start, end = (annotation[key] for key in ("message_index", "start", "end"))
        if any(type(x) is not int for x in (mi, start, end)):
            _fail(where, "message_index/start/end must be integers, not booleans")
        if not 0 <= mi < len(messages):
            _fail(where + ".message_index", "must point to an input message, never target")
        text = messages[mi]["content"]
        if not 0 <= start < end <= len(text):
            _fail(where, "invalid Unicode-codepoint [start,end) span")
        span = text[start:end]
        def arabic_word_character(ch: str) -> bool:
            return "ARABIC" in unicodedata.name(ch, "") and unicodedata.category(ch)[0] in {"L", "M"}

        if (not all(arabic_word_character(ch) for ch in span)
                or not unicodedata.category(span[0]).startswith("L")
                or (start > 0 and arabic_word_character(text[start - 1]))
                or (end < len(text) and arabic_word_character(text[end]))):
            _fail(where, "root span must be a complete Arabic word (letters and Arabic combining marks only), not a partial word, punctuation or forced translation")
        root = annotation["root"]
        if not isinstance(root, str) or len(root) not in (3, 4) or any(c not in ROOT_TO_ID for c in root):
            _fail(where + ".root", "must have 3 or 4 canonical radicals; use ء for hamza, not bare ا")
        _text(annotation["source_id"], where + ".source_id", identifier=True)
        status = annotation["review_status"]
        if not isinstance(status, str) or status not in {"accepted", "pending", "rejected"}:
            _fail(where + ".review_status", "invalid review status")
        if status != "accepted" and not allow_pending:
            _fail(where + ".review_status", "root annotation must be accepted for training")
        for other_start, other_end in used.setdefault(mi, []):
            if start < other_end and other_start < end:
                _fail(where, "root spans overlap in the same input message")
        used[mi].append((start, end))


def _validate_teacher(prov: dict[str, Any]) -> None:
    """A licensed teacher's output: a named model whose licence allows training on
    its output, verified by one of MIZAN's own checks (docs/consent.md)."""
    teacher = prov.get("teacher")
    _keys(teacher, {"provider", "model", "licence"}, {"terms"}, "provenance.teacher")
    provider = _text(teacher["provider"], "provenance.teacher.provider").strip().lower()
    model = _text(teacher["model"], "provenance.teacher.model").strip().lower()
    # OpenRouter names a model "<vendor>/<model>"; the vendor decides, not the router.
    vendor = model.split("/", 1)[0] if "/" in model else ""
    if provider in FORBIDDEN_TEACHERS or vendor in FORBIDDEN_TEACHERS or "claude" in model or model.startswith("gpt-"):
        _fail("provenance.teacher", "Anthropic and OpenAI output is for lookup only, never a training target")
    if teacher["licence"] not in TEACHER_LICENCES:
        _fail("provenance.teacher.licence", f"must be one of {sorted(TEACHER_LICENCES)}")
    verification = prov.get("verification")
    _keys(verification, {"by", "passed"}, set(), "provenance.verification")
    if verification["by"] not in MIZAN_VERIFIERS:
        _fail("provenance.verification.by", f"must be one of {sorted(MIZAN_VERIFIERS)}")
    if verification["passed"] is not True:
        _fail("provenance.verification.passed", "only output MIZAN verified may be a target")
    if prov.get("creation_method", "machine_generation") != "machine_generation":
        _fail("provenance.creation_method", "a teacher's output is machine_generation")


def validate_record(record: dict[str, Any], allow_pending: bool = False) -> dict[str, Any]:
    """Validate one record; accepted review is metadata, not independently certified.

    allow_pending permits inspection of drafts only. Serialization and training do
    not enable this switch. Machine-authored drafts are never original-data gold.
    """
    _keys(record, {"schema_version", "id", "split", "group_id", "language", "task", "messages", "evidence", "target", "provenance"}, {"roots"}, "record")
    if record["schema_version"] != SCHEMA_VERSION:
        _fail("schema_version", f"expected {SCHEMA_VERSION}")
    _text(record["id"], "id", identifier=True)
    _text(record["group_id"], "group_id", identifier=True)
    if not isinstance(record["split"], str) or record["split"] not in SPLITS:
        _fail("split", "must be train, dev or test")
    if not isinstance(record["language"], str) or not _LANG.fullmatch(record["language"]):
        _fail("language", "must be a BCP47-shaped tag, such as ar, en, hi or hi-Latn")
    if not isinstance(record["task"], str) or record["task"] not in TASKS:
        _fail("task", f"must be one of {sorted(TASKS)}")
    _validate_messages(record["messages"])
    _validate_evidence(record["evidence"])
    target = record["target"]
    _keys(target, {"text", "citations", "answer_status"}, set(), "target")
    _text(target["text"], "target.text")
    citation_ids = _strings(target["citations"], "target.citations")
    if not set(citation_ids) <= {e["id"] for e in record["evidence"]}:
        _fail("target.citations", "contains ids absent from supplied evidence")
    if not isinstance(target["answer_status"], str) or target["answer_status"] not in {"answer", "clarify", "abstain"}:
        _fail("target.answer_status", "must be answer, clarify or abstain")
    if record["task"] == "clarification" and target["answer_status"] != "clarify":
        _fail("target.answer_status", "clarification task must be clarify")
    if record["task"] == "abstention" and target["answer_status"] != "abstain":
        _fail("target.answer_status", "abstention task must be abstain")
    if record["task"] == "grounded_qa" and target["answer_status"] == "answer" and not citation_ids:
        _fail("target.citations", "grounded answer needs at least one evidence citation")
    prov = record["provenance"]
    _keys(prov, {"origin", "source_ids", "rights", "reviewer_ids", "review_status"}, {"author_ids", "creation_method", "lineage", "teacher", "verification"}, "provenance")
    if not isinstance(prov["origin"], str) or prov["origin"] not in {"human_original", "source_transcription", "machine_draft", "licensed_teacher"}:
        _fail("provenance.origin", "unsupported origin")
    if prov["origin"] == "licensed_teacher":
        _validate_teacher(prov)
    elif "teacher" in prov or "verification" in prov:
        _fail("provenance", "teacher and verification belong to licensed_teacher records only")
    if prov["origin"] == "machine_draft" and not allow_pending:
        _fail("provenance.origin", "machine-authored draft is not original-data gold, even if review_status says accepted")
    source_ids = _strings(prov["source_ids"], "provenance.source_ids", nonempty=True)
    _text(prov["rights"], "provenance.rights")
    reviewers = _strings(prov["reviewer_ids"], "provenance.reviewer_ids")
    if not isinstance(prov["review_status"], str) or prov["review_status"] not in {"accepted", "pending", "rejected"}:
        _fail("provenance.review_status", "invalid status")
    if prov["review_status"] != "accepted" and not allow_pending:
        _fail("provenance.review_status", "must be accepted for training")
    if prov["review_status"] == "accepted" and not reviewers:
        _fail("provenance.reviewer_ids", "accepted records need a named reviewer id")
    authors = _strings(prov.get("author_ids", []), "provenance.author_ids")
    if prov["origin"] == "human_original" and not authors:
        _fail("provenance.author_ids", "human_original requires named author ids")
    if set(authors) & set(reviewers):
        _fail("provenance", "author and independent reviewer ids overlap")
    if "creation_method" in prov and (not isinstance(prov["creation_method"], str) or prov["creation_method"] not in {"human", "manual_transcription", "automated_transcription", "machine_generation"}):
        _fail("provenance.creation_method", "unsupported method")
    if prov.get("creation_method") == "machine_generation" and not allow_pending and prov["origin"] != "licensed_teacher":
        _fail("provenance.creation_method", "machine-generated targets are outside the original-data training contract")
    if prov["origin"] == "human_original" and prov.get("creation_method", "human") != "human":
        _fail("provenance.creation_method", "human_original cannot declare transcription or machine generation")
    if prov["origin"] == "machine_draft" and prov.get("creation_method", "machine_generation") != "machine_generation":
        _fail("provenance.creation_method", "machine_draft cannot declare human authorship or transcription")
    if "lineage" in prov:
        if not isinstance(prov["lineage"], list):
            _fail("provenance.lineage", "must be a list of non-empty descriptions")
        for i, entry in enumerate(prov["lineage"]):
            _text(entry, f"provenance.lineage[{i}]")
    if prov["origin"] == "source_transcription":
        if prov.get("creation_method") not in {"manual_transcription", "automated_transcription"}:
            _fail("provenance.creation_method", "source_transcription requires an explicit transcription method")
        if not prov.get("lineage"):
            _fail("provenance.lineage", "source_transcription requires extraction/transcription lineage")
    _validate_roots(record.get("roots", []), record["messages"], allow_pending=allow_pending)
    used_sources = {e["source_id"] for e in record["evidence"]} | {r["source_id"] for r in record.get("roots", [])}
    if not used_sources <= set(source_ids):
        _fail("provenance.source_ids", "must include every evidence and root annotation source")
    return record


def _json_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("JSON", f"duplicate object key {key!r}")
        result[key] = value
    return result


def _iter_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    path = Path(path)
    seen = False
    with path.open("r", encoding="utf-8", errors="strict") as handle:
        for number, line in enumerate(handle, start=1):
            seen = True
            if not line.strip():
                _fail(f"{path}:{number}", "blank JSONL row")
            try:
                yield json.loads(line, object_pairs_hook=_json_object_pairs, parse_constant=lambda x: _fail("JSON", f"invalid constant {x}"))
            except (ValueError, TypeError) as exc:
                _fail(f"{path}:{number}", str(exc))
    if not seen:
        _fail(str(path), "empty JSONL file")


def iter_records(path: str | Path, allow_pending: bool = False) -> Iterator[dict[str, Any]]:
    """Stream strict JSONL records; use this for large corpora."""
    for i, record in enumerate(_iter_jsonl(path), start=1):
        try:
            validate_record(record, allow_pending=allow_pending)
        except DataValidationError as exc:
            _fail(f"{path}:{i}", str(exc))
        yield record


def load_records(path: str | Path, allow_pending: bool = False) -> list[dict[str, Any]]:
    """Convenience for small datasets; iter_records avoids retaining all records."""
    return list(iter_records(path, allow_pending=allow_pending))


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        before = _file_identity(handle)
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
        if _file_identity(handle) != before:
            _fail(str(path), "file changed while hashing")
    return digest.hexdigest()


def _file_identity(handle: Any) -> tuple[int, int, int, int, int]:
    import os
    stat = os.fstat(handle.fileno())
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def validate_source(source: dict[str, Any]) -> dict[str, Any]:
    """Validate bibliographic declarations, not their factual authenticity."""
    _keys(source, {"source_id", "source_family", "kind", "title", "edition", "locator", "uri", "rights", "sha256", "local_path"}, {"quran", "tafsir", "hadith", "notes"}, "source")
    _text(source["source_id"], "source.source_id", identifier=True)
    _text(source["source_family"], "source.source_family", identifier=True)
    if not isinstance(source["kind"], str) or source["kind"] not in SOURCE_KINDS:
        _fail("source.kind", f"must be one of {sorted(SOURCE_KINDS)}")
    for key in ("title", "edition", "locator", "uri", "rights", "local_path"):
        _text(source[key], "source." + key)
    if Path(source["local_path"]).is_absolute() or ".." in Path(source["local_path"]).parts:
        _fail("source.local_path", "must be a relative asset path that never escapes the manifest directory")
    uri = source["uri"]
    valid_uri = False
    if not any(ch.isspace() for ch in uri):
        if uri.startswith("urn:"):
            valid_uri = re.fullmatch(r"urn:[A-Za-z0-9][A-Za-z0-9-]{0,31}:.+", uri) is not None
        elif uri.startswith("https://"):
            try:
                parsed = urlsplit(uri)
                valid_uri = bool(parsed.hostname) and parsed.username is None and parsed.password is None
                parsed.port  # reject malformed/out-of-range ports
            except ValueError:
                valid_uri = False
    if not valid_uri:
        _fail("source.uri", "must be https:// source URL or urn: original/private asset identifier")
    _sha(source["sha256"], "source.sha256")
    if "notes" in source:
        _text(source["notes"], "source.notes")
    kind = source["kind"]
    for field in ("quran", "tafsir", "hadith"):
        if field in source and field != kind:
            _fail("source." + field, "metadata must match source kind")
    if kind == "quran":
        q = source.get("quran")
        _keys(q, {"surah", "ayah_start", "ayah_end", "text_edition"}, set(), "source.quran")
        if any(type(q[k]) is not int for k in ("surah", "ayah_start", "ayah_end")):
            _fail("source.quran", "surah and ayah bounds must be integers")
        if not 1 <= q["surah"] <= 114 or not 1 <= q["ayah_start"] <= q["ayah_end"] <= 286:
            _fail("source.quran", "invalid surah or ayah range; verse existence still needs source review")
        _text(q["text_edition"], "source.quran.text_edition")
    elif kind == "tafsir":
        t = source.get("tafsir")
        _keys(t, {"author", "work", "passage", "reviewer_qualification"}, set(), "source.tafsir")
        for key, value in t.items():
            _text(value, "source.tafsir." + key)
    elif kind == "hadith":
        h = source.get("hadith")
        _keys(h, {"collection", "book", "number", "gradings", "reviewer_qualification"}, set(), "source.hadith")
        for key in ("collection", "book", "number", "reviewer_qualification"):
            _text(h[key], "source.hadith." + key)
        if not isinstance(h["gradings"], list) or not h["gradings"]:
            _fail("source.hadith.gradings", "requires attributed grading, not a bare 'authentic' label")
        for i, grading in enumerate(h["gradings"]):
            _keys(grading, {"grade", "grader", "reference"}, set(), f"source.hadith.gradings[{i}]")
            for key, value in grading.items():
                _text(value, f"source.hadith.gradings[{i}].{key}")
    return source


def load_sources(path: str | Path, verify_assets: bool = True) -> dict[str, dict[str, Any]]:
    path = Path(path).resolve()
    return _validate_source_rows(_iter_jsonl(path), path, verify_assets)


def _validate_source_rows(rows: Iterable[dict[str, Any]], path: Path,
                          verify_assets: bool) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    checked_assets: dict[Path, str] = {}
    for i, source in enumerate(rows, start=1):
        try:
            validate_source(source)
        except DataValidationError as exc:
            _fail(f"{path}:{i}", str(exc))
        sid = source["source_id"]
        if sid in result:
            _fail(f"{path}:{i}", f"duplicate source_id {sid}")
        if verify_assets:
            relative_asset = Path(source["local_path"])
            if relative_asset.is_absolute():
                _fail(f"source {sid}", "local_path must be relative to the manifest directory")
            asset = (path.parent / relative_asset).resolve()
            if not asset.is_relative_to(path.parent):
                _fail(f"source {sid}", "local_path escapes manifest directory (including symlinks)")
            if not asset.is_file():
                _fail(f"source {sid}", f"original asset unavailable: {asset}")
            if asset not in checked_assets:
                checked_assets[asset] = file_sha256(asset)
            if checked_assets[asset] != source["sha256"]:
                _fail(f"source {sid}", "original asset SHA256 mismatch")
        result[sid] = source
    return result


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalized_text(text: str) -> str:
    # Only a leakage diagnostic key; original source and model bytes are untouched.
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def validate_dataset(records: Iterable[dict[str, Any]], sources: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Fail closed on normalized conversations, complete turn pairs and source overlap.

    This does not detect arbitrary paraphrases, semantic duplicates or mislabeled
    lineage. Assign conversation and passage families before splitting/reviewing.
    """
    counts = {split: 0 for split in sorted(SPLITS)}
    if sources is not None:
        if not isinstance(sources, dict):
            _fail("sources", "must be a source_id-to-source object mapping")
        for sid, source in sources.items():
            validate_source(source)
            if source["source_id"] != sid:
                _fail("sources", "mapping key differs from source_id")
    ids: set[str] = set()
    ownership: dict[tuple[str, str], tuple[str, str]] = {}
    used_sources: set[str] = set()

    def register(kind: str, key: str, split: str, rid: str) -> None:
        previous = ownership.setdefault((kind, key), (split, rid))
        if previous[0] != split:
            _fail("split leakage", f"{kind} shared by {previous[1]} ({previous[0]}) and {rid} ({split})")

    for record in records:
        validate_record(record)
        rid, split = record["id"], record["split"]
        if rid in ids:
            _fail("dataset", f"duplicate record id {rid}")
        ids.add(rid)
        counts[split] += 1
        register("group_id", record["group_id"], split, rid)
        # Evidence ids/source labels cannot hide the same question/history.
        prompt_key = [{"role": m["role"], "content": _normalized_text(m["content"])} for m in record["messages"] if m["role"] != "system"]
        register("normalized conversation", sha256_text(_canonical(prompt_key)), split, rid)
        # A later conversation row can contain a prior held-out question/answer
        # even when its entire history differs. Compare complete adjacent pairs,
        # including the supervised next reply; never ban a bare common answer.
        turns = prompt_key + [{"role": "assistant", "content": _normalized_text(record["target"]["text"])}]
        for i in range(len(turns) - 1):
            if turns[i]["role"] == "user" and turns[i + 1]["role"] == "assistant":
                register("normalized user/assistant pair", sha256_text(_canonical(turns[i:i + 2])), split, rid)
        register("exact content", sha256_text(_canonical({"messages": record["messages"], "target": record["target"]["text"]})), split, rid)
        teacher_made = record["provenance"]["origin"] == "licensed_teacher"
        for sid in record["provenance"]["source_ids"]:
            used_sources.add(sid)
            if sources is not None:
                if sid not in sources:
                    _fail(rid, f"unresolved source_id {sid}")
                if teacher_made and sources[sid]["kind"] in SCRIPTURE_KINDS:
                    _fail(rid, "a teacher's output over Quran or hadith is never a training target")
                register("source_family", sources[sid]["source_family"], split, rid)
                source = sources[sid]
                register("source asset/locator", _canonical([source["sha256"], source["locator"]]), split, rid)
                if source["kind"] == "hadith":
                    h = source["hadith"]
                    reference = [h["collection"], h["book"], h["number"], source["edition"]]
                    register("hadith reference", _canonical([_normalized_text(v) for v in reference]), split, rid)
                elif source["kind"] == "tafsir":
                    t = source["tafsir"]
                    reference = [t["author"], t["work"], t["passage"], source["edition"]]
                    register("tafsir reference", _canonical([_normalized_text(v) for v in reference]), split, rid)
                if sources[sid]["kind"] == "quran":
                    q = sources[sid]["quran"]
                    for ayah in range(q["ayah_start"], q["ayah_end"] + 1):
                        register("Quran passage", f"{q['surah']}:{ayah}", split, rid)
            else:
                register("source_id", sid, split, rid)
        for e in record["evidence"]:
            register("evidence text", sha256_text(_normalized_text(e["text"])), split, rid)
            if sources is not None and e["locator"] != sources[e["source_id"]]["locator"]:
                _fail(rid, f"evidence locator differs from declared source {e['source_id']}")
    if not ids:
        _fail("dataset", "contains no records")
    return {"schema_version": SCHEMA_VERSION, "records": sum(counts.values()), "by_split": counts,
            "source_ids_used": sorted(used_sources), "leakage_checks": "passed_for_declared_groups_families_and_normalized_exact_content",
            "semantic_authenticity_verified": False, "reviewer_identity_verified": False,
            "target_in_context_semantics_verified": False}


def validate_dataset_files(train_path: str | Path, dev_path: str | Path, sources_path: str | Path,
                           test_path: str | Path | None = None) -> dict[str, Any]:
    """Validate a captured dataset snapshot and return its exact byte identities."""
    return validate_dataset_snapshot(train_path, dev_path, sources_path, test_path)[0]


def _read_jsonl_snapshot(path: str | Path) -> tuple[list[dict[str, Any]], str]:
    """Parse and hash the same byte capture, never an independent later read."""
    path = Path(path)
    with path.open("rb") as handle:
        before = _file_identity(handle)
        raw = handle.read()
        if _file_identity(handle) != before:
            _fail(str(path), "file changed while capturing dataset snapshot")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        _fail(str(path), f"invalid UTF-8: {exc}")
    if not text:
        _fail(str(path), "empty JSONL file")
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    records = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            _fail(f"{path}:{number}", "blank JSONL row")
        try:
            record = json.loads(line, object_pairs_hook=_json_object_pairs,
                                parse_constant=lambda x: _fail("JSON", f"invalid constant {x}"))
        except (ValueError, TypeError) as exc:
            _fail(f"{path}:{number}", str(exc))
        records.append(record)
    return records, hashlib.sha256(raw).hexdigest()


def validate_dataset_snapshot(train_path: str | Path, dev_path: str | Path, sources_path: str | Path,
                              test_path: str | Path | None = None) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    """Return the exact validated in-memory records and their captured byte hashes.

    Training/evaluation must consume these records instead of reloading paths.
    This intentionally retains all rows in memory. Source assets are verified
    against the captured manifest at audit time, not locked against future edits.
    """
    sources_path = Path(sources_path).resolve()
    source_rows, source_hash = _read_jsonl_snapshot(sources_path)
    sources = _validate_source_rows(source_rows, sources_path, verify_assets=True)
    paths = [(split, path) for split, path in (("train", train_path), ("dev", dev_path), ("test", test_path)) if path is not None]
    captured = {split: _read_jsonl_snapshot(path) for split, path in paths}
    records_by_split = {split: value[0] for split, value in captured.items()}

    def records() -> Iterator[dict[str, Any]]:
        for split, path in paths:
            for i, record in enumerate(records_by_split[split], start=1):
                try:
                    validate_record(record)
                except DataValidationError as exc:
                    _fail(f"{path}:{i}", str(exc))
                if record["split"] != split:
                    _fail(f"{path}:{i}", f"all records must declare split={split}")
                yield record

    result = validate_dataset(records(), sources)
    result["file_sha256"] = {split: captured[split][1] for split, path in paths}
    result["sources_manifest_sha256"] = source_hash
    result["source_asset_sha256"] = {sid: source["sha256"] for sid, source in sorted(sources.items())}
    return result, records_by_split


def _field(text: str) -> list[int]:
    raw = text.encode("utf-8")
    return list(str(len(raw)).encode("ascii")) + [ord(":")] + list(raw)


def encode_prompt(messages: list[dict[str, str]], evidence: list[dict[str, str]],
                  roots: list[dict[str, Any]] | None = None, max_seq_len: int = 2048) -> dict[str, torch.Tensor]:
    """Serialize input only. Framing: BOS, EVIDENCE + 4 length fields + END;
    each message role + length field + END; final bare ASSISTANT marker.

    Evidence fields are id, source_id, locator, text. Target text/status/citations,
    language tags, split, provenance and reviewed labels are never injected.
    Caller is responsible for honest source/review declarations at inference.
    """
    _validate_messages(messages)
    _validate_evidence(evidence)
    roots = [] if roots is None else roots
    _validate_roots(roots, messages, allow_pending=False)
    if type(max_seq_len) is not int or max_seq_len <= 0:
        _fail("max_seq_len", "must be a positive integer")
    ids = [BOS_ID]
    rows: list[list[int]] = [[0, 0, 0, 0]]

    def append(tokens: list[int], annotations: list[list[int]] | None = None) -> None:
        ids.extend(tokens)
        rows.extend(annotations if annotations is not None else [[0, 0, 0, 0] for _ in tokens])

    for item in evidence:
        append([EVIDENCE_ID])
        for key in ("id", "source_id", "locator", "text"):
            append(_field(item[key]))
        append([END_ID])
    by_message: dict[int, list[dict[str, Any]]] = {}
    for annotation in roots:
        by_message.setdefault(annotation["message_index"], []).append(annotation)
    for index, message in enumerate(messages):
        raw = message["content"].encode("utf-8")
        append([ROLE_IDS[message["role"]]])
        append(list(str(len(raw)).encode("ascii")) + [ord(":")])
        byte_roots = [[0, 0, 0, 0] for _ in raw]
        for annotation in by_message.get(index, []):
            start = len(message["content"][:annotation["start"]].encode("utf-8"))
            end = len(message["content"][:annotation["end"]].encode("utf-8"))
            root_ids = [ROOT_TO_ID[c] for c in annotation["root"]]
            root_ids += [0] * (4 - len(root_ids))
            for j in range(start, end):
                byte_roots[j] = list(root_ids)
        append(list(raw), byte_roots)
        append([END_ID])
    append([ASSISTANT_ID])
    if len(ids) > max_seq_len:
        _fail("prompt", f"{len(ids)} serialized tokens exceed max_seq_len={max_seq_len}; no silent truncation")
    return {"input_ids": torch.tensor(ids, dtype=torch.long), "roots": torch.tensor(rows, dtype=torch.long)}


def encode_record(record: dict[str, Any], max_seq_len: int) -> dict[str, torch.Tensor]:
    validate_record(record)
    prompt = encode_prompt(record["messages"], record["evidence"], record.get("roots", []), max_seq_len)
    target = list(record["target"]["text"].encode("utf-8"))
    prompt_length = prompt["input_ids"].numel()
    total = prompt_length + len(target)
    if total > max_seq_len:
        _fail(record["id"], f"prompt + target needs {total} tokens, max_seq_len={max_seq_len}; no silent truncation")
    return {"input_ids": torch.cat((prompt["input_ids"], torch.tensor(target, dtype=torch.long))),
            "targets": torch.tensor([IGNORE_INDEX] * (prompt_length - 1) + target + [EOS_ID], dtype=torch.long),
            "roots": torch.cat((prompt["roots"], torch.zeros((len(target), 4), dtype=torch.long)), dim=0)}


def collate_records(encoded: list[dict[str, torch.Tensor]]) -> dict[str, torch.Tensor]:
    if not encoded:
        _fail("batch", "must not be empty")
    lengths = torch.tensor([row["input_ids"].numel() for row in encoded], dtype=torch.long)
    width = int(lengths.max())
    batch = {"input_ids": torch.full((len(encoded), width), END_ID, dtype=torch.long),
             "targets": torch.full((len(encoded), width), IGNORE_INDEX, dtype=torch.long),
             "roots": torch.zeros((len(encoded), width, 4), dtype=torch.long),
             "lengths": lengths}
    for i, row in enumerate(encoded):
        size = int(lengths[i])
        if row["targets"].shape != (size,) or row["roots"].shape != (size, 4):
            _fail("batch", "encoded tensor shapes disagree")
        batch["input_ids"][i, :size] = row["input_ids"]
        batch["targets"][i, :size] = row["targets"]
        batch["roots"][i, :size] = row["roots"]
    return batch
