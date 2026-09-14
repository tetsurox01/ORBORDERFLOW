"""Hand-built profiles with a KNOWN answer -- IVB-SPEC.md sec b.2 / b.3 / b.6.

ivb/profile.py was written for the chart layer, so it gets the same treatment as
ivb/backtest.py: every rule checked against a case worked out by hand.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ivb.profile import (MIN_ZONE_WIDTH, allocate, build_profile,  # noqa: E402
                         method_spread, reload_zone, value_area)

PASS, FAIL = [], []


def check(name: str, ok: bool, extra: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print("{} {}{}".format("PASS" if ok else "FAIL", name,
                           "   " + extra if extra else ""))


def bars(rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["low", "high", "close", "volume"])


def main() -> int:
    # --- 1. uniform allocation splits one bar evenly over the bins it spans ---
    b = bars([(100.0, 103.0, 101.0, 300.0)])          # spans 3 bins at bin=1.0
    edges, cen, w = allocate(b, "volume_uniform", bin_size=1.0)
    check("M1 uniform splits volume evenly across the spanned bins",
          list(w) == [100.0, 100.0, 100.0], str(list(w)))
    check("M1 conserves total volume", w.sum() == 300.0)

    # --- 2. close_only puts every contract in the closing bin ----------------
    _, cen3, w3 = allocate(b, "volume_close_only", bin_size=1.0)
    j = int(w3.argmax())
    check("M3 close_only assigns all volume to the close bin",
          w3[j] == 300.0 and w3.sum() == 300.0 and cen3[j] == 101.5,
          "poc bin centre {}".format(cen3[j]))

    # --- 3. tpo ignores volume entirely -------------------------------------
    b2 = bars([(100.0, 103.0, 101.0, 1.0), (100.0, 103.0, 101.0, 999_999.0)])
    _, _, w4 = allocate(b2, "tpo_minute", bin_size=1.0)
    check("M4 tpo counts bars, not volume", list(w4) == [2.0, 2.0, 2.0], str(list(w4)))

    # --- 4. triangular conserves volume and peaks near (H+L+C)/3 ------------
    _, cen2, w2 = allocate(b, "volume_triangular", bin_size=1.0)
    peak = cen2[int(w2.argmax())]
    check("M2 triangular conserves total volume", abs(w2.sum() - 300.0) < 1e-9)
    check("M2 triangular peaks at the bin holding (H+L+C)/3 = 101.33",
          peak == 101.5, "peak bin centre {}".format(peak))

    # --- 5. value area expansion, worked by hand ----------------------------
    # bins centred 0.5 .. 4.5, weights below. total = 100, target = 70.
    # POC = bin 2 (w 40). up2 = 20+5 = 25, dn2 = 25+5 = 30 -> take DOWN.
    # cum = 40+30 = 70 >= 70 -> stop. included = bins 0..2.
    w_in = [5.0, 25.0, 40.0, 20.0, 5.0]
    e = pd.Series(range(6), dtype=float).to_numpy()
    c = e[:-1] + 0.5
    poc, vah, val = value_area(c, pd.Series(w_in).to_numpy(), e, va_pct=0.70)
    check("VA expansion takes the larger 2-bin pair (down here)",
          (poc, vah, val) == (2.5, 3.0, 0.0), "POC {} VAH {} VAL {}".format(poc, vah, val))

    # --- 6. the value area always sits INSIDE the IB (sec b.1) --------------
    b3 = bars([(10.0, 20.0, 15.0, 100.0), (12.0, 18.0, 14.0, 400.0),
               (13.0, 16.0, 15.0, 900.0)])
    p = build_profile(b3, bin_size=1.0)
    check("VAH <= IB_high and VAL >= IB_low",
          p.vah <= 20.0 and p.val >= 10.0, "VAH {} VAL {}".format(p.vah, p.val))
    check("VAL <= POC <= VAH", p.val <= p.poc <= p.vah)

    # --- 7. reload zone orientation and the degenerate guard (sec b.6) ------
    bot, top, degen = reload_zone(1, poc=10.0, vah=12.0, val=8.0)
    check("long zone is [POC, VAH]", (bot, top, degen) == (10.0, 12.0, False))
    bot, top, degen = reload_zone(-1, poc=10.0, vah=12.0, val=8.0)
    check("short zone is [VAL, POC]", (bot, top, degen) == (8.0, 10.0, False))
    bot, top, degen = reload_zone(1, poc=10.0, vah=10.0, val=8.0)
    check("zero-width zone is widened and flagged",
          degen and abs((top - bot) - MIN_ZONE_WIDTH) < 1e-9,
          "width {}".format(top - bot))

    # --- 8. identical methods must report zero spread -----------------------
    same = {m: build_profile(b3, method="volume_uniform", bin_size=1.0)
            for m in ("a", "b")}
    check("method_spread is 0 when the methods agree",
          all(v == 0 for v in method_spread(same).values()))

    print("\n{}/{} profile tests passed.".format(len(PASS), len(PASS) + len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
