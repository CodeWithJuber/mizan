"""Regression tests for deterministic Mizan source and response contracts."""

import hashlib
import json

import pytest

from mizan_hybrid.gates import (
    AuditLog,
    Decision,
    Outcome,
    SourceRecord,
    SourceRegistry,
    admit_source,
    extract_source_citations,
    gate_response,
    validate_grade_claim,
)


@pytest.fixture
def registry():
    result = SourceRegistry()
    result.add(SourceRecord("SRC-1", "The team met on Tuesday.", "neutral-test-registry"))
    return result


def test_unreviewed_machine_draft_cannot_become_gold():
    draft = SourceRecord("D-1", "draft", "generator-v1", machine_generated=True)
    decision = admit_source(draft, "human_reviewed_gold", 100)
    assert decision.outcome is Outcome.HUMAN_REVIEW
    assert decision.action == "reject_gold_label"
    assert admit_source(draft, "draft", 100).outcome is Outcome.PASS


def test_overlength_excluded_without_source_mutation():
    record = SourceRecord("LONG", "123456789", "publisher-file")
    before = record.text_sha256()
    decision = admit_source(record, "draft", 4)
    assert (decision.outcome, decision.action) == (Outcome.ABSTAIN, "exclude_with_audit")
    assert record.text == "123456789"
    assert record.text_sha256() == before


def test_missing_provenance_requires_review():
    record = SourceRecord("X", "text", "")
    assert admit_source(record, "draft", 100).code == "PROVENANCE_MISSING"


def test_scholar_disagreement_preserved(registry):
    record = SourceRecord(
        "H-1",
        "Publisher text",
        "publisher-snapshot",
        grades_by_scholar={"Scholar A": "hasan", "Scholar B": "daif"},
    )
    registry.add(record)
    assert dict(registry.get("H-1").grades_by_scholar) == {
        "Scholar A": "hasan",
        "Scholar B": "daif",
    }
    assert validate_grade_claim(registry, "H-1", "Scholar A", "hasan").allowed
    conflict = validate_grade_claim(registry, "H-1", "Scholar A", "sahih")
    assert (conflict.outcome, conflict.code) == (Outcome.HUMAN_REVIEW, "GRADE_PROVENANCE_CONFLICT")
    with pytest.raises(TypeError):
        registry.get("H-1").grades_by_scholar["Scholar A"] = "sahih"


def test_registry_rejects_silent_id_remapping(registry):
    with pytest.raises(ValueError, match="different content"):
        registry.add(SourceRecord("SRC-1", "Changed text", "neutral-test-registry"))


def test_registry_loads_json_and_preserves_hash(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps({"sources": [{"source_id": "S", "text": "text", "provenance": "test"}]}),
        encoding="utf-8",
    )
    registry = SourceRegistry.from_file(path)
    assert registry.get("S").text_sha256() == hashlib.sha256(b"text").hexdigest()


def test_unknown_citation_abstains(registry):
    decision = gate_response(
        registry,
        "Unverifiable [SRC:SRC-9].",
        target_language="en",
        finish_reason="end_turn",
    )
    assert (decision.outcome, decision.code) == (Outcome.ABSTAIN, "UNRESOLVED_CITATION")
    assert extract_source_citations("A [SRC:SRC-9] B [source:SRC-1]") == ["SRC-1", "SRC-9"]


def test_adjudicated_relation_mismatch_abstains(registry):
    decision = gate_response(
        registry,
        "supported",
        target_language="en",
        finish_reason="end_turn",
        relation_label="supported",
        adjudicated_relation="refuted",
    )
    assert (decision.outcome, decision.code) == (
        Outcome.ABSTAIN,
        "RELATION_CONTRADICTS_ADJUDICATION",
    )


def test_missing_relation_label_abstains(registry):
    decision = gate_response(
        registry,
        "I think so.",
        target_language="en",
        finish_reason="end_turn",
        adjudicated_relation="insufficient",
    )
    assert decision.code == "RELATION_LABEL_MISSING"


@pytest.mark.parametrize(
    ("response", "language", "code"),
    [
        (b"\xff", "en", "INVALID_UTF8"),
        ("", "en", "EMPTY_RESPONSE"),
        ("bad\ufffdtext", "en", "REPLACEMENT_CHARACTER"),
        ("مرحبا", "en", "LANGUAGE_MISMATCH"),
        ("hello", "ar", "LANGUAGE_MISMATCH"),
    ],
)
def test_technical_failures_retry(registry, response, language, code):
    decision = gate_response(
        registry, response, target_language=language, finish_reason="end_turn"
    )
    assert (decision.outcome, decision.code) == (Outcome.RETRY, code)


def test_length_cap_retries(registry):
    decision = gate_response(
        registry, "Incomplete", target_language="en", finish_reason="max_tokens"
    )
    assert (decision.outcome, decision.code) == (Outcome.RETRY, "NOT_COMPLETE")


def test_valid_cited_response_passes(registry):
    decision = gate_response(
        registry,
        "The team met on Tuesday [SRC:SRC-1].",
        target_language="en",
        finish_reason="end_turn",
    )
    assert decision.outcome is Outcome.PASS


def test_tool_only_response_can_pass(registry):
    decision = gate_response(
        registry, "", target_language="any", finish_reason="tool_use", allow_tool_only=True
    )
    assert decision.allowed


def test_religious_review_is_explicit(registry):
    held = gate_response(
        registry,
        "A claim.",
        target_language="en",
        finish_reason="end_turn",
        religious_review_required=True,
    )
    assert held.outcome is Outcome.HUMAN_REVIEW
    passed = gate_response(
        registry,
        "A claim.",
        target_language="en",
        finish_reason="end_turn",
        religious_review_required=True,
        independent_reviewer_id="attestation-1",
    )
    assert passed.allowed


def test_audit_log_hash_chain_excludes_response(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)
    first = Decision(Outcome.PASS, "OK", "return_response", "safe")
    second = Decision(Outcome.ABSTAIN, "UNKNOWN", "withhold_response", "safe")
    first_hash = log.append("case-1", first)
    second_hash = log.append("case-2", second)
    events = [json.loads(line) for line in path.read_text().splitlines()]
    assert events[0]["event_sha256"] == first_hash
    assert events[1]["previous_sha256"] == first_hash
    assert events[1]["event_sha256"] == second_hash
    assert "response" not in events[0]
    for event in events:
        canonical = {
            key: value for key, value in event.items() if key != "event_sha256"
        }
        encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        assert hashlib.sha256(encoded.encode()).hexdigest() == event["event_sha256"]
