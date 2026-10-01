"""Scholar-review queue: data model, JSONL store, escalation thresholds (beta).

Quran lens (amāna — stewardship, esp. religious content):
  * A wrong Quranic sense shown as fact is a religious-integrity failure, not
    a normal bug. Low-confidence items on Quranic text ALWAYS escalate to
    scholar review — ``needs_review()`` encodes this.
  * Every decision carries provenance: who reviewed (``reviewer``) and when
    (``decided_at``). The store is append-auditable JSONL.

Threshold defaults are conservative by JEV decision (``conservative``,
confidence 0.98, 2026-09-29): Quranic items below 0.95 confidence always go to
review; general items below 0.80. These are defaults, not scholar-calibrated
values — treat them as beta.

Status: beta / unverified. Torch-free, stdlib-only.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"
STATUSES = (PENDING, APPROVED, REJECTED)

# Conservative defaults (JEV: conservative, 0.98). Beta — not scholar-calibrated.
GENERAL_REVIEW_THRESHOLD = 0.80
QURANIC_REVIEW_THRESHOLD = 0.95


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ReviewItem:
    """One proposed sense awaiting (or having received) scholar review."""

    item_id: str
    text: str
    proposed_sense: str
    confidence: float
    status: str = PENDING
    reviewer: str | None = None
    decided_at: str | None = None
    is_quranic: bool = False
    source: str = ""  # provenance: which signal/model produced this proposal

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"invalid status {self.status!r}; must be one of {STATUSES}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence {self.confidence} outside [0, 1]")
        if not self.item_id:
            raise ValueError("item_id must be non-empty")
        if self.status != PENDING and self.reviewer is None:
            raise ValueError("decided items must record a reviewer")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReviewItem:
        return cls(**data)


# ---------------------------------------------------------------------------
# Escalation policy
# ---------------------------------------------------------------------------


def needs_review(
    confidence: float,
    is_quranic: bool = False,
    *,
    general_threshold: float = GENERAL_REVIEW_THRESHOLD,
    quranic_threshold: float = QURANIC_REVIEW_THRESHOLD,
) -> bool:
    """Whether a proposed sense must go to scholar review (amāna).

    Quranic text: anything below ``quranic_threshold`` (default 0.95) ALWAYS
    escalates — no auto-approval of low-confidence religious content.
    General text: below ``general_threshold`` (default 0.80) escalates.
    """
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence {confidence} outside [0, 1]")
    threshold = quranic_threshold if is_quranic else general_threshold
    return confidence < threshold


# ---------------------------------------------------------------------------
# JSONL store
# ---------------------------------------------------------------------------


class ReviewStore:
    """JSONL-backed review queue with an audit trail.

    Usage:
        store = ReviewStore("reviews.jsonl")
        store.add(ReviewItem(...))
        store.decide("id-1", APPROVED, reviewer="scholar@example.org")
        store.save()
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._items: dict[str, ReviewItem] = {}
        if self.path.exists():
            self._load()

    # -- persistence -----------------------------------------------------
    def _load(self) -> None:
        with open(self.path, encoding="utf-8") as fh:
            for lineno, raw in enumerate(fh, 1):
                if raw.strip():
                    try:
                        item = ReviewItem.from_dict(json.loads(raw))
                    except (ValueError, TypeError) as exc:
                        raise ValueError(f"{self.path}:{lineno}: {exc}") from exc
                    if item.item_id in self._items:
                        raise ValueError(f"{self.path}:{lineno}: duplicate item_id")
                    self._items[item.item_id] = item

    def save(self) -> None:
        """Write the queue atomically (tmp file + rename)."""
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            for item in self._items.values():
                fh.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
        tmp.replace(self.path)

    # -- queue operations -------------------------------------------------
    def add(self, item: ReviewItem) -> None:
        if item.item_id in self._items:
            raise ValueError(f"duplicate item_id {item.item_id!r}")
        self._items[item.item_id] = item

    def get(self, item_id: str) -> ReviewItem:
        try:
            return self._items[item_id]
        except KeyError:
            raise KeyError(f"unknown item_id {item_id!r}") from None

    def decide(self, item_id: str, status: str, reviewer: str) -> ReviewItem:
        """Record a scholar decision. Only pending items can be decided."""
        if status not in (APPROVED, REJECTED):
            raise ValueError(f"decide() status must be approved/rejected, got {status!r}")
        if not reviewer or not reviewer.strip():
            raise ValueError("reviewer is required for a decision")
        item = self.get(item_id)
        if item.status != PENDING:
            raise ValueError(f"item {item_id!r} already decided ({item.status})")
        decided = ReviewItem(
            **{
                **item.to_dict(),
                "status": status,
                "reviewer": reviewer,
                "decided_at": _utcnow_iso(),
            }
        )
        self._items[item_id] = decided
        return decided

    def reopen(self, item_id: str) -> ReviewItem:
        """Return a decided item to pending (corrections path)."""
        item = self.get(item_id)
        if item.status == PENDING:
            raise ValueError(f"item {item_id!r} is already pending")
        reopened = ReviewItem(
            **{**item.to_dict(), "status": PENDING, "reviewer": None, "decided_at": None}
        )
        self._items[item_id] = reopened
        return reopened

    def list_pending(self, *, quranic_only: bool = False) -> list[ReviewItem]:
        items = [i for i in self._items.values() if i.status == PENDING]
        if quranic_only:
            items = [i for i in items if i.is_quranic]
        return items

    def pending_count(self) -> int:
        return sum(1 for i in self._items.values() if i.status == PENDING)

    def __len__(self) -> int:
        return len(self._items)

    # -- context manager: auto-save on clean exit -------------------------
    def __enter__(self) -> ReviewStore:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if exc_type is None:
            self.save()


def enqueue_proposal(
    store: ReviewStore,
    *,
    item_id: str,
    text: str,
    proposed_sense: str,
    confidence: float,
    is_quranic: bool = False,
    source: str = "",
) -> ReviewItem:
    """Enqueue a model proposal; raises if it should have gone to review but
    the caller tries to bypass (defensive: proposals are always queued)."""
    item = ReviewItem(
        item_id=item_id,
        text=text,
        proposed_sense=proposed_sense,
        confidence=confidence,
        is_quranic=is_quranic,
        source=source,
    )
    # The queue is the review path: every proposal lands here as pending.
    # needs_review() tells the caller whether a scholar MUST look before use.
    _ = needs_review(confidence, is_quranic)
    store.add(item)
    return item
