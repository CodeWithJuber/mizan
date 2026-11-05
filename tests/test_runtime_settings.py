"""Administrator-managed runtime settings: validation, persistence, secrets, apply."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

import runtime_settings as rs
from security.auth import TokenPayload

ADMIN = TokenPayload("root", "admin", ["admin"], 9999999999, 0, "t")
USER = TokenPayload("alice", "alice", ["user"], 9999999999, 0, "t")


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    for setting in rs.SETTINGS:
        monkeypatch.delenv(setting.key, raising=False)
    monkeypatch.setattr(rs, "_baseline", {})
    monkeypatch.setattr(rs, "_started", {})
    rs.apply_saved()
    return tmp_path


@pytest.mark.parametrize(
    "key,value,expected",
    [
        ("MIZAN_CHAT_EFFORT", "MAX", "max"),
        ("MIZAN_NLP_NATIVE_WSD", True, "true"),
        ("MIZAN_OWNED_LEARNING_AUTORUN", "0", "false"),
        ("MIZAN_CHAT_MAX_STEPS", "250", "250"),
        ("MIZAN_CONTEXT_FILL", 0.25, "0.25"),
        ("LLM_PROVIDER", "openrouter", "openrouter"),
        ("DEFAULT_MODEL", "anthropic/claude-opus-5.5", "anthropic/claude-opus-5.5"),
        ("MIZAN_CHAT_MAX_OUTPUT_TOKENS", "", ""),
    ],
)
def test_values_are_normalized(key, value, expected):
    assert rs.normalize(rs.BY_KEY[key], value) == expected


@pytest.mark.parametrize(
    "key,value",
    [
        ("MIZAN_CHAT_EFFORT", "turbo"),
        ("MIZAN_CHAT_MAX_STEPS", "0"),
        ("MIZAN_CHAT_MAX_STEPS", "ten"),
        ("MIZAN_CONTEXT_FILL", "nan"),
        ("MIZAN_NLP_NATIVE_WSD", "maybe"),
        ("OPENROUTER_API_KEY", ""),
        ("DEFAULT_MODEL", "model; rm -rf /"),
        ("MIZAN_PUBLIC_URL", "javascript:alert(1)"),
        ("MIZAN_SUPPORT_MODEL", "two\nlines"),
    ],
)
def test_invalid_values_are_rejected(key, value):
    with pytest.raises(ValueError):
        rs.normalize(rs.BY_KEY[key], value)


def test_update_persists_seals_secrets_and_reset_restores_environment(store, monkeypatch):
    monkeypatch.setenv("MIZAN_CHAT_EFFORT", "high")
    rs._baseline.clear()
    change = rs.update(
        {"MIZAN_CHAT_EFFORT": "low", "OPENROUTER_API_KEY": "sk-or-secret-value"}, "root"
    )
    assert set(change.applied) == {"MIZAN_CHAT_EFFORT", "OPENROUTER_API_KEY"}
    assert change.provider_changed and not change.model_changed
    assert rs.os.environ["MIZAN_CHAT_EFFORT"] == "low"
    raw = (store / "runtime_settings.json").read_text()
    assert (
        "sk-or-secret-value" not in raw
        and json.loads(raw)["values"]["OPENROUTER_API_KEY"]["sealed"]
    )
    view = {row["key"]: row for row in rs.public_view()["settings"]}
    assert view["OPENROUTER_API_KEY"]["value"] is None and view["OPENROUTER_API_KEY"]["is_set"]
    assert view["MIZAN_CHAT_EFFORT"]["source"] == "admin"
    assert "sk-or-secret-value" not in json.dumps(rs.public_view())
    rs.update({"MIZAN_CHAT_EFFORT": None, "OPENROUTER_API_KEY": None}, "root")
    assert rs.os.environ["MIZAN_CHAT_EFFORT"] == "high"
    assert "OPENROUTER_API_KEY" not in rs.os.environ


def test_owned_only_change_rebuilds_from_configured_provider(store):
    # Leaving owned mode must rebuild from LLM_PROVIDER/DEFAULT_MODEL: the in-memory
    # active provider is still mizan-owned and would re-pin every agent to it.
    for value in ("true", "false", "true", None):
        change = rs.update({"MIZAN_OWNED_ONLY": value}, "root")
        assert change.applied == ["MIZAN_OWNED_ONLY"], value
        assert change.provider_changed and change.model_changed, value


def test_saved_values_win_at_startup_and_restart_settings_are_flagged(store, monkeypatch):
    rs.update({"MIZAN_NLP_NATIVE_WSD": "true", "OPENAI_API_KEY": "sk-test"}, "root")
    assert rs.restart_pending() == ["MIZAN_NLP_NATIVE_WSD"]
    # Simulate a restart with the server's .env saying otherwise.
    monkeypatch.setenv("MIZAN_NLP_NATIVE_WSD", "0")
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setattr(rs, "_baseline", {})
    monkeypatch.setattr(rs, "_started", {})
    rs.apply_saved()
    assert rs.os.environ["MIZAN_NLP_NATIVE_WSD"] == "true"
    assert rs.os.environ["OPENAI_API_KEY"] == "sk-test"
    assert rs.restart_pending() == []
    rs.update({"MIZAN_NLP_NATIVE_WSD": None}, "root")
    assert rs.os.environ["MIZAN_NLP_NATIVE_WSD"] == "0"


def test_batch_with_one_bad_value_changes_nothing(store):
    with pytest.raises(ValueError) as error:
        rs.update({"MIZAN_CHAT_EFFORT": "low", "MIZAN_CHAT_MAX_STEPS": "-1"}, "root")
    assert "MIZAN_CHAT_MAX_STEPS" in json.loads(str(error.value))
    assert "MIZAN_CHAT_EFFORT" not in rs.os.environ
    with pytest.raises(KeyError):
        rs.update({"SECRET_KEY": "x"}, "root")


@pytest.fixture
def api(store, monkeypatch):
    # api.main opens its databases at import time; keep them in the test folder.
    monkeypatch.setenv("DB_PATH", str(store / "memory.db"))
    monkeypatch.setenv("MIZAN_OWNED_DB", str(store / "owned.sqlite3"))
    import api.main as main

    switched = []

    async def fake_switch(provider, model):
        switched.append((provider.provider_name, model))
        return {"provider": provider.provider_name, "model": model}

    monkeypatch.setattr(main, "_switch_all_agents", fake_switch)
    monkeypatch.setattr(
        main,
        "create_provider",
        lambda provider=None, model=None: SimpleNamespace(provider_name=provider or "openrouter"),
    )
    monkeypatch.setattr(main, "wali", SimpleNamespace(audit=SimpleNamespace(log=lambda *a: None)))
    monkeypatch.setattr(main, "manager", SimpleNamespace(broadcast=AsyncMock()))
    return main, switched


async def test_api_is_admin_only_and_switches_the_model(api):
    main, switched = api
    with pytest.raises(HTTPException) as denied:
        await main.runtime_settings_view(USER)
    assert denied.value.status_code == 403
    view = await main.runtime_settings_view(ADMIN)
    assert "Model" in view["groups"]
    result = await main.runtime_settings_update(
        main.RuntimeSettingsUpdate(
            values={"LLM_PROVIDER": "openrouter", "DEFAULT_MODEL": "qwen/qwen3.8-flash"}
        ),
        ADMIN,
    )
    assert switched == [("openrouter", "qwen/qwen3.8-flash")]
    assert any("openrouter / qwen/qwen3.8-flash" in note for note in result["notes"])
    with pytest.raises(HTTPException) as invalid:
        await main.runtime_settings_update(
            main.RuntimeSettingsUpdate(values={"MIZAN_CHAT_EFFORT": "ultra"}), ADMIN
        )
    assert invalid.value.status_code == 422
    assert "MIZAN_CHAT_EFFORT" in invalid.value.detail["errors"]
    with pytest.raises(HTTPException) as unknown:
        await main.runtime_settings_update(
            main.RuntimeSettingsUpdate(values={"MIZAN_ADMIN_PASS": "x"}), ADMIN
        )
    assert unknown.value.status_code == 422


def test_every_change_leaves_a_receipt_without_its_value(store):
    from security import sakk

    sakk._STORES.clear()
    rs.update({"TELEGRAM_BOT_TOKEN": "123:secret-token"}, "admin")
    found = [r for r in sakk.store().receipts("system") if r["kind"] == "setting"]
    assert found and found[0]["keys"] == ["TELEGRAM_BOT_TOKEN"] and found[0]["by"] == "admin"
    assert "secret-token" not in json.dumps(found[0])


def test_only_signed_in_administrator_routes_change_settings():
    """Channel tokens and allowlists are sealed from agents: no module but the
    API's admin routes (and start-up) calls runtime_settings.update."""
    import re
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1] / "backend"
    callers = sorted(
        str(path.relative_to(backend))
        for path in backend.rglob("*.py")
        # A local virtualenv under backend/ holds third-party files, some not UTF-8.
        if "venv" not in path.relative_to(backend).parts
        and re.search(r"runtime_settings\.update\(", path.read_text(encoding="utf-8"))
    )
    assert callers == ["api/main.py"]
