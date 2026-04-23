from hardware_sets.confidence import (
    score_finish, score_mfr, build_mfr_frequency,
    score_catalog_number, score_qty, score_description,
    score_confidence, REVIEW_THRESHOLD,
)
from hardware_sets.types import Component, FieldScore, HardwareSet, SetLocation


def test_bhma_numeric_codes():
    assert score_finish("626") == FieldScore(1.0, None)
    assert score_finish("630") == FieldScore(1.0, None)
    assert score_finish("652") == FieldScore(1.0, None)
    assert score_finish("613") == FieldScore(1.0, None)


def test_us_codes():
    assert score_finish("US26D") == FieldScore(1.0, None)
    assert score_finish("US32D") == FieldScore(1.0, None)
    assert score_finish("US3") == FieldScore(1.0, None)
    assert score_finish("US10") == FieldScore(1.0, None)


def test_three_digit_metal_codes():
    assert score_finish("689") == FieldScore(1.0, None)
    assert score_finish("695") == FieldScore(1.0, None)


def test_color_words():
    assert score_finish("BSP") == FieldScore(1.0, None)
    assert score_finish("SATIN") == FieldScore(1.0, None)
    assert score_finish("BRASS") == FieldScore(1.0, None)
    assert score_finish("BRONZE") == FieldScore(1.0, None)
    assert score_finish("CHROME") == FieldScore(1.0, None)
    assert score_finish("BLACK") == FieldScore(1.0, None)
    assert score_finish("PAINTED ENAMEL") == FieldScore(1.0, None)
    assert score_finish("OIL RUBBED BRONZE") == FieldScore(1.0, None)
    assert score_finish("LIGHT BRONZE") == FieldScore(1.0, None)


def test_null_finish():
    assert score_finish(None) == FieldScore(1.0, None)


def test_unrecognized_finish():
    assert score_finish("XYZ") == FieldScore(0.5, "finish code not recognized")
    assert score_finish("FOOBAR") == FieldScore(0.5, "finish code not recognized")


def test_mfr_frequent_in_large_doc():
    freq = {"SCH": 3, "LCN": 5, "MK": 2}
    total_sets = 10
    assert score_mfr("SCH", freq, total_sets) == FieldScore(1.0, None)


def test_mfr_seen_once_no_finish_match_large_doc():
    freq = {"SCH": 3, "LCN": 5, "XYZ": 1}
    total_sets = 10
    assert score_mfr("XYZ", freq, total_sets) == FieldScore(0.7, "manufacturer code seen only once")


def test_mfr_matches_finish_pattern_large_doc():
    freq = {"SCH": 3, "626": 1}
    total_sets = 10
    assert score_mfr("626", freq, total_sets) == FieldScore(0.3, "matches finish pattern — possible mfr/finish swap")


def test_mfr_null():
    freq = {"SCH": 3}
    assert score_mfr(None, freq, 10) == FieldScore(1.0, None)


def test_mfr_small_doc_no_finish_match():
    freq = {"SCH": 1, "LCN": 1}
    total_sets = 3
    assert score_mfr("SCH", freq, total_sets) == FieldScore(1.0, None)


def test_mfr_small_doc_matches_finish():
    freq = {"SCH": 1, "626": 1}
    total_sets = 3
    assert score_mfr("626", freq, total_sets) == FieldScore(0.3, "matches finish pattern — possible mfr/finish swap")


def test_build_mfr_frequency():
    sets = [
        HardwareSet(
            set_number="1", description=None,
            location=SetLocation(page=1, line_range=(1, 5)),
            components=[
                Component(qty=1, description="Hinge", catalog_number=None, mfr="SCH", finish=None, notes=None),
                Component(qty=1, description="Lock", catalog_number=None, mfr="LCN", finish=None, notes=None),
            ],
        ),
        HardwareSet(
            set_number="2", description=None,
            location=SetLocation(page=1, line_range=(6, 10)),
            components=[
                Component(qty=1, description="Closer", catalog_number=None, mfr="SCH", finish=None, notes=None),
            ],
        ),
    ]
    freq = build_mfr_frequency(sets)
    assert freq == {"SCH": 2, "LCN": 1}


def test_catalog_alphanumeric():
    assert score_catalog_number("A156-18S") == FieldScore(1.0, None)
    assert score_catalog_number("8Q00010-003") == FieldScore(1.0, None)
    assert score_catalog_number("LM9200 EU") == FieldScore(1.0, None)


def test_catalog_null():
    assert score_catalog_number(None) == FieldScore(1.0, None)


def test_catalog_pure_numeric():
    assert score_catalog_number("12345") == FieldScore(0.5, "unusual catalog number format")


def test_catalog_pure_alpha():
    assert score_catalog_number("ABCDE") == FieldScore(0.5, "unusual catalog number format")


def test_catalog_looks_like_finish():
    assert score_catalog_number("US26D") == FieldScore(0.3, "looks like a finish/mfr code, not a catalog number")
    assert score_catalog_number("626") == FieldScore(0.3, "looks like a finish/mfr code, not a catalog number")


def test_qty_present():
    assert score_qty(3, has_siblings_with_qty=True) == FieldScore(1.0, None)


def test_qty_null_siblings_have_qty():
    assert score_qty(None, has_siblings_with_qty=True) == FieldScore(0.5, "missing quantity while other components have one")


def test_qty_null_no_siblings_have_qty():
    assert score_qty(None, has_siblings_with_qty=False) == FieldScore(1.0, None)


def test_description_normal():
    assert score_description("CONTINUOUS HINGE") == FieldScore(1.0, None)


def test_description_short():
    assert score_description("A") == FieldScore(0.5, "very short description — possible parsing artifact")
    assert score_description("AB") == FieldScore(0.5, "very short description — possible parsing artifact")


def test_description_null():
    assert score_description(None) == FieldScore(0.3, "missing description")


def _make_set(
    set_number: str,
    components: list[Component],
    continued_on: list[SetLocation] | None = None,
) -> HardwareSet:
    return HardwareSet(
        set_number=set_number,
        description=None,
        location=SetLocation(page=1, line_range=(1, 5)),
        components=components,
        continued_on=continued_on or [],
    )


def test_all_confident_set():
    sets = [_make_set("1", [
        Component(qty=1, description="HINGE", catalog_number="A156-18S", mfr="SCH", finish="626", notes=None),
        Component(qty=2, description="CLOSER", catalog_number="LM9200", mfr="SCH", finish="630", notes=None),
    ])]
    score_confidence(sets)
    assert sets[0].confidence == 1.0


def test_low_confidence_field_tanks_set():
    sets = [_make_set("1", [
        Component(qty=1, description="HINGE", catalog_number="A156-18S", mfr="SCH", finish="626", notes=None),
        Component(qty=1, description=None, catalog_number="LM9200", mfr="SCH", finish="630", notes=None),
    ])]
    score_confidence(sets)
    assert sets[0].confidence == 0.3


def test_page_break_penalty():
    sets = [_make_set(
        "1",
        [Component(qty=1, description="HINGE", catalog_number="A156-18S", mfr="SCH", finish="626", notes=None)],
        continued_on=[SetLocation(page=2, line_range=(1, 3))],
    )]
    score_confidence(sets)
    assert sets[0].confidence == 0.9


def test_page_break_penalty_floors_at_zero():
    sets = [_make_set(
        "1",
        [Component(qty=None, description=None, catalog_number=None, mfr=None, finish=None, notes=None)],
        continued_on=[SetLocation(page=2, line_range=(1, 3))],
    )]
    score_confidence(sets)
    assert sets[0].confidence >= 0.0


def test_component_confidence_dict_populated():
    sets = [_make_set("1", [
        Component(qty=1, description="HINGE", catalog_number="A156-18S", mfr="SCH", finish="XYZ", notes=None),
    ])]
    score_confidence(sets)
    conf = sets[0].components[0].confidence
    assert "finish" in conf
    assert conf["finish"].score == 0.5
    assert conf["finish"].reason == "finish code not recognized"
    assert conf["mfr"].score == 1.0


def test_review_threshold_boundary():
    assert REVIEW_THRESHOLD == 0.5
