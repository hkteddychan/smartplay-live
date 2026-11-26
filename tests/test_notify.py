"""Task 9 — notify.py: send-first batching, 429 handling, outbox (R33–R36).

Every Notifier uses the real constructor (R6); HTTP is a fake and
``time.sleep`` is recorded, never waited.
"""

import json
from datetime import date
from email.header import decode_header

import pytest

from poller import db
from poller.config import Settings
from poller.diff import Event, is_alerting
from poller.notify import DeliveryResult, Notifier


def make_settings(**over):
    base = dict(
        tg_token="SECRET-TOKEN", tg_chat="1", tg_thread=1,
        ntfy_url="http://n/smartplay",
        r2_endpoint="", r2_bucket="", r2_access_key="", r2_secret_key="",
        db_path=":memory:",
    )
    base.update(over)
    return Settings(**base)


def ev(seq=1, kind="new", venue="香港單車館", facility="主場", day=date(2026, 11, 28),
       start="19:00", end="20:00", before=0, after=2, sport="badminton"):
    return Event(sport=sport, venue=venue, facility=facility, date=day, start=start,
                 end=end, kind=kind, before=before, after=after,
                 ts="2026-11-26T10:00:00+08:00", seq=seq)


class FakeResponse:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = {"ok": True} if body is None else body

    def json(self):
        return self._body


class FakeHttp:
    """Queued responses per channel; the last response repeats forever.

    An Exception item is raised instead of returned (transport failure).
    """

    def __init__(self, tg=None, ntfy=None):
        self.tg = list(tg) if tg else [FakeResponse(200)]
        self.ntfy = list(ntfy) if ntfy else [FakeResponse(200)]
        self.posts = []

    def post(self, url, json=None, data=None, headers=None, timeout=None, **kw):
        self.posts.append({"url": url, "json": json, "data": data,
                           "headers": headers, "timeout": timeout})
        queue = self.tg if "sendMessage" in url else self.ntfy
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def tg_posts(self):
        return [p for p in self.posts if "sendMessage" in p["url"]]

    @property
    def ntfy_posts(self):
        return [p for p in self.posts if "sendMessage" not in p["url"]]


def mem():
    c = db.connect(":memory:")
    db.init_db(c)
    return c


def record_sleeps(monkeypatch):
    sleeps = []
    monkeypatch.setattr("poller.notify.time.sleep", lambda s: sleeps.append(s))
    return sleeps


# --- send-first batching (R33) ---------------------------------------------

def test_first_batch_sent_immediately(monkeypatch):
    sleeps = record_sleeps(monkeypatch)
    http = FakeHttp()
    n = Notifier(make_settings(), http=http)
    result = n.send_events([ev()], lambda e: True)
    assert isinstance(result, DeliveryResult)
    assert len(http.posts) == 1 and "sendMessage" in http.posts[0]["url"]
    assert sleeps == []                      # R33: no pre-send waiting window
    assert http.posts[0]["timeout"] == 10
    payload = http.posts[0]["json"]
    assert payload["chat_id"] == "1" and payload["message_thread_id"] == 1
    assert payload["parse_mode"] == "HTML"
    assert payload["disable_web_page_preview"] is True
    assert payload["disable_notification"] is False
    assert result.delivered is True and result.via == "tg" and result.errors == []


def test_thirty_events_coalesce_to_two_messages(monkeypatch):
    record_sleeps(monkeypatch)
    http = FakeHttp()
    n = Notifier(make_settings(), http=http)
    events = [ev(seq=i, facility=f"{i}號場") for i in range(1, 31)]
    result = n.send_events(events, lambda e: True)
    assert result.delivered is True
    assert len(http.tg_posts) == 2           # first batch + ONE coalesced follow-up
    first = http.tg_posts[0]["json"]["text"]
    second = http.tg_posts[1]["json"]["text"]
    assert first.count("•") == 12
    assert "補充" in second and "…+6 場" in second
    assert len(first) <= 4000 and len(second) <= 4000


def test_format_batch_caps_at_12_with_overflow():
    n = Notifier(make_settings(), http=FakeHttp())
    text = n.format_batch([ev(seq=i) for i in range(1, 16)])
    assert text.count("•") == 12
    assert "…+3 場" in text and "×15" in text
    assert len(text) <= 4000


def test_format_batch_small_batch():
    n = Notifier(make_settings(), http=FakeHttp())
    text = n.format_batch([ev(seq=i) for i in range(1, 4)])
    assert "×3" in text and "…+" not in text


def test_long_venue_messages_stay_under_4096(monkeypatch):
    record_sleeps(monkeypatch)
    http = FakeHttp()
    n = Notifier(make_settings(), http=http)
    events = [ev(seq=i, venue="館" * 5000) for i in range(1, 31)]
    n.send_events(events, lambda e: True)
    assert len(http.tg_posts) == 2
    for post in http.tg_posts:
        assert len(post["json"]["text"]) < 4096   # R35 hard cap


@pytest.mark.parametrize("count", [1, 30])
def test_escape_heavy_venue_posts_stay_under_4096(monkeypatch, count):
    """R35: the 4096 cap applies to the ESCAPED payload, not the plain text.

    ``&"`` escapes to ``&amp;&quot;`` (11 chars per 2 plain), so a plain-text
    cap alone lets the POSTed text blow far past Telegram's hard limit.
    """
    record_sleeps(monkeypatch)
    http = FakeHttp()
    n = Notifier(make_settings(), http=http)
    events = [ev(seq=i, venue='&"' * 2500) for i in range(1, count + 1)]
    result = n.send_events(events, lambda e: True)
    assert result.delivered is True
    assert http.tg_posts
    for post in http.tg_posts:
        text = post["json"]["text"]
        assert len(text) <= 4096               # measured on the escaped text
        assert "&amp;" in text                 # still HTML-escaped, not raw


# --- formatting -------------------------------------------------------------

def test_date_is_human_readable(monkeypatch):
    record_sleeps(monkeypatch)
    http = FakeHttp()
    n = Notifier(make_settings(), http=http)
    n.send_events([ev(day=date(2026, 11, 28))], lambda e: True)
    text = http.tg_posts[0]["json"]["text"]
    assert "11-28 (六)" in text
    assert "2026-11-28" not in text and "datetime" not in text


def test_html_escape_user_strings(monkeypatch):
    record_sleeps(monkeypatch)
    nasty = '<b>A&B</b>"x'
    http = FakeHttp()
    n = Notifier(make_settings(), http=http)
    n.send_events([ev(venue=nasty, facility="<i>主場</i>")], lambda e: True)
    text = http.tg_posts[0]["json"]["text"]
    assert "&lt;b&gt;A&amp;B&lt;/b&gt;" in text
    assert "<b>" not in text and "<i>" not in text

    http2 = FakeHttp(tg=[FakeResponse(500)], ntfy=[FakeResponse(200)])
    n2 = Notifier(make_settings(), http=http2)
    n2.send_events([ev(venue=nasty)], lambda e: True)
    body = http2.ntfy_posts[0]["data"].decode("utf-8")
    assert nasty in body                     # ntfy body stays plain text


@pytest.mark.parametrize("kinds,silent", [
    (["dec", "gone"], True),
    (["new"], False),
    (["inc", "dec"], False),
])
def test_disable_notification_only_for_non_alerting(monkeypatch, kinds, silent):
    record_sleeps(monkeypatch)
    http = FakeHttp()
    n = Notifier(make_settings(), http=http)
    counts = {"new": (0, 2), "inc": (1, 3), "dec": (2, 1), "gone": (2, 0)}
    events = [ev(seq=i, kind=k, before=counts[k][0], after=counts[k][1])
              for i, k in enumerate(kinds, 1)]
    n.send_events(events, lambda e: True)
    assert http.tg_posts[0]["json"]["disable_notification"] is silent


def test_channel_filter_selects_events(monkeypatch):
    record_sleeps(monkeypatch)
    http = FakeHttp()
    n = Notifier(make_settings(), http=http)
    result = n.send_events(
        [ev(seq=1, kind="new"), ev(seq=2, kind="dec", before=2, after=1)], is_alerting)
    text = http.tg_posts[0]["json"]["text"]
    assert "×1" in text and "(新)" in text
    assert result.delivered is True


def test_empty_after_filter_sends_nothing(monkeypatch):
    record_sleeps(monkeypatch)
    http = FakeHttp()
    n = Notifier(make_settings(), http=http)
    result = n.send_events([ev(kind="dec", before=2, after=1)], is_alerting)
    assert http.posts == []
    assert result.delivered is True and result.via is None


# --- sport naming (Teddy 2026-11-26: every message says which sport) --------

@pytest.mark.parametrize("slug,name,emoji", [
    ("badminton", "羽毛球", "🏸"),
    ("basketball", "籃球", "🏀"),
    ("volleyball", "排球", "🏐"),
    ("tennis", "網球", "🎾"),
    ("turf-soccer-pitch", "足球", "⚽"),
])
def test_single_sport_header_names_the_sport(slug, name, emoji):
    n = Notifier(make_settings(), http=FakeHttp())
    text = n.format_batch([ev(sport=slug)])
    assert text.splitlines()[0] == f"{emoji} {name} 放場 ×1"
    assert f"[{name}]" not in text       # single sport: the header carries it


def test_mixed_batch_labels_every_line_and_header_shows_all_emojis():
    n = Notifier(make_settings(), http=FakeHttp())
    events = [
        ev(seq=1),
        ev(seq=2, sport="turf-soccer-pitch"),
        ev(seq=3, sport="tennis"),
    ]
    text = n.format_batch(events)
    assert text.splitlines()[0] == "🏸⚽🎾 放場 ×3"
    assert "• [羽毛球] 11-28 (六) 19:00-20:00 香港單車館 主場 0→2 (新)" in text
    assert "• [足球] 11-28 (六) 19:00-20:00 香港單車館 主場 0→2 (新)" in text
    assert "• [網球] 11-28 (六) 19:00-20:00 香港單車館 主場 0→2 (新)" in text


def test_posted_alert_text_names_the_sport(monkeypatch):
    record_sleeps(monkeypatch)
    http = FakeHttp()
    n = Notifier(make_settings(), http=http)
    n.send_events([ev(sport="turf-soccer-pitch")], lambda e: True)
    wire = http.tg_posts[0]["json"]["text"]
    assert wire.splitlines()[0] == "⚽ 足球 放場 ×1"


# --- Telegram 429 (R35) ------------------------------------------------------

def test_tg_429_waits_retry_after(monkeypatch):
    sleeps = record_sleeps(monkeypatch)
    http = FakeHttp(tg=[FakeResponse(429, {"parameters": {"retry_after": 4}}),
                        FakeResponse(200)])
    n = Notifier(make_settings(), http=http)
    result = n.send_events([ev()], lambda e: True)
    assert sleeps == [4]                     # R35: sleep exactly retry_after
    assert len(http.tg_posts) == 2
    assert result.delivered is True


def test_large_retry_after_caps_the_sleep_and_uses_ntfy(monkeypatch):
    """I6: a one-hour retry_after must not stall the 60s cycle.

    The outbox owns long waits; this round sends via ntfy immediately and
    records why TG was abandoned.
    """
    sleeps = record_sleeps(monkeypatch)
    http = FakeHttp(tg=[FakeResponse(429, {"parameters": {"retry_after": 3600}})],
                    ntfy=[FakeResponse(200)])
    n = Notifier(make_settings(), http=http)

    result = n.send_events([ev()], lambda e: True)

    assert all(sleep <= 5 for sleep in sleeps)
    assert len(http.tg_posts) == 1           # no pointless retry inside the cap
    assert len(http.ntfy_posts) == 1
    assert result.delivered is True and result.via == "ntfy"
    assert any("3600" in error for error in result.errors)


def test_tg_429_exhausted_writes_outbox(monkeypatch):
    sleeps = record_sleeps(monkeypatch)
    conn = mem()
    http = FakeHttp(tg=[FakeResponse(429, {"parameters": {"retry_after": 2}})],
                    ntfy=[FakeResponse(500)])
    n = Notifier(make_settings(), http=http, conn=conn)
    result = n.send_events([ev(seq=9)], lambda e: True)
    assert sleeps == [2, 2, 2, 1, 5, 20]     # 3 retries each, then ntfy ladder
    assert result.delivered is False
    rows = conn.execute("SELECT * FROM outbox").fetchall()
    assert len(rows) == 1 and rows[0]["seq_from"] == 9


# --- channel fallback + outbox (R34, R36) ------------------------------------

def test_tg_fail_falls_back_to_ntfy(monkeypatch):
    record_sleeps(monkeypatch)
    conn = mem()
    http = FakeHttp(tg=[FakeResponse(500)], ntfy=[FakeResponse(200)])
    n = Notifier(make_settings(), http=http, conn=conn)
    result = n.send_events([ev()], lambda e: True)
    assert result.delivered is True and result.via == "ntfy"
    assert result.errors == ["tg_http_500"]
    assert conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 0
    post = http.ntfy_posts[0]
    assert post["url"] == "http://n/smartplay"
    assert post["headers"]["Priority"] == "high"
    assert post["headers"]["Tags"] == "badminton"
    title = "".join(
        part.decode(enc or "utf-8") if isinstance(part, bytes) else part
        for part, enc in decode_header(post["headers"]["Title"]))
    assert "放場" in title
    body = post["data"].decode("utf-8")
    assert "香港單車館" in body and "&amp;" not in body


@pytest.mark.parametrize("status,ok", [
    (200, True), (202, True), (201, False), (404, False), (500, False),
])
def test_ntfy_success_contract(monkeypatch, status, ok):
    record_sleeps(monkeypatch)
    http = FakeHttp(tg=[FakeResponse(500)], ntfy=[FakeResponse(status)])
    n = Notifier(make_settings(), http=http, conn=mem())
    result = n.send_events([ev()], lambda e: True)
    assert result.delivered is ok            # R36: only 200/202 count


def test_ntfy_headers_are_ascii_safe(monkeypatch):
    record_sleeps(monkeypatch)
    http = FakeHttp(tg=[FakeResponse(500)], ntfy=[FakeResponse(200)])
    n = Notifier(make_settings(), http=http)
    n.send_events([ev()], lambda e: True)
    headers = http.ntfy_posts[0]["headers"]
    for value in headers.values():
        value.encode("latin-1")              # must not raise on the wire
    decoded = "".join(
        part.decode(enc or "utf-8") if isinstance(part, bytes) else part
        for part, enc in decode_header(headers["Title"]))
    assert "放場" in decoded


def test_both_channels_fail_writes_outbox(monkeypatch):
    record_sleeps(monkeypatch)
    conn = mem()
    http = FakeHttp(tg=[FakeResponse(500)], ntfy=[FakeResponse(503)])
    n = Notifier(make_settings(), http=http, conn=conn)
    result = n.send_events([ev(seq=5), ev(seq=6)], lambda e: True)
    assert result.delivered is False and result.via is None
    assert "tg_http_500" in result.errors and "ntfy_http_503" in result.errors
    rows = conn.execute("SELECT * FROM outbox").fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert row["seq_from"] == 5 and row["seq_to"] == 6
    assert row["attempts"] == 0 and row["next_try"]
    payload = json.loads(row["payload"])
    assert "香港單車館" in payload["text"]


def test_outbox_fallback_uses_settings_db_path(monkeypatch, tmp_path):
    record_sleeps(monkeypatch)
    path = str(tmp_path / "state.db")
    c = db.connect(path)
    db.init_db(c)
    c.close()
    http = FakeHttp(tg=[FakeResponse(500)], ntfy=[FakeResponse(500)])
    n = Notifier(make_settings(db_path=path), http=http)   # no conn injected
    result = n.send_events([ev(seq=3)], lambda e: True)
    assert result.delivered is False
    c = db.connect(path)
    rows = c.execute("SELECT seq_from, seq_to FROM outbox").fetchall()
    c.close()
    assert len(rows) == 1 and rows[0]["seq_from"] == 3


def test_errors_never_leak_token(monkeypatch):
    record_sleeps(monkeypatch)
    conn = mem()
    boom = RuntimeError("POST https://api.telegram.org/botSECRET-TOKEN/sendMessage failed")
    http = FakeHttp(tg=[boom], ntfy=[FakeResponse(500)])
    n = Notifier(make_settings(), http=http, conn=conn)
    result = n.send_events([ev()], lambda e: True)
    assert result.delivered is False
    assert all("SECRET-TOKEN" not in e for e in result.errors)
    assert "RuntimeError" in result.errors[0]
    row = conn.execute("SELECT last_error FROM outbox").fetchone()
    assert "SECRET-TOKEN" not in row["last_error"]


# --- flush_outbox -------------------------------------------------------------

def _seed_outbox(monkeypatch, conn, seq=5):
    """One failed delivery parked in the outbox, with its event in `events`."""
    record_sleeps(monkeypatch)
    http = FakeHttp(tg=[FakeResponse(500)], ntfy=[FakeResponse(500)])
    n = Notifier(make_settings(), http=http, conn=conn)
    e = ev(seq=seq)
    db.insert_events(conn, [e], seq_start=seq)
    result = n.send_events([e], lambda e: True)
    assert result.delivered is False
    return n


def _make_due(conn):
    """Simulate the 60s retry delay having elapsed."""
    conn.execute("UPDATE outbox SET next_try='2000-01-01T00:00:00+08:00'")
    conn.commit()


def test_flush_outbox_resends_deletes_and_marks(monkeypatch):
    conn = mem()
    n = _seed_outbox(monkeypatch, conn)
    _make_due(conn)
    n.http = FakeHttp()                      # channels recovered
    assert n.flush_outbox(conn) == 1
    assert conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 0
    row = conn.execute("SELECT notified_tg, notified_ntfy FROM events WHERE seq=5").fetchone()
    assert row["notified_tg"] == 1


def test_flush_outbox_via_ntfy_marks_ntfy(monkeypatch):
    conn = mem()
    n = _seed_outbox(monkeypatch, conn)
    _make_due(conn)
    n.http = FakeHttp(tg=[FakeResponse(500)], ntfy=[FakeResponse(202)])
    assert n.flush_outbox(conn) == 1
    row = conn.execute("SELECT notified_tg, notified_ntfy FROM events WHERE seq=5").fetchone()
    assert row["notified_ntfy"] == 1 and row["notified_tg"] == 0


def test_flush_outbox_failure_schedules_retry(monkeypatch):
    conn = mem()
    n = _seed_outbox(monkeypatch, conn)
    _make_due(conn)
    sleeps = record_sleeps(monkeypatch)
    assert n.flush_outbox(conn) == 0
    assert sleeps == []                      # flush never blocks on backoff
    row = conn.execute("SELECT * FROM outbox").fetchone()
    assert row["attempts"] == 1 and row["last_error"] and row["next_try"]


def test_flush_outbox_skips_rows_not_due(monkeypatch):
    conn = mem()
    n = _seed_outbox(monkeypatch, conn)
    conn.execute("UPDATE outbox SET next_try='2999-01-01T00:00:00+08:00'")
    conn.commit()
    n.http = FakeHttp()
    assert n.flush_outbox(conn) == 0
    assert n.http.posts == []
    assert conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 1


def test_flush_marks_only_batch_seqs_not_range(monkeypatch):
    """R38: channel_filter yields non-contiguous seqs (1 new, 2 dec, 3 inc →
    batch [1, 3]); flush must mark exactly the batch's seqs, never min..max."""
    record_sleeps(monkeypatch)
    conn = mem()
    events = [ev(seq=1, kind="new"),
              ev(seq=2, kind="dec", before=2, after=1),
              ev(seq=3, kind="inc", before=1, after=3)]
    db.insert_events(conn, events, seq_start=1)
    http = FakeHttp(tg=[FakeResponse(500)], ntfy=[FakeResponse(500)])
    n = Notifier(make_settings(), http=http, conn=conn)
    result = n.send_events(events, is_alerting)      # selects seq 1 and 3 only
    assert result.delivered is False
    row = conn.execute("SELECT payload FROM outbox").fetchone()
    assert json.loads(row["payload"])["seqs"] == [1, 3]
    _make_due(conn)
    n.http = FakeHttp()
    assert n.flush_outbox(conn) == 1
    rows = conn.execute(
        "SELECT seq, notified_tg, notified_ntfy FROM events ORDER BY seq"
    ).fetchall()
    assert [(r["seq"], r["notified_tg"], r["notified_ntfy"]) for r in rows] == [
        (1, 1, 0), (2, 0, 0), (3, 1, 0)]


def test_flush_outbox_drops_corrupt_row_and_continues(monkeypatch):
    conn = mem()
    n = _seed_outbox(monkeypatch, conn)              # good row (seq 5)
    conn.execute(
        "INSERT INTO outbox (seq_from, seq_to, channel, payload, attempts, next_try, last_error) "
        "VALUES (99, 99, 'tg+ntfy', '{corrupt', 0, '2000-01-01T00:00:00+08:00', 'x')"
    )
    conn.commit()
    _make_due(conn)
    n.http = FakeHttp()
    assert n.flush_outbox(conn) == 1                 # good row resent, corrupt dropped
    assert conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 0
    assert len(n.http.tg_posts) == 1                 # corrupt row never posted


@pytest.mark.parametrize("bad_seqs", ["5", [5, "6"], None, [True], [1.5]])
def test_flush_outbox_drops_rows_with_bad_seqs(monkeypatch, bad_seqs):
    """C3: a bad ``payload["seqs"]`` must skip+delete the row, not crash."""
    record_sleeps(monkeypatch)
    conn = mem()
    payload = json.dumps(
        {"text": "x", "title": "x", "tags": "badminton", "silent": False,
         "seqs": bad_seqs}
    )
    conn.execute(
        "INSERT INTO outbox (seq_from, seq_to, channel, payload, attempts, next_try, last_error) "
        "VALUES (1, 2, 'tg+ntfy', ?, 0, '2000-01-01T00:00:00+08:00', 'x')",
        (payload,),
    )
    conn.commit()
    http = FakeHttp()
    n = Notifier(make_settings(), http=http, conn=conn)

    assert n.flush_outbox(conn) == 0
    assert http.posts == []
    assert conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 0


def test_flush_outbox_bad_seqs_row_does_not_stop_good_rows(monkeypatch):
    conn = mem()
    n = _seed_outbox(monkeypatch, conn)              # good row, seq 5
    payload = json.dumps(
        {"text": "x", "title": "x", "tags": "x", "silent": False, "seqs": "bad"}
    )
    conn.execute(
        "INSERT INTO outbox (seq_from, seq_to, channel, payload, attempts, next_try, last_error) "
        "VALUES (9, 9, 'tg+ntfy', ?, 0, '2000-01-01T00:00:00+08:00', 'x')",
        (payload,),
    )
    conn.commit()
    _make_due(conn)
    n.http = FakeHttp()

    assert n.flush_outbox(conn) == 1
    assert conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 0
    assert conn.execute(
        "SELECT notified_tg FROM events WHERE seq = 5"
    ).fetchone()[0] == 1


def test_flush_outbox_corrupt_only_row_is_dropped(monkeypatch):
    conn = mem()
    n = _seed_outbox(monkeypatch, conn)
    conn.execute("UPDATE outbox SET payload = 'not json at all'")
    _make_due(conn)
    n.http = FakeHttp()
    assert n.flush_outbox(conn) == 0
    assert conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 0
    assert n.http.posts == []


# --- DeliveryResult seq tracking (R37) ----------------------------------------

def test_delivery_result_sent_seqs_on_success(monkeypatch):
    record_sleeps(monkeypatch)
    http = FakeHttp()
    n = Notifier(make_settings(), http=http)
    result = n.send_events([ev(seq=7), ev(seq=8)], lambda e: True)
    assert result.sent_seqs == [7, 8] and result.parked_seqs == []
    assert DeliveryResult(True).sent_seqs == []      # defaults are empty lists
    assert DeliveryResult(True).parked_seqs == []


def test_delivery_result_parked_seqs_on_both_fail(monkeypatch):
    record_sleeps(monkeypatch)
    conn = mem()
    http = FakeHttp(tg=[FakeResponse(500)], ntfy=[FakeResponse(500)])
    n = Notifier(make_settings(), http=http, conn=conn)
    result = n.send_events([ev(seq=5), ev(seq=6)], lambda e: True)
    assert result.delivered is False
    assert result.sent_seqs == [] and result.parked_seqs == [5, 6]


def test_delivery_result_tracks_seqs_per_message(monkeypatch):
    record_sleeps(monkeypatch)
    conn = mem()
    http = FakeHttp(tg=[FakeResponse(500)] * 4 + [FakeResponse(200)],
                    ntfy=[FakeResponse(500)])
    n = Notifier(make_settings(), http=http, conn=conn)
    events = [ev(seq=i) for i in range(1, 31)]
    result = n.send_events(events, lambda e: True)
    assert result.delivered is False and result.via == "tg"
    assert result.parked_seqs == list(range(1, 13))   # first batch both-failed
    assert result.sent_seqs == list(range(13, 31))    # 補充 delivered via TG


# --- sale7 summary (Task 11 / R48) -------------------------------------------

def test_send_summary_sends_one_preformatted_message(monkeypatch):
    record_sleeps(monkeypatch)
    http = FakeHttp()
    n = Notifier(make_settings(), http=http)
    text = "🛒 開賣 summary ×3\n• 香港單車館：2 場\n• 九龍公園：1 場"

    result = n.send_summary(text)

    assert result.delivered is True and result.via == "tg"
    assert result.sent_seqs == [] and result.parked_seqs == []
    assert len(http.posts) == 1 and "sendMessage" in http.posts[0]["url"]
    assert http.posts[0]["json"]["text"] == text
    assert http.posts[0]["json"]["disable_notification"] is False


def test_send_summary_is_a_vacuous_success_for_empty_text(monkeypatch):
    record_sleeps(monkeypatch)
    http = FakeHttp()
    n = Notifier(make_settings(), http=http)

    result = n.send_summary("")

    assert result.delivered is True and result.via is None
    assert http.posts == []
