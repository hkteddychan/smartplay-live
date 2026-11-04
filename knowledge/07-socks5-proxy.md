# 07 — SOCKS5 Proxy Node

Turning the CYD into a SOCKS5 relay so a remote VM (AWS) can egress via the
home residential IP. Firmware: `firmware/esp32_socks5_proxy/`.

## Why standard RFC 1929 auth

The original sketch used a custom "send ACCESS_KEY as first line" gate.
Standard clients never do that, so we implemented RFC 1929
username/password sub-negotiation instead — transparent to
`curl --proxy socks5://user:pass@ip:1080`, PuTTY, proxychains, etc.

## Session state machine

```
PH_GREETING  [05 nmethods m1..mN]   -> pick 0x02 (or 0x00 if ALLOW_NO_AUTH)
PH_AUTH      [01 ulen user plen pass] -> 01 00 accept / 01 01 reject, close
PH_REQUEST   [05 cmd rsv atyp dst port] -> CONNECT only (cmd!=1 -> REP 0x07)
PH_RELAY     raw TCP pump both ways, 120 s idle timeout
```

Unsupported ATYP (IPv6 0x04) → REP 0x08. Target refused → REP 0x05.

## Hardening details that matter

- **Pipelining**: clients may send greeting+auth+request (+ first payload
  bytes) in one TCP segment. A single naive read loses the leftover. We keep
  a per-session buffer and `memmove`-shift away consumed bytes; leftovers
  flush into the remote socket when the tunnel opens.
- **Length validation per ATYP**: wait until `2+n`, `2+ulen+1+plen`,
  `10` (IPv4) / `5+dl+2` (domain) bytes exist before parsing. A malformed
  never-terminating buffer → "buffer full" kill + 20 s handshake timeout.
- **Blocking DNS/connect**: `WiFiClient::connect(host, port)` blocks the
  loop for the duration (~40 ms LAN, up to seconds worst case); other
  sessions pause briefly. Acceptable at 4 sessions.
- **EOF handling**: relay ends when either side reports `!connected() &&
  !available()` — read remaining bytes before killing.
- **WiFi**: `WiFi.setSleep(false)` for latency; reconnect + `server.begin()`
  re-run on drop; credentials from NVS `"cydmath"` / `ssid`,`pass` first,
  build flags as fallback.
- **LED**: green = ready, blue blink = session active, red = no WiFi.

## Verified

`tools/test-socks5.py` (raw socket, no libraries):

```
[1] greeting -> 0502 OK    [2] auth -> 0100 OK
[3] CONNECT example.com:80 -> 05 00 ... OK
[4] HTTP/1.1 200 OK over tunnel OK
[6] bad password -> 01 01 rejected OK
```

Standard client (`curl`): HTTP 200 in 0.2 s, HTTPS 200 in 0.45 s.
Serial: `[+] slot 0 ... [slot] auth ok ... [0->] example.com:80 -> OK (39 ms)`.

## NAT reality check（揀咗 B — reverse relay）

The ESP32 sits behind home NAT, so a remote VM cannot dial in. Instead the
ESP32 dials OUT to the VM every 5 s and keeps a pool of spare channels
(`tools/cyd_relay.py` on the VM). Protocol over the reverse channel:

```
ESP32 -> VM:9000 : "CYD RELAY 1\r\n"
VM    -> ESP32   : "OK\r\n"
then vanilla SOCKS5 flows VM-client -> ESP32 (auth teddy/pogo-teddy-2026)
```

Key firmware bits: `reversePump()` top-up worker, `Sess::reverse` flag,
reverse channels get the long (120 s) handshake-idle budget so pooled idle
channels survive; LAN SOCKS stays available simultaneously.

VM deploy: `tools/cyd_relay.py` + `tools/cyd_relay.service`, front bound to
`127.0.0.1:1080`, AWS SG opens 9000 to the home IP. Test from the VM:

```bash
curl --proxy 'socks5://teddy:pogo-teddy-2026@127.0.0.1:1080' https://example.com
```
