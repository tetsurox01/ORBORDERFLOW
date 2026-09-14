"""Synthetic tests for the pessimistic intrabar rule -- IVB-SPEC.md sec a.5.

These verify the logic against hand-constructed bars where the correct answer is
known. They do not need market data and must pass before any real backtest is
believed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ivb.backtest import simulate                      # noqa: E402
from ivb.config import P0                              # noqa: E402
from ivb.sessions import Session                       # noqa: E402

CFG = P0.with_(slippage_ticks_market=0, commission_per_side=0.0)


def mk_session(bars: list[tuple[float, float, float, float]]) -> Session:
    df = pd.DataFrame(bars, columns=["open", "high", "low", "close"])
    df["ts_et"] = pd.date_range("2020-01-02 10:00", periods=len(df), freq="1min", tz="America/New_York")
    df["volume"] = 100.0
    df["roll_day_flag"] = False
    return Session(
        session_date=pd.Timestamp("2020-01-02"), bars=df,
        ib_high=105.0, ib_low=95.0, ib_range=10.0,
        ib_close_idx=0, trade_end_idx=len(df) - 1,
        is_half_day=False, roll_day_flag=False,
    )


def test_case1_stop_and_target_same_bar_gives_stop():
    """Bar spans both levels. Pessimistic -> stop. The stop bar contributes 0 MFE."""
    s = mk_session([
        (100, 100.0, 99.5, 100),   # entry bar, NO favourable excursion
        (100, 110.0, 90.0, 100),   # spans stop(95) AND target(110)
    ])
    t = simulate(s, 1, 0, 100.0, 95.0, 110.0, CFG)
    assert t.exit_reason == "stop", t.exit_reason
    assert t.exit_price == 95.0
    assert t.ambiguous is True
    assert t.ambiguous_case == "stop_and_target"
    assert t.mfe_points == 0.0, f"stop-out bar must contribute 0 MFE, got {t.mfe_points}"
    print("PASS case1 stop_and_target -> stop, stop bar contributes 0 MFE")


def test_case1_retains_earlier_legitimate_excursion():
    """The stop bar contributes 0, but REAL excursion on earlier bars is kept.

    'MFE on a stop-out bar = 0' means that bar adds nothing -- it does not erase
    excursion the trade genuinely achieved before it.
    """
    s = mk_session([
        (100, 103.0, 99.5, 102),   # +3 genuinely achieved, no stop touched
        (102, 110.0, 90.0, 100),   # spans stop AND target -> stop
    ])
    t = simulate(s, 1, 0, 100.0, 95.0, 110.0, CFG)
    assert t.exit_reason == "stop"
    assert t.mfe_points == 3.0, f"earlier excursion must be retained, got {t.mfe_points}"
    print("PASS earlier legitimate excursion retained (MFE=3.0)")


def test_case2_entry_and_stop_same_bar():
    """Stop touched on the entry bar itself -> immediate full loss."""
    s = mk_session([(100, 101.0, 94.0, 96.0)])
    t = simulate(s, 1, 0, 100.0, 95.0, 110.0, CFG)
    assert t.exit_reason == "stop"
    assert t.ambiguous_case == "entry_and_stop"
    assert t.net_points == -5.0, t.net_points
    print("PASS case2 entry_and_stop -> immediate loss")


def test_case4_entry_and_target_same_bar_does_not_fill():
    """Favourable half of the entry bar is assumed to precede the fill."""
    s = mk_session([
        (100, 111.0, 99.5, 100),   # target(110) touched on entry bar
        (100, 100.2, 99.8, 100),   # quiet
    ])
    t = simulate(s, 1, 0, 100.0, 95.0, 110.0, CFG)
    assert t.exit_reason == "time", f"expected time exit, got {t.exit_reason}"
    assert t.ambiguous_case == "entry_and_target"
    print("PASS case4 entry_and_target -> target does NOT fill")


def test_clean_target_fills():
    s = mk_session([
        (100, 100.5, 99.5, 100),
        (100, 110.5, 99.6, 110),
    ])
    t = simulate(s, 1, 0, 100.0, 95.0, 110.0, CFG)
    assert t.exit_reason == "target"
    assert t.net_points == 10.0
    assert t.r_multiple == 2.0, t.r_multiple
    print("PASS clean target fill, R = 2.0")


def test_short_side_mirrors():
    s = mk_session([
        (100, 100.5, 99.5, 100),
        (100, 100.4, 89.5, 90),
    ])
    t = simulate(s, -1, 0, 100.0, 105.0, 90.0, CFG)
    assert t.exit_reason == "target"
    assert t.net_points == 10.0
    print("PASS short side mirrors long")


def test_optimistic_flips_case1():
    s = mk_session([
        (100, 100.5, 99.5, 100),
        (100, 110.0, 90.0, 100),
    ])
    t = simulate(s, 1, 0, 100.0, 95.0, 110.0, CFG.with_(intrabar="optimistic"))
    assert t.exit_reason == "target", t.exit_reason
    print("PASS optimistic diagnostic flips case1 to target")


def test_costs_applied():
    """1 tick slippage each side + commission, on a market entry and time exit."""
    cfg = P0.with_(slippage_ticks_market=1, commission_per_side=0.85, cost_model="MNQ")
    s = mk_session([(100, 100.5, 99.5, 100), (100, 100.5, 99.5, 100)])
    t = simulate(s, 1, 0, 100.0, 95.0, 110.0, cfg)
    # gross 0; entry +0.25 adverse, exit -0.25 adverse, commission 1.70/2 = 0.85 pt
    expected = -0.25 - 0.25 - (2 * 0.85 / 2.0)
    assert abs(t.net_points - expected) < 1e-9, (t.net_points, expected)
    print(f"PASS costs: net {t.net_points:.3f} pts on a flat trade (MNQ drag)")


def test_mfe_raw_ignores_stop():
    """MFE_raw must see the high even when the trade was stopped out earlier."""
    s = mk_session([
        (100, 100.5, 94.0, 96.0),   # stopped here
        (96, 130.0, 95.0, 129.0),   # huge move after the stop
    ])
    t = simulate(s, 1, 0, 100.0, 95.0, 110.0, CFG)
    assert t.exit_reason == "stop"
    assert t.mfe_points == 0.0
    assert t.mfe_raw_points == 30.0, t.mfe_raw_points
    print("PASS MFE_raw ignores the stop; MFE_net does not")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
    print(f"\n{len(fns)}/{len(fns)} synthetic tests passed.")
