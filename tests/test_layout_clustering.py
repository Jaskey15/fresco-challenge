from hardware_sets.layout import cluster_words_into_lines


def _w(text: str, x0: float, top: float, x1: float, bottom: float) -> dict:
    return {"text": text, "x0": x0, "top": top, "x1": x1, "bottom": bottom}


def test_three_lines_cluster_correctly():
    words = [
        _w("SET", 50, 100, 75, 110),
        _w("1.1", 80, 100, 98, 110),
        _w("HINGE", 50, 120, 90, 130),
        _w("FOOTER", 50, 700, 100, 710),
    ]
    lines = cluster_words_into_lines(words, y_tol=2.0)
    assert len(lines) == 3
    assert lines[0] == ("SET 1.1", (50.0, 100.0, 98.0, 110.0))
    assert lines[1] == ("HINGE", (50.0, 120.0, 90.0, 130.0))
    assert lines[2] == ("FOOTER", (50.0, 700.0, 100.0, 710.0))


def test_words_within_tolerance_merge():
    words = [
        _w("A", 10, 100.0, 20, 110),
        _w("B", 25, 100.8, 35, 110.5),
    ]
    lines = cluster_words_into_lines(words, y_tol=2.0)
    assert len(lines) == 1
    assert lines[0] == ("A B", (10.0, 100.0, 35.0, 110.5))


def test_empty_input():
    assert cluster_words_into_lines([], y_tol=2.0) == []


def test_sorted_top_down_regardless_of_input_order():
    words = [
        _w("C", 10, 300, 20, 310),
        _w("A", 10, 100, 20, 110),
        _w("B", 10, 200, 20, 210),
    ]
    lines = cluster_words_into_lines(words, y_tol=2.0)
    assert len(lines) == 3
    tops = [bbox[1] for _, bbox in lines]
    assert tops == sorted(tops)


def test_words_sorted_by_x_within_line():
    words = [
        _w("WORLD", 80, 100, 120, 110),
        _w("HELLO", 10, 100, 60, 110),
    ]
    lines = cluster_words_into_lines(words, y_tol=2.0)
    assert lines[0][0] == "HELLO WORLD"
