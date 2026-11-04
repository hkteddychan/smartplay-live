"""Offline regression test for the layer parser (no device needed).

    python tools/_layer_selftest.py

Uses real driver dumps captured on the device, so it verifies the *parser* and
the *classifier* deterministically.  The fixtures are verbatim TSV lines from
`pgo_drive.py dump`.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pgo_layer as L

# --- real dump from an encounter (木木梟 L21 IV53 10/6/8, 2026-11-02) --------
ENCOUNTER = """OK nodes=12
android.view.View||Game view|0,0,1080,2160|E
android.widget.TextView|蔓莓果||143,214,286,279|E
android.widget.TextView|蕉香果||297,214,440,279|E
android.widget.TextView|凰梨果||451,214,594,279|E
android.widget.TextView|L||366,440,384,484|E
android.widget.TextView|21||384,428,434,487|E
android.widget.TextView|IV||445,440,477,484|E
android.widget.TextView|53||477,428,527,487|E
android.widget.TextView|10/6/8||538,433,658,486|E
android.widget.TextView|✿/౯||669,429,751,487|E
"""

# --- real dump from the Pokémon detail page (no berry row) ------------------
DETAIL = """OK nodes=6
android.view.View||Game view|0,0,1080,2160|E
android.widget.TextView|10||417,428,467,487|E
android.widget.TextView|40||510,428,560,487|E
android.widget.TextView|1/8/9||571,433,669,486|E
android.widget.TextView|L||399,440,417,484|E
android.widget.TextView|IV||478,440,510,484|E
"""

# --- settings rows (Switch flags are the source of truth) -------------------
SETTINGS = """OK nodes=10
android.widget.TextView|設置||208,96,1080,228|E
android.widget.LinearLayout|||55,806,1025,880|CE
android.widget.Switch|||897,806,1025,880|CEKX
android.widget.LinearLayout|||55,815,897,871|E
android.widget.TextView|虛擬定位||55,815,897,871|E
android.widget.LinearLayout|||55,704,1025,778|C
android.widget.Switch|||897,704,1025,778|CEK
android.widget.TextView|帳號管理員||55,713,897,769|E
android.widget.EditText|30.0||759,908,924,1032|CE
android.widget.TextView|快速捕捉||55,2874,897,2160|E
"""


def check(name, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got={got!r} want={want!r}")
    return ok


def main() -> int:
    allok = True

    ns = L.parse_dump(ENCOUNTER)
    allok &= check("encounter nodes", len(ns), 10)
    allok &= check("encounter state", L.state(ns), "encounter")
    m = L.mon(ns)
    allok &= check("encounter level", m["level"], "21")
    allok &= check("encounter iv", m["iv"], "53")
    allok &= check("encounter split", m["split"], "10/6/8")
    allok &= check("encounter boost", m["boost"], "✿/౯")
    allok &= check("encounter berries", len(m["berries"]), 3)
    allok &= check("encounter consistent", m["consistent"], True)

    ns = L.parse_dump(DETAIL)
    allok &= check("detail state", L.state(ns), "mon_detail")
    m = L.mon(ns)
    allok &= check("detail iv", m["iv"], "40")
    allok &= check("detail split", m["split"], "1/8/9")
    allok &= check("detail consistent", m["consistent"], True)

    ns = L.parse_dump(SETTINGS)
    allok &= check("settings state", L.state(ns), "settings")
    sw = L.switches(ns)
    allok &= check("虛擬定位 switch", sw.get("虛擬定位"), True)
    allok &= check("帳號管理員 switch", sw.get("帳號管理員"), False)
    allok &= check("speed value", list(L.values(ns)), ["30.0"])

    # IV formula is truncated, not rounded: 6+4+15 = 25 -> 55.56 -> 55
    fake = L.parse_dump(
        "OK nodes=6\n"
        "android.widget.TextView|L||399,440,417,484|E\n"
        "android.widget.TextView|16||417,428,467,487|E\n"
        "android.widget.TextView|IV||478,440,510,484|E\n"
        "android.widget.TextView|55||510,428,560,487|E\n"
        "android.widget.TextView|6/4/15||571,433,669,486|E\n"
        "android.widget.TextView|蔓莓果||143,214,286,279|E\n")
    m = L.mon(fake)
    allok &= check("truncation iv_expected", m["iv_expected"], 55)
    allok &= check("truncation consistent", m["consistent"], True)

    print("\nALL PASS" if allok else "\nFAILURES")
    return 0 if allok else 1


if __name__ == "__main__":
    raise SystemExit(main())
