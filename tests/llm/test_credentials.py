"""Credential resolution order and redaction."""

from __future__ import annotations

from pathlib import Path

import pytest

from field_return_triage.llm.credentials import ApiKey, load_api_key, read_env_file
from field_return_triage.llm.errors import ConfigurationError

KEY_A = "test-key-from-environment-aaa"
KEY_B = "test-key-from-env-file-bbb"
KEY_C = "test-key-from-dotenv-ccc"


def test_environment_wins_over_files(tmp_path: Path) -> None:
    env_file = tmp_path / "gateway.env"
    env_file.write_text(f"FRT_API_KEY={KEY_C}\n", encoding="utf-8")
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"FRT_API_KEY={KEY_C}\n", encoding="utf-8")

    key = load_api_key({"FRT_API_KEY": KEY_A}, env_file=env_file, dotenv=dotenv)
    assert key.reveal() == KEY_A


def test_frt_env_file_is_used_when_the_environment_is_empty(tmp_path: Path) -> None:
    env_file = tmp_path / "gateway.env"
    env_file.write_text(f'export FRT_API_KEY="{KEY_B}"\n', encoding="utf-8")
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"FRT_API_KEY={KEY_C}\n", encoding="utf-8")

    key = load_api_key({"FRT_ENV_FILE": str(env_file)}, dotenv=dotenv)
    assert key.reveal() == KEY_B


def test_dotenv_is_the_last_source(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"FRT_API_KEY={KEY_C}\n", encoding="utf-8")
    key = load_api_key({}, dotenv=dotenv)
    assert key.reveal() == KEY_C


def test_named_variable_alternatives_are_tried(tmp_path: Path) -> None:
    key = load_api_key({"OPENCODE_API_KEY": KEY_A}, dotenv=tmp_path / "absent.env")
    assert key.reveal() == KEY_A


def test_missing_key_names_the_sources_without_a_value(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError) as caught:
        load_api_key({}, dotenv=tmp_path / "absent.env")
    message = str(caught.value)
    assert "FRT_API_KEY" in message
    assert "FRT_ENV_FILE" in message


def test_a_missing_frt_env_file_is_a_configuration_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError):
        load_api_key({"FRT_ENV_FILE": str(tmp_path / "absent.env")}, dotenv=tmp_path / "absent")


def test_api_key_repr_and_str_are_redacted() -> None:
    key = ApiKey(KEY_A)
    assert KEY_A not in repr(key)
    assert KEY_A not in str(key)
    assert repr(key) == "ApiKey(<redacted>)"
    assert key.reveal() == KEY_A


def test_empty_key_is_rejected() -> None:
    with pytest.raises(ConfigurationError):
        ApiKey("   ")


def test_env_file_parser_ignores_comments_and_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "gateway.env"
    path.write_text(
        "# comment\n\nFRT_API_KEY=test-value-123\nEMPTY=\n",
        encoding="utf-8",
    )
    values = read_env_file(path)
    assert values == {"FRT_API_KEY": "test-value-123"}
