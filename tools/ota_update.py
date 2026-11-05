#!/usr/bin/env python3
"""
ota_update.py — SmartPLAY CYD OTA helper

Builds the firmware (optional), computes its SHA256, compares it with the last
successfully uploaded firmware, and uploads via espota only when needed.

Usage:
  python tools/ota_update.py --ip 192.168.31.34
  python tools/ota_update.py --ip 192.168.31.34 --no-build
  python tools/ota_update.py --ip 192.168.31.34 --check
  python tools/ota_update.py --ip 192.168.31.34 --force
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FW_DIR = ROOT / "firmware" / "esp32_smartplay"
BIN = FW_DIR / ".pio" / "build" / "esp32-cyd-smartplay" / "firmware.bin"
LAST_HASH_FILE = ROOT / ".work" / "ota_last_hash.txt"

DEFAULT_ESPOTA = Path(
    r"C:\Users\Teddy\.platformio\packages\framework-arduinoespressif32\tools\espota.py"
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def find_espota(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.exists():
            raise FileNotFoundError(f"espota not found: {p}")
        return p
    if DEFAULT_ESPOTA.exists():
        return DEFAULT_ESPOTA
    # Try PATH / common names
    for name in ("espota.py", "espota"):
        import shutil

        found = shutil.which(name)
        if found:
            return Path(found)
    raise FileNotFoundError(
        "espota.py not found. Pass --espota <path> or install PlatformIO ESP32 framework."
    )


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print(">", " ".join(str(x) for x in cmd))
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and OTA-upload SmartPLAY CYD firmware")
    parser.add_argument("--ip", default="192.168.31.34", help="ESP32 IP address")
    parser.add_argument("--port", type=int, default=3232, help="OTA port")
    parser.add_argument("--password", default="smartplay", help="OTA password")
    parser.add_argument("--no-build", action="store_true", help="Skip pio run")
    parser.add_argument("--check", action="store_true", help="Only check whether firmware changed")
    parser.add_argument("--force", action="store_true", help="Upload even if hash is unchanged")
    parser.add_argument("--progress", action="store_true", help="Show upload progress")
    parser.add_argument("--espota", help="Path to espota.py")
    args = parser.parse_args()

    if not args.no_build:
        print("[ota] building firmware...")
        run(["pio", "run"], cwd=FW_DIR)

    if not BIN.exists():
        print(f"[ota] firmware not found: {BIN}", file=sys.stderr)
        return 1

    new_hash = sha256_file(BIN)
    old_hash = ""
    if LAST_HASH_FILE.exists():
        old_hash = LAST_HASH_FILE.read_text(encoding="utf-8").strip()

    print(f"[ota] firmware: {BIN}")
    print(f"[ota] size    : {BIN.stat().st_size} bytes")
    print(f"[ota] sha256  : {new_hash}")
    if old_hash:
        print(f"[ota] last    : {old_hash}")

    if old_hash and new_hash == old_hash and not args.force:
        print("[ota] 韌體未變更，毋須更新。使用 --force 可強制上傳。")
        return 0

    if args.check:
        print("[ota] 韌體已變更，可執行更新。")
        return 0

    espota = find_espota(args.espota)
    cmd = [
        sys.executable,
        str(espota),
        "-i",
        args.ip,
        "-p",
        str(args.port),
        "-a",
        args.password,
        "-f",
        str(BIN),
    ]
    if args.progress:
        cmd.append("-r")

    print(f"[ota] uploading to {args.ip}:{args.port} ...")
    run(cmd)

    LAST_HASH_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAST_HASH_FILE.write_text(new_hash + "\n", encoding="utf-8")
    print("[ota] 更新成功，已記錄新韌體 hash。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as e:
        print(f"[ota] command failed with exit code {e.returncode}", file=sys.stderr)
        raise SystemExit(e.returncode)
    except Exception as e:
        print(f"[ota] error: {e}", file=sys.stderr)
        raise SystemExit(1)
