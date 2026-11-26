# tests/test_fetch.py
import json, pytest
from poller.fetch import fetch_dataset
from tests.conftest import FakeGateResponse

@pytest.mark.parametrize("resp,expected_error", [
    (FakeGateResponse(405, "text/html", "<html>405</html>"), "http_405"),
    (FakeGateResponse(200, "text/html", "<html>blocked</html>"), "html_response"),
    (FakeGateResponse(200, "application/json", "not-json"), "bad_json"),
    (FakeGateResponse(200, "application/json", "{}"), "not_list"),
    (FakeGateResponse(200, "application/json", "[]"), "empty_payload"),
])
def test_bad_responses_are_rejected(resp, expected_error):
    class G:
        def get(self, url, **kw): return resp
    r = fetch_dataset(G(), "http://x", "badminton")
    assert r.ok is False and r.error == expected_error

def test_good_response_parses():
    data = json.load(open("tests/fixtures/badminton_sample.json", encoding="utf-8"))
    class G:
        def get(self, url, **kw): return FakeGateResponse(200, "application/json", json.dumps(data))
    r = fetch_dataset(G(), "http://x", "badminton")
    assert r.ok and len(r.records) == len(data) and r.bytes > 0

def _payload(count):
    return [{"Available_Courts": 1, "Available_Date": "2026-11-27"}] * count


def test_relative_guard_rejects_a_payload_below_half_the_previous_count():
    """I3: 3000 rows after 10,000 is a truncated upstream, not a real shrink."""
    class G:
        def get(self, url, **kw):
            return FakeGateResponse(200, "application/json", json.dumps(_payload(3000)))

    r = fetch_dataset(G(), "http://x", "badminton", prev_count=10_000)

    assert r.ok is False and r.error == "suspiciously_small"


def test_relative_guard_accepts_sixty_percent_of_the_previous_count():
    class G:
        def get(self, url, **kw):
            return FakeGateResponse(200, "application/json", json.dumps(_payload(6000)))

    r = fetch_dataset(G(), "http://x", "badminton", prev_count=10_000)

    assert r.ok is True and len(r.records) == 6000


def test_relative_guard_accepts_a_first_run_without_a_baseline():
    class G:
        def get(self, url, **kw):
            return FakeGateResponse(200, "application/json", json.dumps(_payload(150)))

    r = fetch_dataset(G(), "http://x", "badminton", prev_count=None)

    assert r.ok is True


def test_fixture_uses_real_lcsd_columns():
    rows = json.load(open("tests/fixtures/badminton_sample.json", encoding="utf-8"))
    assert len(rows) == 150
    assert "Facility_Location_Name_TC" in rows[0]
    assert "Facility_Type_Name_TC" in rows[0]
    assert "Facility_Name_TC" not in rows[0]
