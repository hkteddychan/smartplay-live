# tests/test_seq.py
import json
import os

import pytest
import requests

from poller.seq import SeqAllocator, SeqConflict


class FakeR2:
    def __init__(self): self.val = {"seq": 100}; self.puts = 0
    def get(self, url, headers=None, timeout=None):
        class R: status_code = 200
        R.json = lambda s: dict(self.val); R.headers = {"ETag": "e1"}
        return R()
    def put(self, url, data=None, headers=None, timeout=None):
        self.puts += 1
        body = json.loads(data) if isinstance(data, str) else json.loads(data.decode())
        self.val = body
        class R: status_code = 200
        return R()


class ConflictR2(FakeR2):
    """First `fail_times` PUTs lose the race (412); a competitor advances seq."""
    def __init__(self, fail_times=1):
        super().__init__()
        self.fail_times = fail_times
        self.gets = 0
    def get(self, url, headers=None, timeout=None):
        self.gets += 1
        return super().get(url, headers=headers, timeout=timeout)
    def put(self, url, data=None, headers=None, timeout=None):
        if self.puts < self.fail_times:
            self.puts += 1
            self.val = {"seq": self.val["seq"] + 5}  # someone else advanced
            class R: status_code = 412
            return R()
        return super().put(url, data=data, headers=headers, timeout=timeout)


class FlakyR2(FakeR2):
    """FakeR2 that can be switched offline (both GET and PUT raise)."""
    def __init__(self):
        super().__init__()
        self.down = False
    def get(self, url, headers=None, timeout=None):
        if self.down: raise requests.ConnectionError("r2 down")
        return super().get(url, headers=headers, timeout=timeout)
    def put(self, url, data=None, headers=None, timeout=None):
        if self.down: raise requests.ConnectionError("r2 down")
        return super().put(url, data=data, headers=headers, timeout=timeout)


class DownR2:
    def get(self, url, headers=None, timeout=None):
        raise requests.ConnectionError("r2 down")
    def put(self, url, data=None, headers=None, timeout=None):
        raise requests.ConnectionError("r2 down")


def test_allocate_advances_counter(tmp_path):
    r2 = FakeR2()
    a = SeqAllocator("u", "t", str(tmp_path / "seq.json"), http=r2)
    start = a.allocate(3)
    assert start == 101 and r2.val["seq"] == 103


def test_two_consecutive_allocate_one_return_consecutive(tmp_path):
    r2 = FakeR2()
    a = SeqAllocator("u", "t", str(tmp_path / "seq.json"), http=r2)
    assert a.allocate(1) == 101
    assert a.allocate(1) == 102
    assert r2.val["seq"] == 102


def test_reserve_returns_new_counter(tmp_path):
    r2 = FakeR2()
    a = SeqAllocator("u", "t", str(tmp_path / "seq.json"), http=r2)
    assert a.reserve(3) == 103
    assert r2.val["seq"] == 103


def test_conflict_retries_once(tmp_path):
    r2 = ConflictR2(fail_times=1)
    a = SeqAllocator("u", "t", str(tmp_path / "seq.json"), http=r2)
    start = a.allocate(3)
    # competitor advanced 100 -> 105 on the 412; retry reserves 106..108
    assert start == 106 and r2.val["seq"] == 108
    assert r2.puts == 2 and r2.gets == 2


def test_second_conflict_raises_seq_conflict(tmp_path):
    r2 = ConflictR2(fail_times=99)
    a = SeqAllocator("u", "t", str(tmp_path / "seq.json"), http=r2)
    with pytest.raises(SeqConflict):
        a.allocate(1)
    assert r2.puts == 2  # exactly one retry, no infinite loop


def test_put_sends_if_match_auth_and_body(tmp_path):
    class RecordingR2(FakeR2):
        def put(self, url, data=None, headers=None, timeout=None):
            self.put_headers = headers
            self.put_body = data
            return super().put(url, data=data, headers=headers, timeout=timeout)
    r2 = RecordingR2()
    a = SeqAllocator("u", "t", str(tmp_path / "seq.json"), http=r2)
    a.allocate(3)
    assert r2.put_headers["If-Match"] == "e1"
    assert r2.put_headers["Authorization"] == "Bearer t"
    body = r2.put_body
    assert json.loads(body if isinstance(body, str) else body.decode()) == {"seq": 103}


def test_local_file_exact_shape_and_atomic_replace(tmp_path, monkeypatch):
    calls = []
    real_replace = os.replace
    def spy(src, dst):
        calls.append((src, dst))
        return real_replace(src, dst)
    monkeypatch.setattr("poller.seq.os.replace", spy)
    path = tmp_path / "seq.json"
    a = SeqAllocator("u", "t", str(path), http=FakeR2())
    a.allocate(3)
    assert len(calls) == 1
    assert calls[0][1] == str(path)  # temp file replaced onto target
    assert calls[0][0] != str(path)
    assert json.loads(path.read_text(encoding="utf-8")) == {"seq": 103}
    assert not (tmp_path / "seq.json.tmp").exists()


def test_r2_down_falls_back_with_buffer_and_degraded(tmp_path):
    path = tmp_path / "seq.json"
    path.write_text(json.dumps({"seq": 100}), encoding="utf-8")
    a = SeqAllocator("u", "t", str(path), http=DownR2())
    assert a.allocate(3) == 1101  # local 100 + 1000 buffer, first of block
    assert a.degraded is True
    assert json.loads(path.read_text(encoding="utf-8")) == {"seq": 1103}


def test_degraded_jump_is_at_least_1000(tmp_path):
    r2 = FlakyR2()
    a = SeqAllocator("u", "t", str(tmp_path / "seq.json"), http=r2)
    first = a.allocate(1)
    r2.down = True
    second = a.allocate(1)
    assert second - first >= 1000
    assert a.degraded is True


def test_degraded_resets_and_never_goes_backwards_on_recovery(tmp_path):
    r2 = FlakyR2()
    a = SeqAllocator("u", "t", str(tmp_path / "seq.json"), http=r2)
    assert a.allocate(1) == 101
    r2.down = True
    assert a.allocate(1) == 1102  # local 101 + 1000 + 1
    assert a.degraded is True
    r2.down = False
    # R2 still says 101 but local already issued up to 1102: must not reuse
    assert a.allocate(1) == 1103
    assert a.degraded is False
    assert r2.val["seq"] == 1103


def test_local_ahead_of_r2_heals_forward(tmp_path):
    path = tmp_path / "seq.json"
    path.write_text(json.dumps({"seq": 5000}), encoding="utf-8")
    r2 = FakeR2()  # stale authority at 100
    a = SeqAllocator("u", "t", str(path), http=r2)
    assert a.allocate(1) == 5001
    assert r2.val["seq"] == 5001


def test_local_write_failure_after_r2_success_rereads_r2(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a dir", encoding="utf-8")
    local = str(blocker / "seq.json")  # parent is a file: local writes fail
    r2 = FakeR2()
    a = SeqAllocator("u", "t", local, http=r2)
    assert a.allocate(1) == 101  # R2 write succeeded; local cache failure tolerated
    assert a.degraded is False
    assert a.allocate(1) == 102  # next allocate re-reads R2, not a stale local
    assert r2.val["seq"] == 102


def test_fallback_without_local_file_stays_positive(tmp_path):
    a = SeqAllocator("u", "t", str(tmp_path / "seq.json"), http=DownR2())
    assert a.allocate(1) == 1001  # 0 + 1000 buffer + 1
    assert a.degraded is True


def test_get_error_status_falls_back(tmp_path):
    class S:
        def get(self, url, headers=None, timeout=None):
            return type("R", (), {"status_code": 500})()
        def put(self, url, data=None, headers=None, timeout=None):
            raise AssertionError("must not write when GET failed")
    a = SeqAllocator("u", "t", str(tmp_path / "seq.json"), http=S())
    assert a.allocate(1) == 1001
    assert a.degraded is True


def test_put_network_error_falls_back(tmp_path):
    class PutDownR2(FakeR2):
        def put(self, url, data=None, headers=None, timeout=None):
            raise requests.ConnectionError("r2 down")
    path = tmp_path / "seq.json"
    path.write_text(json.dumps({"seq": 100}), encoding="utf-8")
    r2 = PutDownR2()
    a = SeqAllocator("u", "t", str(path), http=r2)
    assert a.allocate(1) == 1101
    assert a.degraded is True
    assert r2.val["seq"] == 100  # R2 untouched


class BootstrapR2:
    """Counter does not exist yet: GET 404 until a PUT creates it."""
    def __init__(self):
        self.val = None
        self.put_headers = None
        self.puts = 0
    def get(self, url, headers=None, timeout=None):
        if self.val is None:
            return type("R", (), {"status_code": 404})()
        class R: status_code = 200
        R.json = lambda s: dict(self.val); R.headers = {"ETag": "e1"}
        return R()
    def put(self, url, data=None, headers=None, timeout=None):
        self.puts += 1
        self.put_headers = headers
        body = json.loads(data) if isinstance(data, str) else json.loads(data.decode())
        self.val = body
        class R: status_code = 200
        return R()


def test_404_bootstraps_counter_instead_of_degrading(tmp_path):
    path = tmp_path / "seq.json"
    r2 = BootstrapR2()
    a = SeqAllocator("u", "t", str(path), http=r2)
    assert a.allocate(1) == 1
    assert a.degraded is False
    assert r2.put_headers["If-None-Match"] == "*"
    assert "If-Match" not in r2.put_headers
    assert r2.put_headers["Authorization"] == "Bearer t"
    assert r2.val == {"seq": 1}
    assert json.loads(path.read_text(encoding="utf-8")) == {"seq": 1}


def test_bootstrap_conflict_retries_once(tmp_path):
    class RacedBootstrapR2(BootstrapR2):
        def put(self, url, data=None, headers=None, timeout=None):
            if self.puts == 0:
                self.puts += 1
                self.val = {"seq": 7}  # competitor created the counter first
                class R: status_code = 412
                return R()
            return super().put(url, data=data, headers=headers, timeout=timeout)
    r2 = RacedBootstrapR2()
    a = SeqAllocator("u", "t", str(tmp_path / "seq.json"), http=r2)
    assert a.allocate(1) == 8  # re-read sees 7, reserves 8 with If-Match
    assert a.degraded is False
    assert r2.puts == 2
    assert r2.put_headers["If-Match"] == "e1"


def test_successful_read_uses_max_of_remote_and_local(tmp_path):
    path = tmp_path / "seq.json"
    path.write_text(json.dumps({"seq": 500}), encoding="utf-8")
    r2 = FakeR2()
    r2.val = {"seq": 120}  # stale authority behind the local cache
    a = SeqAllocator("u", "t", str(path), http=r2)
    assert a.allocate(1) == 501  # never at or below the 500 already issued
    assert r2.val["seq"] == 501


def test_transport_error_sets_degraded(tmp_path):
    path = tmp_path / "seq.json"
    path.write_text(json.dumps({"seq": 100}), encoding="utf-8")
    a = SeqAllocator("u", "t", str(path), http=DownR2())
    assert a.allocate(1) == 1101  # local 100 + 1000 buffer, first of block
    assert a.degraded is True


def test_n_below_one_raises_value_error(tmp_path):
    r2 = FakeR2()
    a = SeqAllocator("u", "t", str(tmp_path / "seq.json"), http=r2)
    with pytest.raises(ValueError):
        a.allocate(0)
    with pytest.raises(ValueError):
        a.allocate(-3)
    assert r2.puts == 0
