"""Scholar-review pipeline — Phase 0 credibility foundation (beta).

Quran-lens gate (amāna): no low-confidence sense output on Quranic text may
reach a user without scholar review. This package is the queue that enforces
that: items, conservative escalation thresholds, and a JSONL store with an
audit trail (reviewer + decided_at on every decision).

Status: beta / unverified — thresholds are conservative defaults, not
scholar-calibrated. Torch-free, stdlib-only.
"""

__all__ = []
