# tests/test_gate.py
import pytest
from poller.gate import Gate, GateBackoff, SAFE_MODE_SECONDS

class FakeSession:
    def __init__(self): self.calls = []
    def get(self, url, **kw):
        self.calls.append(url)
        return type("R", (), {"status_code": 200, "headers": {}, "text": "{}", "json": lambda s: {}})()

def test_sequential_and_staggered():
    slept, fake = [], FakeSession()
    g = Gate(fake, sleep=lambda s: slept.append(s), jitter=lambda: 0)
    g.get("u1"); g.get("u2")
    assert len(slept) == 1 and 7 <= slept[0] <= 9

def test_405_enters_latch_and_ladder():
    g = Gate(FakeSession(), sleep=lambda s: None, jitter=lambda: 0)
    assert g.on_status(405) == 90
    assert g.state == "latch"
    assert g.on_status(405) == 150

def test_three_latches_within_30min_enters_safe_mode():
    g = Gate(FakeSession(), sleep=lambda s: None, jitter=lambda: 0)
    for _ in range(3): g.on_status(405)
    assert g.state == "safe" and g.safe_mode() is True

class StatusSession:
    """FakeSession with a switchable status code."""
    def __init__(self, status=200): self.status = status
    def get(self, url, **kw):
        return type("R", (), {"status_code": self.status, "headers": {}, "text": "", "json": lambda s: {}})()

def test_get_raises_gate_backoff_on_405_and_records_latch():
    class S:
        def get(self, url, **kw):
            return type("R", (), {"status_code": 405, "headers": {}, "text": "", "json": lambda s: {}})()
    g = Gate(S(), sleep=lambda s: None, jitter=lambda: 0)
    with pytest.raises(GateBackoff) as e:
        g.get("u")
    assert e.value.seconds == 90
    assert g.state == "latch"

def test_state_recovers_to_ok_after_success():
    s = StatusSession(405)
    g = Gate(s, sleep=lambda x: None, jitter=lambda: 0)
    with pytest.raises(GateBackoff):
        g.get("u")
    assert g.state == "latch"
    s.status = 200
    resp = g.get("u")
    assert resp.status_code == 200
    assert g.state == "ok"

def test_target_cycle_seconds_is_120_in_safe_mode():
    g = Gate(FakeSession(), sleep=lambda s: None, jitter=lambda: 0)
    assert g.target_cycle_seconds == 60
    for _ in range(3): g.on_status(405)
    assert g.target_cycle_seconds == 120

def test_success_during_safe_mode_stays_safe():
    s = StatusSession(405)
    g = Gate(s, sleep=lambda x: None, jitter=lambda: 0)
    for _ in range(3):
        with pytest.raises(GateBackoff):
            g.get("u")
    assert g.state == "safe"
    s.status = 200
    g.get("u")
    assert g.state == "safe" and g.target_cycle_seconds == 120

def test_safe_mode_expiry_recovers_state_lazily():
    now = [0.0]
    s = StatusSession(405)
    g = Gate(s, sleep=lambda x: None, clock=lambda: now[0], jitter=lambda: 0)
    for _ in range(3):
        with pytest.raises(GateBackoff):
            g.get("u")
    assert g.state == "safe" and g.target_cycle_seconds == 120
    now[0] = SAFE_MODE_SECONDS + 1
    assert g.safe_mode() is False
    assert g.state == "ok" and g.target_cycle_seconds == 60

def test_expiry_keeps_latch_recorded_after_expiry():
    # latches at t=0/10/20 -> safe mode (safe_until = 20 + 3600 = 3620)
    now = [0.0]
    s = StatusSession(405)
    g = Gate(s, sleep=lambda x: None, clock=lambda: now[0], jitter=lambda: 0)
    for t in (0.0, 10.0, 20.0):
        now[0] = t
        with pytest.raises(GateBackoff):
            g.get("u")
    assert g.state == "safe"
    # advance clock past safe_until; a 405 records a fresh latch
    safe_until = 20.0 + SAFE_MODE_SECONDS
    now[0] = safe_until + 80
    with pytest.raises(GateBackoff) as e:
        g.get("u")
    # first state read after expiry must NOT wipe the 5-second-old latch
    now[0] = safe_until + 85
    assert g.state == "latch"
    assert e.value.seconds == 90  # fresh ladder: out-of-window latches pruned
    assert g.safe_mode() is False and g.target_cycle_seconds == 60

def test_405_after_post_expiry_200_is_not_wiped():
    # 200 after expiry clears latches but leaves the expired _safe_until;
    # a new 405 before any state read must survive the lazy expiry cleanup.
    now = [0.0]
    s = StatusSession(405)
    g = Gate(s, sleep=lambda x: None, clock=lambda: now[0], jitter=lambda: 0)
    for t in (0.0, 10.0, 20.0):
        now[0] = t
        with pytest.raises(GateBackoff):
            g.get("u")
    now[0] = 20.0 + SAFE_MODE_SECONDS + 80
    s.status = 200
    g.get("u")
    s.status = 405
    with pytest.raises(GateBackoff):
        g.get("u")
    assert g.state == "latch"
