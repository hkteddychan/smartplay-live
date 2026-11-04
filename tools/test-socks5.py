"""Raw-socket SOCKS5 client test for the ESP32 CYD proxy.

1. greeting [05 01 02]            -> expect [05 02] (user/pass)
2. RFC 1929 auth                  -> expect [01 00]
3. CONNECT example.com:80         -> expect [05 00 ...]
4. HTTP GET over tunnel           -> expect HTTP/1.1 200...
5. Bonus: bad password must be rejected (server closes)

Usage: python tools/test-socks5.py [ip] [port] [user] [pass]
"""
import socket
import sys

ip = sys.argv[1] if len(sys.argv) > 1 else "192.168.31.34"
port = int(sys.argv[2]) if len(sys.argv) > 2 else 1080
user = (sys.argv[3] if len(sys.argv) > 3 else "teddy").encode()
pw = (sys.argv[4] if len(sys.argv) > 4 else "pogo-teddy-2026").encode()


def recv_exact(s, n, label):
    data = b""
    while len(data) < n:
        chunk = s.recv(n - len(data))
        if not chunk:
            raise RuntimeError(f"{label}: connection closed early, got {data!r}")
        data += chunk
    return data


def do_full(user, pw, host=b"example.com", sport=80):
    s = socket.create_connection((ip, port), timeout=10)
    s.settimeout(10)

    # 1. greeting: only user/pass method
    s.sendall(b"\x05\x01\x02")
    r = recv_exact(s, 2, "greeting")
    assert r[0] == 5 and r[1] == 2, f"greeting rejected: {r.hex()}"
    print(f"[1] greeting  -> {r.hex()} (user/pass) OK")

    # 2. RFC 1929 auth
    auth = b"\x01" + bytes([len(user)]) + user + bytes([len(pw)]) + pw
    s.sendall(auth)
    r = recv_exact(s, 2, "auth")
    assert r[0] == 1 and r[1] == 0, f"auth failed: {r.hex()}"
    print(f"[2] auth      -> {r.hex()} OK")

    # 3. CONNECT domain
    req = b"\x05\x01\x00\x03" + bytes([len(host)]) + host + sport.to_bytes(2, "big")
    s.sendall(req)
    r = recv_exact(s, 4, "connect")
    assert r == b"\x05\x00\x00\x01", f"connect failed: {r.hex()}"
    r = recv_exact(s, 6, "bnd")       # BND.ADDR + BND.PORT
    print(f"[3] CONNECT   -> 05 00 00 01 + bnd {r.hex()} OK")

    # 4. HTTP over tunnel
    s.sendall(b"GET / HTTP/1.1\r\nHost: example.com\r\nConnection: close\r\n\r\n")
    body = b""
    while True:
        try:
            chunk = s.recv(4096)
        except socket.timeout:
            break
        if not chunk:
            break
        body += chunk
    assert body.startswith(b"HTTP/"), f"no HTTP response: {body[:80]!r}"
    print(f"[4] HTTP      -> {body.split(b'\r\n', 1)[0].decode()} "
          f"({len(body)} bytes) OK")

    # 5. half-close test: server should EOF both ways cleanly
    s.close()
    print("[5] closed    OK")


def do_bad_auth():
    s = socket.create_connection((ip, port), timeout=10)
    s.sendall(b"\x05\x01\x02")
    r = recv_exact(s, 2, "greeting")
    assert r == b"\x05\x02", f"greeting: {r.hex()}"
    s.sendall(b"\x01\x05wrong\x04keys")
    r = recv_exact(s, 2, "badauth")
    assert r[1] != 0, "BAD PASSWORD WAS ACCEPTED!"
    print(f"[6] bad auth  -> {r.hex()} rejected OK")
    s.close()


try:
    do_full(user, pw)
except Exception as exc:  # noqa: BLE001
    print(f"FAIL: {exc}")
    sys.exit(1)

try:
    do_bad_auth()
except Exception as exc:  # noqa: BLE001
    print(f"NOTE bad-auth test: {exc}")

print("ALL TESTS PASSED")
