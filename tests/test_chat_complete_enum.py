"""
Regression tests for the chat_complete "Thinking..." freeze (2026-09-29).

Root cause: thinking_trace metadata carried a raw YaqinLevel Enum
(backend/agents/base.py emitted {"level": yaqin_tag.level, ...}).
json.dumps raised TypeError inside ws.send_json, and ConnectionManager
swallowed it silently -> chat_complete never reached the client ->
UI froze on "Thinking..." with zero log evidence.

Fixes guarded here:
1. base.py emits yaqin_tag.level.value (a plain str)
2. main.py sanitizes trace metadata via json.loads(json.dumps(..., default=str))
3. ConnectionManager.send/broadcast log failures instead of swallowing them
"""

import json
import logging
from unittest.mock import patch

import pytest


def _import_manager():
    with patch.dict(
        "os.environ",
        {"ANTHROPIC_API_KEY": "", "DB_PATH": ":memory:", "SECRET_KEY": "test-secret"},
    ):
        from api.main import ConnectionManager

        return ConnectionManager


def test_yaqin_level_value_is_json_serializable():
    """The emitted level must be a plain string, not a raw Enum."""
    from qca.yaqin_engine import YaqinLevel

    payload = {"level": YaqinLevel.ILM_AL_YAQIN.value, "source": "agentic_reasoning"}
    assert json.dumps(payload) == json.dumps(
        {"level": "ilm_al_yaqin", "source": "agentic_reasoning"}
    )
    # And the raw enum itself must NOT be serializable (documents why the fix exists)
    with pytest.raises(TypeError):
        json.dumps({"level": YaqinLevel.ILM_AL_YAQIN})


def test_metadata_sanitizer_pattern_handles_enums():
    """The trace_dict metadata safety net must survive stray non-serializables."""
    from qca.yaqin_engine import YaqinLevel

    metadata = {"level": YaqinLevel.AYN_AL_YAQIN, "nested": {"x": 1}}
    cleaned = json.loads(json.dumps(metadata, default=str))
    assert json.dumps(cleaned)  # must not raise
    assert cleaned["nested"] == {"x": 1}


class _FailingSocket:
    async def send_json(self, data):
        raise TypeError("Object of type YaqinLevel is not JSON serializable")


@pytest.mark.asyncio
async def test_send_logs_failure_instead_of_swallowing(caplog):
    ConnectionManager = _import_manager()
    manager = ConnectionManager()
    manager.connections["c1"] = _FailingSocket()
    manager.owners["c1"] = "u1"
    from security.auth import TokenPayload, bind_principal

    bind_principal(TokenPayload("u1", "u1", ["user"], 9999999999, 0, "test"))
    with caplog.at_level(logging.ERROR, logger="mizan.api"):
        await manager.send("c1", {"type": "chat_complete"})
    assert "c1" not in manager.connections  # still disconnects
    assert any(
        r.levelno == logging.ERROR and "send" in r.getMessage().lower() for r in caplog.records
    ), "send() must log the failure, not swallow it"


@pytest.mark.asyncio
async def test_broadcast_logs_failure_instead_of_swallowing(caplog):
    ConnectionManager = _import_manager()
    manager = ConnectionManager()
    manager.connections["c1"] = _FailingSocket()
    manager.owners["c1"] = "u1"
    from security.auth import TokenPayload, bind_principal

    bind_principal(TokenPayload("u1", "u1", ["user"], 9999999999, 0, "test"))
    with caplog.at_level(logging.ERROR, logger="mizan.api"):
        await manager.broadcast({"type": "chat_complete"})
    assert "c1" not in manager.connections
    assert any(
        r.levelno == logging.ERROR and "broadcast" in r.getMessage().lower() for r in caplog.records
    ), "broadcast() must log the failure, not swallow it"
