from hardware_sets.extract import attach_bboxes
from hardware_sets.types import HardwareSet, NumberedLine, PageLayout, SetLocation


def _line(num: int, bbox: tuple[float, float, float, float] | None = None) -> NumberedLine:
    return NumberedLine(number=num, text=f"L{num}", bbox=bbox)


def test_single_set_gets_union_bbox():
    lines = [
        _line(1, (10, 100, 200, 112)),
        _line(2, (15, 115, 190, 127)),
        _line(3, (10, 130, 200, 142)),
    ]
    layout = PageLayout(page_number=1, lines=lines, page_width=612, page_height=792)
    sets = [
        HardwareSet(
            set_number="1",
            description=None,
            location=SetLocation(page=1, line_range=(1, 3)),
        )
    ]
    attach_bboxes(sets, [layout])
    assert sets[0].location.bbox == (10.0, 100.0, 200.0, 142.0)


def test_continued_on_gets_bbox():
    layout_p1 = PageLayout(
        page_number=1,
        lines=[_line(1, (10, 100, 200, 112)), _line(2, (10, 120, 200, 132))],
        page_width=612, page_height=792,
    )
    layout_p2 = PageLayout(
        page_number=2,
        lines=[_line(1, (20, 50, 180, 62)), _line(2, (20, 70, 180, 82))],
        page_width=612, page_height=792,
    )
    sets = [
        HardwareSet(
            set_number="1",
            description=None,
            location=SetLocation(page=1, line_range=(1, 2)),
            continued_on=[SetLocation(page=2, line_range=(1, 2))],
        )
    ]
    attach_bboxes(sets, [layout_p1, layout_p2])
    assert sets[0].location.bbox == (10.0, 100.0, 200.0, 132.0)
    assert sets[0].continued_on[0].bbox == (20.0, 50.0, 180.0, 82.0)


def test_missing_page_gives_none_bbox():
    sets = [
        HardwareSet(
            set_number="1",
            description=None,
            location=SetLocation(page=99, line_range=(1, 2)),
        )
    ]
    attach_bboxes(sets, [])
    assert sets[0].location.bbox is None


def test_line_without_bbox_gives_none():
    lines = [_line(1, (10, 100, 200, 112)), _line(2)]
    layout = PageLayout(page_number=1, lines=lines, page_width=612, page_height=792)
    sets = [
        HardwareSet(
            set_number="1",
            description=None,
            location=SetLocation(page=1, line_range=(1, 2)),
        )
    ]
    attach_bboxes(sets, [layout])
    assert sets[0].location.bbox is None
