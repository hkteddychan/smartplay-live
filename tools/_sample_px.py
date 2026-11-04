"""Print RGB statistics of small boxes, to calibrate a colour detector.

    python tools/_sample_px.py tools/pgo_sessions/probe/look.png 480 1110 40
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image


def main() -> int:
    p = Path(sys.argv[1])
    x, y, r = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]) if len(sys.argv) > 4 else 40
    a = np.asarray(Image.open(p).convert("RGB"), dtype=np.int16)
    box = a[max(0, y - r):y + r, max(0, x - r):x + r].reshape(-1, 3)
    R, G, B = box[:, 0], box[:, 1], box[:, 2]
    lum = 0.299 * R + 0.587 * G + 0.114 * B
    print(f"box ({x},{y}) r={r}")
    print(f"  mean R={R.mean():.0f} G={G.mean():.0f} B={B.mean():.0f} lum={lum.mean():.0f}")
    print(f"  lum p50={np.percentile(lum,50):.0f} p90={np.percentile(lum,90):.0f} "
          f"p99={np.percentile(lum,99):.0f} max={lum.max():.0f}")
    print(f"  G-R mean={(G-R).mean():.1f} p90={np.percentile(G-R,90):.1f}")
    print(f"  B-R mean={(B-R).mean():.1f} p90={np.percentile(B-R,90):.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
