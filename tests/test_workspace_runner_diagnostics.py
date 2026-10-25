"""The diagnostic can explain validation failures without publishing config values."""

import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "runner_diagnostics",
    Path(__file__).resolve().parents[1] / "scripts/workspace_runner_diagnostics.py",
)
diagnostics = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostics)


def test_error_details_redact_all_known_environment_values_and_all_quotes():
    message = "services.workspace-runner: secret_token_value bad\n\"unknown quoted value\" 'another value' `third` “fourth” ‘fifth’\nkey=literal$$credential"
    result = diagnostics.safe_error_detail(message, ["secret_token_value", "literal$credential"])
    for value in (
        "secret_token_value",
        "unknown quoted value",
        "another value",
        "third",
        "fourth",
        "fifth",
        "credential",
    ):
        assert value not in result
    assert "services.workspace-runner" in result and "bad" in result


def test_redaction_precedes_truncation_and_handles_json_escaped_values():
    secret = "long-secret-" * 150
    result = diagnostics.safe_error_detail("services.workspace-runner: " + secret, [secret])
    assert "long-secret" not in result and len(result) <= 1200
    result = diagnostics.safe_error_detail(r"invalid a\\b", [r"a\b"])
    assert result == "invalid <redacted>"


def test_unknown_credentials_urls_and_long_opaque_values_are_withheld():
    result = diagnostics.safe_error_detail(
        "services.workspace-runner: https://user:credential@example.test/path Bearer unseen-value token=unknown-secret ghp_short_example ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        [],
    )
    for value in (
        "example.test",
        "credential@example",
        "unseen-value",
        "unknown-secret",
        "ghp_short_example",
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    ):
        assert value not in result


def test_environment_collection_covers_map_and_list_forms_without_keys():
    values = diagnostics.environment_values(
        {
            "services": {
                "backend": {"environment": {"TOKEN": "hidden", "UNSET": None}},
                "other": {"environment": ["SECRET=private", "ABSENT"]},
            }
        }
    )
    assert values == ["hidden", "private"]
