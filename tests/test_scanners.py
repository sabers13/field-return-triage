"""Unit tests for the two repository scanners, using temporary files only.

Adapted from which-ai-model (same author, MIT).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str) -> ModuleType:
    path = REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"frt_scripts_{name}", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def forbidden() -> ModuleType:
    return _load_script("scan_forbidden")


@pytest.fixture(scope="module")
def secrets() -> ModuleType:
    return _load_script("scan_secrets")


# --- forbidden names -------------------------------------------------------


def test_load_hashes_ignores_comments_and_blank_lines(
    forbidden: ModuleType, tmp_path: Path
) -> None:
    digest = "a" * 64
    path = tmp_path / "hashes.txt"
    path.write_text(f"# comment\n\n{digest.upper()}\n", encoding="utf-8")
    assert forbidden.load_hashes(path) == {digest}


def test_load_hashes_rejects_a_non_hex_line(forbidden: ModuleType, tmp_path: Path) -> None:
    path = tmp_path / "hashes.txt"
    path.write_text("not-a-hash\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not a sha256 hex digest"):
        forbidden.load_hashes(path)


def test_token_hashes_also_splits_dotted_and_dashed_runs(forbidden: ModuleType) -> None:
    import hashlib

    tokens = {token for token, _digest in forbidden.token_hashes("jane.doe jane-doe")}
    assert "jane" in tokens
    assert "doe" in tokens
    assert "jane.doe" in tokens
    # The comparison is by hash, so the plain token never leaves this function.
    digest = hashlib.sha256(b"jane").hexdigest()
    assert (("jane", digest)) in set(forbidden.token_hashes("jane"))


def test_find_forbidden_lines_reports_position_and_hash_prefix(
    forbidden: ModuleType,
) -> None:
    import hashlib

    digest = hashlib.sha256(b"secretname").hexdigest()
    hits = forbidden.find_forbidden_lines("clean line\nmentions secretname here\n", {digest})
    assert hits == [(2, digest[:12])]


def test_scan_skips_binaries_and_reports_clean_text(forbidden: ModuleType, tmp_path: Path) -> None:
    import hashlib

    digest = hashlib.sha256(b"secretname").hexdigest()
    clean = tmp_path / "clean.txt"
    clean.write_text("nothing to see\n", encoding="utf-8")
    dirty = tmp_path / "dirty.txt"
    dirty.write_text("secretname\n", encoding="utf-8")
    assert forbidden.scan(tmp_path, {digest}, commits=0, files=[clean]) == []
    findings = forbidden.scan(tmp_path, {digest}, commits=0, files=[dirty])
    assert findings == ["dirty.txt:1: forbidden token (sha256 " + digest[:12] + "…)"]


def test_committed_hash_file_is_readable_and_not_empty(forbidden: ModuleType) -> None:
    hashes = forbidden.load_hashes(REPO_ROOT / "config" / "forbidden.sha256")
    assert hashes


# --- secrets ---------------------------------------------------------------


def test_secret_scanner_flags_known_key_shapes(secrets: ModuleType) -> None:
    text = "\n".join(
        (
            'API_KEY = "sk-' + "a" * 24 + '"',
            "-----BEGIN RSA " + "PRIVATE KEY-----",
            'password = "' + "hunter2" * 3 + '"',
        )
    )
    rules = [rule for _lineno, rule in secrets.scan_text(text)]
    assert "openai-style key" in rules
    assert "private key block" in rules
    assert "secret assignment" in rules


def test_secret_scanner_ignores_placeholders_and_env_references(secrets: ModuleType) -> None:
    text = 'api_key = "env:OPENCODE_GO_API_KEY"\npassword = "<your password here>"\n'
    assert secrets.scan_text(text) == []


def test_secret_scanner_never_prints_the_value(secrets: ModuleType, tmp_path: Path) -> None:
    value = "sk-" + "b" * 24
    path = tmp_path / "leak.txt"
    path.write_text(f"key: {value}\n", encoding="utf-8")
    findings = secrets.scan(tmp_path, files=[path])
    assert findings == ["leak.txt:1: possible openai-style key (value not shown)"]
    assert value not in findings[0]


def test_scanners_fail_loudly_outside_a_git_repository(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "scan_secrets.py"), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "not a git repository" in result.stderr
