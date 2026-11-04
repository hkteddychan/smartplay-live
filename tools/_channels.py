"""Compare the cost and the information content of every available data channel.

Channels
  screencap     1 raw framebuffer dump        -> pixels
  uiautomator   view hierarchy dump            -> labels + bounds
  logcat        the game's own logging        -> app state events
  dumpsys       activity / window state        -> foreground component

The point is to find out which one can *decide* on its own, so the bot can
stop paying for screencaps.
"""
import subprocess
import time

SERIAL = "1bbd5689"


def sh(cmd):
    t0 = time.time()
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True)
    return time.time() - t0, r.stdout


def main():
    print("=== timings (3 runs each) ===")
    for name, cmd in [
        ("screencap raw", "screencap > /dev/null"),
        ("uiautomator dump", "uiautomator dump /sdcard/x.xml >/dev/null"),
        ("logcat -d -t 50", "logcat -d -t 50 >/dev/null"),
        ("dumpsys window", "dumpsys window >/dev/null"),
    ]:
        ts = []
        for _ in range(3):
            dt, _ = sh(cmd)
            ts.append(dt)
        print(f"  {name:20s} min={min(ts):.2f}s avg={sum(ts)/len(ts):.2f}s")

    print("\n=== logcat content from the game (last 200 lines) ===")
    _, out = sh("logcat -d -v brief -t 200")
    tags = {}
    for line in out.splitlines():
        if "/" in line and len(line.split("/", 1)[0]) < 40:
            tag = line.split("/", 1)[0].split()[-1]
            tags[tag] = tags.get(tag, 0) + 1
    for t, n in sorted(tags.items(), key=lambda kv: -kv[1])[:12]:
        print(f"  {n:4d}  {t}")

    print("\n=== app-specific lines ===")
    shown = 0
    for line in out.splitlines():
        low = line.lower()
        if any(k in low for k in ("quago", "holoholo", "encounter", "pokemon", "spawn", "catch")):
            print("  " + line[:180])
            shown += 1
    if not shown:
        print("  (none - the app logs nothing about gameplay in this buffer)")

    print("\n=== dumpsys activity top ===")
    _, out = sh("dumpsys activity activities | head -40")
    for line in out.splitlines():
        if any(k in line for k in ("mResumedActivity", "mFocusedActivity", "topResumedActivity",
                                   "Hist #", "mCurrentFocus")):
            print("  " + line.strip()[:150])


if __name__ == "__main__":
    main()
