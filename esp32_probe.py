"""
ESP32 live probe
- Opens the serial port
- Pulses the auto-reset circuit (RTS -> EN, DTR -> IO0)
- Captures the boot log
- Optionally sends a line and listens for a reply

Usage:
    python esp32_probe.py                 # boot log only
    python esp32_probe.py --send "hello"  # boot log + send a line
"""

import argparse
import sys
import time

import serial

from esp32_port import resolve_port_or_die


def reset_into_run_mode(ser: serial.Serial) -> None:
    """Classic ESP32 auto-reset sequence (esptool-compatible)."""
    ser.setDTR(False)
    ser.setRTS(True)     # EN low  -> chip held in reset
    time.sleep(0.15)
    ser.setDTR(False)
    ser.setRTS(False)    # EN high -> boot normally
    time.sleep(0.05)


def read_for(ser: serial.Serial, seconds: float, label: str) -> bytes:
    deadline = time.time() + seconds
    buf = bytearray()
    while time.time() < deadline:
        chunk = ser.read(ser.in_waiting or 1)
        if chunk:
            buf.extend(chunk)
    text = buf.decode("utf-8", errors="replace")
    print(f"\n--- {label} ({len(buf)} bytes) ---")
    print(text if text.strip() else "(no output)")
    return bytes(buf)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=None,
                    help="serial port (auto-detected from the CH340 id by default)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--send", default=None, help="line to send after boot")
    args = ap.parse_args()

    port = resolve_port_or_die(args.port)

    print(f"Opening {port} @ {args.baud} ...")
    try:
        ser = serial.Serial(port, args.baud, timeout=0.1)
    except serial.SerialException as exc:
        print(f"FAILED to open port: {exc}")
        return 1

    with ser:
        ser.reset_input_buffer()
        reset_into_run_mode(ser)

        # Boot log is emitted at 115200 on most ESP32 dev boards.
        read_for(ser, 2.5, "BOOT LOG")

        if args.send:
            payload = (args.send + "\n").encode()
            ser.write(payload)
            ser.flush()
            print(f">>> sent: {args.send!r}")
            read_for(ser, 3.0, "RESPONSE")

    print("\nDone. If the boot log shows a ROM banner, the chip and wiring are good.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
