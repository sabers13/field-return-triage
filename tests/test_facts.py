"""The facts checker must pass on the scaffold and switch on once docs exist."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def facts() -> ModuleType:
    path = REPO_ROOT / "scripts" / "check_facts.py"
    spec = importlib.util.spec_from_file_location("frt_scripts_check_facts", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_scaffold_without_project_facts_passes_and_says_so(
    facts: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(facts, "FACTS", tmp_path / "project-facts.yml")
    assert facts.main() == 0
    assert "not built yet (lane R9)" in capsys.readouterr().out


def test_facts_table_row_must_name_one_results_file(
    facts: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "\n".join(
            (
                "<!-- facts:start -->",
                "| Result | Value | Source | Proof |",
                "|---|---|---|---|",
                "| Macro-F1 | 0.42 | `results/SUMMARY.md` | macro-F1 0.42 |",
                "<!-- facts:end -->",
                "https://sabersojudi.com/field-return-triage/",
                "https://github.com/sabers13/field-return-triage",
                "results/page/screenshots/",
                "results/SUMMARY.md",
            )
        ),
        encoding="utf-8",
    )
    results = tmp_path / "results"
    results.mkdir()
    (results / "SUMMARY.md").write_text("macro-F1 0.42\n", encoding="utf-8")

    monkeypatch.setattr(facts, "README", readme)
    monkeypatch.setattr(facts, "ROOT", tmp_path)
    problems = facts.Problems()
    cache: dict[str, str | None] = {}
    assert facts.check_readme(problems, cache) == 1
    assert problems.items == []
