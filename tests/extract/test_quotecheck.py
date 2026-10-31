"""The quote check: verbatim after whitespace normalisation and case folding."""

from __future__ import annotations

from field_return_triage.contracts import Clue, Extraction, FaultCode, Mileage
from field_return_triage.extract.quotecheck import check_quotes, normalise, quote_passes

NARRATIVE = "The  dashboard went DARK\nintermittently after rain. Code U0121 at 42,000 miles."


def test_normalise_collapses_whitespace_and_folds_case() -> None:
    assert normalise("  A\t b\n\nC ") == "a b c"


def test_verbatim_quotes_pass_across_whitespace_and_case() -> None:
    assert quote_passes("dashboard went dark", NARRATIVE)
    assert quote_passes("DARK intermittently", NARRATIVE)
    assert quote_passes("42,000 miles", NARRATIVE)


def test_a_paraphrase_fails() -> None:
    assert not quote_passes("dashboard turned dark", NARRATIVE)
    assert not quote_passes("went dark after rain", NARRATIVE)


def test_an_empty_quote_fails() -> None:
    assert not quote_passes("   ", NARRATIVE)


def test_check_quotes_counts_every_field() -> None:
    extraction = Extraction(
        component_group="body_control",
        safety_relevant=True,
        safety_quote="went DARK",  # passes
        symptoms=(
            Clue(kind="noise", quote="loud rattle"),  # fails
            Clue(kind="display_fault", quote="dashboard went dark"),  # passes
        ),
        conditions=(Clue(kind="moisture", quote="after rain"),),  # passes
        fault_codes=(FaultCode(code="U0121", quote="code u0121"),),  # passes
        mileage=Mileage(value=1, quote="100,000 miles"),  # fails
    )
    check = check_quotes(extraction, NARRATIVE)

    assert check.checked == 6
    assert check.passed == 4
    assert len(check.dropped) == 2
    assert [item.field for item in check.dropped] == ["symptoms", "mileage"]
    assert check.checked == check.passed + len(check.dropped)
    assert not check.all_passed
    assert not check.none_passed


def test_every_quote_failing_is_reported() -> None:
    extraction = Extraction(symptoms=(Clue(kind="noise", quote="nope"),))
    check = check_quotes(extraction, NARRATIVE)
    assert check.checked == 1
    assert check.passed == 0
    assert check.none_passed


def test_no_quotes_at_all_is_not_a_pass() -> None:
    check = check_quotes(Extraction(), NARRATIVE)
    assert check.checked == 0
    assert not check.all_passed
