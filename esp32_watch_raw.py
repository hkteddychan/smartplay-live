"""Long watch (no curl): boot + first relay dial attempt."""
import serial
import time
import sys

from esp32_port import resolve_port_or_die

port = resolve_port_or_die(sys.argv[1] if len(sys.argv) > 1 else None)
secs = int(sys.argv[2]) if len(sys.argv) > 2 else 40

ser = serial.Serial(port, 115200, timeout=0.2)
ser.dtr = False
ser.rts = False
buf = bytearray()
deadline = time.time() + secs
while time.time() < deadline:
    chunk = ser.read(ser.in_waiting or 1)
    if chunk:
        buf.extend(chunk)
        sys.stdout.write(chunk.decode("utf-8", errors="replace"))
ser.close()
