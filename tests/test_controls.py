"""Control tests -- IVB-SPEC.md sec b.9, b.10, h.1.

Three things that were asserted in prose before this file existed, and are now
checked by running code:

  1. sec b.9 IN BOTH DIRECTIONS. The gate must TRIP on the negative control
     (volume drawn independently of price) and must NOT trip on the positive
     control (volume concentrated around a drifting anchor). Until the pass branch
     executes, a MATERIAL verdict is the only answer the gate can give and is
     therefore not evidence about Layer 1.

  2. sec b.10 the invalidation window is a CONSTANT. `|far_VA_edge - hard_stop|`
     equals `hard_stop_ticks` on every fill, so the close-beyond-VAL rule has a
     fixed, session-independent amount of room -- which is half of why it barely
     fires.

  3. sec h.1 the funnel RECONCILES. `S_ib_broke - S_breakout` must equal the sum of
     the per-skip_reason counts. Two stages that should agree and do not are where
     bugs live; this is the assertion that catches it.

The b.9 checks run on IB windows drawn straight from the two generators rather than
on the full parquet files, so the test is fast and depends on nothing built by
scripts/01 or scripts/02.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ivb.config import P0, TICK_SIZE                                # noqa: E402
from ivb.profile import (METHODS, bin_width, build_profile,         # noqa: E402
                         method_spread, resolve_bin_size)
from ivb.provenance import (NEGATIVE_CONTROL, POSITIVE_CONTROL, REAL,  # noqa: E402
                           QuarantineError, assert_reportable, classify, redact)
from ivb.sessions import Session, find_breakout                     # noqa: E402

import make_synthetic as gen                                        # noqa: E402

HARD_STOP_TICKS = 8        # scripts/04_charts.py, sec (f)
N_WINDOWS = 300
PASS, FAIL = [], []


def check(name: str, ok: bool, extra: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print("{} {}{}".format("PASS" if ok else "FAIL", name,
                           "   " + extra if extra else ""))


# ---------------------------------------------------------------------------
# sec b.9 -- the gate, evaluated on IB windows from each generator
# ---------------------------------------------------------------------------
def _bars(op, hi, lo, cl, vol) -> pd.DataFrame:
    q = gen._tick
    op, hi, lo, cl = q(op), q(hi), q(lo), q(cl)
    hi = np.maximum.reduce([hi, op, cl])
    lo = np.minimum.reduce([lo, op, cl])
    return pd.DataFrame({"open": op, "high": hi, "low": lo, "close": cl,
                         "volume": np.asarray(vol, float)})


def ib_windows(structure: str, n: int, seed: int = 11) -> list:
    """n IB windows of 30 bars, drawn exactly as tests/make_synthetic.py draws them."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        if structure == "anchored_volume":
            op, cl, wig, vol = gen._anchored_ib(rng, 4200.0, gen.IB_MINUTES)
        else:
            op, cl, wig, vol = gen._random_walk_session(rng, 4200.0, gen.IB_MINUTES)
        out.append(_bars(op, np.maximum(op, cl) + wig,
                         np.minimum(op, cl) - wig, cl, vol))
    return out


def gate(windows: list) -> dict:
    """sec b.9, on the three conditions an IB window alone can decide.

    d_fill_rate needs post-IB bars, so it is left to scripts/04_charts.py; it is
    the one condition that has never been the binding trigger on either control.
    """
    d_poc, d_risk, risk, bar_rng = [], [], [], []
    for ib in windows:
        profs = {m: build_profile(ib, method=m) for m in METHODS}
        sp = method_spread(profs)
        d_poc.append(sp["d_POC"])
        d_risk.append(sp["d_risk"])
        p = profs["volume_uniform"]
        risk.append((p.vah - p.val + HARD_STOP_TICKS * TICK_SIZE) / TICK_SIZE)
        bar_rng.append(float((ib["high"] - ib["low"]).mean()))
    med = float(np.median(risk))
    g = {"d_risk p50 > 0.20 * med": float(np.percentile(d_risk, 50)) > 0.20 * med,
         "d_risk p90 > 0.40 * med": float(np.percentile(d_risk, 90)) > 0.40 * med,
         "d_POC p50 > 4 ticks": float(np.percentile(d_poc, 50)) > 4.0}
    return {"MATERIAL": any(g.values()), "gate": g, "med_risk": med,
            "dPOC50": float(np.percentile(d_poc, 50)),
            "dRisk50": float(np.percentile(d_risk, 50)),
            "dRisk90": float(np.percentile(d_risk, 90)),
            "bar_range": float(np.mean(bar_rng))}


# ---------------------------------------------------------------------------
# sec h.1 -- the funnel identity, on a hand-built pair of sessions
# ---------------------------------------------------------------------------
def mk_session(rows, *, ib_high, ib_low, ib_close_idx, date="2020-01-02") -> Session:
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])
    df["ts_et"] = pd.date_range(date + " 09:30", periods=len(df), freq="1min",
                                tz="America/New_York")
    df["roll_day_flag"] = False
    return Session(session_date=pd.Timestamp(date), bars=df,
                   ib_high=ib_high, ib_low=ib_low, ib_range=ib_high - ib_low,
                   ib_close_idx=ib_close_idx, trade_end_idx=len(df) - 1,
                   is_half_day=False, roll_day_flag=False)


def breakout_session(date: str, ib_range: float) -> Session:
    """30 IB bars inside [100, 100+ib_range], then a clean break upward."""
    lo, hi = 100.0, 100.0 + ib_range
    rows = [(lo + 1, hi, lo, lo + 1, 500.0) for _ in range(30)]
    rows += [(hi + 2, hi + 3, hi + 1, hi + 2, 500.0) for _ in range(30)]
    return mk_session(rows, ib_high=hi, ib_low=lo, ib_close_idx=30, date=date)


def main() -> int:
    from ivb.backtest import run_strategy

    # ---- 1. sec b.9 NEGATIVE control must TRIP ---------------------------
    neg = gate(ib_windows("random_walk", N_WINDOWS))
    check("sec b.9 NEGATIVE control (random_walk) returns MATERIAL",
          neg["MATERIAL"],
          "d_POC p50 {:.1f}  d_risk p50 {:.1f} / p90 {:.1f}  med_risk {:.1f}".format(
              neg["dPOC50"], neg["dRisk50"], neg["dRisk90"], neg["med_risk"]))
    # WHICH condition trips is not pinned. On the full parquet the negative control
    # trips all three; on these 30-bar windows d_POC p50 lands exactly ON the 4-tick
    # threshold rather than above it, so d_risk is the binding trigger. The gate is
    # an OR, so the requirement is that at least one fires -- pinning the test to a
    # particular condition would fail for a reason that says nothing about the gate.
    check("sec b.9 negative control trips at least one condition",
          any(neg["gate"].values()),
          "tripped: " + ", ".join(k for k, v in neg["gate"].items() if v))

    # ---- 2. sec b.9 POSITIVE control must NOT trip ------------------------
    pos = gate(ib_windows("anchored_volume", N_WINDOWS))
    check("sec b.9 POSITIVE control (anchored_volume) returns NOT MATERIAL",
          not pos["MATERIAL"],
          "d_POC p50 {:.1f}  d_risk p50 {:.1f} / p90 {:.1f}  med_risk {:.1f}".format(
              pos["dPOC50"], pos["dRisk50"], pos["dRisk90"], pos["med_risk"]))
    for cond, tripped in pos["gate"].items():
        check("sec b.9 positive control: [{}] does not trip".format(cond), not tripped)

    # ---- 3. the gate can therefore say BOTH things ------------------------
    check("sec b.9 gate has executed BOTH branches",
          neg["MATERIAL"] and not pos["MATERIAL"],
          "a gate that can only trip has never been tested")

    # ---- 4. the mechanism, restated for RELATIVE bins ---------------------
    # Under the old FIXED 1.0-point bin the two controls separated on absolute bar
    # height: the positive control's 0.9-point bars spanned one bin and agreed, the
    # negative control's 3.0-point bars spanned three and did not. sec b.2 now sets
    # the bin width FROM the bar height, so that separation is gone by construction
    # and the controls must separate on volume STRUCTURE alone -- which is what they
    # were always supposed to test. The bar ranges are still recorded, as a property
    # of the generators, but they are no longer the mechanism.
    check("generator bar ranges still differ (a generator property, not the gate)",
          pos["bar_range"] < neg["bar_range"],
          "positive {:.2f} pt vs negative {:.2f} pt".format(
              pos["bar_range"], neg["bar_range"]))
    n_trip = sum(neg["gate"].values())
    check("sec b.9 the negative control still trips under RELATIVE bins",
          n_trip >= 1,
          "{}/{} conditions trip on this 300-window draw -- the same count as under "
          "the old fixed 1.0-point bin, though a different condition carries it. "
          "The relative rule did not measurably weaken the gate here; the "
          "0.5x / 2.0x sensitivity is reported anyway, because the CONSTRUCTION "
          "argument in sec b.2 stands whatever this draw says".format(
              n_trip, len(neg["gate"])))
    check("sec b.9 the positive control still passes under RELATIVE bins",
          sum(pos["gate"].values()) == 0,
          "0/{} conditions trip".format(len(pos["gate"])))

    # ---- 5. sec b.10 the invalidation window is a CONSTANT ----------------
    wins = []
    for ib in ib_windows("anchored_volume", 120) + ib_windows("random_walk", 120):
        p = build_profile(ib, method="volume_uniform")
        for d in (1, -1):
            far = p.val if d == 1 else p.vah
            hard = (far - HARD_STOP_TICKS * TICK_SIZE if d == 1
                    else far + HARD_STOP_TICKS * TICK_SIZE)
            wins.append(abs(far - hard) / TICK_SIZE)
    w = np.asarray(wins)
    check("sec b.10 (VAL - hard_stop) is CONSTANT across every profile",
          float(w.min()) == float(w.max()),
          "min {:.1f} max {:.1f} ticks over {:,} cases".format(
              w.min(), w.max(), len(w)))
    check("sec b.10 that constant IS hard_stop_ticks",
          np.allclose(w, HARD_STOP_TICKS),
          "so the close rule's room does not vary with the market")

    # ---- 6. sec h.1 the funnel identity ----------------------------------
    # Two sessions that both break the IB. One has an IB range far below
    # min_ib_range_atr * ATR and must be removed BEFORE find_breakout is reached.
    wide = breakout_session("2020-01-02", 40.0)
    thin = breakout_session("2020-01-03", 0.5)
    sessions = [wide, thin]
    feats = pd.DataFrame({"session_date": [s.session_date for s in sessions],
                          "atr14": [100.0, 100.0]})
    df = run_strategy(sessions, feats, P0)

    s_ib_broke = sum(1 for s in sessions
                     if (bo := find_breakout(s, P0)) is not None
                     and not bo["ambiguous_breakout"])
    s_breakout = int((df["traded"] == True).sum())              # noqa: E712
    broke = {s.session_date for s in sessions
             if (bo := find_breakout(s, P0)) is not None
             and not bo["ambiguous_breakout"]}
    by_filter = (df[df["session_date"].isin(broke) & (df["traded"] == False)]  # noqa: E712
                 ["skip_reason"].value_counts().to_dict())

    check("sec h.1 S_ib_broke counts the PHYSICAL break, filters ignored",
          s_ib_broke == 2, "got {}".format(s_ib_broke))
    check("sec h.1 S_breakout is smaller -- the sec f filter removed one",
          s_breakout == 1, "got {}".format(s_breakout))
    check("sec h.1 funnel RECONCILES: skip_reason counts sum to the gap",
          sum(by_filter.values()) == s_ib_broke - s_breakout,
          "{} accounted for vs {} lost".format(
              sum(by_filter.values()), s_ib_broke - s_breakout))
    check("sec h.1 the removing filter is NAMED",
          by_filter.get("min_ib_range_atr") == 1, str(by_filter))


    # -----------------------------------------------------------------------
    # sec b.2 -- BIN WIDTH IS RELATIVE
    # -----------------------------------------------------------------------
    # A width fixed in points is a different fraction of a bar in 2015 and in 2026,
    # so the profile would not be the same object at both ends of the sample. These
    # checks pin the rule itself, not a number produced under it.
    def flat_ib(rng_pts, n=30, base=4200.0):
        """n identical bars, each spanning exactly `rng_pts` points."""
        return pd.DataFrame({"open": [base] * n, "high": [base + rng_pts] * n,
                             "low": [base] * n, "close": [base] * n,
                             "volume": [1000.0] * n})

    check("sec b.2 bin width = median IB bar range, in ticks",
          bin_width(flat_ib(3.0)) == 3.0,
          "got {}".format(bin_width(flat_ib(3.0))))
    check("sec b.2 bin width SCALES with bar height (2x bars -> 2x bin)",
          bin_width(flat_ib(6.0)) == 2 * bin_width(flat_ib(3.0)))
    check("sec b.2 bin width is INDEPENDENT of price level",
          bin_width(flat_ib(3.0, base=4200.0)) == bin_width(flat_ib(3.0, base=25000.0)),
          "the whole point: 2015 and 2026 measure the same object")
    check("sec b.2 bin width rounds to the nearest tick",
          bin_width(flat_ib(3.30)) == 3.25 and bin_width(flat_ib(3.40)) == 3.50,
          "3.30 -> {}   3.40 -> {}".format(bin_width(flat_ib(3.30)),
                                           bin_width(flat_ib(3.40))))
    check("sec b.2 half a tick rounds UP, not to even",
          bin_width(flat_ib(0.375)) == 0.50 and bin_width(flat_ib(0.625)) == 0.75,
          "numpy would round both to the even tick")
    check("sec b.2 bin width is FLOORED at 1 tick",
          bin_width(flat_ib(0.01)) == TICK_SIZE,
          "got {}".format(bin_width(flat_ib(0.01))))
    check("sec b.2 the multiplier is a labelled sensitivity, and it bites",
          bin_width(flat_ib(4.0), mult=0.5) == 2.0
          and bin_width(flat_ib(4.0), mult=2.0) == 8.0)
    check("sec b.2 bin_size=None applies the rule; a float OVERRIDES it",
          resolve_bin_size(flat_ib(3.0), None) == 3.0
          and resolve_bin_size(flat_ib(3.0), 1.0) == 1.0)

    # Scale invariance of the whole profile, which is what the rule is FOR. Take one
    # anchored IB window, multiply every price by 5 (a 2015 -> 2026 move in NQ), and
    # the profile geometry must be the same shape: same bin count, same value area
    # measured in bins. Under a fixed 1.0-point bin it would not be.
    w = ib_windows("anchored_volume", 1, seed=99)[0]
    w5 = w.copy()
    for c in ("open", "high", "low", "close"):
        w5[c] = (w5[c] * 5.0 / TICK_SIZE).round() * TICK_SIZE
    pa, pb = build_profile(w), build_profile(w5)
    check("sec b.2 relative bins are SCALE-INVARIANT: same bin count at 5x price",
          abs(len(pa.centers) - len(pb.centers)) <= 1,
          "{} bins vs {} bins".format(len(pa.centers), len(pb.centers)))
    va_bins_a = (pa.vah - pa.val) / pa.bin_size
    va_bins_b = (pb.vah - pb.val) / pb.bin_size
    check("sec b.2 value area is the same WIDTH IN BINS at 5x price",
          abs(va_bins_a - va_bins_b) <= 1.0,
          "{:.1f} vs {:.1f} bins".format(va_bins_a, va_bins_b))
    fixed_a = build_profile(w, bin_size=1.0)
    fixed_b = build_profile(w5, bin_size=1.0)
    check("sec b.2 a FIXED 1.0-point bin is NOT scale-invariant -- the failure mode",
          len(fixed_b.centers) > 3 * len(fixed_a.centers),
          "{} bins vs {} bins at 5x price".format(len(fixed_a.centers),
                                                  len(fixed_b.centers)))

    # -----------------------------------------------------------------------
    # sec b.10 -- THE COUPLING. risk_R IS the value-area width plus a constant.
    # -----------------------------------------------------------------------
    hs = HARD_STOP_TICKS * TICK_SIZE
    worst = 0.0
    for ib in ib_windows("random_walk", 60, seed=5) + ib_windows("anchored_volume", 60,
                                                                 seed=6):
        for d in (1, -1):
            pr = build_profile(ib)
            entry = pr.vah if d == 1 else pr.val
            far = pr.val if d == 1 else pr.vah
            hard = far - hs if d == 1 else far + hs
            worst = max(worst, abs(abs(entry - hard) - ((pr.vah - pr.val) + hs)))
    check("sec b.10 risk_R == (VAH - VAL) + hard_stop_ticks, exactly, both sides",
          worst < 1e-9,
          "worst deviation {:.3g} pt -- so every R multiple is a linear function "
          "of the value-area width".format(worst))

    # -----------------------------------------------------------------------
    # sec b.11 -- THE POSITIVE-CONTROL QUARANTINE, enforced in code
    # -----------------------------------------------------------------------
    check("sec b.11 classify() names the three kinds of file",
          classify("data/raw/synthetic.parquet") == NEGATIVE_CONTROL
          and classify("data/raw/synthetic_structured.parquet") == POSITIVE_CONTROL
          and classify("data/raw/nq_ohlcv1m_2010-01-01_2026-08-31.parquet") == REAL)

    blocked = ["exit_mix", "touch_only_fills", "fill_rate", "step1_report",
               "funnel", "mfe", "inval_window", "risk_coupling", "pnl"]
    raised = []
    for stat in blocked:
        try:
            assert_reportable(POSITIVE_CONTROL, stat)
        except QuarantineError:
            raised.append(stat)
    check("sec b.11 the positive control may not source ANY reported statistic",
          raised == blocked, "blocked {}/{}".format(len(raised), len(blocked)))

    ok_one = True
    try:
        assert_reportable(POSITIVE_CONTROL, "b9_gate_verdict")
    except QuarantineError:
        ok_one = False
    check("sec b.11 the ONE permitted use -- the b.9 gate verdict -- still passes",
          ok_one, "otherwise the positive control could not do its job at all")

    clean = True
    for kind in (NEGATIVE_CONTROL, REAL):
        for stat in blocked:
            try:
                assert_reportable(kind, stat)
            except QuarantineError:
                clean = False
    check("sec b.11 the NEGATIVE control and real bars are NOT quarantined",
          clean, "the negative control was never tuned to a verdict")

    check("sec b.11 redact() withholds the value and keeps the label",
          redact(POSITIVE_CONTROL, "exit_mix", "19.0%") != "19.0%"
          and redact(POSITIVE_CONTROL, "b9_gate_verdict", "keep") == "keep"
          and redact(NEGATIVE_CONTROL, "exit_mix", "6.1%") == "6.1%")


    # ---- C4 AUDIT REGRESSIONS (Step 1 C4 audit, 2026-09-15) ---------------
    # Both defects produced a control that BEAT the strategy (+$7.37/session vs
    # -$2.57). Neither is detectable from C4's headline number alone, so both are
    # pinned here by construction rather than by eyeballing an expectancy.
    from ivb.controls import c4_random_time
    from ivb.backtest import simulate as _sim
    from ivb.sessions import stop_level as _stop

    def _late_break_flat(date: str) -> Session:
        """IB [100,110] for 30 bars, a wander INSIDE the range, break up at bar 60.

        Bars 61..80 are perfectly flat at 112.0, so every admissible C4 entry has
        entry == exit and nets exactly the round-turn cost. Any entry drawn from
        the pre-breakout wander lands on a different price and cannot produce
        that number -- which is the whole point of the fixture.
        """
        rows = [(101.0, 110.0, 100.0, 101.0, 500.0) for _ in range(30)]     # IB
        for i in range(30):                                                  # inside
            c = 101.0 + (i % 7)                                              # 101..107
            rows.append((c, min(c + 1, 110.0), max(c - 1, 100.0), c, 500.0))
        rows.append((110.0, 112.0, 110.0, 112.0, 500.0))                     # bar 60: break
        rows += [(112.0, 112.0, 112.0, 112.0, 500.0) for _ in range(20)]     # 61..80 flat
        return mk_session(rows, ib_high=110.0, ib_low=100.0, ib_close_idx=30, date=date)

    late = [_late_break_flat("2020-{:02d}-02".format(m)) for m in range(1, 13)]
    c4 = c4_random_time(late, P0)
    tr4 = c4[c4["traded"] == True]                                           # noqa: E712
    cost_pts = 2 * P0.slippage_points + (2 * P0.commission_per_side) / P0.point_value
    expected = -cost_pts * P0.point_value
    check("C4 D1 -- entry is NEVER drawn before the breakout entry bar",
          len(tr4) == len(late)
          and bool(np.allclose(tr4["net_dollars"].to_numpy(), expected)),
          "n={} all net=${:.2f}? (a pre-breakout draw cannot hit this)".format(
              len(tr4), expected))

    def _collapse(date: str) -> Session:
        """Breaks UP at bar 60, then every enterable bar sits BELOW the IB low.

        `opposite_ib_extreme` returns a fixed level, so the stop (99.75) ends up
        ABOVE a long's entry (90.0). `risk = abs(...)` stays positive, so the old
        code accepted it and `simulate` booked the stop as an instant winner.
        """
        rows = [(101.0, 110.0, 100.0, 101.0, 500.0) for _ in range(30)]
        rows += [(105.0, 106.0, 104.0, 105.0, 500.0) for _ in range(30)]
        rows.append((110.0, 112.0, 110.0, 112.0, 500.0))                     # bar 60
        rows += [(90.0, 90.0, 90.0, 90.0, 500.0) for _ in range(20)]         # below IB low
        return mk_session(rows, ib_high=110.0, ib_low=100.0, ib_close_idx=30, date=date)

    coll = [_collapse("2021-{:02d}-04".format(m)) for m in range(1, 13)]
    c4c = c4_random_time(coll, P0)
    check("C4 D2 -- a stop already on the profitable side of entry is SKIPPED",
          int((c4c["traded"] == True).sum()) == 0                            # noqa: E712
          and set(c4c["skip_reason"]) == {"stop_wrong_side"},
          "traded={} reasons={}".format(int((c4c["traded"] == True).sum()),   # noqa: E712
                                        sorted(set(c4c["skip_reason"]))))

    # The defect was real, not theoretical: price the rejected setup and show it
    # is a guaranteed win. If this ever stops being a win the guard is pointless.
    s_ = coll[0]
    ep_ = 90.0
    sl_ = _stop(s_, 1, ep_, P0)
    free = _sim(s_, 1, 61, ep_, sl_, ep_ + P0.r_mult * abs(ep_ - sl_), P0)
    check("C4 D2 -- the rejected setup really was free money (why the guard exists)",
          free.exit_reason == "stop" and free.net_dollars > 0 and sl_ > ep_,
          "stop {} > entry {} -> exit={} net=${:.2f}".format(
              sl_, ep_, free.exit_reason, free.net_dollars))

    # RESIDUAL EXPOSURE, recorded not asserted. run_strategy has no such guard
    # either. P0 is protected by its geometry, not by a check: it enters the bar
    # after a CLOSE through the IB edge, so the entry is normally on the far side
    # of the opposite extreme. A large enough gap on that entry bar would break
    # it. Measured on DEVELOPMENT: 0 of 1,971 trades, so it has never happened on
    # this sample -- which is an observation, not an invariant. The `coll`
    # fixture above is exactly the shape that would trip it.

    print("\n{}/{} control tests passed.".format(len(PASS), len(PASS) + len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
