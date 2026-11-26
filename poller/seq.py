"""Monotonic seq allocator behind a Worker route, with a local degraded mode.

The counter lives in R2 (`meta/seq.json`) but is reached only through a
Worker route (`GET`/`PUT` with `Authorization: Bearer <token>`); the poller
never speaks the R2 S3 API directly. R2 is the authority because Cloudflare
survives an Oracle rebuild; the local file is only a cache. A gap in the
sequence is safe, a duplicate is not: when the route is unreachable we
deliberately skip a block of FALLBACK_BUFFER numbers and flag `degraded`,
and we never write the counter backwards even if the local cache ran ahead
while R2 was down. A GET 404 means the counter does not exist yet: it is
bootstrapped at 0 and created with `If-None-Match: *`, not treated as an
outage.

R58: when `SEQ_URL` is empty (Plan 1, before the Worker `/seq` route exists)
the allocator runs **local-only**: sequential numbers from the local file with
no FALLBACK_BUFFER jump, `degraded=True` and `seq_source="local"`. There is no
R2 counter, so there is no gap to report with a resync.
"""

from __future__ import annotations

import json
import os

import requests

FALLBACK_BUFFER = 1000
HTTP_TIMEOUT = 10


class SeqConflict(Exception):
    """Raised when two consecutive conditional writes both lose the race."""


class _R2Unavailable(Exception):
    """Internal: R2 could not be read or written; caller may fall back."""


class SeqAllocator:
    """Reserve blocks of seq numbers; R2 authoritative, local file a cache."""

    def __init__(self, url: str, token: str, local_path: str, http=None) -> None:
        self._url = url
        self._token = token
        self._local_path = local_path
        self._http = http if http is not None else requests
        self.degraded = False
        # R58: "local" means configured for local-only operation (no Worker
        # route yet), not merely a transient R2 failure.
        self.seq_source = "local" if not (url or "").strip() else "r2"

    def allocate(self, n: int) -> int:
        """Reserve n seqs and return the FIRST seq of the block.

        allocate(3) with counter 100 returns 101 and leaves the counter 103.
        Raises ValueError for n < 1 and SeqConflict on a second 412.
        """
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            raise ValueError(f"n must be a positive int, got {n!r}")
        if self.seq_source == "local":
            return self._allocate_local_only(n)
        try:
            new = self.reserve(n)
        except _R2Unavailable:
            return self._allocate_local(n)
        try:
            self._save_local(new)
        except OSError:
            pass  # R2 succeeded and stays the authority; next allocate re-reads it
        self.degraded = False
        return new - n + 1

    def reserve(self, n: int) -> int:
        """Conditionally write {"seq": current + n} to the counter; return it.

        Uses If-Match with the ETag from the GET, or If-None-Match: * when
        the counter does not exist yet (GET 404 → bootstrap at 0). A 412
        means someone else advanced or created the counter: re-read once
        and retry; a second 412 raises SeqConflict. Raises _R2Unavailable
        on transport failures, timeouts and 5xx.
        """
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            raise ValueError(f"n must be a positive int, got {n!r}")
        for _ in range(2):  # initial attempt + exactly one retry after a 412
            current, etag = self._read_r2()
            # Never go backwards: the local cache may have run ahead in
            # degraded mode while R2 stayed stale. A forward gap is safe.
            current = max(current, self._read_local())
            new = current + n
            if self._write_r2(new, etag) != 412:
                return new
        raise SeqConflict("seq counter advanced twice during reserve; retry later")

    def _allocate_local(self, n: int) -> int:
        """R2 is down: skip FALLBACK_BUFFER numbers, persist, flag degraded."""
        base = self._read_local() + FALLBACK_BUFFER
        new = base + n
        self._save_local(new)  # must succeed: local is now the only record
        self.degraded = True
        return base + 1

    def _allocate_local_only(self, n: int) -> int:
        """R58: no R2 at all — plain sequential allocation, no block jump."""
        base = self._read_local()
        new = base + n
        self._save_local(new)  # must succeed: local is the only record
        self.degraded = True
        return base + 1

    def seed_at_least(self, seq: int) -> None:
        """Never restart below ``seq`` (I7: seed from ``MAX(events.seq)``).

        Losing ``seq.json`` must not hand out a number that already exists in
        ``events`` — that would crash-loop on the primary key.
        """
        if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
            raise ValueError(f"seq must be a non-negative int, got {seq!r}")
        if seq > self._read_local():
            self._save_local(seq)

    def _read_r2(self) -> tuple[int, str | None]:
        try:
            resp = self._http.get(
                self._url, headers=self._auth_headers(), timeout=HTTP_TIMEOUT
            )
        except requests.RequestException as exc:
            raise _R2Unavailable(f"GET {self._url}: {exc}") from exc
        if resp.status_code == 404:
            # Counter does not exist yet, not an outage: bootstrap at 0 and
            # let the reserve create it with If-None-Match: *.
            return 0, None
        if resp.status_code != 200:
            raise _R2Unavailable(f"GET {self._url} -> {resp.status_code}")
        etag = resp.headers.get("ETag") or resp.headers.get("etag")
        try:
            seq = resp.json()["seq"]
        except (ValueError, KeyError, TypeError) as exc:
            raise _R2Unavailable(f"GET {self._url}: bad payload: {exc}") from exc
        if not etag or not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
            raise _R2Unavailable(f"GET {self._url}: missing ETag or invalid seq")
        return seq, etag

    def _write_r2(self, new: int, etag: str | None) -> int:
        headers = self._auth_headers()
        if etag is None:
            headers["If-None-Match"] = "*"  # create-only: lose to a racer, 412
        else:
            headers["If-Match"] = etag
        headers["Content-Type"] = "application/json"
        try:
            resp = self._http.put(
                self._url,
                data=json.dumps({"seq": new}),
                headers=headers,
                timeout=HTTP_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise _R2Unavailable(f"PUT {self._url}: {exc}") from exc
        if resp.status_code == 412:
            return 412
        if not 200 <= resp.status_code < 300:
            raise _R2Unavailable(f"PUT {self._url} -> {resp.status_code}")
        return resp.status_code

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def _read_local(self) -> int:
        """Best-effort cache read; missing/corrupt file counts as 0."""
        try:
            with open(self._local_path, encoding="utf-8") as f:
                seq = json.load(f)["seq"]
        except (OSError, ValueError, KeyError, TypeError):
            return 0
        if isinstance(seq, int) and not isinstance(seq, bool) and seq >= 0:
            return seq
        return 0

    def _save_local(self, seq: int) -> None:
        """Atomic cache write: temp file + os.replace, shape {"seq": <int>}."""
        tmp = self._local_path + ".tmp"
        try:
            parent = os.path.dirname(self._local_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"seq": seq}, f)
                f.flush()
                os.fsync(f.fileno())  # I7: durable before the rename
            os.replace(tmp, self._local_path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
