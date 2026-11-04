"""Tests for esp32_port — resolving the CYD's CH340 USB-serial port.

Windows picks the COM number at plug time, so the board has shown up as
COM7 and then COM8 on the same machine.  These helpers resolve the port from
the CH340's hardware ID (USB\\VID_1A86&PID_7523) instead of a fixed number,
so the helper scripts can never end up poking an unrelated device.

Run:  python -m pytest test/test_esp32_port.py -v
"""
import os
import sys
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from esp32_port import (  # noqa: E402
    Esp32PortAmbiguous,
    Esp32PortNotFound,
    detect_ports,
    port_details,
    resolve_port,
    resolve_port_or_die,
)


class ResolvePortTests(unittest.TestCase):
    """Pure logic — the detected-port list is injected, no hardware needed."""

    def test_explicit_argument_wins_over_detected(self):
        self.assertEqual(resolve_port("COM3", detected=["COM8"]), "COM3")

    def test_explicit_argument_wins_over_env(self):
        with mock.patch.dict(os.environ, {"ESP32_PORT": "COM5"}):
            self.assertEqual(resolve_port("COM3", detected=["COM8"]), "COM3")

    def test_env_var_used_when_no_argument(self):
        with mock.patch.dict(os.environ, {"ESP32_PORT": "COM5"}):
            self.assertEqual(resolve_port(detected=["COM8"]), "COM5")

    def test_empty_env_var_is_ignored(self):
        with mock.patch.dict(os.environ, {"ESP32_PORT": ""}):
            self.assertEqual(resolve_port(detected=["COM8"]), "COM8")

    def test_detected_port_used_when_nothing_else(self):
        with mock.patch.dict(os.environ, {"ESP32_PORT": ""}):
            self.assertEqual(resolve_port(detected=["COM8"]), "COM8")

    def test_raises_when_no_port_found(self):
        with mock.patch.dict(os.environ, {"ESP32_PORT": ""}):
            with self.assertRaises(Esp32PortNotFound):
                resolve_port(detected=[])

    def test_raises_when_ambiguous(self):
        with mock.patch.dict(os.environ, {"ESP32_PORT": ""}):
            with self.assertRaises(Esp32PortAmbiguous):
                resolve_port(detected=["COM8", "COM9"])

    def test_or_die_returns_the_resolved_port(self):
        with mock.patch.dict(os.environ, {"ESP32_PORT": ""}):
            self.assertEqual(resolve_port_or_die(detected=["COM8"]), "COM8")

    def test_or_die_exits_non_zero_when_no_port(self):
        with mock.patch.dict(os.environ, {"ESP32_PORT": ""}):
            with self.assertRaises(SystemExit) as cm:
                resolve_port_or_die(detected=[])
        self.assertNotEqual(cm.exception.code, 0)


class DetectPortsTests(unittest.TestCase):
    """Live hardware — the board must be plugged in for these to pass."""

    def test_detected_ports_match_the_ch340_hardware_id(self):
        details = dict(port_details())
        expected = {p for p, pnp in details.items() if "VID_1A86" in pnp}
        self.assertEqual(set(detect_ports()), expected)

    def test_bluetooth_decoys_are_never_selected(self):
        decoys = {p for p, pnp in port_details() if pnp.startswith("BTHENUM")}
        for p in decoys:
            self.assertNotIn(p, detect_ports())

    def test_detected_port_is_a_real_com_port(self):
        real = [p for p, _ in port_details()]
        for p in detect_ports():
            self.assertIn(p, real)


if __name__ == "__main__":
    unittest.main()
