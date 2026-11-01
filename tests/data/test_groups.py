"""The binding group file, its normalisation and the longest-prefix rule."""

from __future__ import annotations

from pathlib import Path

import pytest

from field_return_triage.data.spec import load_groups, map_component, normalise_component


def test_the_committed_group_file_has_the_eight_groups() -> None:
    groups = load_groups()
    assert len(groups) == 8
    assert set(groups) == {
        "airbags",
        "battery_charging_12v",
        "driver_assist_sensors",
        "ev_high_voltage",
        "exterior_lighting",
        "instrument_panel_displays",
        "power_windows_locks_switches",
        "wipers_washers",
    }


def test_normalisation_collapses_whitespace_and_colon_spaces() -> None:
    assert normalise_component("  air bags :  frontal  ") == "AIR BAGS:FRONTAL"


def test_prefix_equals_and_starts_with_colon() -> None:
    groups = load_groups()
    assert map_component("AIR BAGS", groups) == "airbags"
    assert map_component("AIR BAGS:FRONTAL:PASSENGER SIDE", groups) == "airbags"
    assert map_component("EXTERIOR LIGHTING:BRAKE LIGHTS", groups) == "exterior_lighting"


def test_the_longest_prefix_wins() -> None:
    groups = load_groups()
    # "ELECTRICAL SYSTEM:WIRING" is a battery prefix, but the longer switch prefix maps
    # the same label to the power-window group.
    assert (
        map_component("ELECTRICAL SYSTEM:WIRING:SWITCHES/KNOBS/BUTTONS", groups)
        == "power_windows_locks_switches"
    )
    assert map_component("ELECTRICAL SYSTEM:WIRING", groups) == "battery_charging_12v"


def test_unmapped_and_blank_labels_are_none() -> None:
    groups = load_groups()
    assert map_component("ENGINE", groups) is None
    assert map_component("", groups) is None
    assert map_component("AIR BAGSX", groups) is None


def test_a_custom_group_file_is_read_by_group_id(tmp_path: Path) -> None:
    target = tmp_path / "groups.toml"
    target.write_text(
        """
[[group]]
id = "airbags"
prefixes = ["AIR BAGS"]

[[group]]
id = "wipers"
prefixes = ["VISIBILITY/WIPER"]
""",
        encoding="utf-8",
    )
    groups = load_groups(target)
    assert groups["airbags"] == ("AIR BAGS",)
    assert map_component("VISIBILITY/WIPER", groups) == "wipers"


def test_an_empty_group_file_is_an_error(tmp_path: Path) -> None:
    target = tmp_path / "groups.toml"
    target.write_text("version = 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="group list is empty"):
        load_groups(target)
