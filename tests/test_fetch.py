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

def test_fixture_uses_real_lcsd_columns():
    rows = json.load(open("tests/fixtures/badminton_sample.json", encoding="utf-8"))
    assert len(rows) == 150
    assert "Facility_Location_Name_TC" in rows[0]
    assert "Facility_Type_Name_TC" in rows[0]
    assert "Facility_Name_TC" not in rows[0]
