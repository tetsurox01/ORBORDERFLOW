"""STEP 1 -- the baseline IB breakout, its four controls, and the kill criteria.

RESEARCH-PLAN.md Step 1. Runs P0 only for the gates; the 16-config grid is a
labelled sensitivity appendix that can never pass, fail, or rescue a gate.

Usage:
    python scripts/03_run_step1.py data/raw/nq_ohlcv1m_2015-01-01_2026-09-01.parquet
    python scripts/03_run_step1.py <path> --no-grid     # skip the 16-config grid
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ivb.backtest import run_strategy                                    # noqa: E402
from ivb.config import P0, OUT, sensitivity_grid                         # noqa: E402
from ivb.controls import c1_drift, c2_coinflip, c3_inversion, c4_random_time  # noqa: E402
from ivb.data import load                                                # noqa: E402
from ivb.partitions import select                                        # noqa: E402
from ivb.provenance import assert_reportable, banner, classify           # noqa: E402
from ivb.report import write_step1                                       # noqa: E402
from ivb.rolls import front_month_bars, load_roll_calendar               # noqa: E402
from ivb.sessions import build_sessions, daily_features                  # noqa: E402
from ivb.stats import metrics, paired_block_bootstrap_ci, percentile_rank  # noqa: E402
from ivb.timestamps import assert_verified                               # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    do_grid = "--no-grid" not in sys.argv
    cfg = P0
    t0 = time.time()

    # sec b.11 QUARANTINE. Step 1 is nothing BUT reported statistics -- expectancy,
    # profit factor, the four controls, the funnel. The positive control was tuned
    # until sec b.9 returned "not material", so it was selected to produce an
    # outcome and none of these numbers mean anything. Refuse outright.
    kind = classify(path)
    for line in banner(kind):
        print("[03] " + line)
    assert_reportable(kind, "step1_report")

    assert_verified()
    print("[03] timestamp convention verified")

    bars = load(path)
    cal = load_roll_calendar()
    front = front_month_bars(bars, cal)
    print(f"[03] front-month bars: {len(front):,}")

    # DEVELOPMENT only. Holdouts are sealed in code and raise if touched.
    front = select(front, cfg.partition)
    print(f"[03] partition={cfg.partition}: {front['session_date'].nunique():,} sessions")

    adj = pd.read_parquet("data/daily_adjusted.parquet")
    feats = daily_features(adj, cfg)

    sessions = build_sessions(front, cfg)
    print(f"[03] sessions built: {len(sessions):,}")

    # ---- P0 ---------------------------------------------------------------
    print("[03] running P0 ...")
    df = run_strategy(sessions, feats, cfg)
    m = metrics(df, s_all=len(df))
    print(f"[03] P0: {m['trades']:,} trades over {m['sessions']:,} sessions, "
          f"exp/session = ${m['exp_per_session']:.3f}")

    # ---- controls ----------------------------------------------------------
    print("[03] controls C1, C3, C4 ...")
    controls = {
        "C1 drift (stop-matched)": c1_drift(sessions, cfg, stop_matched=True),
        "C1 drift (no stop)": c1_drift(sessions, cfg, stop_matched=False),
        "C3 inversion": c3_inversion(sessions, cfg),
        "C4 random-time": c4_random_time(sessions, cfg),
    }

    print(f"[03] C2 coin-flip, {cfg.n_shuffles} shuffles (slow) ...")
    c2 = c2_coinflip(sessions, cfg)
    dist = c2["expectancy_per_session"].to_numpy()
    pct = percentile_rank(m["exp_per_session"], dist)
    p_val = float((dist >= m["exp_per_session"]).mean())

    # ---- paired CIs --------------------------------------------------------
    print("[03] paired block bootstrap ...")
    cis = {}
    for name in ("C1 drift (stop-matched)", "C3 inversion", "C4 random-time"):
        cis[f"P0 - {name}"] = paired_block_bootstrap_ci(
            df, controls[name], n=cfg.bootstrap_n, seed=cfg.seed
        )
    # direction_value = (P0 - inverse) / 2, valid under the same-distance reading
    dv = paired_block_bootstrap_ci(df, controls["C3 inversion"], n=cfg.bootstrap_n, seed=cfg.seed)
    cis["direction_value = (P0 - C3)/2"] = {
        "point": dv["point"] / 2, "lo": dv["lo"] / 2, "hi": dv["hi"] / 2,
        "n_blocks": dv["n_blocks"], "excludes_zero": dv["excludes_zero"],
    }

    extras = {
        "source": path,   # sec b.11: carried so write_step1 can re-check it
        "controls": {k: metrics(v, s_all=len(df)) for k, v in controls.items()},
        "cis": cis,
        "c2": {"pct_rank": pct, "p_value": p_val, "n": len(dist)},
    }

    # ---- 16-config sensitivity grid ----------------------------------------
    if do_grid:
        print("[03] 16-config sensitivity grid ...")
        rows = []
        for gc in sensitivity_grid():
            gdf = run_strategy(sessions, feats, gc)
            gm = metrics(gdf, s_all=len(gdf))
            rows.append({"config": gc.label, "trades": gm["trades"],
                         "exp_per_session": gm["exp_per_session"],
                         "exp_per_trade": gm["exp_per_trade"],
                         "profit_factor": gm["profit_factor"],
                         "win_rate": gm["win_rate"]})
        extras["grid"] = pd.DataFrame(rows)

    text = write_step1(df, cfg, extras)
    print("\n" + text)

    # ---- kill criteria -----------------------------------------------------
    print("\n" + "=" * 78)
    print("KILL CRITERIA (spec sec i.3) -- P0 only, S_all, MNQ, DEVELOPMENT")
    print("=" * 78)
    c1ci = cis["P0 - C1 drift (stop-matched)"]
    dvci = cis["direction_value = (P0 - C3)/2"]
    amb = df[df["traded"] == True]["ambiguous"].mean() if (df["traded"] == True).any() else np.nan  # noqa: E712

    checks = [
        ("1. P0 - C1 CI excludes zero, positive",
         bool(c1ci.get("lo", -1) > 0)),
        ("2. P0 above 90th pct of C2 shuffles",
         bool(pct > 90)),
        ("3. direction_value CI excludes zero, positive",
         bool(dvci.get("lo", -1) > 0)),
        ("4. ambiguous_bar_pct <= 15%",
         bool(np.isfinite(amb) and amb <= cfg.ambiguous_bar_gate)),
    ]
    if do_grid:
        pos = int((extras["grid"]["exp_per_session"] > 0).sum())
        label5 = (f"5. grid_robustness={pos}/16 -- "
                  + ("uniform fail, no config positive" if pos == 0
                     else "spike band (1-4), evidence AGAINST P0" if pos <= 4
                     else "outside spike band"))
        checks.append((label5, bool(pos > 4)))

    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")

    verdict = all(ok for _, ok in checks)
    print("\nVERDICT: " + ("PASS -- proceed to Step 2." if verdict else
                           "FAIL -- Layer 0 is not an edge on this sample. STOP.\n"
                           "        Layers 1-3 cannot rescue a non-existent directional base."))
    print(f"\n[03] {time.time() - t0:.0f}s   report -> {OUT / f'step1_{cfg.label}.txt'}")
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
