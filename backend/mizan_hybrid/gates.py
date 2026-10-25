"""Deterministic source-admission and response gates for Mizan.

These checks use explicit metadata, registry membership, adjudicated labels,
and technical output properties. They do not authenticate reviewers, infer
religious correctness, or replace a trained evidence-relation model.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType


class Outcome(StrEnum):
    PASS = "PASS"
    RETRY = "RETRY"
    ABSTAIN = "ABSTAIN"
    HUMAN_REVIEW = "HUMAN_REVIEW"


@dataclass(frozen=True)
class Decision:
    outcome: Outcome
    code: str
    action: str
    detail: str

    @property
    def allowed(self) -> bool:
        return self.outcome is Outcome.PASS

    def metadata(self) -> dict[str, str]:
        return {
            "outcome": self.outcome.value,
            "code": self.code,
            "action": self.action,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    text: str
    provenance: str
    machine_generated: bool = False
    independently_reviewed: bool = False
    reviewer_id: str | None = None
    grades_by_scholar: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "grades_by_scholar", MappingProxyType(dict(self.grades_by_scholar))
        )

    def text_sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


class SourceRegistry:
    """Registry whose IDs cannot silently change content or metadata."""

    def __init__(self) -> None:
        self._records: dict[str, SourceRecord] = {}
        self._hashes: dict[str, str] = {}

    def add(self, record: SourceRecord) -> str:
        if not record.source_id.strip() or not record.provenance.strip():
            raise ValueError("source_id and provenance are required")
        digest = record.text_sha256()
        existing = self._records.get(record.source_id)
        if existing is not None:
            if self._hashes[record.source_id] != digest or existing != record:
                raise ValueError("source ID already exists with different content or metadata")
            return digest
        self._records[record.source_id] = record
        self._hashes[record.source_id] = digest
        return digest

    def get(self, source_id: str) -> SourceRecord | None:
        return self._records.get(source_id)

    def resolve_all(self, source_ids: Iterable[str]) -> list[str]:
        return sorted({source_id for source_id in source_ids if source_id not in self._records})

    @classmethod
    def from_file(cls, path: Path) -> SourceRegistry:
        """Load source records without truncating or rewriting their text."""
        data = json.loads(path.read_text(encoding="utf-8"))
        raw_records = data.get("sources") if isinstance(data, dict) else data
        if not isinstance(raw_records, list):
            raise ValueError("source registry must be a list or an object with a sources list")
        registry = cls()
        for raw in raw_records:
            if not isinstance(raw, dict):
                raise ValueError("every source registry entry must be an object")
            registry.add(
                SourceRecord(
                    source_id=str(raw["source_id"]),
                    text=str(raw["text"]),
                    provenance=str(raw["provenance"]),
                    machine_generated=bool(raw.get("machine_generated", False)),
                    independently_reviewed=bool(raw.get("independently_reviewed", False)),
                    reviewer_id=raw.get("reviewer_id"),
                    grades_by_scholar=raw.get("grades_by_scholar") or {},
                )
            )
        return registry


ARABIC = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]")
LATIN = re.compile(r"[A-Za-z]")
SOURCE_CITATION = re.compile(r"\[(?:SRC|source):([A-Za-z0-9._:-]+)\]")
LABELS = {"supported", "refuted", "insufficient", "conflicting"}
COMPLETE_REASONS = {"eos", "end_turn", "stop", "tool_use"}


def extract_source_citations(text: str) -> list[str]:
    """Extract only explicit registry citations such as ``[SRC:SRC-9]``."""
    return sorted(set(SOURCE_CITATION.findall(text)))


def admit_source(record: SourceRecord, proposed_label: str, max_characters: int) -> Decision:
    """Decide admission without truncating or mutating the source text."""
    if len(record.text) > max_characters:
        return Decision(
            Outcome.ABSTAIN,
            "SOURCE_OVERLENGTH",
            "exclude_with_audit",
            "Source exceeds the declared character limit; original text is unchanged.",
        )
    if not record.provenance.strip():
        return Decision(
            Outcome.HUMAN_REVIEW,
            "PROVENANCE_MISSING",
            "hold_for_review",
            "Source provenance is missing.",
        )
    if proposed_label == "human_reviewed_gold":
        if not record.independently_reviewed or not record.reviewer_id:
            return Decision(
                Outcome.HUMAN_REVIEW,
                "REVIEW_ATTESTATION_MISSING",
                "reject_gold_label",
                "Independent review attestation is required for this label.",
            )
    if record.machine_generated and not record.independently_reviewed and proposed_label == "gold":
        return Decision(
            Outcome.HUMAN_REVIEW,
            "UNREVIEWED_MACHINE_GOLD",
            "reject_gold_label",
            "An unreviewed machine draft cannot become gold.",
        )
    return Decision(
        Outcome.PASS,
        "SOURCE_ADMISSIBLE",
        "admit_with_provenance",
        "Declared admission checks passed; this is not source authentication.",
    )


def validate_grade_claim(
    registry: SourceRegistry, source_id: str, scholar: str, claimed_grade: str
) -> Decision:
    record = registry.get(source_id)
    if record is None:
        return Decision(
            Outcome.ABSTAIN, "UNKNOWN_GRADE_SOURCE", "withhold_claim", "Grade source is unresolved."
        )
    actual = record.grades_by_scholar.get(scholar)
    if actual is None:
        return Decision(
            Outcome.HUMAN_REVIEW,
            "SCHOLAR_GRADE_UNRESOLVED",
            "hold_for_review",
            "No scholar-specific grade exists in the registry.",
        )
    if claimed_grade.strip().casefold() != actual.strip().casefold():
        return Decision(
            Outcome.HUMAN_REVIEW,
            "GRADE_PROVENANCE_CONFLICT",
            "hold_for_review",
            "Claim conflicts with the scholar-specific record; disagreement is preserved.",
        )
    return Decision(
        Outcome.PASS,
        "GRADE_CLAIM_MATCHES_RECORD",
        "allow_attributed_claim",
        "The attributed claim matches the record, not an independent grading endorsement.",
    )


def _decode(response: str | bytes) -> tuple[str | None, Decision | None]:
    if isinstance(response, bytes):
        try:
            return response.decode("utf-8", errors="strict"), None
        except UnicodeDecodeError:
            return None, Decision(
                Outcome.RETRY, "INVALID_UTF8", "regenerate", "Response is not valid UTF-8."
            )
    if not isinstance(response, str):
        return None, Decision(
            Outcome.RETRY,
            "INVALID_RESPONSE_TYPE",
            "regenerate",
            "Response must be text or UTF-8 bytes.",
        )
    return response, None


def gate_response(
    registry: SourceRegistry,
    response: str | bytes,
    *,
    target_language: str,
    finish_reason: str,
    citations: Iterable[str] = (),
    relation_label: str | None = None,
    adjudicated_relation: str | None = None,
    religious_review_required: bool = False,
    independent_reviewer_id: str | None = None,
    allow_tool_only: bool = False,
) -> Decision:
    """Fail closed on declared technical, citation, evidence, and review contracts."""
    text, failure = _decode(response)
    if failure:
        return failure
    assert text is not None
    if not text.strip() and not (allow_tool_only and finish_reason == "tool_use"):
        return Decision(Outcome.RETRY, "EMPTY_RESPONSE", "regenerate", "Response is empty.")
    if "\ufffd" in text:
        return Decision(
            Outcome.RETRY,
            "REPLACEMENT_CHARACTER",
            "regenerate",
            "Response contains U+FFFD.",
        )
    if finish_reason not in COMPLETE_REASONS:
        return Decision(
            Outcome.RETRY,
            "NOT_COMPLETE",
            "regenerate_with_bounded_budget",
            f"Finish reason {finish_reason!r} does not establish completion.",
        )
    arabic = len(ARABIC.findall(text))
    latin = len(LATIN.findall(text))
    if target_language == "en" and (arabic or not latin):
        return Decision(
            Outcome.RETRY, "LANGUAGE_MISMATCH", "regenerate", "English-output contract failed."
        )
    if target_language == "ar" and arabic < 2:
        return Decision(
            Outcome.RETRY, "LANGUAGE_MISMATCH", "regenerate", "Arabic-output contract failed."
        )
    if target_language not in {"any", "en", "ar"}:
        raise ValueError("target_language must be any, en, or ar")
    all_citations = set(citations) | set(extract_source_citations(text))
    missing = registry.resolve_all(all_citations)
    if missing:
        return Decision(
            Outcome.ABSTAIN,
            "UNRESOLVED_CITATION",
            "withhold_response",
            "Unresolved source IDs: " + ", ".join(missing),
        )
    if adjudicated_relation is not None:
        if adjudicated_relation not in LABELS:
            raise ValueError("invalid adjudicated relation")
        normalized = (relation_label or "").strip().casefold()
        if normalized not in LABELS:
            return Decision(
                Outcome.ABSTAIN,
                "RELATION_LABEL_MISSING",
                "withhold_response",
                "No valid four-state label was supplied.",
            )
        if normalized != adjudicated_relation:
            return Decision(
                Outcome.ABSTAIN,
                "RELATION_CONTRADICTS_ADJUDICATION",
                "withhold_response",
                "Generated label conflicts with the independently adjudicated fixture label.",
            )
    if religious_review_required and not independent_reviewer_id:
        return Decision(
            Outcome.HUMAN_REVIEW,
            "RELIGIOUS_REVIEW_REQUIRED",
            "hold_for_review",
            "Declared religious review requirement is unmet.",
        )
    return Decision(
        Outcome.PASS,
        "RESPONSE_GATES_PASSED",
        "return_response",
        "Declared gates passed; this is not universal factual or religious certification.",
    )


class AuditLog:
    """Hash-linked JSONL decisions; prompts, secrets, and source text are excluded."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def append(self, case_id: str, decision: Decision) -> str:
        with self._lock:
            previous = "0" * 64
            if self.path.exists():
                lines = [line for line in self.path.read_text(encoding="utf-8").splitlines() if line]
                if lines:
                    previous = json.loads(lines[-1])["event_sha256"]
            event = {"case_id": case_id, "previous_sha256": previous, **asdict(decision)}
            event["outcome"] = decision.outcome.value
            canonical = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            event["event_sha256"] = digest
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
            return digest
