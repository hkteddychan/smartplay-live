"""Measure the per-step cost of the data-layer play loop.

    python tools/_bench_steps.py

Prints median latency for every primitive the hunt loop uses, so optimisation
work can be checked against a number instead of a feeling.
"""
from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pgo_layer as L


def bench(name: str, fn, n: int = 5) -> float:
    xs = []
    for _ in range(n):
        a = time.perf_counter()
        fn()
        xs.append((time.perf_counter() - a) * 1000)
    med = statistics.median(xs)
    print(f"  {name:<28} {med:8.1f} ms   (min {min(xs):.0f}, max {max(xs):.0f})")
    return med


def main() -> int:
    if not L.ensure_driver():
        print("driver unavailable")
        return 1
    print("data-layer primitive latency:")
    bench("ping", lambda: L.drive("ping"))
    bench("dump (all nodes)", lambda: L.nodes())
    bench("probe (screenshot)", lambda: L.probe())
    bench("scan (screenshot+cv)", lambda: L.scan())
    print()
    print("screenshot for comparison:")
    import pgo_bot as B
    bench("screencap full png", lambda: B.grab(), n=3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
