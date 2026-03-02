"""Tests for the RuhLearner interaction capture system."""

import pytest

from learner.ruh_learner import RuhLearner


class TestCapture:
    """Test capturing LLM interactions."""

    async def test_capture_stores_interaction(self, temp_db: str) -> None:
        """capture() should persist an interaction that shows up in get_recent."""
        learner = RuhLearner(db_path=temp_db)
        await learner.initialize()

        await learner.capture(
            prompt="What is Tawbah?",
            response="Tawbah means repentance.",
            provider="anthropic",
            model="claude-sonnet-4-20250514",
        )

        recent = await learner.get_recent(limit=10)
        assert len(recent) == 1
        assert recent[0]["prompt"] == "What is Tawbah?"
        assert recent[0]["response"] == "Tawbah means repentance."
        assert recent[0]["provider"] == "anthropic"
        assert recent[0]["model"] == "claude-sonnet-4-20250514"

    async def test_capture_with_metadata(self, temp_db: str) -> None:
        """capture() should accept optional metadata dict."""
        learner = RuhLearner(db_path=temp_db)
        await learner.initialize()

        await learner.capture(
            prompt="test prompt",
            response="test response",
            provider="openrouter",
            model="gpt-4o",
            metadata={"tokens": 150, "latency_ms": 320},
        )

        recent = await learner.get_recent(limit=1)
        assert len(recent) == 1

    async def test_capture_multiple_interactions(self, temp_db: str) -> None:
        """Multiple captures should all be retrievable."""
        learner = RuhLearner(db_path=temp_db)
        await learner.initialize()

        for idx in range(5):
            await learner.capture(
                prompt=f"question {idx}",
                response=f"answer {idx}",
                provider="anthropic",
                model="claude",
            )

        recent = await learner.get_recent(limit=10)
        assert len(recent) == 5

    async def test_get_recent_respects_limit(self, temp_db: str) -> None:
        """get_recent should return at most 'limit' items."""
        learner = RuhLearner(db_path=temp_db)
        await learner.initialize()

        for idx in range(10):
            await learner.capture(
                prompt=f"q{idx}",
                response=f"a{idx}",
                provider="test",
                model="test",
            )

        recent = await learner.get_recent(limit=3)
        assert len(recent) == 3

    async def test_get_recent_returns_newest_first(self, temp_db: str) -> None:
        """get_recent should return most recent interactions first."""
        learner = RuhLearner(db_path=temp_db)
        await learner.initialize()

        await learner.capture("first", "r1", "p", "m")
        await learner.capture("second", "r2", "p", "m")
        await learner.capture("third", "r3", "p", "m")

        recent = await learner.get_recent(limit=3)
        assert recent[0]["prompt"] == "third"
        assert recent[2]["prompt"] == "first"


class TestGetStats:
    """Test interaction statistics."""

    async def test_stats_empty_database(self, temp_db: str) -> None:
        """Stats on an empty database should show zero totals."""
        learner = RuhLearner(db_path=temp_db)
        await learner.initialize()

        stats = await learner.get_stats()
        assert stats["total_interactions"] == 0
        assert stats["by_provider"] == {}

    async def test_stats_counts_by_provider(self, temp_db: str) -> None:
        """Stats should group interaction counts by provider name."""
        learner = RuhLearner(db_path=temp_db)
        await learner.initialize()

        await learner.capture("q1", "r1", "anthropic", "claude")
        await learner.capture("q2", "r2", "anthropic", "claude")
        await learner.capture("q3", "r3", "openrouter", "gpt-4o")

        stats = await learner.get_stats()
        assert stats["total_interactions"] == 3
        assert stats["by_provider"]["anthropic"] == 2
        assert stats["by_provider"]["openrouter"] == 1

    async def test_stats_total_matches_sum(self, temp_db: str) -> None:
        """Total interactions should equal sum of per-provider counts."""
        learner = RuhLearner(db_path=temp_db)
        await learner.initialize()

        await learner.capture("q", "r", "anthropic", "m")
        await learner.capture("q", "r", "openai", "m")
        await learner.capture("q", "r", "ruh", "m")

        stats = await learner.get_stats()
        provider_sum = sum(stats["by_provider"].values())
        assert stats["total_interactions"] == provider_sum


class TestInitialize:
    """Test database initialization."""

    async def test_initialize_creates_table(self, temp_db: str) -> None:
        """initialize() should create the interactions table."""
        learner = RuhLearner(db_path=temp_db)
        await learner.initialize()

        # If the table exists, capture should work without error
        await learner.capture("q", "r", "p", "m")
        stats = await learner.get_stats()
        assert stats["total_interactions"] == 1

    async def test_initialize_idempotent(self, temp_db: str) -> None:
        """Calling initialize() twice should not raise or drop data."""
        learner = RuhLearner(db_path=temp_db)
        await learner.initialize()
        await learner.capture("q", "r", "p", "m")

        await learner.initialize()  # second init

        stats = await learner.get_stats()
        assert stats["total_interactions"] == 1


class TestUpdateQuality:
    """Test quality score updates."""

    async def test_update_quality_score(self, temp_db: str) -> None:
        """update_quality should set the quality_score for an interaction."""
        learner = RuhLearner(db_path=temp_db)
        await learner.initialize()

        await learner.capture("q", "r", "p", "m")
        recent = await learner.get_recent(limit=1)
        interaction_id = recent[0]["id"]

        await learner.update_quality(interaction_id, 0.95)

        updated = await learner.get_recent(limit=1)
        assert updated[0]["quality_score"] == pytest.approx(0.95)

    async def test_update_quality_rejects_invalid_score(self, temp_db: str) -> None:
        """update_quality should raise ValueError for scores outside [0.0, 1.0]."""
        learner = RuhLearner(db_path=temp_db)
        await learner.initialize()

        await learner.capture("q", "r", "p", "m")
        recent = await learner.get_recent(limit=1)
        interaction_id = recent[0]["id"]

        with pytest.raises(ValueError, match="between 0.0 and 1.0"):
            await learner.update_quality(interaction_id, 1.5)

        with pytest.raises(ValueError, match="between 0.0 and 1.0"):
            await learner.update_quality(interaction_id, -0.1)

    async def test_update_quality_boundary_values(self, temp_db: str) -> None:
        """Boundary values 0.0 and 1.0 should be accepted."""
        learner = RuhLearner(db_path=temp_db)
        await learner.initialize()

        await learner.capture("q1", "r1", "p", "m")
        await learner.capture("q2", "r2", "p", "m")

        recent = await learner.get_recent(limit=2)

        await learner.update_quality(recent[0]["id"], 1.0)
        await learner.update_quality(recent[1]["id"], 0.0)

        updated = await learner.get_recent(limit=2)
        scores = {item["id"]: item["quality_score"] for item in updated}
        assert scores[recent[0]["id"]] == pytest.approx(1.0)
        assert scores[recent[1]["id"]] == pytest.approx(0.0)
