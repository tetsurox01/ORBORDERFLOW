"""Exit taxonomy tests -- IVB-SPEC.md sec (c), c.1.

Two halves:
  1. the classification rule in ivb/exits.py, against hand-worked cases;
  2. an END-TO-END check that the Layer 1 resolver in scripts/04_charts.py puts
     the right string on a session built so the correct answer is known by hand.

(2) exists because the defect this file was written for was a LABEL defect, not a
maths defect: the price was right and the CATEGORY was the thing at risk.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ivb.config import P0                                          # noqa: E402
from ivb.exits import (CLOSE_INVALIDATION, HARD_STOP,              # noqa: E402
                       LAYER0_TO_LAYER1, LAYER1_EXIT_REASONS, TIME_STOP, TP1,
                       frequency, resolve, validate)
from ivb.sessions import Session                                   # noqa: E402

PASS, FAIL = [], []


def check(name: str, ok: bool, extra: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print("{} {}{}".format("PASS" if ok else "FAIL", name,
                           "   " + extra if extra else ""))


def _charts():
    """Import scripts/04_charts.py by path -- the leading digit blocks `import`."""
    spec = importlib.util.spec_from_file_location(
        "charts04", ROOT / "scripts" / "04_charts.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def mk_session(rows, *, ib_high, ib_low, ib_close_idx) -> Session:
    """rows: (open, high, low, close, volume). ts starts 09:30 ET, 1-min bars."""
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])
    df["ts_et"] = pd.date_range("2020-01-02 09:30", periods=len(df), freq="1min",
                                tz="America/New_York")
    df["roll_day_flag"] = False
    return Session(
        session_date=pd.Timestamp("2020-01-02"), bars=df,
        ib_high=ib_high, ib_low=ib_low, ib_range=ib_high - ib_low,
        ib_close_idx=ib_close_idx, trade_end_idx=len(df) - 1,
        is_half_day=False, roll_day_flag=False,
    )


def main() -> int:
    # ---- 1. the enum is closed --------------------------------------------
    try:
        validate("invalidated")
        check("validate rejects a reason outside the enum", False,
              "the old free-text string was accepted")
    except ValueError:
        check("validate rejects a reason outside the enum", True)
    check("enum has exactly the four spec categories",
          set(LAYER1_EXIT_REASONS) == {"tp1", "close_invalidation", "hard_stop",
                                       "time_stop"})
    check("Layer 0 vocabulary maps onto the Layer 1 enum",
          set(LAYER0_TO_LAYER1) == {"target", "stop", "time"}
          and set(LAYER0_TO_LAYER1.values()) <= set(LAYER1_EXIT_REASONS))

    # ---- 2. hard-stop dominance, long -------------------------------------
    # long: the hard stop sits BELOW. An exit strictly above it is a real
    # invalidation; at or below it, the resting stop had already filled.
    check("long: invalidation exit above the hard stop stays close_invalidation",
          resolve(1, CLOSE_INVALIDATION, 100.25, 100.0) == CLOSE_INVALIDATION)
    check("long: invalidation exit EXACTLY at the hard stop becomes hard_stop",
          resolve(1, CLOSE_INVALIDATION, 100.0, 100.0) == HARD_STOP)
    check("long: invalidation exit gapped below the hard stop becomes hard_stop",
          resolve(1, CLOSE_INVALIDATION, 98.0, 100.0) == HARD_STOP)

    # ---- 3. hard-stop dominance, short (mirror) ---------------------------
    check("short: invalidation exit below the hard stop stays close_invalidation",
          resolve(-1, CLOSE_INVALIDATION, 99.75, 100.0) == CLOSE_INVALIDATION)
    check("short: invalidation exit EXACTLY at the hard stop becomes hard_stop",
          resolve(-1, CLOSE_INVALIDATION, 100.0, 100.0) == HARD_STOP)
    check("short: invalidation exit gapped above the hard stop becomes hard_stop",
          resolve(-1, CLOSE_INVALIDATION, 102.0, 100.0) == HARD_STOP)

    # ---- 4. the other three reasons pass through untouched ----------------
    check("tp1 / hard_stop / time_stop are never reclassified",
          all(resolve(1, r, 90.0, 100.0) == r
              for r in (TP1, HARD_STOP, TIME_STOP)))

    # ---- 5. frequency keeps zero rows -------------------------------------
    f = frequency([TP1, TP1, HARD_STOP])
    check("frequency reports every enum member, zeros included",
          f == {"tp1": 2, "close_invalidation": 0, "hard_stop": 1,
                "time_stop": 0, "total": 3}, str(f))

    # ---- 6. END TO END: a real close_invalidation -------------------------
    # IB = three identical bars, low 95 / high 105, volume flat. Worked by hand
    # against sec b.2 / b.3 at bin_size 1.0: ten bins of equal weight, POC 99.50,
    # the 70% area expanding up-up-down, so VAL = 97.00 and VAH = 104.00.
    # The session breaks DOWN, so for this short:
    #     entry = VAL  = 97.00     far = VAH = 104.00
    #     hard stop    = VAH + 8 ticks = 106.00
    #     risk_to_hard_stop = 9.00 pt      risk_to_val = 7.00 pt
    # A 5-min close above 104.00 invalidates; where the NEXT bar opens decides
    # which bucket the exit lands in.
    ch = _charts()
    cfg = P0.with_(ib_minutes=3, slippage_ticks_market=0, commission_per_side=0.0,
                   min_ib_range_atr=0.0)

    def resolve_session(after_close: float, open_next: float):
        """Break DOWN, retrace to VAL, fill, then close back above VAH."""
        rows = [(100, 105, 95, 100, 100.0),        # 09:30  IB
                (100, 105, 95, 100, 100.0),        # 09:31  IB
                (100, 105, 95, 100, 100.0),        # 09:32  IB
                (95, 95, 88, 89, 50.0),            # 09:33  break below IB_low
                (89, 104, 89, 103, 50.0)]          # 09:34  retrace, fills at VAL
        rows += [(103, 104, 102, 103, 50.0)] * 4                   # 09:35..09:38
        rows += [(103, 105.5, 102, after_close, 50.0)]             # 09:39 CLOSE
        #        high 105.50 stays INSIDE the 106.00 hard stop, so the only thing
        #        that can end this trade is the close and the next bar's open.
        rows += [(open_next, open_next + 1.0, open_next - 1.0,     # 09:40 exit bar
                  open_next, 50.0)]
        rows += [(100, 101, 99, 100, 50.0)] * 3
        s = mk_session(rows, ib_high=105.0, ib_low=95.0, ib_close_idx=3)
        return ch.illustrate_layer1_trade(s, cfg)

    r = resolve_session(after_close=105.0, open_next=105.0)
    check("end to end: close beyond VAH, next open INSIDE the hard stop "
          "-> close_invalidation",
          r.get("exit_reason") == CLOSE_INVALIDATION
          and r.get("scenario") == CLOSE_INVALIDATION,
          "got reason={} scenario={} exit={}".format(
              r.get("exit_reason"), r.get("scenario"), r.get("exit_price")))

    # ---- 7. END TO END: the dominance case --------------------------------
    r2 = resolve_session(after_close=105.0, open_next=108.0)
    check("end to end: invalidation that gaps THROUGH the hard stop -> hard_stop",
          r2.get("exit_reason") == HARD_STOP
          and r2.get("exit_price") is not None and r2["exit_price"] >= 106.0,
          "got reason={} exit={}".format(r2.get("exit_reason"),
                                         r2.get("exit_price")))

    # ---- 8. the two adverse categories must stay separable ----------------
    check("scenario distinguishes close_invalidation from hard_stop",
          r.get("scenario") != r2.get("scenario"),
          "{} vs {}".format(r.get("scenario"), r2.get("scenario")))

    # ---- 9. both risk numbers are reported (sec b.10) ---------------------
    check("resolver reports risk_to_hard_stop AND risk_to_val",
          {"risk_to_hard_stop", "risk_to_val"} <= set(r))
    check("risk_to_hard_stop is the WIDER of the two (sec b.10)",
          r.get("risk_to_hard_stop", 0) > r.get("risk_to_val", 0),
          "hard={} val={}".format(r.get("risk_to_hard_stop"),
                                  r.get("risk_to_val")))
    check("risk_points is measured to the HARD stop (sec c.2)",
          abs(r.get("risk_points", -1.0) - r.get("risk_to_hard_stop", -2.0)) < 1e-9)

    print("\n{}/{} exit-taxonomy tests passed.".format(
        len(PASS), len(PASS) + len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
