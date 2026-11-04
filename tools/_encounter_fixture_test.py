"""Offline proof that an encounter is read from data, not from pixels.

    python tools/_encounter_fixture_test.py

The fixture tools/verify/fixtures/encounter.txt is a real accessibility dump
captured on the phone while a wild Pokémon was on screen.  This test replays it
through the same parser the bot uses, so the whole decision path — state,
level, IV split, berry row — is verified with no screenshot and no OCR.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pgo_layer as L

FIXTURE = Path("tools/verify/fixtures/encounter.txt")


def check(cond: bool, msg: str) -> bool:
    print(f"{'PASS' if cond else 'FAIL'}  {msg}")
    return bool(cond)


def main() -> int:
    raw = FIXTURE.read_text(encoding="utf-8-sig")
    ns = L.parse_dump(raw)

    ok = True
    ok &= check(len(ns) > 40, f"parsed {len(ns)} nodes from the dump")
    ok &= check(L.state(ns) == "encounter",
                f"state(ns) == encounter (got {L.state(ns)!r})")

    m = L.mon(ns)
    ok &= check(m["level"] == "9", f"level read from TextView '9' (got {m['level']})")
    ok &= check(m["iv"] == "75", f"IV read from TextView '75' (got {m['iv']})")
    ok &= check(m["split"] == "12/13/9",
                f"IV split read from TextView (got {m['split']})")
    ok &= check(m["berries"] == ["蔓莓果", "蕉香果", "凰梨果"],
                f"berry row identifies the encounter (got {m['berries']})")
    ok &= check(m["iv_expected"] == 75,
                f"truncation formula agrees with the shown IV (got {m['iv_expected']})")
    ok &= check(m["consistent"] is True, "IV split and IV label are consistent")

    print("\nALL PASS" if ok else "\nFAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
