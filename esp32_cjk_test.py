"""Test CJK rendering path over serial (no crash = good)."""
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


def pump(seconds, label):
    deadline = time.time() + seconds
    while time.time() < deadline:
        chunk = ser.read(ser.in_waiting or 1)
        if chunk:
            buf.extend(chunk)
    text = buf.decode("utf-8", errors="replace")
    print(f"\n===== {label} =====")
    print(text[-1200:] if len(text) > 1200 else text)
    buf.clear()


pump(8.0, "boot")

ser.write(b"cjk\n")
ser.flush()
time.sleep(0.8)
pump(2.0, "after cjk sample")

ser.write(b"test question\n")
ser.flush()
pump(5.0, "after question")

# make sure it is still alive
ser.write(b"demo\n")
ser.flush()
pump(2.0, "still alive?")
ser.close()
