"""Resolve the ESP32 CYD's USB-serial port.

Windows assigns the COM number at plug time, so the board has shown up as
COM7 and then COM8 on the same machine.  These helpers resolve the port from
the CH340's hardware ID (USB\\VID_1A86&PID_7523) instead of a hardcoded
number, so the helper scripts can never end up poking an unrelated device.

Priority: explicit argument  >  ESP32_PORT env var  >  auto-detect.

Usage:
    from esp32_port import resolve_port
    port = resolve_port(sys.argv[1] if len(sys.argv) > 1 else None)
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

CH340_PNP = "VID_1A86"      # CH340 / CH341 family
ESP_USB_PNP = "VID_303A"    # ESP32-S2/S3 native USB (not this board, harmless)
ENV_VAR = "ESP32_PORT"

# pnputil answers in ~60 ms; the WMI/CIM equivalent takes ~10 s, so it is only
# a fallback for machines where pnputil is unavailable.
_PNPUTIL_ARGS = ["pnputil", "/enum-devices", "/connected", "/class", "Ports"]
_CIM_QUERY = (
    "Get-CimInstance -ClassName Win32_SerialPort | "
    "ForEach-Object { $_.DeviceID + '|' + $_.PNPDeviceID }"
)
_COM_IN_TEXT = re.compile(r"\((COM\d+)\)", re.IGNORECASE)


class Esp32PortError(RuntimeError):
    """Base class for port resolution failures."""


class Esp32PortNotFound(Esp32PortError):
    """No CH340 / ESP32 USB-serial port is attached."""


class Esp32PortAmbiguous(Esp32PortError):
    """More than one candidate port — the caller has to choose."""


def _parse_pnputil(text: str) -> list[tuple[str, str]]:
    """Pull (COM port, instance id) out of `pnputil /enum-devices` output.

    Each device is a block of "Key: value" lines:
        Instance ID:        USB\\VID_1A86&PID_7523\\5&54725E2&0&4
        Device Description: USB-SERIAL CH340 (COM8)
    """
    details: list[tuple[str, str]] = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        instance_id = ""
        description = ""
        for line in block.splitlines():
            s = line.strip()
            low = s.lower()
            if low.startswith("instance id:"):
                instance_id = s.split(":", 1)[1].strip()
            elif low.startswith("device description:"):
                description = s.split(":", 1)[1].strip()
        if not instance_id:
            continue
        m = _COM_IN_TEXT.search(description)
        if m:
            details.append((m.group(1).upper(), instance_id))
    return details


def _query_pnputil() -> list[tuple[str, str]]:
    try:
        proc = subprocess.run(
            _PNPUTIL_ARGS, capture_output=True, text=True, timeout=15, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return _parse_pnputil(proc.stdout)


def _query_cim() -> list[tuple[str, str]]:
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _CIM_QUERY],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    details: list[tuple[str, str]] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if "|" not in line:
            continue
        port, _, pnp = line.partition("|")
        port = port.strip().upper()
        if port.startswith("COM") and port[3:].isdigit():
            details.append((port, pnp.strip()))
    return details


def port_details() -> list[tuple[str, str]]:
    """(COM port, PNP hardware id) for every serial port on this machine."""
    details = _query_pnputil()
    return details if details else _query_cim()


def detect_ports() -> list[str]:
    """COM ports backed by the board's USB-serial chip."""
    return [p for p, pnp in port_details() if CH340_PNP in pnp or ESP_USB_PNP in pnp]


def resolve_port(explicit: str | None = None, detected: list[str] | None = None) -> str:
    """Return the COM port to talk to.

    explicit — port given by the caller, always wins
    detected — inject the candidate list instead of querying the OS
               (used by the tests to stay hardware independent)
    """
    if explicit:
        return explicit.strip().upper()

    env = os.environ.get(ENV_VAR, "").strip()
    if env:
        return env.upper()

    ports = list(detect_ports()) if detected is None else list(detected)
    if len(ports) == 1:
        return ports[0].upper()
    if not ports:
        raise Esp32PortNotFound(
            "no ESP32 serial port found (CH340 USB\\VID_1A86&PID_7523). "
            "Is the board plugged in with a data cable? "
            f"Set {ENV_VAR}=COMx to override."
        )
    raise Esp32PortAmbiguous(
        f"several ESP32 serial ports found: {', '.join(ports)}. "
        f"Set {ENV_VAR}=COMx to choose."
    )


def resolve_port_or_die(explicit: str | None = None, detected: list[str] | None = None) -> str:
    """resolve_port() for the helper scripts: explain the problem and exit(1)."""
    try:
        return resolve_port(explicit, detected)
    except Esp32PortError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
