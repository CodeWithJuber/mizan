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
