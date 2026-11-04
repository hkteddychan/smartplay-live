#!/usr/bin/env python3
"""
CID relay — ESP32 CYD SOCKS5 proxy reverse tunnel (VM side)  [CydRelay]
+ 放場通知 push（SmartPLAY Live）

架構：
  VM 本地 client (curl) -> 本 front listener (:1080)
                          | byte relay
                          v
                    pool listener (:9000) <- ESP32 主動出連 (CYD RELAY 1)
                                             SOCKS5 greeting/auth/CONNECT 全由 ESP32 做

  同一個 pool port 亦收放場通知 push channel：
                    pool listener (:9000) <- ESP32 主動出連 (CYD PUSH 1)
                                             VM 一見到 feed 有更新就推落去 -> 板子即刻 beep

用法：
  python3 cyd_relay.py --pool 9000 --front 1080 --bind 127.0.0.1 -v
  sudo systemctl start cyd-relay     (見 cyd_relay.service)

AWS 注意：Security Group 要開 TCP 9000（ESP32 出連用，來源限你屋企 IP 最好）。
front 1080 只 bind loopback，外面連唔到。
"""
import argparse
import json
import queue
import socket
import sys
import threading
import time
import urllib.request

GREETING = b"CYD RELAY 1"
PUSH_GREETING = b"CYD PUSH 1"
ACK = b"OK\r\n"

FEED_EVE = "https://hkteddychan.github.io/smartplay-live/esp32/changes-eve.json"
FEED_TODAY = "https://hkteddychan.github.io/smartplay-live/esp32/today.json"
FEED_INDEX = "https://hkteddychan.github.io/smartplay-live/esp32/index.json"
VENUE_MAP_TTL = 3600.0  # 秒 — venue→district 對照表幾耐更新一次

SPORT_ZH = {
    "badminton": "羽毛球",
    "basketball": "籃球",
    "volleyball": "排球",
    "tennis": "網球",
    "turf-soccer-pitch": "草地足球",
}

push_clients: "list[socket.socket]" = []
push_lock = threading.Lock()
venue_district: "dict[str, str]" = {}
venue_map_at = 0.0
feed_version = ""

pool_q: "queue.Queue[socket.socket]" = queue.Queue()
stop = threading.Event()
LOG = False


def log(msg: str) -> None:
    if LOG:
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] {msg}", flush=True)


def set_keepalive(sock: socket.socket) -> None:
    """死鏈偵測：60 s 冇 byte 就探一次，3 次唔通切斷。"""
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    try:  # Linux values
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 15)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
    except (AttributeError, OSError):
        pass


def read_line(sock: socket.socket) -> bytes:
    """讀一行（\n 為止），最多 64 bytes。EOF / 超時 -> b\"\""""
    out = b""
    sock.settimeout(10)
    while len(out) < 64:
        try:
            b = sock.recv(1)
        except socket.timeout:
            return b""
        if not b or b == b"\n":
            return out
        if b != b"\r":
            out += b
    return out


def pool_server(port: int) -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(8)
    log(f"pool listening on :{port} (ESP32 dials in here)")
    while not stop.is_set():
        try:
            conn, addr = srv.accept()
        except OSError:
            break
        set_keepalive(conn)
        line = read_line(conn)
        if line.startswith(PUSH_GREETING):
            # 放場通知 push channel — keep the socket open and push to it
            conn.sendall(ACK)
            with push_lock:
                push_clients.append(conn)
            log(f"push: ESP32 channel from {addr[0]} (boards={len(push_clients)})")
            threading.Thread(target=hold_push_conn, args=(conn,), daemon=True).start()
            continue
        if not line.startswith(GREETING):
            log(f"pool: reject {addr[0]} bad greeting {line!r}")
            conn.close()
            continue
        conn.sendall(ACK)
        pool_q.put(conn)          # 邊個 session 用咗就唔會有人搶：單一 worker pop
        log(f"pool: ESP32 channel from {addr[0]} (queued, size={pool_q.qsize()})")
    srv.close()


# --------------------------------------------------------------------------
# 放場通知 push
# --------------------------------------------------------------------------
def hold_push_conn(conn: socket.socket) -> None:
    """Hold the board's socket open until it disconnects."""
    conn.settimeout(30.0)
    try:
        while not stop.is_set():
            try:
                if not conn.recv(1024):
                    break
            except socket.timeout:
                continue
            except OSError:
                break
    finally:
        with push_lock:
            if conn in push_clients:
                push_clients.remove(conn)
        try:
            conn.close()
        except OSError:
            pass
        log("push: board disconnected")


def broadcast(line: bytes) -> int:
    """Send one line to every connected board. Returns how many got it."""
    with push_lock:
        targets = list(push_clients)
    sent = 0
    dead = []
    for c in targets:
        try:
            c.sendall(line)
            sent += 1
        except OSError:
            dead.append(c)
    for c in dead:
        with push_lock:
            if c in push_clients:
                push_clients.remove(c)
        try:
            c.close()
        except OSError:
            pass
    return sent


def _harvest_sport(sp: dict, m: dict) -> None:
    venues = sp.get("v") or []
    dists = sp.get("s") or []
    for row in sp.get("r") or []:
        if len(row) < 2:
            continue
        vi, di = row[0], row[1]
        if 0 <= vi < len(venues) and 0 <= di < len(dists):
            m.setdefault(venues[vi], dists[di])


def _fetch_json(url: str):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def load_venue_map() -> None:
    """venue -> district（server 端查，板子唔使拉 30 KB 嘅 today.json）

    today.json 只包含「而家仲有位」嘅場地 —— 啱啱放出嚟嘅新場地未必喺入面，
    所以連 7 日檔一齊掃，覆蓋率先夠。
    """
    global venue_map_at
    m: "dict[str, str]" = {}

    def harvest(data) -> None:
        if "sports" in data:
            for sp in (data.get("sports") or {}).values():
                _harvest_sport(sp, m)
        else:
            _harvest_sport(data, m)

    try:
        harvest(_fetch_json(FEED_TODAY))
    except Exception as e:  # noqa: BLE001
        log(f"venue map: today.json failed ({e})")

    # 7 日檔（用 index.json manifest 攞檔名）—— 覆蓋多好多場地
    try:
        idx = _fetch_json(FEED_INDEX)
        base = FEED_INDEX.rsplit("/", 1)[0]
        for sport, meta in (idx.get("s") or {}).items():
            fname = meta.get("f")
            if not fname:
                continue
            try:
                harvest(_fetch_json(f"{base}/{fname}"))
            except Exception as e:  # noqa: BLE001
                log(f"venue map: {fname} failed ({e})")
    except Exception as e:  # noqa: BLE001
        log(f"venue map: index.json failed ({e})")

    venue_district.clear()
    venue_district.update(m)
    venue_map_at = time.time()
    log(f"venue map: {len(m)} venues")


def release_line(sport: str, ch: list) -> bytes:
    """Build one RELEASE line for the board."""
    date, venue, fac, sm, em, kind, old, new = (
        ch[0], ch[1], ch[2], ch[3], ch[4], ch[5], ch[6], ch[7]
    )
    payload = {
        "sport": SPORT_ZH.get(sport, sport),
        "district": venue_district.get(venue, ""),
        "venue": venue,
        "facility": fac,
        "date": date,
        "start": sm,
        "end": em,
        "old": old,
        "new": new,
    }
    return b"RELEASE " + json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\r\n"


def feed_watcher(interval: float) -> None:
    """Watch changes-eve.json; push every new release to the boards."""
    global feed_version
    while not stop.is_set():
        try:
            with urllib.request.urlopen(FEED_EVE, timeout=30) as r:
                data = json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            log(f"watch: fetch failed ({e})")
            stop.wait(interval)
            continue
        gen = data.get("g", "")
        if gen and gen != feed_version:
            first = not feed_version
            feed_version = gen
            if first:
                log("watch: baseline (no push)")
            else:
                if time.time() - venue_map_at > VENUE_MAP_TTL:
                    load_venue_map()
                n = 0
                for sport, changes in (data.get("sports") or {}).items():
                    for ch in changes or []:
                        if len(ch) < 8:
                            continue
                        kind = ch[5]
                        old, new = ch[6], ch[7]
                        is_release = (kind == "chg" and new > old) or kind == "new"
                        if not is_release:
                            continue
                        got = broadcast(release_line(sport, ch))
                        n += 1
                        log(f"push: [{sport}] {ch[1]} {ch[3]}-{ch[4]} {old}->{new} "
                            f"-> {got} board(s)")
                log(f"watch: {n} release(s) found")
        stop.wait(interval)


def grab_channel(timeout: float) -> socket.socket | None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            return pool_q.get(timeout=0.5)
        except queue.Empty:
            continue
    return None


def pump(a: socket.socket, b: socket.socket) -> None:
    try:
        a.settimeout(None)
        b.settimeout(None)
        while True:
            data = a.recv(65536)
            if not data:
                break
            b.sendall(data)
    except OSError:
        pass
    finally:
        try: b.shutdown(socket.SHUT_WR)
        except OSError: pass
        try: a.shutdown(socket.SHUT_WR)
        except OSError: pass


def front_server(port: int, bind: str) -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((bind, port))
    srv.listen(8)
    log(f"front listening on {bind}:{port} (bind VM apps here as socks5://..)")
    while not stop.is_set():
        try:
            cli, caddr = srv.accept()
        except OSError:
            break
        ch = grab_channel(timeout=15)
        if ch is None:
            log(f"front: {caddr} no ESP32 channel in pool, reject")
            cli.close()
            continue
        ch_isp = ch.getpeername()
        log(f"front: {caddr} <-> channel {ch_isp[0]}")
        t1 = threading.Thread(target=pump, args=(cli, ch), daemon=True)
        t2 = threading.Thread(target=pump, args=(ch, cli), daemon=True)
        t1.start()
        t2.start()

        def reap(t1=t1, t2=t2, ch=ch):
            t1.join()
            t2.join()
            ch.close()
            log("front: session closed; ESP32 will re-dial within ~5 s")

        threading.Thread(target=reap, daemon=True).start()
    srv.close()


def main() -> None:
    global LOG, FEED_EVE, FEED_TODAY, FEED_INDEX
    ap = argparse.ArgumentParser(description="CYD reverse relay (VM side)")
    ap.add_argument("--pool", type=int, default=9000, help="port ESP32 dials (default 9000)")
    ap.add_argument("--front", type=int, default=1080, help="local SOCKS front (default 1080)")
    ap.add_argument("--bind", default="127.0.0.1", help="front bind addr (default 127.0.0.1)")
    ap.add_argument("--watch", type=float, default=30.0,
                    help="seconds between feed checks for the push notifier (0 = off)")
    ap.add_argument("--feed-eve", default=FEED_EVE, help="changes-eve.json URL")
    ap.add_argument("--feed-today", default=FEED_TODAY, help="today.json URL")
    ap.add_argument("--feed-index", default=FEED_INDEX, help="index.json manifest URL")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    LOG = args.verbose

    FEED_EVE, FEED_TODAY, FEED_INDEX = args.feed_eve, args.feed_today, args.feed_index

    if args.bind != "127.0.0.1" and args.bind != "localhost":
        print("WARN: front bound to a non-loopback address — "
              "anyone reaching the VM can try the SOCKS login.", file=sys.stderr)

    threads = [
        threading.Thread(target=pool_server, args=(args.pool,), daemon=True),
        threading.Thread(target=front_server, args=(args.front, args.bind), daemon=True),
    ]
    if args.watch > 0:
        threads.append(threading.Thread(target=feed_watcher, args=(args.watch,), daemon=True))
    for t in threads:
        t.start()
    print("CydRelay up. VM側用法：", flush=True)
    print(f"  curl --proxy 'socks5://teddy:pogo-teddy-2026@{args.bind}:{args.front}' https://example.com", flush=True)
    print(f"  push notifier: watching changes-eve.json every {args.watch:g}s (boards dial in on :{args.pool})", flush=True)
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        stop.set()


if __name__ == "__main__":
    main()
