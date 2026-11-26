"""Delivery layer for slot-release alerts (spec §5.4, R33–R38).

Send-first, coalesce-after (R33): the first batch of a round goes out
immediately — no pre-send waiting window. Everything else in the same call
is coalesced into ONE follow-up 「補充」 message, so a burst of 30 events
costs at most 2 messages. The 15-second coalescing window is the caller's
accumulation window; this module never delays the first send.

Telegram is primary, ntfy the fallback. A message counts as delivered if
EITHER channel accepts it (R34); when both fail the batch is parked in the
``outbox`` table for :meth:`Notifier.flush_outbox` to retry.

The bot token only ever appears in the request URL — never in error
strings, payloads or the outbox (transport exception messages can embed
the URL, so only the exception type name is recorded).
"""

from __future__ import annotations

import html
import json
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from email.header import Header
from typing import Callable

import requests

from poller import db
from poller.diff import Event, is_alerting

MAX_LINES = 12                # per message; the rest become "…+N 場"
MAX_BATCH_CHARS = 4000        # format_batch plain-text target
TG_MAX_CHARS = 4096           # Telegram hard limit, measured on ESCAPED text (R35)
BACKOFF_SECONDS = (1, 5, 20)  # spec §5.4 retry ladder
TG_MAX_INLINE_SLEEP = 5        # I6: a 60s cycle cannot honour a longer 429
OUTBOX_RETRY_SECONDS = 60
MAX_OUTBOX_ATTEMPTS = 3 * 24 * 60  # ~3 days at one retry/minute (spec §5.4)

_WEEKDAYS = "一二三四五六日"
_SPORT_EMOJI = {
    "turf-soccer-pitch": "⚽",
    "tennis": "🎾",
    "basketball": "🏀",
    "volleyball": "🏐",
    "badminton": "🏸",
}
_SPORT_NAME = {
    "turf-soccer-pitch": "足球",
    "tennis": "網球",
    "basketball": "籃球",
    "volleyball": "排球",
    "badminton": "羽毛球",
}


def sport_name(sport: str) -> str:
    """Chinese display name for a dataset slug; unknown slugs pass through."""
    return _SPORT_NAME.get(sport, sport)


@dataclass
class DeliveryResult:
    """``delivered``: every message reached at least one channel (R34).

    ``via`` is "tg", "ntfy" or "tg+ntfy" (channels used across messages),
    None when nothing was delivered or nothing needed sending. ``errors``
    lists each failed channel's final error, even when the fallback saved
    the delivery. ``sent_seqs``/``parked_seqs`` (R37) partition the selected
    events per message so the cycle can mark ``notified_*`` per event:
    a channel accepted the message → its seqs in ``sent_seqs``; both
    channels failed → its seqs in ``parked_seqs`` (row in the outbox).
    """

    delivered: bool
    via: str | None = None
    errors: list[str] = field(default_factory=list)
    sent_seqs: list[int] = field(default_factory=list)
    parked_seqs: list[int] = field(default_factory=list)


def _format_date(value: date | str) -> str:
    """Human day label, e.g. ``11-28 (六)`` — never a date/datetime repr."""
    d = value if isinstance(value, date) else date.fromisoformat(value)
    return f"{d.month:02d}-{d.day:02d} ({_WEEKDAYS[d.weekday()]})"


def _format_line(ev: Event, mixed: bool = False) -> str:
    if ev.kind == "new":
        note = " (新)"
    elif ev.kind == "inc":
        note = f" (+{ev.after - ev.before})"
    elif ev.kind == "dec":
        note = f" ({ev.after - ev.before})"
    elif ev.kind == "gone":
        note = " (冇)"
    else:
        note = ""
    # A mixed-sport batch cannot rely on the header alone: label every line.
    label = f"[{sport_name(ev.sport)}] " if mixed else ""
    return (
        f"• {label}{_format_date(ev.date)} {ev.start}-{ev.end} "
        f"{ev.venue} {ev.facility} {ev.before}→{ev.after}{note}"
    )


def _render(events: list[Event], label: str = "放場") -> tuple[str, int]:
    """Build one message: header + up to MAX_LINES lines + overflow note.

    Returns ``(text, shown)`` where ``shown`` counts events with a line in
    the text. Overlong batches drop whole lines first, so splits always
    fall on event boundaries (R35); a single pathological line (e.g. a
    5000-character venue) is ellipsised. The hard 4096 cap is measured on
    the HTML-ESCAPED text: escaping expands ``&``/quotes up to 6×, so a
    plain-text cap alone cannot guarantee what actually goes on the wire.
    """
    if not events:
        return "", 0
    sports = list(dict.fromkeys(e.sport for e in events))
    if len(sports) == 1:
        emoji = _SPORT_EMOJI.get(sports[0], "🔔")
        header = f"{emoji} {sport_name(sports[0])} {label} ×{len(events)}"
        mixed = False
    else:
        emoji = "".join(_SPORT_EMOJI.get(s, "🔔") for s in sports)
        header = f"{emoji} {label} ×{len(events)}"
        mixed = True
    lines = [_format_line(e, mixed) for e in events[:MAX_LINES]]
    shown = len(lines)
    hidden = len(events) - shown
    while True:
        tail = f"…+{hidden} 場" if hidden else ""
        text = "\n".join([header, *lines] + ([tail] if tail else []))
        if len(text) <= MAX_BATCH_CHARS and len(html.escape(text)) <= TG_MAX_CHARS:
            return text, shown
        if len(lines) > 1:
            lines.pop()
            shown -= 1
            hidden += 1
        elif lines:
            # Ellipsise the plain line, then re-verify after escaping: keep
            # the longest prefix whose escaped form fits the remaining budget.
            overhead = len(html.escape(header)) + 1 + (
                len(html.escape(tail)) + 1 if tail else 0)
            budget = TG_MAX_CHARS - overhead - 1   # -1 for the ellipsis
            line = lines[0]
            lo, hi = 0, max(min(len(line), MAX_BATCH_CHARS - overhead - 1), 0)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if len(html.escape(line[:mid])) <= budget:
                    lo = mid
                else:
                    hi = mid - 1
            lines[0] = line[:lo] + "…"
        else:
            return text, shown


def _retry_after(resp) -> int | float | None:
    """Telegram 429 body: ``parameters.retry_after`` seconds (R35)."""
    try:
        value = resp.json()["parameters"]["retry_after"]
    except Exception:
        return None
    return value if isinstance(value, (int, float)) and value >= 0 else None


def _header_value(value: str) -> str:
    """HTTP headers must survive latin-1 encoding; ntfy decodes RFC 2047.

    Without this, a Chinese/emoji ``Title`` would raise on the wire and
    silently kill the fallback channel.
    """
    try:
        value.encode("latin-1")
        return value
    except UnicodeEncodeError:
        return Header(value, "utf-8").encode()


class Notifier:
    """Send alert batches over Telegram + ntfy; park failures in the outbox.

    ``conn`` is optional: when given, outbox writes use it (the cycle layer
    shares its connection); otherwise a short-lived connection to
    ``settings.db_path`` is opened only when a write is needed.
    """

    def __init__(self, settings, http=requests, conn: sqlite3.Connection | None = None):
        self.settings = settings
        self.http = http
        self.conn = conn

    # -- public API ---------------------------------------------------------

    def send_events(
        self, events: list[Event], channel_filter: Callable[[Event], bool]
    ) -> DeliveryResult:
        """Deliver one alert round: first batch now, the rest as one 補充.

        Events rejected by ``channel_filter`` are never sent. An empty
        selection is a vacuous success (nothing to deliver).
        """
        selected = [e for e in events if channel_filter(e)]
        if not selected:
            return DeliveryResult(True, None, [])
        errors: list[str] = []
        used: set[str] = set()
        delivered = True
        sent_seqs: list[int] = []
        parked_seqs: list[int] = []
        text, shown = _render(selected)
        groups = [(selected[:shown], text)]
        rest = selected[shown:]
        if rest:
            groups.append((rest, _render(rest, label="補充放場")[0]))
        for batch, plain in groups:
            title = plain.split("\n", 1)[0]
            tags = ",".join(dict.fromkeys(e.sport for e in batch))
            silent = not any(is_alerting(e) for e in batch)
            ok, via, errs = self._try_channels(plain, title, tags, silent)
            seqs = [e.seq for e in batch]
            if ok:
                used.add(via)
                sent_seqs.extend(seqs)
            else:
                delivered = False
                parked_seqs.extend(seqs)
                write_err = self._write_outbox(batch, plain, title, tags, silent, errs)
                if write_err:
                    errs.append(write_err)
            errors.extend(errs)
        via = "+".join(c for c in ("tg", "ntfy") if c in used) or None
        return DeliveryResult(delivered, via, errors, sent_seqs, parked_seqs)

    def format_batch(self, events: list[Event]) -> str:
        """One message: ≤12 lines, overflow as ``…+N 場``, ≤4000 chars."""
        return _render(events)[0]

    def send_summary(self, text: str, retries: int = 0) -> DeliveryResult:
        """Send one pre-formatted summary (R48) through TG→ntfy.

        The caller owns the text and the row bookkeeping (``mark_sale7_notified``);
        this method only delivers. ``retries=0`` by default so a sale7 summary
        can never stall the 60s facility loop for the full backoff ladder —
        the loop itself retries the still-unmarked rows next minute.
        """
        if not text:
            return DeliveryResult(True, None, [])
        title = text.split("\n", 1)[0]
        ok, via, errors = self._try_channels(
            text, title, "sale7", silent=False, retries=retries
        )
        return DeliveryResult(ok, via, errors)

    def flush_outbox(self, conn: sqlite3.Connection) -> int:
        """Retry due outbox rows once per channel; return the number resent.

        Success deletes the row and marks exactly the batch's seqs (the
        payload's ``seqs`` list, R38 — never a min..max range) notified on
        the channel that accepted; failure bumps ``attempts`` and schedules
        ``next_try`` 60s out. Rows that exhausted ~3 days of retries are
        dropped, and so are rows with a corrupt payload — a broken outbox
        must not crash the cycle. Single attempt per channel (no backoff
        sleeps) so a flush never blocks — the 60s cadence is the retry
        mechanism.
        """
        now = datetime.now(db.HK)
        now_iso = now.isoformat(timespec="seconds")
        next_try = (now + timedelta(seconds=OUTBOX_RETRY_SECONDS)).isoformat(timespec="seconds")
        sent = 0
        rows = conn.execute(
            "SELECT id, seq_from, seq_to, payload, attempts, next_try "
            "FROM outbox ORDER BY id"
        ).fetchall()
        for row in rows:
            if row["next_try"] and row["next_try"] > now_iso:
                continue
            if row["attempts"] >= MAX_OUTBOX_ATTEMPTS:
                conn.execute("DELETE FROM outbox WHERE id = ?", (row["id"],))
                conn.commit()
                continue
            try:
                payload = json.loads(row["payload"])
                send_args = (payload["text"], payload["title"],
                             payload["tags"], payload["silent"])
                # C3: the payload's seq list is bookkeeping, never input to
                # SQL. A row without a clean list of ints is corrupt: drop it
                # instead of interpolating whatever string is there.
                seqs = payload.get("seqs")
                if not isinstance(seqs, list) or not all(
                    isinstance(seq, int) and not isinstance(seq, bool)
                    for seq in seqs
                ):
                    raise ValueError("bad seqs")
            except (ValueError, TypeError, KeyError):
                # Corrupt row: drop it and keep flushing the rest.
                conn.execute("DELETE FROM outbox WHERE id = ?", (row["id"],))
                conn.commit()
                continue
            ok, via, errors = self._try_channels(*send_args, retries=0)
            if ok:
                conn.execute("DELETE FROM outbox WHERE id = ?", (row["id"],))
                if seqs:
                    column = "notified_tg" if via == "tg" else "notified_ntfy"
                    conn.execute(
                        f"UPDATE events SET {column} = 1, notify_err = NULL "
                        f"WHERE seq IN ({','.join('?' * len(seqs))})",
                        seqs,
                    )
                conn.commit()
                sent += 1
            else:
                conn.execute(
                    "UPDATE outbox SET attempts = attempts + 1, last_error = ?, "
                    "next_try = ? WHERE id = ?",
                    ("; ".join(errors), next_try, row["id"]),
                )
                conn.commit()
        return sent

    # -- channels -----------------------------------------------------------

    def _try_channels(
        self, plain: str, title: str, tags: str, silent: bool, retries: int = 3
    ) -> tuple[bool, str | None, list[str]]:
        """TG first, ntfy fallback; either acceptance delivers (R34)."""
        errors: list[str] = []
        ok, err = self._tg_send(html.escape(plain), silent, retries)
        if ok:
            return True, "tg", errors
        errors.append(err)
        ok, err = self._ntfy_send(plain, title, tags, retries)
        if ok:
            return True, "ntfy", errors
        errors.append(err)
        return False, None, errors

    def _tg_send(self, text: str, silent: bool, retries: int = 3) -> tuple[bool, str | None]:
        url = f"https://api.telegram.org/bot{self.settings.tg_token}/sendMessage"
        payload = {
            "chat_id": self.settings.tg_chat,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "disable_notification": silent,
        }
        if self.settings.tg_thread:
            payload["message_thread_id"] = self.settings.tg_thread
        error = "tg_unknown"
        for attempt in range(retries + 1):
            resp = None
            try:
                resp = self.http.post(url, json=payload, timeout=10)
            except Exception as exc:
                # Never str(exc): transport errors can embed the token URL.
                error = f"tg_{type(exc).__name__}"
            if resp is not None:
                if resp.status_code == 200:
                    try:
                        ok = bool(resp.json().get("ok"))
                    except Exception:
                        ok = False
                    if ok:
                        return True, None
                    error = "tg_not_ok"
                elif resp.status_code == 429:
                    error = "tg_429"
                    delay = _retry_after(resp)
                    if delay is not None:
                        if delay > TG_MAX_INLINE_SLEEP:
                            # I6: never block longer than 5s. Record the real
                            # retry_after, sleep the capped amount, then let
                            # ntfy (and, if that fails, the outbox) carry the
                            # batch — they already retry once a minute.
                            time.sleep(TG_MAX_INLINE_SLEEP)
                            error = f"tg_429_retry_after_{int(delay)}"
                            break
                        if attempt < retries:
                            time.sleep(delay)  # R35: exactly retry_after
                            continue
                else:
                    error = f"tg_http_{resp.status_code}"
            if attempt < retries:
                time.sleep(BACKOFF_SECONDS[attempt])
        return False, error

    def _ntfy_send(
        self, plain: str, title: str, tags: str, retries: int = 3
    ) -> tuple[bool, str | None]:
        url = self.settings.ntfy_url
        if not url:
            return False, "ntfy_unconfigured"
        headers = {
            "Title": _header_value(title),
            "Priority": "high",
            "Tags": _header_value(tags),
        }
        error = "ntfy_unknown"
        for attempt in range(retries + 1):
            resp = None
            try:
                resp = self.http.post(
                    url, data=plain.encode("utf-8"), headers=headers, timeout=10
                )
            except Exception as exc:
                error = f"ntfy_{type(exc).__name__}"
            if resp is not None:
                if resp.status_code in (200, 202):  # R36
                    return True, None
                error = f"ntfy_http_{resp.status_code}"
            if attempt < retries:
                time.sleep(BACKOFF_SECONDS[attempt])
        return False, error

    # -- outbox -------------------------------------------------------------

    def _write_outbox(
        self, batch: list[Event], plain: str, title: str, tags: str,
        silent: bool, errors: list[str],
    ) -> str | None:
        """Park a both-failed batch for flush_outbox; returns a write error.

        The payload carries the exact ``seqs`` list (R38): channel_filter
        selections are routinely non-contiguous, so a min..max range would
        mark events that were never in the batch.
        """
        seqs = [e.seq for e in batch]
        payload = json.dumps(
            {"text": plain, "title": title, "tags": tags, "silent": silent,
             "seqs": seqs},
            ensure_ascii=False,
        )
        now = datetime.now(db.HK)
        row = (
            min(seqs), max(seqs), "tg+ntfy", payload, 0,
            (now + timedelta(seconds=OUTBOX_RETRY_SECONDS)).isoformat(timespec="seconds"),
            "; ".join(errors),
        )
        conn = self.conn
        owned = conn is None
        if owned:
            conn = db.connect(self.settings.db_path)
        try:
            conn.execute(
                "INSERT INTO outbox "
                "(seq_from, seq_to, channel, payload, attempts, next_try, last_error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                row,
            )
            conn.commit()
        except Exception:
            # A broken outbox must not crash the cycle; the delivery errors
            # already surface to the caller.
            return "outbox_write_failed"
        finally:
            if owned:
                conn.close()
        return None
