# tests/test_diff.py
"""Pure diff engine: previous counts + current counts -> session events."""

from poller.diff import diff_sessions, is_evening

K = ("badminton", "A館", "主場", "2026-11-27", "19:00", "20:00")
TS = "2026-11-26T10:00:00+08:00"


def kinds(prev, cur):
    return sorted((e.kind, e.before, e.after) for e in diff_sessions(prev, cur, TS))


def test_new_inc_dec_gone():
    assert kinds({}, {K: 2}) == [("new", 0, 2)]
    assert kinds({K: 1}, {K: 3}) == [("inc", 1, 3)]
    assert kinds({K: 3}, {K: 1}) == [("dec", 3, 1)]
    assert kinds({K: 2}, {}) == [("gone", 2, 0)]


def test_no_event_when_unchanged():
    assert diff_sessions({K: 2}, {K: 2}, TS) == []


def test_evening_boundary():
    e = diff_sessions({}, {K: 1}, TS)[0]
    assert is_evening(e) is True
