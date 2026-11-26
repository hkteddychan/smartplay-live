# tests/test_http.py
"""C1 — realistic browser headers and a persistent cookie jar (spec §5.1.1).

The Alibaba anti-bot in front of LCSD latches on a bare ``python-requests``
User-Agent and issues a fresh ``acw_tc`` cookie per challenge; without a
persistent jar every cycle looks like a new client. These tests use a mounted
adapter, so nothing ever leaves the process.
"""

import json

import requests

import poller.main as main_module


class RecordingAdapter(requests.adapters.BaseAdapter):
    """Capture the PreparedRequest and answer 200 without any socket."""

    def __init__(self):
        super().__init__()
        self.requests = []

    def send(self, request, **kwargs):
        self.requests.append(request)
        response = requests.Response()
        response.status_code = 200
        response._content = b"[]"
        response.headers["Content-Type"] = "application/json"
        response.url = request.url
        response.request = request
        return response

    def close(self):
        pass


def make_session(tmp_path, logs=None):
    session = main_module.PersistentCookieSession(
        str(tmp_path / "cookies.json"), log=(logs.append if logs is not None else lambda _: None)
    )
    adapter = RecordingAdapter()
    session.mount("https://", adapter)
    return session, adapter


def test_requests_carry_realistic_browser_headers(tmp_path):
    session, adapter = make_session(tmp_path)

    session.get("https://data.smartplay.lcsd.gov.hk/rest/x")

    headers = adapter.requests[0].headers
    assert "SmartPlayLive/5.0" in headers["User-Agent"]
    assert "Chrome/" in headers["User-Agent"]
    assert headers["Accept"] == "application/json"
    assert headers["Accept-Encoding"] == "gzip, deflate"
    assert headers["Referer"] == "https://www.smartplay.lcsd.gov.hk/"
    assert headers["Accept-Language"] == "zh-HK,zh;q=0.9,en;q=0.8"


def test_cookies_round_trip_through_the_file(tmp_path):
    session, _ = make_session(tmp_path)
    session.cookies.set(
        "acw_tc", "abc123", domain="data.smartplay.lcsd.gov.hk", path="/"
    )
    session.save_cookies()

    saved = json.loads((tmp_path / "cookies.json").read_text(encoding="utf-8"))
    assert {"name": "acw_tc", "value": "abc123",
            "domain": "data.smartplay.lcsd.gov.hk", "path": "/"} in saved

    reloaded, _ = make_session(tmp_path)
    assert reloaded.cookies.get(
        "acw_tc", domain="data.smartplay.lcsd.gov.hk"
    ) == "abc123"


def test_successful_get_saves_the_cookie_jar(tmp_path):
    session, _ = make_session(tmp_path)
    session.cookies.set("acw_tc", "per-request")

    session.get("https://data.smartplay.lcsd.gov.hk/rest/x")

    assert (tmp_path / "cookies.json").exists()
    saved = json.loads((tmp_path / "cookies.json").read_text(encoding="utf-8"))
    assert any(item["name"] == "acw_tc" for item in saved)


def test_corrupt_cookie_file_is_logged_and_ignored(tmp_path):
    (tmp_path / "cookies.json").write_text("{not json", encoding="utf-8")
    logs = []

    session = main_module.PersistentCookieSession(
        str(tmp_path / "cookies.json"), log=logs.append
    )

    assert session.headers["Accept"] == "application/json"
    assert any("cookies" in line for line in logs)


def test_cookie_save_failure_is_logged_not_raised(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    logs = []
    session = main_module.PersistentCookieSession(
        str(blocker / "cookies.json"), log=logs.append
    )
    session.cookies.set("acw_tc", "x")

    session.save_cookies()  # must never take the cycle down

    assert any("cookies" in line for line in logs)
