"""Read serial WITHOUT resetting the board, fire a SOCKS request, print logs."""
import subprocess
import sys
import threading
import time

import serial

from esp32_port import resolve_port_or_die

ip = sys.argv[1] if len(sys.argv) > 1 else "192.168.31.34"
port = resolve_port_or_die()

ser = serial.Serial(port, 115200, timeout=0.2)
ser.dtr = False  # CH340: 開 port 唔好拉 reset）
ser.rts = False

lines = []


def reader():
    while not stop.is_set():
        chunk = ser.readline()
        if chunk:
            try:
                lines.append(chunk.decode("utf-8", errors="replace").rstrip())
            except Exception:  # noqa: BLE001
                pass


stop = threading.Event()
t = threading.Thread(target=reader, daemon=True)
t.start()

proxy = f"socks5h://teddy:pogo-teddy-2026@{ip}:1080"
r = subprocess.run(
    ["curl", "-s", "--max-time", "15", "--proxy", proxy,
     "-o", "NUL", "-w", "curl: HTTP %{http_code}", "http://example.com"],
    capture_output=True, text=True)
print(f"curl rc={r.returncode}: {r.stdout} {r.stderr}")

time.sleep(2)
stop.set()
t.join(timeout=2)
ser.close()

print("\n--- device serial ---")
for ln in lines[-25:]:
    if ln:
        print(ln)
