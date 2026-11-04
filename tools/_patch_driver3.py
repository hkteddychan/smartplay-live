"""One-off: drop the stale checked= field from the toggle reply."""
from __future__ import annotations

import pathlib

P = pathlib.Path(r"D:\Teddy\Opencode\Firsttry\driver\java\com\opencode\pgdrive\Driver.java")
s = P.read_text(encoding="utf-8")

old = '''                    boolean ok = sw.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                    sb.append(ok ? "OK toggled " : "ERR togglefailed ").append(want)
                      .append(" checked=").append(sw.isChecked());'''
new = '''                    boolean ok = sw.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                    // NOTE: sw.isChecked() is still the pre-click value here
                    // (the node is not refreshed yet), so we do not report it.
                    sb.append(ok ? "OK toggled " : "ERR togglefailed ").append(want);'''
assert old in s
s = s.replace(old, new)
P.write_text(s, encoding="utf-8")
print("patched toggle reply")
