"""Read the ESP32 serial port for N seconds and print everything."""
import sys
import time

import serial

from esp32_port import resolve_port_or_die

port = resolve_port_or_die(sys.argv[1] if len(sys.argv) > 1 else None)
seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 15.0

ser = serial.Serial(port, 115200, timeout=0.2)
ser.setDTR(False)
ser.setRTS(True)
time.sleep(0.15)
ser.setRTS(False)
time.sleep(0.05)

buf = bytearray()
deadline = time.time() + seconds
while time.time() < deadline:
    chunk = ser.read(ser.in_waiting or 1)
    if chunk:
        buf.extend(chunk)
ser.close()

print(buf.decode("utf-8", errors="replace"))
print(f"\n[{len(buf)} bytes captured]")
