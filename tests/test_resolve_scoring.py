"""Tests for resolve.py confidence scoring (pure logic)."""

from hardware_sets.resolve import validate_and_score
from hardware_sets.types import Component, HardwareSet, SetLocation


def _set(components: list[Component], *, is_not_used: bool = False) -> HardwareSet:
    return HardwareSet(
        set_number="1",
        description=None,
        location=SetLocation(page=1, line_range=(1, 10)),
        components=components,
        is_not_used=is_not_used,
    )


def _c(**kw) -> Component:
    defaults = dict(qty=1, description=None, catalog_number=None, mfr=None,
                    finish=None, notes=None)
    defaults.update(kw)
    return Component(**defaults)


def test_known_mfr_and_finish_score_high():
    s = _set([_c(mfr="SCH", finish="626")])
    [out] = validate_and_score([s])
    c = out.components[0]
    assert c.confidence["mfr"] == 1.0
    assert c.confidence["finish"] == 1.0
    assert out.confidence == 1.0


def test_mfr_that_looks_like_finish_scores_low():
    s = _set([_c(mfr="626", finish="SCH")])
    [out] = validate_and_score([s])
    c = out.components[0]
    assert c.confidence["mfr"] == 0.2
    assert c.confidence["finish"] == 0.2


def test_unknown_shortcode_mfr_plausible():
    s = _set([_c(mfr="XYZ", finish="US26D")])
    [out] = validate_and_score([s])
    c = out.components[0]
    assert c.confidence["mfr"] == 0.7
    assert c.confidence["finish"] == 1.0


def test_bhma_pattern_scores_finish_090():
    # 691 is in the US/BHMA range but (deliberately) also in our vocab.
    # Pick a BHMA code NOT in the vocab to hit the 0.9 branch.
    s = _set([_c(mfr="SCH", finish="615")])
    [out] = validate_and_score([s])
    assert out.components[0].confidence["finish"] == 0.9


def test_null_fields_score_full():
    s = _set([_c(mfr=None, finish=None)])
    [out] = validate_and_score([s])
    c = out.components[0]
    assert c.confidence["mfr"] == 1.0
    assert c.confidence["finish"] == 1.0


def test_not_used_set_confidence_is_one():
    s = _set([], is_not_used=True)
    [out] = validate_and_score([s])
    assert out.confidence == 1.0


def test_set_confidence_is_mean_of_component_mins():
    s = _set([
        _c(mfr="SCH", finish="626"),   # min 1.0
        _c(mfr="626", finish="SCH"),   # min 0.2
    ])
    [out] = validate_and_score([s])
    assert out.confidence == (1.0 + 0.2) / 2
