"""
MIZAN Test Configuration
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure backend is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

# api.main opens its databases at import, under /data when these are unset, and CI has no /data.
# Serially an earlier test happened to import it with DB_PATH set; a parallel worker whose first
# import is another module would fail. Set a throwaway default so the import never depends on order.
_import_time_data = tempfile.mkdtemp(prefix="mizan-tests-")
os.environ.setdefault("DB_PATH", os.path.join(_import_time_data, "mizan_memory.db"))
os.environ.setdefault("QUEUE_DB_PATH", os.path.join(_import_time_data, "mizan_queue.db"))


@pytest.fixture(autouse=True)
def isolated_provider_mode(monkeypatch):
    """Legacy provider contracts run outside owned mode unless explicitly enabled.

    Doctor tests can create/load .env from .env.example; deployment defaults
    must not silently change unrelated tests later in the same process.
    """
    monkeypatch.setenv("MIZAN_OWNED_ONLY", "false")
    monkeypatch.setenv("LLM_PROVIDER", "")
    # No live catalog fetches from the app lifespan during tests.
    monkeypatch.setenv("MIZAN_MODEL_LIMITS_REFRESH", "false")
    monkeypatch.setenv("MIZAN_MEMORY_MAINTENANCE", "false")
    # Legacy suites test the model-driven agent loop; tests/test_tadbir.py
    # covers MIZAN's own orchestration (mizan and hybrid, the production default).
    monkeypatch.setenv("MIZAN_ORCHESTRATION", "llm")
    monkeypatch.setenv("MIZAN_LOCKED_EVAL", "off")  # tests never download the locked eval
    monkeypatch.setenv("MIZAN_HADITH_INDEX", "off")  # nor the six books' text
    monkeypatch.setenv("MIZAN_IQTIBAS", "off")  # nor read the Quran's texts for quotes
    monkeypatch.setenv("MIZAN_TADQIQ", "off")  # nor ask a scripted model an audit's question
    monkeypatch.setenv("MIZAN_TADRIB", "off")  # nor keep lessons for an own model to learn
    monkeypatch.setenv("MIZAN_EPISODIC", "off")  # nor keep episodes of what people said
    monkeypatch.setenv("MIZAN_REPLAY", "off")  # nor answer from a replayed trace
    monkeypatch.setenv("MIZAN_WARA", "off")  # nor ask PyPI/npm/OSV about installs (test_wara)


@pytest.fixture
def unplaced_wording(monkeypatch):
    """Qasd reads every message as an action whose recipe finds nothing to build
    in the words (a page to read, but no link), so P(converse) < ½ and MIZAN
    asks Lisan to map the wording. Tests of that path use it, whatever Qasd
    would make of their particular sentence."""
    from tadbir import qasd

    def posterior(message, project=False, overlay=None, earlier=()):
        return {"web_read": 0.7, "converse": 0.3}

    monkeypatch.setattr(qasd, "posterior", posterior)


@pytest.fixture
def temp_db():
    """Provide a temporary database file for tests."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def mock_wali():
    """Mock Wali security guardian."""
    wali = MagicMock()
    wali.check_rate_limit.return_value = True
    wali.validate_command.return_value = True
    wali.validate_url.return_value = True
    wali.validate_file_path.return_value = True
    wali.audit = MagicMock()
    return wali


@pytest.fixture
def mock_izn():
    """Mock Izn permission system."""
    izn = MagicMock()
    izn.check_permission.return_value = {
        "allowed": True,
        "reason": "Test mode",
        "requires_approval": False,
    }
    return izn
