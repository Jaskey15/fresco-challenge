import time
from unittest.mock import patch

from hardware_sets_api import session


def test_put_and_get():
    sid = session.put(b"pdf-bytes", "test.pdf")
    assert isinstance(sid, str)
    assert len(sid) == 32
    result = session.get(sid)
    assert result == (b"pdf-bytes", "test.pdf")


def test_get_missing_returns_none():
    assert session.get("nonexistent-id-000000000000") is None


def test_entry_expires_after_ttl():
    base = time.monotonic()
    with patch.object(session, "time") as mock_time:
        mock_time.monotonic.return_value = base
        sid = session.put(b"data", "f.pdf")

        mock_time.monotonic.return_value = base + 1799
        assert session.get(sid) is not None

        mock_time.monotonic.return_value = base + 1801 + 1800
        assert session.get(sid) is None


def test_sliding_window_resets_ttl():
    base = time.monotonic()
    with patch.object(session, "time") as mock_time:
        mock_time.monotonic.return_value = base
        sid = session.put(b"data", "f.pdf")

        mock_time.monotonic.return_value = base + 1500
        assert session.get(sid) is not None

        mock_time.monotonic.return_value = base + 1500 + 1799
        assert session.get(sid) is not None
