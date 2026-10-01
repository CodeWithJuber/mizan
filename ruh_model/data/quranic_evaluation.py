"""Strict Quran quotation, citation and annotation evaluation.

These mechanical scores measure text integrity, not tafsir correctness or the
ability to issue religious advice. Expected text must come from the pinned data.
"""

from __future__ import annotations

import json
import unicodedata


def _marks(text: str) -> list[str]:
    return [char for char in text if unicodedata.category(char).startswith("M")]


def quotation_score(expected: str, generated: str) -> dict:
    """Exact codepoint comparison includes diacritics, hamza and negation."""
    expected_words, generated_words = expected.split(), generated.split()
    matching = sum(a == b for a, b in zip(expected_words, generated_words, strict=False))
    negations = [word for word in expected_words if _plain(word) in {"لا", "لم", "لن", "ليس", "ما"}]
    actual_negations = [
        word for word in generated_words if _plain(word) in {"لا", "لم", "لن", "ليس", "ما"}
    ]
    return {
        "exact_match": expected == generated,
        "word_position_accuracy": matching / max(len(expected_words), len(generated_words), 1),
        "diacritic_sequence_exact": _marks(expected) == _marks(generated),
        "negation_tokens_exact": negations == actual_negations,
        "empty": not generated.strip(),
        "invalid_utf8": "\ufffd" in generated,
        "expected_characters": len(expected),
        "generated_characters": len(generated),
    }


def _plain(text: str) -> str:
    return "".join(char for char in text if not unicodedata.category(char).startswith("M"))


def score_record(row: dict) -> dict:
    task, generated, expected = row["task"], row["generated"], row["expected"]
    result = dict(verse_id=row["verse_id"], task=task, **quotation_score(expected, generated))
    if task in {"grounded_translation", "grounded_tafsir"}:
        attribution = row.get("attribution")
        if not attribution:
            raise ValueError("Grounded evaluation requires source attribution")
        result["correct_citation"] = (
            f"Quran {row['verse_id']};" in generated and attribution in generated
        )
    if task == "morphology":
        try:
            expected_obj, generated_obj = json.loads(expected), json.loads(generated)
            result["valid_json"] = isinstance(generated_obj, dict)
            result["annotation_exact"] = expected_obj == generated_obj
        except (ValueError, TypeError):
            result["valid_json"], result["annotation_exact"] = False, False
    return result


def summarize_scores(rows: list[dict]) -> dict:
    if not rows:
        raise ValueError("Evaluation needs held-out predictions")
    scores = [score_record(row) for row in rows]
    keys = {key for score in scores for key, value in score.items() if type(value) is bool}
    metrics = {
        key + "_rate": sum(bool(score[key]) for score in scores if key in score)
        / sum(key in score for score in scores)
        for key in sorted(keys)
    }
    return {
        "samples": len(scores),
        "metrics": metrics,
        "scores": scores,
        "promotion": {
            "approved": False,
            "reason": "Exact quotation checks require independent semantic and qualified-source review before promotion.",
        },
    }
