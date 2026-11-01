"""One complaint through the whole flow, from a fixture recording."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import numpy as np
from pipeline_support import (
    FakeClient,
    fixture_items,
    fixture_library,
    fixture_paths,
    make_complaint,
    run_setting,
)

from field_return_triage.contracts import Priority
from field_return_triage.llm.client import ChatClient
from field_return_triage.pipeline.config import Paths, load_group_descriptions, resolve_index
from field_return_triage.pipeline.triage import (
    CallStats,
    render_card,
    triage_item,
    triage_one,
    triage_text,
)
from field_return_triage.rules.keywords import load_safety_keywords
from field_return_triage.rules.rulebook import Rulebook

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


def _client(paths: Paths, model_id: str = "fixture-primary") -> ChatClient:
    from field_return_triage.llm.settings import load_model_settings

    settings = load_model_settings(paths.models)
    chosen = next(model for model in settings if model.model_id == model_id)
    return ChatClient(
        chosen,
        recordings=paths.recordings,
        prices_path=paths.prices,
    )


def test_replay_produces_a_grounded_card(rulebook: Rulebook) -> None:
    paths = fixture_paths()
    item = next(row for row in fixture_items() if row.id == "fx-001")
    index, embedder = resolve_index(paths)
    card = triage_one(
        item,
        client=_client(paths),
        library=fixture_library(),
        rulebook=rulebook,
        groups=load_group_descriptions(paths.groups),
        keywords=load_safety_keywords(),
        index=index,
        embedder=embedder,
        now=NOW,
    )
    assert card.priority is Priority.CLEAR_CLUES
    assert card.extraction.component_group == "battery_charging_12v"
    assert card.quote_check.checked > 0
    assert card.quote_check.all_passed
    assert card.model_id == "fixture-primary"
    assert card.neighbours
    assert card.created_at == NOW


def test_safety_wins_on_a_recorded_safety_case(rulebook: Rulebook) -> None:
    paths = fixture_paths()
    item = next(row for row in fixture_items() if row.id == "fx-003")
    index, embedder = resolve_index(paths)
    card = triage_one(
        item,
        client=_client(paths),
        library=fixture_library(),
        rulebook=rulebook,
        groups=load_group_descriptions(paths.groups),
        keywords=load_safety_keywords(),
        index=index,
        embedder=embedder,
        now=NOW,
    )
    assert card.priority is Priority.SAFETY
    assert card.needs_human_review


def test_unclear_group_needs_human_reading(rulebook: Rulebook) -> None:
    paths = fixture_paths()
    item = next(row for row in fixture_items() if row.id == "fx-010")
    index, embedder = resolve_index(paths)
    card = triage_one(
        item,
        client=_client(paths),
        library=fixture_library(),
        rulebook=rulebook,
        groups=load_group_descriptions(paths.groups),
        keywords=load_safety_keywords(),
        index=index,
        embedder=embedder,
        now=NOW,
    )
    assert card.priority is Priority.HUMAN_READING
    assert card.needs_human_review


def test_invalid_answer_becomes_a_human_reading_card(rulebook: Rulebook) -> None:
    client = FakeClient(
        run_setting(),
        content=json.dumps({"component_group": "instrument_panel_displays", "nope": 1}),
    )
    empty = ([], np.zeros((0, 384), dtype=np.float32))
    card, stats = triage_item(
        make_complaint(),
        client=client,  # type: ignore[arg-type]
        library=(),
        rulebook=rulebook,
        groups={"instrument_panel_displays": "instrument panel"},
        keywords=("smoke",),
        index=empty,
        now=NOW,
    )
    assert card.priority is Priority.HUMAN_READING
    assert isinstance(stats, CallStats)
    assert stats.failure is not None
    assert stats.failure.startswith("schema-invalid:")
    assert card.quote_check.checked == 0


def test_a_paraphrased_quote_is_dropped(rulebook: Rulebook) -> None:
    content = json.dumps(
        {
            "component_group": "instrument_panel_displays",
            "safety_relevant": False,
            "safety_quote": None,
            "symptoms": [{"kind": "display_fault", "quote": "the dashboard went black"}],
            "conditions": [],
            "fault_codes": [],
            "mileage": None,
        }
    )
    client = FakeClient(run_setting(), content=content)
    empty = ([], np.zeros((0, 384), dtype=np.float32))
    card, _ = triage_item(
        make_complaint(),
        client=client,  # type: ignore[arg-type]
        library=(),
        rulebook=rulebook,
        groups={"instrument_panel_displays": "instrument panel"},
        keywords=("smoke",),
        index=empty,
        now=NOW,
    )
    assert card.quote_check.dropped
    assert card.priority is Priority.HUMAN_READING
    assert "the dashboard went black" not in card.quotes


def test_triage_text_reads_raw_text(rulebook: Rulebook) -> None:
    client = FakeClient(
        run_setting(),
        content=json.dumps(
            {
                "component_group": "instrument_panel_displays",
                "safety_relevant": False,
                "safety_quote": None,
                "symptoms": [{"kind": "display_fault", "quote": "went dark"}],
                "conditions": [{"kind": "moisture", "quote": "after rain"}],
                "fault_codes": [],
                "mileage": None,
            }
        ),
    )
    empty = ([], np.zeros((0, 384), dtype=np.float32))
    card = triage_text(
        "The dashboard went dark after rain.",
        complaint_id="demo",
        client=client,  # type: ignore[arg-type]
        library=(),
        rulebook=rulebook,
        groups={"instrument_panel_displays": "instrument panel"},
        keywords=("smoke",),
        index=empty,
        now=NOW,
    )
    assert card.complaint.id == "demo"
    assert card.quote_check.all_passed


def test_render_card_is_readable_and_never_decides(rulebook: Rulebook) -> None:
    paths = fixture_paths()
    item = next(row for row in fixture_items() if row.id == "fx-003")
    index, embedder = resolve_index(paths)
    card = triage_one(
        item,
        client=_client(paths),
        library=fixture_library(),
        rulebook=rulebook,
        groups=load_group_descriptions(paths.groups),
        keywords=load_safety_keywords(),
        index=index,
        embedder=embedder,
        now=NOW,
    )
    text = render_card(card)
    assert "Priority 1 (safety)" in text
    assert "Suggested next step" in text
    assert "A technician decides every case" in text
    assert "never closes" in text


def test_a_card_carries_no_close_scrap_or_return_state(rulebook: Rulebook) -> None:
    paths = fixture_paths()
    item = next(row for row in fixture_items() if row.id == "fx-001")
    index, embedder = resolve_index(paths)
    card = triage_one(
        item,
        client=_client(paths),
        library=fixture_library(),
        rulebook=rulebook,
        groups=load_group_descriptions(paths.groups),
        keywords=load_safety_keywords(),
        index=index,
        embedder=embedder,
        now=NOW,
    )

    banned = {"close", "closed", "scrap", "scrapped", "return", "returned", "disposition"}

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                assert key.casefold() not in banned
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(card.model_dump(mode="json"))
