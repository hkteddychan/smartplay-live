"""End-to-end test of the AI Math Tutor over serial.

1. reset the board
2. wait for boot + WiFi scan
3. send 'demo' to enter chat
4. send a question
5. capture the reply

Usage: python esp32_chat_test.py [COMx]
"""
import sys
import time

import serial

from esp32_port import resolve_port_or_die

port = resolve_port_or_die(sys.argv[1] if len(sys.argv) > 1 else None)
ser = serial.Serial(port, 115200, timeout=0.2)

# clean reset into run mode
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
    print(text[-1500:] if len(text) > 1500 else text)
    buf.clear()


pump(7.0, "boot")
ser.write(b"demo\n")
ser.flush()
time.sleep(0.8)
pump(1.5, "after demo")

ser.write(b"what is 2+2?\n")
ser.flush()
pump(5.0, "after question")

ser.close()
