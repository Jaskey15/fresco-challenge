"""Invariant handling in `_coerce_sets`."""

import logging

import pytest

from hardware_sets.extract import _coerce_sets


COMPONENT_KEYS = ("qty", "description", "catalog_number", "mfr", "finish", "notes")


def _component(**overrides):
    base = {k: None for k in COMPONENT_KEYS}
    base.update(overrides)
    return base


def _set_payload(
    *,
    set_number="1",
    description=None,
    page=1,
    line_range=(1, 5),
    continued_on=None,
    is_not_used=False,
    components=None,
):
    return {
        "set_number": set_number,
        "description": description,
        "location": {"page": page, "line_range": list(line_range)},
        "continued_on": list(continued_on or []),
        "is_not_used": is_not_used,
        "components": list(components or []),
    }


def _coerce(sets):
    return _coerce_sets({"sets": sets})


# --- auto-fix cases ------------------------------------------------------


def test_reversed_primary_line_range_is_swapped_and_warned(caplog):
    with caplog.at_level(logging.WARNING):
        result = _coerce([_set_payload(line_range=(10, 5))])
    assert result[0].location.line_range == (5, 10)
    messages = [r.getMessage() for r in caplog.records]
    assert any("line_range" in m and "1" in m for m in messages), messages


def test_reversed_continued_on_range_is_swapped_and_warned(caplog):
    with caplog.at_level(logging.WARNING):
        result = _coerce([_set_payload(
            continued_on=[{"page": 2, "line_range": [20, 12]}],
        )])
    assert result[0].continued_on[0].line_range == (12, 20)
    assert any("line_range" in r.getMessage() for r in caplog.records)


def test_already_ordered_line_range_is_unchanged_and_silent(caplog):
    with caplog.at_level(logging.WARNING):
        result = _coerce([_set_payload(line_range=(5, 10))])
    assert result[0].location.line_range == (5, 10)
    assert caplog.records == []


# --- log-and-keep cases --------------------------------------------------


def test_is_not_used_with_components_is_kept_verbatim_and_warned(caplog):
    payload = _set_payload(
        is_not_used=True,
        components=[_component(qty=1, description="X")],
    )
    with caplog.at_level(logging.WARNING):
        result = _coerce([payload])
    assert result[0].is_not_used is True
    assert len(result[0].components) == 1
    assert any("is_not_used" in r.getMessage() for r in caplog.records)


def test_blank_set_number_is_kept_and_warned(caplog):
    with caplog.at_level(logging.WARNING):
        result = _coerce([_set_payload(set_number="   ")])
    assert result[0].set_number == "   "
    assert any("set_number" in r.getMessage() for r in caplog.records)


def test_missing_location_still_raises(caplog):
    bad = _set_payload()
    del bad["location"]
    with pytest.raises(KeyError):
        _coerce([bad])


# --- clean response produces no warnings ---------------------------------


def test_well_formed_response_produces_no_warnings(caplog):
    with caplog.at_level(logging.WARNING):
        result = _coerce([
            _set_payload(
                set_number="1",
                description="Single door",
                line_range=(3, 12),
                continued_on=[{"page": 2, "line_range": [1, 4]}],
                components=[_component(qty=3, description="Hinge", mfr="IVE", finish="626")],
            ),
            _set_payload(set_number="2", page=2, line_range=(5, 9)),
        ])
    assert len(result) == 2
    assert caplog.records == []
