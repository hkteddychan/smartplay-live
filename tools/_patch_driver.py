"""One-off: make driver commands accept labels containing spaces."""
from __future__ import annotations

import pathlib

P = pathlib.Path(r"D:\Teddy\Opencode\Firsttry\driver\java\com\opencode\pgdrive\Driver.java")
s = P.read_text(encoding="utf-8")

s = s.replace(
    '''            case "text": {
                String want = parts.length > 1 ? parts[1] : "";''',
    '''            case "text": {
                String want = argAfter(line);''')

s = s.replace(
    '''                String want = parts.length > 1 ? parts[1] : "";
                AccessibilityNodeInfo hit = findText(getUiAutomation().getRootInActiveWindow(), want);''',
    '''                String want = argAfter(line);
                AccessibilityNodeInfo hit = findText(getUiAutomation().getRootInActiveWindow(), want);''')

s = s.replace(
    '''    private void injectTap(float x, float y) {''',
    '''    /** Everything after the first token: labels may contain spaces. */
    private static String argAfter(String line) {
        int i = line.indexOf(' ');
        return i < 0 ? "" : line.substring(i + 1).trim();
    }

    private void injectTap(float x, float y) {''')

P.write_text(s, encoding="utf-8")
print("patched; argAfter occurrences:", s.count("argAfter(line)"))
