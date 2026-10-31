"""The safety keyword rule is deterministic and quotes the span it matched."""

from __future__ import annotations

from pathlib import Path

import pytest

from field_return_triage.rules.keywords import (
    DEFAULT_KEYWORDS_PATH,
    keyword_safety,
    load_safety_keywords,
)


def write_keywords(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "safety_keywords.txt"
    path.write_text(text, encoding="utf-8")
    return path


def test_default_path_points_at_the_data_lane_file() -> None:
    assert Path("data/safety_keywords.txt") == DEFAULT_KEYWORDS_PATH


def test_load_skips_comments_and_blanks_and_dedupes(tmp_path: Path) -> None:
    path = write_keywords(
        tmp_path,
        "# comment\n\nfire\nsmoke\nFIRE\n  burn  \n",
    )
    assert load_safety_keywords(path) == ("fire", "smoke", "burn")


def test_empty_keyword_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="keyword list is empty"):
        load_safety_keywords(write_keywords(tmp_path, "# only a comment\n\n"))


def test_match_is_case_insensitive_and_returns_the_narrative_span() -> None:
    narrative = "The wiring harness started to SMOKE after the repair."
    assert keyword_safety(narrative, ["smoke"]) == "SMOKE"


def test_multi_word_keyword_tolerates_any_whitespace() -> None:
    narrative = "Then there was a burning   smell and later a fire."
    assert keyword_safety(narrative, ["burning smell"]) == "burning   smell"


def test_a_multi_word_keyword_must_match_its_words_in_order() -> None:
    assert keyword_safety("a smell of burning", ["burning smell"]) is None


def test_earliest_span_wins_regardless_of_list_order() -> None:
    narrative = "Smoke appeared, then the unit caught fire."
    assert keyword_safety(narrative, ["fire", "smoke"]) == "Smoke"
    assert keyword_safety(narrative, ["smoke", "fire"]) == "Smoke"


def test_no_match_returns_none() -> None:
    assert keyword_safety("The radio lost its presets.", ["fire", "smoke"]) is None


def test_empty_keyword_is_ignored_instead_of_matching_everywhere() -> None:
    assert keyword_safety("anything at all", ["", "  "]) is None
