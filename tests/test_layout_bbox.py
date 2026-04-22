"""Tests for layout.cluster_words_into_lines — pure math, no PDFs.

Hand-crafted word dicts mimic pdfplumber's `extract_words()` output.
Catches silent failures in the bbox highlighting that would otherwise
surface as 'highlight drawn in the wrong place'.
"""

from hardware_sets.layout import cluster_words_into_lines


def _w(text: str, x0: float, top: float, x1: float, bottom: float) -> dict:
    return {"text": text, "x0": x0, "top": top, "x1": x1, "bottom": bottom}


def test_three_distinct_lines_cluster_into_three_bboxes():
    words = [
        _w("SET", 50, 100, 75, 110),
        _w("1.1", 80, 100, 98, 110),
        _w("HINGE", 50, 120, 90, 130),
        _w("FOOTER", 50, 700, 100, 710),
    ]
    lines = cluster_words_into_lines(words, y_tol=2.0)

    assert len(lines) == 3
    # First line: union of two words at top=100
    assert lines[0] == (50.0, 100.0, 98.0, 110.0)
    # Second line
    assert lines[1] == (50.0, 120.0, 90.0, 130.0)
    # Third line
    assert lines[2] == (50.0, 700.0, 100.0, 710.0)


def test_words_within_tolerance_merge_into_same_line():
    # top values 100.0 and 100.8 should cluster together with y_tol=2.0
    words = [
        _w("A", 10, 100.0, 20, 110),
        _w("B", 25, 100.8, 35, 110.5),
    ]
    lines = cluster_words_into_lines(words, y_tol=2.0)
    assert len(lines) == 1
    assert lines[0] == (10.0, 100.0, 35.0, 110.5)


def test_empty_input_returns_empty():
    assert cluster_words_into_lines([], y_tol=2.0) == []


def test_output_is_sorted_top_down():
    # Feed words out of order; expect top-down output
    words = [
        _w("C", 10, 300, 20, 310),
        _w("A", 10, 100, 20, 110),
        _w("B", 10, 200, 20, 210),
    ]
    lines = cluster_words_into_lines(words, y_tol=2.0)
    assert len(lines) == 3
    tops = [b[1] for b in lines]
    assert tops == sorted(tops)
