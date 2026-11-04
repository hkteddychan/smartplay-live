"""Inspect the game's transport layer without root.

* /proc/net/tcp{,6}   -> listening sockets owned by the game (a local API
  would let us read spawn data directly instead of scraping pixels)
* logcat               -> the game's own analytics/debug output, which in
  this build logs the encounter/segment state machine

Usage:
    python tools/_netinfo.py
"""
import re
import subprocess

SERIAL = "1bbd5689"

HEX = re.compile(r"^([0-9A-F]+):([0-9A-F]+) ([0-9A-F]+) ([0-9A-F]+)")


def sh(cmd):
    return subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                          capture_output=True, text=True).stdout


def decode_addr(hexaddr: str, hexport: str):
    ip = ".".join(str(int(hexaddr[i:i + 2], 16)) for i in (6, 4, 2, 0))
    return f"{ip}:{int(hexport, 16)}"


print("=== listening TCP sockets ===")
for f in ("/proc/net/tcp", "/proc/net/tcp6"):
    for line in sh(f"cat {f}").splitlines()[1:]:
        m = HEX.match(line)
        if not m:
            continue
        addr, port, st = m.group(1), m.group(2), m.group(4)
        if st == "0A":  # LISTEN
            print(f"  LISTEN {decode_addr(addr, port)}")

print("\n=== app sockets (uid of game) ===")
uid = sh("dumpsys package com.nianticlabs.pokemongo | grep -m1 userId=")
print("  " + uid.strip())

print("\n=== logcat tags seen from the game (last 400 lines, all buffers) ===")
out = sh("logcat -d -v brief -t 400")
tags = {}
for line in out.splitlines():
    m = re.match(r"^[VDIWEF]/([A-Za-z0-9_.-]+)\(", line)
    if m:
        tags[m.group(1)] = tags.get(m.group(1), 0) + 1
for t, n in sorted(tags.items(), key=lambda kv: -kv[1])[:25]:
    print(f"  {n:5d}  {t}")

print("\n=== sample of QUAGO / holoholo / pokemon lines ===")
out = sh("logcat -d -v brief -t 800")
shown = 0
for line in out.splitlines():
    low = line.lower()
    if any(k in low for k in ("quago", "holoholo", "pokemon", "encounter", "spawn", "wild")):
        print("  " + line[:200])
        shown += 1
        if shown > 30:
            break
