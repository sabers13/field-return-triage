"""The cost-free baselines: a learned group model and the committed keyword rules."""

from __future__ import annotations

import json
from pathlib import Path

from field_return_triage.contracts import Complaint
from field_return_triage.pipeline.baseline import (
    load_condition_keywords,
    run_baselines,
    write_baselines,
)

GROUPS = ("battery_charging_12v", "instrument_panel_displays", "exterior_lighting")
WORDS = {
    "battery_charging_12v": "battery alternator starter charging voltage",
    "instrument_panel_displays": "dashboard cluster display speedometer gauge",
    "exterior_lighting": "headlight tail light bulb lamp",
}


def _complaint(identifier: str, group: str, narrative: str, **overrides: object) -> Complaint:
    values: dict[str, object] = {
        "id": identifier,
        "narrative": narrative,
        "received": "2021-05-05",
        "group": group,
    }
    values.update(overrides)
    return Complaint.model_validate(values)


def _library() -> list[Complaint]:
    rows: list[Complaint] = []
    for group in GROUPS:
        for index in range(5):
            rows.append(
                _complaint(
                    f"lib-{group}-{index}",
                    group,
                    f"{WORDS[group]} problem number {index}",
                )
            )
    return rows


def _items() -> list[Complaint]:
    return [
        _complaint("eval-1", "battery_charging_12v", "battery voltage drops at idle"),
        _complaint("eval-2", "instrument_panel_displays", "dashboard display went dark"),
        _complaint("eval-3", "exterior_lighting", "headlight lamp flickers"),
        _complaint("eval-4", "battery_charging_12v", "smoke from the battery", crash=True),
        _complaint("eval-5", "exterior_lighting", "tail light after rain"),
    ]


def test_the_group_baseline_learns_distinct_groups() -> None:
    payload = run_baselines(
        _items(),
        _library(),
        safety_keywords=("smoke",),
        condition_keywords={"moisture": ("rain",)},
    )
    group = payload["group"]
    assert group["available"] is True
    metrics = group["metrics"]
    assert metrics["accuracy"]["value"] == 1.0
    assert metrics["macro_f1"]["value"] == 1.0
    assert metrics["coverage"]["value"] == 1.0


def test_the_group_baseline_is_deterministic() -> None:
    first = run_baselines(
        _items(),
        _library(),
        safety_keywords=("smoke",),
        condition_keywords={"moisture": ("rain",)},
    )
    second = run_baselines(
        _items(),
        _library(),
        safety_keywords=("smoke",),
        condition_keywords={"moisture": ("rain",)},
    )
    assert first == second


def test_the_safety_baseline_uses_the_coded_fields() -> None:
    payload = run_baselines(
        _items(),
        _library(),
        safety_keywords=("smoke",),
        condition_keywords={"moisture": ("rain",)},
    )
    safety = payload["safety"]
    assert safety["evaluation_items"] == 5
    assert safety["coded_safety_items"] == 1
    assert safety["metrics"]["recall"]["value"] == 1.0
    assert safety["metrics"]["precision"]["value"] == 1.0


def test_the_conditions_baseline_reports_coverage_only() -> None:
    payload = run_baselines(
        _items(),
        _library(),
        safety_keywords=("smoke",),
        condition_keywords={"moisture": ("rain",), "heat": ("hot",)},
    )
    conditions = payload["conditions"]
    assert conditions["evaluation_items"] == 5
    assert conditions["items_with_any_condition"] == 1
    assert conditions["per_kind"] == {"moisture": 1, "heat": 0}
    assert "not accuracy" in conditions["note"]


def test_baselines_without_a_library_or_items_say_so() -> None:
    payload = run_baselines(
        [],
        [],
        safety_keywords=("smoke",),
        condition_keywords={"moisture": ("rain",)},
    )
    assert payload["group"]["available"] is False
    assert payload["safety"]["available"] is False
    assert payload["conditions"]["available"] is False


def test_write_baselines_is_byte_identical(tmp_path: Path) -> None:
    payload = run_baselines(
        _items(),
        _library(),
        safety_keywords=("smoke",),
        condition_keywords={"moisture": ("rain",)},
    )
    first = write_baselines(payload, tmp_path / "one")
    second = write_baselines(payload, tmp_path / "two")
    assert [path.name for path in first] == ["conditions.json", "group.json", "safety.json"]
    for left, right in zip(first, second, strict=True):
        assert left.read_bytes() == right.read_bytes()
        json.loads(left.read_text(encoding="utf-8"))


def test_load_condition_keywords_reads_the_committed_file() -> None:
    keywords = load_condition_keywords()
    assert "moisture" in keywords
    assert "rain" in keywords["moisture"]
