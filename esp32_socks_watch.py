"""Watch SOCKS5 proxy boot over serial and print WiFi/IP status."""
import sys
import time

import serial

from esp32_port import resolve_port_or_die

port = resolve_port_or_die(sys.argv[1] if len(sys.argv) > 1 else None)
ser = serial.Serial(port, 115200, timeout=0.2)
ser.setDTR(False)
ser.setRTS(True)
time.sleep(0.15)
ser.setRTS(False)
time.sleep(0.05)

buf = bytearray()
deadline = time.time() + 20
while time.time() < deadline:
    chunk = ser.read(ser.in_waiting or 1)
    if chunk:
        buf.extend(chunk)
    if b"[SOCKS] listening" in buf:
        time.sleep(0.5)
        buf.extend(ser.read(ser.in_waiting))
        break

text = buf.decode("utf-8", errors="replace")
print(text[-2000:])
ser.close()
