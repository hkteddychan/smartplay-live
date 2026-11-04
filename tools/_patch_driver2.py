"""One-off: make findText prefer an exact label match before substring match."""
from __future__ import annotations

import pathlib

P = pathlib.Path(r"D:\Teddy\Opencode\Firsttry\driver\java\com\opencode\pgdrive\Driver.java")
s = P.read_text(encoding="utf-8")

old = '''    private AccessibilityNodeInfo findText(AccessibilityNodeInfo n, String want) {
        if (n == null) return null;
        List<AccessibilityNodeInfo> stack = new ArrayList<>();
        stack.add(n);'''
new = '''    private AccessibilityNodeInfo findText(AccessibilityNodeInfo n, String want) {
        // Exact label first (so "快速狙擊 I" never matches "快速狙擊 II"),
        // then fall back to substring.
        AccessibilityNodeInfo exact = findTextPass(n, want, true);
        return exact != null ? exact : findTextPass(n, want, false);
    }

    private AccessibilityNodeInfo findTextPass(AccessibilityNodeInfo n, String want, boolean exact) {
        if (n == null) return null;
        List<AccessibilityNodeInfo> stack = new ArrayList<>();
        stack.add(n);'''
assert old in s
s = s.replace(old, new)

old2 = '''            if ((ts.contains(want) || ds.contains(want)) && !(ts.isEmpty() && ds.isEmpty())) {
                return cur;
            }'''
new2 = '''            boolean hit = exact ? (ts.equals(want) || ds.equals(want))
                                : (ts.contains(want) || ds.contains(want));
            if (hit && !(ts.isEmpty() && ds.isEmpty())) {
                return cur;
            }'''
assert old2 in s
s = s.replace(old2, new2)

P.write_text(s, encoding="utf-8")
print("patched findText (two-pass exact/contains)")
