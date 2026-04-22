"""Tests for filter.py pattern-matching helpers — pure string logic.

Covers the spec §4.1 start/end markers against realistic line snippets.
No PDF fixtures — those live in the sample-run script.
"""

from hardware_sets.filter import (
    _match_start,
    _heuristic_start,
    _current_section,
    END_OF_SECTION_RE,
)


def test_start_door_hardware_schedule():
    name, needs_guard = _match_start("DOOR HARDWARE SCHEDULE")
    assert name == "door_hardware_schedule"
    assert needs_guard is True


def test_start_hardware_sets_colon():
    name, needs_guard = _match_start("E. Hardware Sets:")
    assert name == "hardware_sets_colon"
    assert needs_guard is True
    name, _ = _match_start("D. Hardware Sets:")
    assert name == "hardware_sets_colon"


def test_start_schedule_section_3dot():
    name, needs_guard = _match_start("   3.01 SCHEDULE")
    assert name == "schedule_section_3dot"
    assert needs_guard is True
    name, _ = _match_start("  3.07 HARDWARE SCHEDULE")
    assert name == "schedule_section_3dot"


def test_start_hardware_schedule_head():
    name, needs_guard = _match_start("\nHardware Schedule\n")
    assert name == "hardware_schedule_head"
    assert needs_guard is True


def test_start_group_or_set():
    name, needs_guard = _match_start("Hardware Group No. 01")
    assert name == "group_or_set"
    assert needs_guard is False
    name, _ = _match_start("Hardware Set #1")
    assert name == "group_or_set"
    name, _ = _match_start("Hardware Group/Set #103")
    assert name == "group_or_set"


def test_start_hw_number():
    name, needs_guard = _match_start("HW 01  Interior Single Bedroom")
    assert name == "hw_number"
    assert needs_guard is False


def test_start_set_label():
    name, needs_guard = _match_start("Set: EX-1.0")
    assert name == "set_label"
    assert needs_guard is False
    name, _ = _match_start("Set: 1.0")
    assert name == "set_label"


def test_start_set_hash():
    name, needs_guard = _match_start("Set #101")
    assert name == "set_hash"
    assert needs_guard is False
    name, _ = _match_start("Set #SR38CL")
    assert name == "set_hash"


def test_start_heading_number():
    name, needs_guard = _match_start("Heading #1")
    assert name == "heading_number"
    assert needs_guard is False
    name, _ = _match_start("Heading #4")
    assert name == "heading_number"


def test_start_no_match_on_narrative():
    name, _ = _match_start("Hardware sets are indicated on Drawings.")
    assert name is None


def test_end_of_section():
    assert END_OF_SECTION_RE.search("  END OF SECTION  ")


def test_current_section():
    assert _current_section("SECTION 08 71 00 — DOOR HARDWARE") == "087100"
    assert _current_section("SECTION 087100") == "087100"
    assert _current_section("hello world") is None


def test_heuristic_fallback_fires_on_structural_signals():
    text = "SET 1\n\nQTY  DESCRIPTION\n 1  Hinge\n 2  Closer\n 1  Lockset"
    assert _heuristic_start(text)


def test_heuristic_fires_on_set_and_qty_lines():
    text = "SET 1\n1 Hinge\n2 Closer\n1 Lockset\n3 Strike\n1 Bolt\n2 Stop\n1 Sweep\n1 Threshold"
    assert _heuristic_start(text)


def test_heuristic_does_not_fire_on_narrative():
    assert not _heuristic_start(
        "The hardware sets specified in this section shall comply with the project requirements."
    )


def test_heuristic_does_not_fire_on_single_signal():
    assert not _heuristic_start("QTY  DESCRIPTION  MFR\nSome narrative text follows.")


def test_tabular_content_matches_real_schedule_rows():
    from hardware_sets.filter import _has_tabular_content
    assert _has_tabular_content("1        EA     CONT. HINGE")
    assert _has_tabular_content(" 3 EA HINGE 5BB1")
    assert _has_tabular_content("4        EA-R   ACTUATOR, TOUCH")
    assert _has_tabular_content("1 Ea.  Lockset  L9070")
    assert _has_tabular_content("1 Set  Continuous Hinge  AC500")
    # Bare quantity lines (3+) without unit labels
    assert _has_tabular_content("  3   Standard Hinge\n  1   Lockset\n  1   Wall Door Stop")


def test_tabular_content_rejects_prose():
    from hardware_sets.filter import _has_tabular_content
    assert not _has_tabular_content(
        "Door Hardware Schedule: Prepared by the Architectural Hardware Consultant."
    )
    assert not _has_tabular_content("Refer to Door and Frame Schedule on Drawings.")
