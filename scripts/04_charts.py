"""CHARTS -- draw what IVB-SPEC.md describes, so it can be looked at.

This script produces pictures only. It writes no research artifact, decides no
gate, and its numbers must never be quoted as a result. Charts 3, 4 and 5 come
straight out of the real Step 1 code (`ivb.backtest.run_strategy`), so they cannot
drift from the backtest. Chart 1 and 2 need Layer 1 geometry, which Step 3 has not
built yet -- see the warning on `illustrate_layer1_trade` below.

Usage:
    python scripts/04_charts.py                                  # synthetic data
    python scripts/04_charts.py data/raw/nq_ohlcv1m_....parquet   # real data
    python scripts/04_charts.py <path> --session-date 2019-06-12
    python scripts/04_charts.py <path> --outdir output/charts

Output: output/charts/*.png  (never committed)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ivb.backtest import run_strategy                              # noqa: E402
from ivb.config import DATA, OUT, P0, TICK_SIZE                    # noqa: E402
from ivb.partitions import build_partitions, select                # noqa: E402
from ivb.profile import (DEFAULT_BIN_SIZE, DEFAULT_VA_PCT, METHOD_LABELS,  # noqa: E402
                         METHODS, build_profile, method_spread, reload_zone)
from ivb.rolls import (ROLL_FILE, build_roll_calendar, daily_adjusted,  # noqa: E402
                       front_month_bars, load_roll_calendar)
from ivb.data import load                                          # noqa: E402
from ivb.sessions import build_sessions, daily_features, find_breakout  # noqa: E402
from ivb.timestamps import assert_verified                         # noqa: E402
from src import viz                                                # noqa: E402

# ---- Layer 1 parameters, IVB-SPEC.md sec (f) defaults ------------------------
RELOAD_TIMEOUT_MIN = 30
TF_INVAL_MIN = 5
INVAL_BUFFER_TICKS = 0
HARD_STOP_TICKS = 8
MIN_OBS_PER_BUCKET = 100
TP1_PCT = 32.5            # = 1 - tp1_hit_rate_target (0.675)

SYNTHETIC = DATA / "raw" / "synthetic.parquet"


# =============================================================================
# ILLUSTRATIVE Layer 1 resolver
# =============================================================================
def illustrate_layer1_trade(s, cfg, *, bin_size=DEFAULT_BIN_SIZE,
                            va_pct=DEFAULT_VA_PCT, r_mult=2.0) -> dict:
    """Resolve ONE session under the Layer 1 rules, FOR DRAWING ONLY.

    ================== THIS IS NOT THE STEP 3 BACKTEST ==================
    Step 3 has not been written. This is a direct, deliberately plain reading of
    the spec (sec b.6, b.7 variant E1, b.8, c, c.1, c.2) so the geometry can be
    put on a chart. It has no unit tests, no cost sweep, no walk-forward, and no
    control. Every number it returns is a label on a picture, nothing more.
    =====================================================================

    Exit regime is `close_plus_hard` (sec c.1 regime 2), the tradeable one, so
    risk_R is measured against the hard stop as sec c.2 requires.
    Intrabar ambiguity is resolved against the trade, matching ivb/backtest.py.
    """
    ib_bars = s.bars.iloc[:s.ib_close_idx]
    prof = build_profile(ib_bars, method="volume_uniform", bin_size=bin_size,
                         va_pct=va_pct)
    out = {"profile": prof, "poc": prof.poc, "vah": prof.vah, "val": prof.val}

    bo = find_breakout(s, cfg)
    if bo is None:
        return {**out, "scenario": "no_breakout", "direction": 0}
    if bo["ambiguous_breakout"]:
        return {**out, "scenario": "ambiguous_breakout", "direction": 0}

    d = int(bo["direction"])
    sig = int(bo["signal_idx"])
    zb, zt, degen = reload_zone(d, prof.poc, prof.vah, prof.val)
    out.update({"direction": d, "breakout_idx": sig, "zone_bottom": zb,
                "zone_top": zt, "degenerate_zone": degen})

    # ---- b.7 E1: limit at the near value-area edge -------------------------
    limit = prof.vah if d == 1 else prof.val
    far = prof.val if d == 1 else prof.vah          # invalidation boundary
    hard = far - HARD_STOP_TICKS * TICK_SIZE if d == 1 else far + HARD_STOP_TICKS * TICK_SIZE
    buf = INVAL_BUFFER_TICKS * TICK_SIZE

    # ---- b.8 retracement window --------------------------------------------
    deadline = min(s.trade_end_idx, sig + RELOAD_TIMEOUT_MIN)
    fill_idx = None
    for i in range(sig + 1, deadline + 1):
        if (s.lo[i] <= limit) if d == 1 else (s.hi[i] >= limit):
            fill_idx = i
            break
    if fill_idx is None:
        return {**out, "scenario": "no_fill",
                "no_fill_reason": "zone not touched within {} min".format(
                    RELOAD_TIMEOUT_MIN)}

    entry = float(limit)
    risk = abs(entry - hard)                        # sec c.2, actual stop
    if risk <= 0:
        return {**out, "scenario": "zero_risk"}
    tp1 = entry + r_mult * risk * d

    exit_idx, exit_price, reason = s.trade_end_idx, float(s.cl[s.trade_end_idx]), "time"
    ts = pd.to_datetime(s.bars["ts_et"]).dt.minute.to_numpy()

    for i in range(fill_idx, s.trade_end_idx + 1):
        hit_hard = (s.lo[i] <= hard) if d == 1 else (s.hi[i] >= hard)
        hit_tp = (s.hi[i] >= tp1) if d == 1 else (s.lo[i] <= tp1)

        if hit_hard:                                # pessimistic: adverse first
            exit_idx, exit_price, reason = i, hard, "hard_stop"
            break
        if hit_tp and i > fill_idx:                 # entry bar cannot also target
            exit_idx, exit_price, reason = i, tp1, "target"
            break

        is_window_close = ((ts[i] + 1) % TF_INVAL_MIN) == 0
        if is_window_close:
            beyond = (s.cl[i] < far - buf) if d == 1 else (s.cl[i] > far + buf)
            if beyond and i < s.trade_end_idx:
                exit_idx = i + 1                    # sec c: next bar open, market
                exit_price, reason = float(s.op[i + 1]), "invalidated"
                break

    slip = cfg.slippage_points
    entry_fill = entry + slip if d == 1 else entry - slip
    exit_fill = exit_price if reason == "target" else (
        exit_price - slip if d == 1 else exit_price + slip)
    net = (exit_fill - entry_fill) if d == 1 else (entry_fill - exit_fill)
    net -= (2 * cfg.commission_per_side) / cfg.point_value

    # sec b.7: a fill where the bar merely GRAZED the limit assumes front-of-queue
    touch_only = bool(np.isclose(s.lo[fill_idx] if d == 1 else s.hi[fill_idx], entry))

    scenario = {"target": "target", "hard_stop": "stopped",
                "invalidated": "stopped", "time": "timed_out"}[reason]
    return {**out, "scenario": scenario, "touch_only_fill": touch_only,
            "entry_idx": fill_idx, "entry_price": entry,
            "stop_price": hard, "inval_price": far, "tp1_price": tp1, "tp1_r": r_mult,
            "exit_idx": exit_idx, "exit_price": exit_price, "exit_reason": reason,
            "risk_points": risk, "net_points": net, "r_multiple": net / risk}


# =============================================================================
# pipeline
# =============================================================================
def ensure_artifacts(bars: pd.DataFrame) -> pd.DataFrame:
    """Roll calendar / adjusted series / partitions, built if scripts/02 has not run."""
    adj_file = DATA / "daily_adjusted.parquet"
    if ROLL_FILE.exists() and adj_file.exists():
        return load_roll_calendar()
    print("[04] roll artifacts missing -- building them (same code as scripts/02)")
    cal = build_roll_calendar(bars)
    daily_adjusted(bars, cal).to_parquet(adj_file)
    build_partitions(cal["session_date"])
    return cal


def pick(cands: list, target_ib: float):
    """Deterministic choice, made for legibility, not for a flattering result.

    Prefers an early breakout (more post-breakout chart to look at) and an IB range
    near the sample median (so the price scale is typical). Ties break on date.
    """
    if not cands:
        return None
    return sorted(cands, key=lambda r: (r.get("breakout_idx", 999) > 45,
                                        abs(r["ib_range"] - target_ib),
                                        str(r["session_date"])))[0]


def terciles(x: pd.Series) -> pd.Series:
    q = x.quantile([1 / 3, 2 / 3]).to_numpy()
    return pd.cut(x, [-np.inf, q[0], q[1], np.inf], labels=["low", "mid", "high"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", nargs="?", default=str(SYNTHETIC))
    ap.add_argument("--session-date", default=None,
                    help="YYYY-MM-DD; force chart 1 and 2 onto this session")
    ap.add_argument("--outdir", default=str(OUT / "charts"))
    args = ap.parse_args()

    cfg = P0
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / ".gitignore").write_text("*\n", encoding="utf-8")

    assert_verified()
    bars = load(args.path)
    cal = ensure_artifacts(bars)
    front = select(front_month_bars(bars, cal), cfg.partition)
    feats = daily_features(pd.read_parquet(DATA / "daily_adjusted.parquet"), cfg)
    sessions = build_sessions(front, cfg)
    sessions = [s for s in sessions if not (cfg.exclude_half_days and s.is_half_day)]
    print("[04] {}  partition={}  sessions={:,}".format(
        Path(args.path).name, cfg.partition, len(sessions)))

    src_note = "SYNTHETIC random-walk data -- shapes only, no edge by construction" \
        if "synthetic" in Path(args.path).name else "source: " + Path(args.path).name
    written: list[Path] = []

    # ---- resolve every session once ----------------------------------------
    by_date = {str(s.session_date.date()): s for s in sessions}
    rows = []
    for s in sessions:
        r = illustrate_layer1_trade(s, cfg)
        r["session_date"] = s.session_date
        r["ib_range"] = s.ib_range
        rows.append(r)
    med_ib = float(np.median([r["ib_range"] for r in rows]))

    # =====================================================================
    # CHART 1 -- four annotated sessions
    # =====================================================================
    wanted = [
        ("a_textbook_long",
         lambda r: r["scenario"] == "target" and r["direction"] == 1,
         "CHART 1(a)   TEXTBOOK LONG -- break up, retrace to VAH, fill, TP1"),
        ("b_no_fill",
         lambda r: r["scenario"] == "no_fill",
         "CHART 1(b)   NO FILL -- price never came back. Layer 1 sits out, "
         "Layer 0 keeps the move"),
        ("c_stopped_out",
         lambda r: r.get("exit_reason") == "invalidated",
         "CHART 1(c)   STOPPED OUT -- filled, then CLOSED beyond the far "
         "value-area edge"),
        ("d_textbook_short",
         lambda r: r["scenario"] == "target" and r["direction"] == -1,
         "CHART 1(d)   TEXTBOOK SHORT -- the mirror of (a)"),
    ]
    # fallback so (c) always has a picture: a hard-stop exit is still a stop-out
    fallbacks = {"c_stopped_out": (
        lambda r: r.get("exit_reason") == "hard_stop",
        "CHART 1(c)   STOPPED OUT -- filled, then the HARD STOP fired (sec c.1)")}

    if args.session_date:
        s = by_date.get(args.session_date)
        if s is None:
            print("[04] session {} not in partition {}. Available: {} .. {}".format(
                args.session_date, cfg.partition, min(by_date), max(by_date)))
            return 2
        r = illustrate_layer1_trade(s, cfg)
        r["session_date"], r["ib_range"] = s.session_date, s.ib_range
        wanted = [("session_" + args.session_date, None,
                   "CHART 1   session {} -- scenario: {}".format(
                       args.session_date, r["scenario"]))]
        chosen = {wanted[0][0]: r}
    else:
        chosen, captions = {}, {}
        for name, pred, cap in wanted:
            c = pick([r for r in rows if pred(r)], med_ib)
            if c is None and name in fallbacks:
                alt_pred, alt_cap = fallbacks[name]
                c = pick([r for r in rows if alt_pred(r)], med_ib)
                if c is not None:
                    cap = alt_cap
                    print("[04] no '{}' example in sample; used the fallback".format(name))
            if c is None:
                print("[04] WARNING: no session matched scenario '{}'".format(name))
            else:
                chosen[name] = c
                captions[name] = cap
        wanted = [(n, p, captions.get(n, c)) for n, p, c in wanted]

    for name, _, caption in wanted:
        r = chosen.get(name)
        if r is None:
            continue
        s = by_date[str(r["session_date"].date())]
        win = s.bars.iloc[:s.trade_end_idx + 1]
        levels = {"ib_high": s.ib_high, "ib_low": s.ib_low, "vah": r["vah"],
                  "poc": r["poc"], "val": r["val"], "ib_end_idx": s.ib_close_idx,
                  "zone_bottom": r.get("zone_bottom"), "zone_top": r.get("zone_top")}
        trade = r if r.get("direction") else None
        f = viz.chart_session(
            win, levels, trade, r["profile"], title=caption,
            subtitle="{}   IB{}m, E1 limit at the near VA edge, close_plus_hard "
                     "exit, R=2.0   |   {}".format(
                         str(r["session_date"].date()), cfg.ib_minutes, src_note))
        written.append(viz.save(f, outdir / "01_{}.png".format(name)))

    # =====================================================================
    # CHART 2 -- sec b.9 allocation sensitivity
    # =====================================================================
    ref_row = chosen.get("a_textbook_long") or next(iter(chosen.values()))
    s = by_date[str(ref_row["session_date"].date())]
    ib_bars = s.bars.iloc[:s.ib_close_idx]
    profs = {m: build_profile(ib_bars, method=m) for m in METHODS}
    sp = method_spread(profs)
    f = viz.chart_profile_methods(
        profs, reference="volume_uniform", labels=METHOD_LABELS, spreads=sp,
        title="CHART 2   Why sec b.9 is a gate: the same session under four "
              "volume-allocation assumptions",
        subtitle="{}   VAL is the STOP and VAH is the ENTRY. If they move here, "
                 "the R:R claim moves with them.   |   {}".format(
                     str(s.session_date.date()), src_note))
    written.append(viz.save(f, outdir / "02_profile_methods.png"))

    # =====================================================================
    # CHART 3 -- sample funnel (real Step 1 code)
    # =====================================================================
    df = run_strategy(sessions, feats, cfg)
    s_all = len(df)
    s_break = int((df["skip_reason"].isin(["", "no_breakout", "ambiguous_breakout"])
                   & (df["traded"] == True)).sum())  # noqa: E712
    s_filled = sum(1 for r in rows if r["scenario"] in
                   ("target", "stopped", "timed_out"))
    f = viz.chart_funnel(
        [("S_all\nsessions in partition", s_all),
         ("S_breakout\nIB broke, trade taken", s_break),
         ("S_filled\nreload zone also touched", s_filled)],
        title="CHART 3   Sample funnel (IVB-SPEC.md sec h.1)",
        subtitle="{}   {}".format(cfg.partition, src_note),
        notes=["S_breakout is the denominator for Layer 0 vs Layer 1 (sec h.1).",
               "S_filled is from the ILLUSTRATIVE Layer 1 resolver, not a tested backtest.",
               "no_fill sessions are carried as zero-PnL, never dropped (sec b.8)."])
    written.append(viz.save(f, outdir / "03_funnel.png"))

    # =====================================================================
    # CHART 4 -- MFE distribution and TP1
    # =====================================================================
    traded = df[df["traded"] == True]  # noqa: E712
    mfe = traded["mfe_points"].to_numpy(float)
    tp1 = float(np.percentile(mfe, TP1_PCT)) if len(mfe) else np.nan

    # monthly block bootstrap of the percentile, matching ivb/stats.py philosophy
    lo = hi = np.nan
    if len(mfe) > 30:
        months = traded["session_date"].dt.to_period("M").astype(str).to_numpy()
        groups = [mfe[months == m] for m in pd.unique(months)]
        rng = np.random.default_rng(cfg.seed)
        boot = np.array([
            np.percentile(np.concatenate([groups[j] for j in
                                          rng.integers(0, len(groups), len(groups))]),
                          TP1_PCT) for _ in range(2000)])
        lo, hi = float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))

    f = viz.chart_mfe(
        mfe, tp1=tp1, ci=(lo, hi), pct=TP1_PCT,
        title="CHART 4   MFE before stop, and where TP1 lands (Step 2 preview)",
        subtitle="Layer 0 / P0 trades, {}   |   {}".format(cfg.partition, src_note),
        notes=["TP1 = {:.1f}th percentile, so it is reached ~{:.1f}% of the time.".format(
                   TP1_PCT, 100 - TP1_PCT),
               "MFE is 0 by rule on a bar where the stop also filled (pessimistic, sec a.5).",
               "This is the UNCONDITIONAL distribution. Step 2 cuts it by feature cell."])
    written.append(viz.save(f, outdir / "04_mfe_tp1.png"))

    # =====================================================================
    # CHART 5 -- Layer 3 cell counts
    # =====================================================================
    t = traded.copy()
    t["dir_cell"] = np.where(t["direction"] == 1, "long", "short")
    t["ib_cell"] = terciles(t["ib_range_atr"])
    t["dly_cell"] = terciles(t["brk_delay_min"].astype(float))

    six = (t.groupby(["dir_cell", "ib_cell"], observed=True).size()
            .rename("n").reset_index())
    eighteen = (t.groupby(["dir_cell", "ib_cell", "dly_cell"], observed=True).size()
                 .rename("n").reset_index())
    c6 = {"{}|{}".format(r.dir_cell, r.ib_cell): int(r.n) for r in six.itertuples()}
    c18 = {"{}|{}|{}".format(r.dir_cell, r.ib_cell, r.dly_cell): int(r.n)
           for r in eighteen.itertuples()}

    f = viz.chart_cell_counts(
        {"6-cell  direction x ib_range_atr": c6,
         "18-cell  + brk_delay": c18},
        min_obs=MIN_OBS_PER_BUCKET,
        title="CHART 5   Layer 3 cell counts against min_obs_per_bucket (sec h.3)",
        subtitle="{}   {}".format(cfg.partition, src_note),
        notes=["Counts shown are WHOLE-SAMPLE. Walk-forward splits them across 8 test",
               "folds, so divide by ~8 for the number a fold actually fits on.",
               "Terciles here are full-sample; the spec uses EXPANDING terciles (sec h.2).",
               "That changes which session lands in which cell, not the cell sizes."])
    written.append(viz.save(f, outdir / "05_cell_counts.png"))

    print("\n[04] wrote {} charts:".format(len(written)))
    for p in written:
        print("     " + str(p.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
