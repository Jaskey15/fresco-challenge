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
    assert _match_start("E. Hardware Sets:") == "hardware_sets_colon"
    assert _match_start("D. Hardware Sets:") == "hardware_sets_colon"


def test_start_schedule_section_3dot():
    assert _match_start("   3.01 SCHEDULE") == "schedule_section_3dot"
    assert _match_start("  3.07 HARDWARE SCHEDULE") == "schedule_section_3dot"


def test_start_hardware_schedule_head():
    assert _match_start("\nHardware Schedule\n") == "hardware_schedule_head"


def test_start_group_or_set():
    assert _match_start("Hardware Group No. 01") == "group_or_set"
    assert _match_start("Hardware Set #1") == "group_or_set"
    assert _match_start("Hardware Group/Set #103") == "group_or_set"


def test_start_hw_number():
    assert _match_start("HW 01  Interior Single Bedroom") == "hw_number"


def test_start_set_label():
    assert _match_start("Set: EX-1.0") == "set_label"
    assert _match_start("Set: 1.0") == "set_label"


def test_start_set_hash():
    assert _match_start("Set #101") == "set_hash"
    assert _match_start("Set #SR38CL") == "set_hash"


def test_start_heading_number():
    assert _match_start("Heading #1") == "heading_number"
    assert _match_start("Heading #4") == "heading_number"


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
