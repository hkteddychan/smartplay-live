import re
import sys
import xml.etree.ElementTree as ET

path = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\Teddy\AppData\Local\Temp\ui.xml"
tree = ET.parse(path)
root = tree.getroot()
rows = []
for node in root.iter("node"):
    txt = node.get("text") or ""
    desc = node.get("content-desc") or ""
    cls = node.get("class") or ""
    bounds = node.get("bounds") or ""
    rid = node.get("resource-id") or ""
    clickable = node.get("clickable")
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
    if not m:
        continue
    x1, y1, x2, y2 = (int(v) for v in m.groups())
    label = txt or desc
    if not label and not clickable == "true":
        continue
    rows.append((label, cls, rid, (x1 + x2) // 2, (y1 + y2) // 2, x2 - x1, y2 - y1, clickable))

print(f"nodes with label or clickable: {len(rows)}\n")
for label, cls, rid, cx, cy, w, h, clickable in rows:
    label = (label or "")[:44].replace("\n", " ")
    print(f"  ({cx:>5},{cy:>5}) {w:>5}x{h:<5} click={clickable:<5} {cls.split('.')[-1]:<22} {label}")
