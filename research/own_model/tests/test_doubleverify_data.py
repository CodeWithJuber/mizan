"""Adversarial mechanical fixtures only; no language corpus or accuracy benchmark."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest
import torch
from jsonschema import Draft202012Validator

import mizan_reply.data as data


def record(rid="a", split="train", sid="s1", text="mechanical input A"):
    return {"schema_version": "mizan.reply.v1", "id": rid, "split": split,
            "group_id": "group-" + rid, "language": "en", "task": "dialogue",
            "messages": [{"role": "user", "content": text}], "evidence": [],
            "target": {"text": "mechanical response A", "citations": [], "answer_status": "answer"},
            "provenance": {"origin": "human_original", "source_ids": [sid],
                           "rights": "Mechanical test only", "author_ids": ["author"],
                           "reviewer_ids": ["reviewer"], "review_status": "accepted",
                           "creation_method": "human"}}


def source(sid="s1"):
    return {"source_id": sid, "source_family": "family-" + sid, "kind": "other",
            "title": "Mechanical fixture " + sid, "edition": "test only",
            "locator": "row:" + sid, "uri": "urn:mechanical:" + sid,
            "rights": "Mechanical fixture only", "sha256": data.sha256_text("mechanical asset"),
            "local_path": "asset.txt"}


def annotation(start, end):
    return {"message_index": 0, "start": start, "end": end, "root": "كتب",
            "source_id": "s1", "review_status": "accepted"}


@pytest.mark.parametrize("method", ["manual_transcription", "automated_transcription", "machine_generation"])
def test_human_origin_cannot_conflict_with_creation_method(method):
    r = record()
    r["provenance"]["creation_method"] = method
    with pytest.raises(data.DataValidationError, match="human_original"):
        data.validate_record(r, allow_pending=True)


@pytest.mark.parametrize("method", ["human", "manual_transcription", "automated_transcription"])
def test_machine_origin_cannot_claim_human_or_transcription(method):
    r = record()
    r["provenance"].update(origin="machine_draft", creation_method=method)
    with pytest.raises(data.DataValidationError, match="machine_draft"):
        data.validate_record(r, allow_pending=True)


@pytest.mark.parametrize("text,start,end", [
    ("كتب", 0, 1), ("كتب🙂", 0, 4), ("كتب!س", 0, 5), ("كَتب", 1, 4),
    ("كَتب", 0, 1), ("كَتب", 0, 3), ("ك1تب", 0, 4), ("ك\u200btب", 0, 4),
])
def test_roots_reject_partial_words_and_nonword_span_content(text, start, end):
    r = record(text=text)
    r["roots"] = [annotation(start, end)]
    with pytest.raises(data.DataValidationError, match="Arabic word"):
        data.validate_record(r)


def test_astral_codepoints_and_combining_marks_map_to_exact_utf8_bytes():
    r = record(text="🙂!كَتب،🙂")
    r["roots"] = [annotation(2, 6)]
    encoded = data.encode_record(r, 300)
    active = encoded["roots"].any(dim=-1)
    assert bytes(encoded["input_ids"][active].tolist()) == "كَتب".encode("utf-8")
    assert active.sum().item() == 8
    bad = deepcopy(r)
    bad["roots"][0].update(start=3, end=7)  # JavaScript UTF-16 offsets are wrong here.
    with pytest.raises(data.DataValidationError, match="Arabic word"):
        data.validate_record(bad)


@pytest.mark.parametrize("where", ["message", "target", "evidence", "source"])
def test_unpaired_surrogates_fail_as_data_errors(where):
    r = record()
    s = source()
    if where == "message":
        r["messages"][0]["content"] = "invalid \ud800"
    elif where == "target":
        r["target"]["text"] = "invalid \udfff"
    elif where == "evidence":
        r["evidence"] = [{"id": "e", "source_id": "s1", "locator": "row:s1",
                           "text": "invalid \ud800", "sha256": "0" * 64}]
    else:
        s["title"] = "invalid \ud800"
    with pytest.raises(data.DataValidationError, match="invalid Unicode"):
        data.validate_source(s) if where == "source" else data.validate_record(r)


def test_train_target_pair_cannot_reappear_in_heldout_history_either_order():
    a, b = record(), record("b", "dev", "s2", "mechanical followup")
    b["messages"] = a["messages"] + [{"role": "assistant", "content": " MECHANICAL   RESPONSE A "}] + b["messages"]
    for rows in ([a, b], [b, a]):
        with pytest.raises(data.DataValidationError, match="user/assistant pair"):
            data.validate_dataset(rows)


def test_shared_historical_pair_is_caught_inside_different_conversations():
    a, b = record(), record("b", "dev", "s2", "mechanical input B")
    shared = [{"role": "user", "content": "common mechanical question"},
              {"role": "assistant", "content": "common mechanical reply"}]
    for r in (a, b):
        r["messages"] = [r["messages"][0], {"role": "assistant", "content": r["id"]}] + shared + [{"role": "user", "content": r["id"] + " finish"}]
    with pytest.raises(data.DataValidationError, match="user/assistant pair"):
        data.validate_dataset([a, b])


def test_common_answers_do_not_alone_count_as_leakage():
    a, b = record(), record("b", "dev", "s2", "different mechanical request")
    a["target"]["text"] = b["target"]["text"] = "yes"
    assert data.validate_dataset([a, b])["records"] == 2


def test_same_asset_locator_cannot_hide_behind_different_ids_or_families():
    a, b = record(), record("b", "dev", "s2", "mechanical input B")
    sources = {"s1": source(), "s2": source("s2")}
    sources["s2"]["locator"] = sources["s1"]["locator"]
    with pytest.raises(data.DataValidationError, match="source asset/locator"):
        data.validate_dataset([a, b], sources)
    sources["s2"]["locator"] = "different exact passage"
    assert data.validate_dataset([a, b], sources)["records"] == 2


@pytest.mark.parametrize("kind", ["hadith", "tafsir"])
def test_canonical_references_cannot_hide_behind_renamed_families(kind):
    a, b = record(), record("b", "dev", "s2", "mechanical input B")
    sources = {"s1": source(), "s2": source("s2")}
    for index, s in enumerate(sources.values()):
        s["kind"] = kind
        if kind == "hadith":
            s[kind] = {"collection": "MECHANICAL COLLECTION" if index else "mechanical collection", "book": "1", "number": "2",
                       "gradings": [{"grade": "test", "grader": "test", "reference": "test"}], "reviewer_qualification": "test"}
        else:
            s[kind] = {"author": "MECHANICAL AUTHOR" if index else "mechanical author", "work": "test", "passage": "2", "reviewer_qualification": "test"}
    with pytest.raises(data.DataValidationError, match=kind + " reference"):
        data.validate_dataset([a, b], sources)


def test_target_and_evidence_are_not_semantically_certified():
    # Exact quotation can legitimately equal target text. Bytes cannot establish
    # whether input text is honest evidence or an answer hidden by its collector.
    r = record()
    r["evidence"] = [{"id": "e", "source_id": "s1", "locator": "row:s1",
                       "text": r["target"]["text"], "sha256": data.sha256_text(r["target"]["text"])}]
    summary = data.validate_dataset([r])
    assert summary["target_in_context_semantics_verified"] is False
    assert summary["semantic_authenticity_verified"] is False


@pytest.mark.parametrize("missing", ["schema_version", "id", "split", "group_id", "language", "task", "messages", "evidence", "target", "provenance"])
def test_each_required_top_level_field_fails_clearly(missing):
    r = record()
    del r[missing]
    with pytest.raises(data.DataValidationError, match="missing fields"):
        data.validate_record(r)


@pytest.mark.parametrize("uri", ["https://", "https://host name/path", "https://host:broken/", "https://user:secret@host/", "urn:", "urn:only-one-part"])
def test_empty_or_malformed_source_identifiers_are_rejected(uri):
    s = source()
    s["uri"] = uri
    with pytest.raises(data.DataValidationError, match="source.uri"):
        data.validate_source(s)


def write_snapshot_fixture(tmp_path):
    (tmp_path / "asset.txt").write_text("mechanical asset")
    rows = {"train": [record()], "dev": [record("b", "dev", "s2", "mechanical input B")],
            "sources": [source(), source("s2")]}
    paths = {}
    for key, values in rows.items():
        paths[key] = tmp_path / (key + ".jsonl")
        paths[key].write_text("".join(json.dumps(value) + "\n" for value in values))
    return paths


def test_snapshot_hashes_and_records_use_same_capture_when_disk_changes(tmp_path):
    paths = write_snapshot_fixture(tmp_path)
    before = paths["train"].read_bytes()
    original = data._read_jsonl_snapshot

    def capture_then_change(path):
        captured = original(path)
        if Path(path) == paths["train"]:
            paths["train"].write_text("a later invalid replacement\n")
        return captured

    with patch.object(data, "_read_jsonl_snapshot", side_effect=capture_then_change):
        summary, captured = data.validate_dataset_snapshot(paths["train"], paths["dev"], paths["sources"])
    assert summary["file_sha256"]["train"] == hashlib.sha256(before).hexdigest()
    assert captured["train"][0] == record()
    assert summary["file_sha256"]["train"] != data.file_sha256(paths["train"])


def test_snapshot_rejects_invalid_utf8_and_reports_path(tmp_path):
    paths = write_snapshot_fixture(tmp_path)
    paths["train"].write_bytes(b"\xff\n")
    with pytest.raises(data.DataValidationError, match="train.jsonl.*invalid UTF-8"):
        data.validate_dataset_snapshot(paths["train"], paths["dev"], paths["sources"])


def test_long_unicode_rejected_without_truncation_and_exact_limit_accepted():
    r = record(text="🙂كَتب" * 64)
    r["target"]["text"] = "🙂" * 10
    prompt = data.encode_prompt(r["messages"], [], max_seq_len=4000)
    required = len(prompt["input_ids"]) + len(r["target"]["text"].encode())
    result = data.encode_record(r, required)
    assert len(result["input_ids"]) == required
    assert result["targets"][-1] == data.EOS_ID
    with pytest.raises(data.DataValidationError, match="no silent truncation"):
        data.encode_record(r, required - 1)


def validator(name):
    path = Path(__file__).parents[1] / "schemas" / name
    schema = json.loads(path.read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@pytest.mark.parametrize("field,value", [
    ("id", "trailing-newline\n"), ("group_id", "trailing-newline\n"),
    ("language", "en\n"), ("id", "__REPLACE_ID__"),
])
def test_schema_and_runtime_agree_on_identifier_boundaries(field, value):
    r = record()
    r[field] = value
    assert not validator("reply-record.schema.json").is_valid(r)
    with pytest.raises(data.DataValidationError):
        data.validate_record(r)


@pytest.mark.parametrize("content", ["", " \t\r\n", "NUL\x00byte", "__REPLACE_TEXT__"])
def test_schema_and_runtime_agree_on_bad_text(content):
    r = record(text=content)
    assert not validator("reply-record.schema.json").is_valid(r)
    with pytest.raises(data.DataValidationError):
        data.validate_record(r)


@pytest.mark.parametrize("case", ["reviewers", "human_method", "clarification", "abstention", "grounded"])
def test_schema_and_runtime_agree_on_conditional_record_constraints(case):
    r = record()
    if case == "reviewers":
        r["provenance"]["reviewer_ids"] = []
    elif case == "human_method":
        r["provenance"]["creation_method"] = "automated_transcription"
    elif case in {"clarification", "abstention"}:
        r["task"] = case
    else:
        r["task"] = "grounded_qa"
    assert not validator("reply-record.schema.json").is_valid(r)
    with pytest.raises(data.DataValidationError):
        data.validate_record(r)


def test_source_schema_rejects_metadata_for_wrong_source_kind():
    s = source()
    s["quran"] = {"surah": 1, "ayah_start": 1, "ayah_end": 1, "text_edition": "mechanical metadata only"}
    assert not validator("source-item.schema.json").is_valid(s)
    with pytest.raises(data.DataValidationError, match="metadata must match"):
        data.validate_source(s)


@pytest.mark.parametrize("field,value", [
    ("sha256", "0" * 64 + "\n"), ("local_path", "../escape"),
    ("local_path", "/absolute"), ("uri", "https://"), ("uri", "urn:"),
    ("title", " \t\r\n"), ("notes", "NUL\x00byte"),
])
def test_source_schema_and_runtime_reject_bad_structural_fields(field, value):
    s = source()
    s[field] = value
    assert not validator("source-item.schema.json").is_valid(s)
    with pytest.raises(data.DataValidationError):
        data.validate_source(s)


def test_schemas_accept_valid_unicode_records_and_sources_but_runtime_remains_mandatory():
    r = record(text="🙂!كَتب،🙂")
    r["roots"] = [annotation(2, 6)]
    assert validator("reply-record.schema.json").is_valid(r)
    assert validator("source-item.schema.json").is_valid(source())
    data.validate_record(r)
    # JSON Schema has no original input string lookup for runtime span offsets.
    r["roots"][0]["end"] = 999
    assert validator("reply-record.schema.json").is_valid(r)
    with pytest.raises(data.DataValidationError, match="span"):
        data.validate_record(r)


# ── Licensed teacher output (owner's decision of 30 Oct 2026, docs/consent.md) ──


def teacher_record(rid="t", sid="s1"):
    r = record(rid=rid, sid=sid)
    r["provenance"] = {"origin": "licensed_teacher", "source_ids": [sid],
                       "rights": "DeepSeek terms allow training on output",
                       "reviewer_ids": ["reviewer"], "review_status": "accepted",
                       "creation_method": "machine_generation",
                       "teacher": {"provider": "openrouter", "model": "deepseek/deepseek-chat",
                                   "licence": "deepseek-terms-of-use"},
                       "verification": {"by": "tathabbut", "passed": True}}
    return r


def test_verified_licence_clean_teacher_output_is_a_training_target():
    r = teacher_record()
    assert validator("reply-record.schema.json").is_valid(r)
    assert data.validate_record(r) is r


@pytest.mark.parametrize("change", [
    {"teacher": {"provider": "anthropic", "model": "any", "licence": "mit"}},
    {"teacher": {"provider": "OpenAI", "model": "any", "licence": "mit"}},
    {"teacher": {"provider": "openrouter", "model": "deepseek/x", "licence": "proprietary"}},
    {"verification": {"by": "tathabbut", "passed": False}},
    {"verification": {"by": "the model itself", "passed": True}},
    {"verification": None},
    {"teacher": None},
    {"creation_method": "human"},
])
def test_schema_and_runtime_refuse_an_unlicensed_or_unverified_teacher(change):
    r = teacher_record()
    for key, value in change.items():
        if value is None:
            del r["provenance"][key]
        else:
            r["provenance"][key] = value
    assert not validator("reply-record.schema.json").is_valid(r)
    with pytest.raises(data.DataValidationError):
        data.validate_record(r)


@pytest.mark.parametrize("model", ["anthropic/claude-opus-5-5", "openai/gpt-oss-120b", "gpt-5", "Claude-Fable"])
def test_a_router_cannot_launder_anthropic_or_openai_output(model):
    r = teacher_record()
    r["provenance"]["teacher"]["model"] = model
    with pytest.raises(data.DataValidationError, match="lookup only"):
        data.validate_record(r)


def test_teacher_fields_belong_to_teacher_records_only():
    r = record()
    r["provenance"]["verification"] = {"by": "tathabbut", "passed": True}
    assert not validator("reply-record.schema.json").is_valid(r)
    with pytest.raises(data.DataValidationError, match="licensed_teacher"):
        data.validate_record(r)


@pytest.mark.parametrize("kind", ["quran", "hadith"])
def test_teacher_output_over_scripture_is_never_a_target(kind):
    s = source()
    s["kind"] = kind
    if kind == "quran":
        s["quran"] = {"surah": 1, "ayah_start": 1, "ayah_end": 1, "text_edition": "mechanical"}
    else:
        s["hadith"] = {"collection": "c", "book": "b", "number": "1", "reviewer_qualification": "q",
                       "gradings": [{"grade": "sahih", "grader": "g", "reference": "r"}]}
    with pytest.raises(data.DataValidationError, match="never a training target"):
        data.validate_dataset([teacher_record()], {"s1": s})
    # A human-written record over the same source stays allowed.
    assert data.validate_dataset([record()], {"s1": s})["records"] == 1
