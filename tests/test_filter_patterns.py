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
    assert _match_start("DOOR HARDWARE SCHEDULE") == "door_hardware_schedule"


def test_start_hardware_sets_colon():
    assert _match_start("D. Hardware Sets:") == "hardware_sets_colon"


def test_start_schedule_section_3dot():
    assert _match_start("   3.01 SCHEDULE") == "schedule_section_3dot"


def test_start_group_1():
    assert _match_start("Hardware Group No. 01") == "group_1"
    assert _match_start("Hardware Set #1") == "group_1"


def test_start_no_match_on_narrative():
    assert _match_start("Hardware sets are indicated on Drawings.") is None


def test_end_of_section():
    assert END_OF_SECTION_RE.search("  END OF SECTION  ")


def test_current_section():
    assert _current_section("SECTION 08 71 00 — DOOR HARDWARE") == "087100"
    assert _current_section("SECTION 087100") == "087100"
    assert _current_section("hello world") is None


def test_heuristic_fallback_fires_on_three_signals():
    # bare SET token, QTY column, known mfr (SCH)
    text = "SET 1\n\nQTY  DESCRIPTION  MFR\n 1   Hinge        SCH"
    assert _heuristic_start(text)


def test_heuristic_does_not_fire_on_narrative():
    # Narrative paragraph with no SET/QTY/vocab signals
    assert not _heuristic_start(
        "The hardware sets specified in this section shall comply with the project requirements."
    )


def test_qty_ea_row_pattern_matches_real_table_rows():
    from hardware_sets.filter import _QTY_EA_ROW_RE
    assert _QTY_EA_ROW_RE.search("1        EA     CONT. HINGE")
    assert _QTY_EA_ROW_RE.search(" 3 EA HINGE 5BB1")
    assert _QTY_EA_ROW_RE.search("4        EA-R   ACTUATOR, TOUCH")


def test_qty_ea_row_pattern_rejects_prose():
    from hardware_sets.filter import _QTY_EA_ROW_RE
    # Prose that talks about door hardware schedules — no numeric EA rows
    assert not _QTY_EA_ROW_RE.search(
        "Door Hardware Schedule: Prepared by the Architectural Hardware Consultant."
    )
    assert not _QTY_EA_ROW_RE.search("Refer to Door and Frame Schedule on Drawings.")
