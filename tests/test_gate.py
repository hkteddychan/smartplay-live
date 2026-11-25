# tests/test_gate.py
import pytest
from poller.gate import Gate

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
