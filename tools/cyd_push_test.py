#!/usr/bin/env python3
"""
End-to-end test of the push notifier (VM side) without touching the real VM.

  1. serve a fake changes-eve.json + today.json on localhost
  2. start tools/cyd_relay.py against it (--watch 1s, random ports)
  3. connect like the ESP32 does ("CYD PUSH 1") and wait for a RELEASE line
  4. flip the fake feed (new "g" + one release) and check the line arrives

Usage:  python tools/cyd_push_test.py
"""
from __future__ import annotations

import http.server
import json
import socket
import subprocess
import sys
import threading
import time

HERE = __file__.replace("\\", "/").rsplit("/", 1)[0]
RELAY = f"{HERE}/cyd_relay.py"

STATE = {
    "eve": {
        "g": "2026-11-04 08:00",
        "prev": {},
        "sports": {"badminton": [], "basketball": [], "volleyball": [],
                   "tennis": [], "turf-soccer-pitch": []},
    },
    # today.json deliberately does NOT contain 香港單車館 — the venue must be
    # resolved from the 7-day feed via the index.json manifest
    "today": {
        "g": "2026-11-04 08:00",
        "d": ["2026-11-04", "2026-11-05"],
        "sports": {
            "badminton": {
                "v": ["蒲崗村道體育館"],
                "s": ["黃大仙區"],
                "r": [[0, 0, 0, 1080, 1140, 1]],
            }
        },
    },
    "index": {
        "g": "2026-11-04 08:00",
        "s": {"badminton": {"t": 1, "d": 1, "f": "badminton-7d.json"}},
        "files": ["today.json", "badminton-7d.json"],
    },
    "badminton-7d": {
        "g": "2026-11-04 08:00",
        "v": ["香港單車館"],
        "s": ["九龍城區"],
        "d": ["2026-11-04", "2026-11-05"],
        "r": [[0, 0, 0, 1080, 1140, 1]],
    },
}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.startswith("/eve"):
            body = json.dumps(STATE["eve"], ensure_ascii=False).encode()
        elif self.path.startswith("/today"):
            body = json.dumps(STATE["today"], ensure_ascii=False).encode()
        elif self.path.startswith("/index"):
            body = json.dumps(STATE["index"], ensure_ascii=False).encode()
        elif self.path.startswith("/badminton-7d"):
            body = json.dumps(STATE["badminton-7d"], ensure_ascii=False).encode()
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # silence
        pass


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main() -> int:
    http_port = free_port()
    pool_port = free_port()
    front_port = free_port()

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", http_port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    cmd = [
        sys.executable, RELAY,
        "--pool", str(pool_port), "--front", str(front_port),
        "--bind", "127.0.0.1", "--watch", "1", "-v",
        "--feed-eve", f"http://127.0.0.1:{http_port}/eve.json",
        "--feed-today", f"http://127.0.0.1:{http_port}/today.json",
        "--feed-index", f"http://127.0.0.1:{http_port}/index.json",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1)

    def drain():
        for line in proc.stdout:
            print(f"  [daemon] {line.rstrip()}")

    threading.Thread(target=drain, daemon=True).start()
    time.sleep(1.5)

    # --- connect like the board ---
    s = socket.create_connection(("127.0.0.1", pool_port), timeout=10)
    s.sendall(b"CYD PUSH 1\r\n")
    ack = s.recv(16)
    print(f"  [board] handshake ack: {ack!r}")
    if not ack.startswith(b"OK"):
        print("FAIL: no OK ack")
        proc.kill()
        return 1

    s.settimeout(12)
    time.sleep(2.0)   # let the watcher baseline

    # --- flip the feed: new version + one release ---
    print("  [feed] flipping version and adding a release")
    STATE["eve"]["g"] = "2026-11-04 08:05"
    STATE["eve"]["sports"]["badminton"] = [
        ["2026-11-05", "香港單車館", "主場", 1080, 1140, "chg", 1, 3]
    ]

    # --- wait for the RELEASE line ---
    deadline = time.time() + 12
    buf = b""
    got = None
    while time.time() < deadline:
        try:
            chunk = s.recv(4096)
        except socket.timeout:
            break
        if not chunk:
            break
        buf += chunk
        if b"RELEASE " in buf:
            got = buf.split(b"RELEASE ", 1)[1].split(b"\r\n")[0]
            break

    s.close()
    proc.terminate()
    srv.shutdown()

    if not got:
        print("FAIL: no RELEASE line arrived")
        return 1

    payload = json.loads(got.decode("utf-8"))
    print(f"  [board] RELEASE {json.dumps(payload, ensure_ascii=False)}")

    checks = [
        ("venue", payload.get("venue"), "香港單車館"),
        ("district", payload.get("district"), "九龍城區"),
        ("sport", payload.get("sport"), "羽毛球"),
        ("facility", payload.get("facility"), "主場"),
        ("start", payload.get("start"), 1080),
        ("end", payload.get("end"), 1140),
        ("old", payload.get("old"), 1),
        ("new", payload.get("new"), 3),
    ]
    bad = [(n, got_v, want) for n, got_v, want in checks if got_v != want]
    if bad:
        for n, g, w in bad:
            print(f"FAIL: {n} = {g!r}, expected {w!r}")
        return 1

    print("PASS: push notifier delivered the release with venue + district")
    return 0


if __name__ == "__main__":
    sys.exit(main())
