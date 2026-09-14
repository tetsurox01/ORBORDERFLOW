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
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ivb.backtest import run_strategy                              # noqa: E402
from ivb.config import (DATA, GRID_BIN_WIDTH_MULTS,                # noqa: E402
                        GRID_HARD_STOP_TICKS, OUT, P0, TICK_SIZE)
from ivb.exits import (CLOSE_INVALIDATION, HARD_STOP, TIME_STOP,   # noqa: E402
                       TP1 as EXIT_TP1, format_frequency, frequency, resolve)
from ivb.partitions import build_partitions, select                # noqa: E402
from ivb.quality import degraded_dates, load_degraded             # noqa: E402
from ivb.profile import (BIN_WIDTH_MULT, DEFAULT_VA_PCT, METHOD_LABELS,  # noqa: E402
                         METHODS, bin_width, build_profile, method_spread,
                         reload_zone)
from ivb.provenance import (NEGATIVE_CONTROL, POSITIVE_CONTROL,  # noqa: E402
                            assert_reportable, banner, classify, is_synthetic,
                            redact)
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
def illustrate_layer1_trade(s, cfg, *, bin_size=None, bin_mult=BIN_WIDTH_MULT,
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

    `exit_reason` is one of the four members of ivb.exits.LAYER1_EXIT_REASONS and
    nothing else, and `scenario` carries the SAME string for a filled trade -- the
    two adverse categories must never be collapsed into one bucket (sec b.10).
    """
    ib_bars = s.bars.iloc[:s.ib_close_idx]
    # bin_size=None -> the sec b.2 pre-registered RELATIVE rule, per session.
    prof = build_profile(ib_bars, method="volume_uniform", bin_size=bin_size,
                         bin_mult=bin_mult, va_pct=va_pct)
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
    # sec b.10: BOTH numbers, always. risk_R is the first one (sec c.2); the second
    # is the distance Valentini's framing implicitly quotes, and it is never the
    # denominator of an R multiple here.
    risk_to_hard = abs(entry - hard)
    risk_to_val = abs(entry - far)
    risk = risk_to_hard                             # sec c.2, the ACTUAL stop
    if risk <= 0:
        return {**out, "scenario": "zero_risk"}
    tp1 = entry + r_mult * risk * d

    # sec b.10: what Layer 0 would have risked on the same session, for contrast.
    l0_entry = float(s.op[sig + 1]) if sig + 1 <= s.trade_end_idx else float(s.cl[sig])
    l0_stop = s.ib_low if d == 1 else s.ib_high
    l0_risk = abs(l0_entry - l0_stop)

    exit_idx = s.trade_end_idx
    exit_price = float(s.cl[s.trade_end_idx])
    reason = TIME_STOP
    ts = pd.to_datetime(s.bars["ts_et"]).dt.minute.to_numpy()

    for i in range(fill_idx, s.trade_end_idx + 1):
        hit_hard = (s.lo[i] <= hard) if d == 1 else (s.hi[i] >= hard)
        hit_tp = (s.hi[i] >= tp1) if d == 1 else (s.lo[i] <= tp1)

        if hit_hard:                                # pessimistic: adverse first
            exit_idx, exit_price, reason = i, hard, HARD_STOP
            break
        if hit_tp and i > fill_idx:                 # entry bar cannot also target
            exit_idx, exit_price, reason = i, tp1, EXIT_TP1
            break

        is_window_close = ((ts[i] + 1) % TF_INVAL_MIN) == 0
        if is_window_close:
            beyond = (s.cl[i] < far - buf) if d == 1 else (s.cl[i] > far + buf)
            if beyond and i < s.trade_end_idx:
                exit_idx = i + 1                    # sec c: next bar open, market
                exit_price = float(s.op[i + 1])
                # Hard-stop dominance: if that open is at or through the hard stop,
                # the resting stop filled first and this is a hard_stop, not an
                # invalidation. Same fill price, different bucket -- and the bucket
                # is the number sec c.3 turns on.
                reason = resolve(d, CLOSE_INVALIDATION, exit_price, hard)
                break

    slip = cfg.slippage_points
    entry_fill = entry + slip if d == 1 else entry - slip
    exit_fill = exit_price if reason == EXIT_TP1 else (
        exit_price - slip if d == 1 else exit_price + slip)
    net = (exit_fill - entry_fill) if d == 1 else (entry_fill - exit_fill)
    net -= (2 * cfg.commission_per_side) / cfg.point_value

    # sec b.7: a fill where the bar merely GRAZED the limit assumes front-of-queue
    touch_only = bool(np.isclose(s.lo[fill_idx] if d == 1 else s.hi[fill_idx], entry))

    # sec b.10: the price band in which close_invalidation is even POSSIBLE. Below
    # `far` the close rule can fire; at or below `hard` the resting stop has
    # already filled. So the rule lives entirely inside |far - hard|, and that
    # distance is HARD_STOP_TICKS by construction -- it does not vary with the
    # profile, the session, or anything a market does. Reported per fill so the
    # constancy is measured rather than asserted.
    inval_window = abs(far - hard)

    return {**out, "scenario": reason, "touch_only_fill": touch_only,
            "entry_idx": fill_idx, "entry_price": entry,
            "inval_window_points": inval_window,
            "inval_window_ticks": inval_window / TICK_SIZE,
            "inval_window_frac_of_risk": inval_window / risk,
            "stop_price": hard, "inval_price": far, "tp1_price": tp1, "tp1_r": r_mult,
            "exit_idx": exit_idx, "exit_price": exit_price, "exit_reason": reason,
            "risk_points": risk, "risk_to_hard_stop": risk_to_hard,
            "risk_to_val": risk_to_val, "layer0_entry_price": l0_entry,
            "layer0_stop_price": l0_stop, "layer0_risk_points": l0_risk,
            "net_points": net, "r_multiple": net / risk}


# =============================================================================
# pipeline
# =============================================================================
def ensure_artifacts(bars: pd.DataFrame, src: Path) -> pd.DataFrame:
    """Roll calendar / adjusted series / partitions, built if scripts/02 has not run.

    The artifacts are KEYED ON THE SOURCE FILE. daily_adjusted.parquet feeds ATR14,
    which feeds the min_ib_range_atr no-trade filter, so silently reusing another
    file's artifacts would filter one dataset's sessions using another dataset's
    volatility. A stamp file records which source built them; a mismatch rebuilds.
    """
    adj_file = DATA / "daily_adjusted.parquet"
    stamp = DATA / "artifacts_source.json"
    st = src.stat()
    # Name is not enough: a regenerated file keeps its name and changes every bar in
    # it. Size and mtime go into the key so re-running the generator invalidates the
    # cache. Getting this wrong is silent -- ATR14 from one dataset filtering the
    # sessions of another -- so it is keyed on content, not on intent.
    key = {"source": src.name, "size": st.st_size, "mtime_ns": st.st_mtime_ns}
    prev = (json.loads(stamp.read_text(encoding="utf-8")) if stamp.exists() else {})
    same = prev == key
    if ROLL_FILE.exists() and adj_file.exists() and same:
        return load_roll_calendar()
    if ROLL_FILE.exists() and not same:
        why = ("a DIFFERENT source file" if prev.get("source") != src.name
               else "an OLDER version of this same file")
        print("[04] artifacts were built from {} -- rebuilding for {}".format(
            why, src.name))
    else:
        print("[04] roll artifacts missing -- building them (same code as scripts/02)")
    cal = build_roll_calendar(bars)
    daily_adjusted(bars, cal).to_parquet(adj_file)
    build_partitions(cal["session_date"])
    stamp.write_text(json.dumps(key, indent=2), encoding="utf-8")
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


def b9_sensitivity(sessions, cfg, *, bin_mult=BIN_WIDTH_MULT) -> dict:
    """sec b.9 across the WHOLE partition, not one session.

    The gate is aimed at the two quantities the allocation assumption can actually
    corrupt under exit regime 2 (sec b.10):

      d_risk       spread of risk_to_hard_stop = (VAH - VAL) + hard_stop_ticks.
                   The constant cancels, so this is the spread of the VA WIDTH --
                   it moves whether VAH moves, VAL moves, or both.
      d_fill_rate  spread of the E1 fill rate across M1..M4. A method that puts the
                   near edge somewhere else trades a different set of sessions.

    BIN WIDTH is the sec b.2 RELATIVE rule (median IB bar range, per session),
    scaled by `bin_mult`. `bin_mult=1.0` is the pre-registered primary; 0.5 and 2.0
    are the labelled sensitivity. The realised width distribution is returned so the
    rule's effect is visible rather than assumed -- and so is `bars_per_bin`, the
    median IB bar range measured in bins, which is the quantity that actually drives
    whether the four methods can disagree (sec b.9 mechanism note).

    d_VAL alone is NOT the trigger any more. Under regime 2 the stop is
    `VAL -/+ hard_stop_ticks`, so VAL only reaches risk_R through d_risk, and d_risk
    already contains it. Keying the gate on d_VAL misses an entry that moves while
    the stop stands still -- which is what the single-session run actually showed.
    """
    per_method_fills = {m: 0 for m in METHODS}
    d_risk, d_poc, d_vah, d_val, risk_hard = [], [], [], [], []
    widths, spans = [], []
    n_breakout = 0
    n_degraded = 0
    broke_dates = set()

    # sec 0.2.4: the gate is measured on the IB PROFILE, and a degraded day can be
    # missing the messages that define it. Excluded here as well as in the backtest,
    # or the gate would be decided partly on windows that are not real.
    degraded = degraded_dates()

    for s in sessions:
        if s.session_date in degraded:
            n_degraded += 1
            continue
        bo = find_breakout(s, cfg)
        if bo is None or bo["ambiguous_breakout"]:
            continue
        n_breakout += 1
        broke_dates.add(s.session_date)
        d = int(bo["direction"])
        sig = int(bo["signal_idx"])
        deadline = min(s.trade_end_idx, sig + RELOAD_TIMEOUT_MIN)
        lo_w = s.lo[sig + 1:deadline + 1]
        hi_w = s.hi[sig + 1:deadline + 1]

        ib_bars = s.bars.iloc[:s.ib_close_idx]
        bw = bin_width(ib_bars, mult=bin_mult)
        widths.append(bw / TICK_SIZE)
        med_bar = float(np.median(ib_bars["high"].to_numpy(float)
                                  - ib_bars["low"].to_numpy(float)))
        spans.append(med_bar / bw)
        profs = {m: build_profile(ib_bars, method=m, bin_size=bw) for m in METHODS}
        sp = method_spread(profs)
        d_risk.append(sp["d_risk"])
        d_poc.append(sp["d_POC"])
        d_vah.append(sp["d_VAH"])
        d_val.append(sp["d_VAL"])

        prim = profs["volume_uniform"]
        risk_hard.append((abs((prim.vah if d == 1 else prim.val)
                              - (prim.val if d == 1 else prim.vah))
                          + HARD_STOP_TICKS * TICK_SIZE) / TICK_SIZE)

        for m, p in profs.items():
            lim = p.vah if d == 1 else p.val
            hit = bool((lo_w <= lim).any()) if d == 1 else bool((hi_w >= lim).any())
            per_method_fills[m] += int(hit)

    def q(v):
        a = np.asarray(v, float)
        if not len(a):
            return {"p50": np.nan, "p90": np.nan, "max": np.nan}
        return {"p50": float(np.percentile(a, 50)),
                "p90": float(np.percentile(a, 90)),
                "max": float(a.max())}

    fill_rates = {m: (100.0 * n / n_breakout if n_breakout else np.nan)
                  for m, n in per_method_fills.items()}
    d_fill = (max(fill_rates.values()) - min(fill_rates.values())
              if n_breakout else np.nan)
    # sec b.10 worked example: the allocation assumption does not only move
    # risk_R, it moves HOW MANY TRADES EXIST. A rate spread that looks small in
    # percentage points is a large absolute swing in S_filled once it is
    # multiplied by n_breakout, and S_filled is the denominator of every Layer 1
    # per-trade statistic. Reported next to d_fill_rate, never instead of it.
    d_fill_count = (max(per_method_fills.values()) - min(per_method_fills.values())
                    if n_breakout else 0)
    med_risk = float(np.median(risk_hard)) if risk_hard else np.nan

    gate = {
        "d_risk p50 > 0.20 * median(risk_to_hard_stop)":
            bool(q(d_risk)["p50"] > 0.20 * med_risk),
        "d_risk p90 > 0.40 * median(risk_to_hard_stop)":
            bool(q(d_risk)["p90"] > 0.40 * med_risk),
        "d_fill_rate > 10 percentage points": bool(d_fill > 10.0),
        "d_POC p50 > 4 ticks": bool(q(d_poc)["p50"] > 4.0),
    }
    return {"n_breakout": n_breakout, "broke_dates": broke_dates,
            "n_degraded_excluded": n_degraded,
            "bin_mult": bin_mult,
            "bin_width_ticks": q(widths), "bars_per_bin": q(spans),
            "d_risk": q(d_risk), "d_POC": q(d_poc),
            "d_VAH": q(d_vah), "d_VAL": q(d_val), "fill_rates": fill_rates,
            "d_fill_rate": d_fill, "fill_counts": dict(per_method_fills),
            "d_fill_count": d_fill_count,
            "median_risk_to_hard_stop_ticks": med_risk,
            "gate": gate, "MATERIAL": any(gate.values())}


def b9_caveat(null_synth: bool, pos_synth: bool, material: bool) -> list:
    """The sec b.9 admissibility note. The two synthetic files expect OPPOSITE
    verdicts, so each gets its own text and each says why the verdict is not a
    finding about NQ.
    """
    if null_synth:
        out = ["*** NOT ADMISSIBLE -- NEGATIVE CONTROL. This generator draws bar volume",
               "*** from rng.integers(200, 2000): i.i.d. and INDEPENDENT of price. No",
               "*** volume structure exists for a profile to find, so POC is noise and",
               "*** the four methods must disagree. MATERIAL is the arithmetic working,",
               "*** not a finding about Layer 1."]
        if not material:
            out.append("*** CONTROL FAILED: the negative control did NOT trip. That is a bug.")
        else:
            out.append("*** Control behaved as required: the gate FIRES.")
        return out + ["*** sec b.9 is DECIDED on real NQ bars only."]
    if pos_synth:
        out = ["*** NOT ADMISSIBLE -- POSITIVE CONTROL, and QUARANTINED (sec b.11).",
               "*** Inside the IB, price mean-reverts around a slowly drifting anchor and",
               "*** volume is a kernel of the distance from it, so a real POC exists. The",
               "*** generator was tuned until this verdict came out NOT MATERIAL; the GATE",
               "*** THRESHOLDS were not touched. Under the sec b.2 RELATIVE bin width the",
               "*** two controls no longer separate on absolute bar height -- the bin",
               "*** scales with the bar -- so they separate on volume STRUCTURE alone,",
               "*** which is what they were always meant to test.",
               "*** This verdict is the ONLY thing this file may source. Every other",
               "*** statistic from it is withheld, and charts 3-5 are not drawn."]
        if material:
            out.append("*** CONTROL FAILED: the positive control still trips. The gate has")
            out.append("*** still never executed its pass branch -- treat MATERIAL elsewhere")
            out.append("*** as uninformative until this is fixed.")
        else:
            out.append("*** Control behaved as required: the gate CAN return NOT MATERIAL,")
            out.append("*** so a MATERIAL verdict elsewhere is now informative in both")
            out.append("*** directions.")
        return out + ["*** sec b.9 is DECIDED on real NQ bars only."]
    return []


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
    cal = ensure_artifacts(bars, Path(args.path))
    front = select(front_month_bars(bars, cal), cfg.partition)
    feats = daily_features(pd.read_parquet(DATA / "daily_adjusted.parquet"), cfg)
    sessions = build_sessions(front, cfg)
    sessions = [s for s in sessions if not (cfg.exclude_half_days and s.is_half_day)]
    print("[04] {}  partition={}  sessions={:,}".format(
        Path(args.path).name, cfg.partition, len(sessions)))

    # Which file is this? The two synthetic files carry OPPOSITE expectations for
    # b.9, and the positive control is QUARANTINED (sec b.11) -- one shared "is it
    # synthetic" flag would put the wrong caveat on the chart and let the tuned
    # file's statistics out.
    name = Path(args.path).name
    kind = classify(args.path)
    null_synth = kind == NEGATIVE_CONTROL
    pos_synth = kind == POSITIVE_CONTROL
    synthetic = is_synthetic(kind)

    # sec b.11: on the positive control every statistic except the sec b.9 gate
    # verdict is withheld. `Q(stat, text)` replaces the value and keeps the label,
    # so a withheld number is visibly withheld rather than silently absent.
    def Q(stat: str, text: str) -> str:
        return redact(kind, stat, text)

    for line in banner(kind):
        print("[04] " + line)

    if null_synth:
        src_note = "SYNTHETIC random-walk data -- shapes only, no edge by construction"
    elif pos_synth:
        src_note = ("SYNTHETIC structured-volume data -- sec b.9 POSITIVE CONTROL, "
                    "QUARANTINED (sec b.11): gate verdict only")
    else:
        src_note = "source: " + name
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
    # DIAGNOSTICS -- printed, not plotted. These are the numbers that decide
    # things, so they go to the console where they cannot be read off a picture.
    # =====================================================================
    filled = [r for r in rows if r.get("entry_idx") is not None]
    freq = frequency([r["exit_reason"] for r in filled])
    n_touch = sum(1 for r in filled if r["touch_only_fill"])
    touch_pct = 100.0 * n_touch / len(filled) if filled else float("nan")

    print("\n[04] Layer 1 exit taxonomy (ILLUSTRATIVE resolver, sec c / c.1):")
    print(Q("exit_mix", format_frequency(freq)))
    print("     close_invalidation vs hard_stop is the sec c.3 question. If those")
    print("     two are ever merged, the question cannot be answered.")

    # ---- sec b.10: how much room does the close rule actually have? ----------
    win_t = np.array([r["inval_window_ticks"] for r in filled], float)
    win_f = np.array([r["inval_window_frac_of_risk"] for r in filled], float)
    ci_n = freq[CLOSE_INVALIDATION]
    ci_pct = 100.0 * ci_n / max(1, freq["total"])
    b10 = {"p10": float(np.percentile(win_t, 10)) if len(win_t) else np.nan,
           "p50": float(np.percentile(win_t, 50)) if len(win_t) else np.nan,
           "p90": float(np.percentile(win_t, 90)) if len(win_t) else np.nan,
           "min": float(win_t.min()) if len(win_t) else np.nan,
           "max": float(win_t.max()) if len(win_t) else np.nan,
           "frac_p50": float(np.percentile(win_f, 50)) if len(win_f) else np.nan,
           "ci_n": ci_n, "ci_pct": ci_pct, "n_fills": len(filled)}

    # sec b.10 COUPLING -- risk_R IS the value-area width plus a constant:
    #     risk_R = |entry - hard_stop| = (VAH - VAL) + hard_stop_ticks
    # for a long (entry VAH, hard VAL - h) and for a short alike. So every R
    # multiple, TP1 at 2R included, is a linear function of (VAH - VAL) -- the exact
    # quantity sec b.9 measures the instability of as `d_risk`.
    va_w = np.array([r["risk_to_val"] for r in filled], float) / TICK_SIZE
    rr = np.array([r["risk_to_hard_stop"] for r in filled], float) / TICK_SIZE
    hs_share = float(np.median(HARD_STOP_TICKS / rr)) if len(rr) else np.nan

    print("\n[04] sec b.10  (VAL - hard_stop) = the band the close rule can fire in,")
    print("     over all {:,} fills, in ticks:".format(len(filled)))
    print("     " + Q("inval_window",
                      "p10 {:5.1f}   p50 {:5.1f}   p90 {:5.1f}      min {:5.1f}   "
                      "max {:5.1f}".format(b10["p10"], b10["p50"], b10["p90"],
                                           b10["min"], b10["max"])))
    print("     as a fraction of risk_to_hard_stop: p50 " + Q(
        "inval_window", "{:.3f}".format(b10["frac_p50"])))
    if np.isclose(b10["min"], b10["max"]):
        print("     CONSTANT at {:.0f} ticks = hard_stop_ticks. Not a distribution --"
              .format(b10["p50"]))
        print("     `hard = far -/+ hard_stop_ticks` makes this band a fixed width by")
        print("     construction. It is measured here only to confirm that.")
    print("     " + Q("exit_mix", "close_invalidation fired {:,}/{:,} = {:.1f}% of "
                      "exits.".format(ci_n, freq["total"], ci_pct)))

    print("\n[04] sec b.10 COUPLING -- risk_R IS the value-area width:")
    print("     risk_R = |entry - hard_stop| = (VAH - VAL) + hard_stop_ticks")
    print("     " + Q("risk_coupling",
                      "VA width  p50 {:5.1f} ticks    risk_R  p50 {:5.1f} ticks"
                      .format(float(np.median(va_w)) if len(va_w) else np.nan,
                              float(np.median(rr)) if len(rr) else np.nan)))
    print("     " + Q("risk_coupling",
                      "hard_stop_ticks is {:.0f} of that = {:.0%} of risk_R; the other "
                      "{:.0%}".format(HARD_STOP_TICKS, hs_share, 1 - hs_share)))
    print("     is the profile. The hard stop adds a CONSTANT, so it does not damp")
    print("     d_risk by a single tick -- sec b.9's instability passes straight")
    print("     through into risk_R, into TP1 at 2R, and into every R multiple.")
    print("     hard_stop_ticks = {:.0f} is a FREE PARAMETER with no justification;"
          .format(HARD_STOP_TICKS))
    print("     it is swept over {} and reported, never tuned (sec b.10 / g.0.1)."
          .format(list(GRID_HARD_STOP_TICKS)))

    print("\n[04] touch-only fills (sec b.7): " + Q(
        "touch_only_fills", "{}/{} = {:.1f}% of fills".format(
            n_touch, len(filled), touch_pct)))
    if pos_synth:
        print("     *** WITHHELD (sec b.11). The positive control was tuned until the")
        print("     *** sec b.9 gate passed, so its fill statistics were selected too.")
        print("     *** The sec b.7 switch is decided on real bars only.")
    elif touch_pct > 30.0:
        print("     ABOVE 30% -- require_penetration_ticks = 1 becomes the PRIMARY")
        print("     and front-of-queue drops to the sensitivity check.")
    else:
        print("     Below 30% -- front-of-queue stays primary,")
        print("     require_penetration_ticks = 1 stays the sensitivity check.")

    # ---- sec b.9, at the PRE-REGISTERED relative bin width -------------------
    b9 = b9_sensitivity(sessions, cfg)
    print("\n[04] sec b.2 bin width = median IB bar range, per session, RELATIVE")
    print("     (pre-registered blind; mult = {:.1f} is the primary)".format(
        b9["bin_mult"]))
    print("     realised bin width ticks   p50 {:5.1f}   p90 {:5.1f}   max {:5.1f}"
          .format(b9["bin_width_ticks"]["p50"], b9["bin_width_ticks"]["p90"],
                  b9["bin_width_ticks"]["max"]))
    print("     median IB bar span, bins   p50 {:5.2f}   p90 {:5.2f}   max {:5.2f}"
          .format(b9["bars_per_bin"]["p50"], b9["bars_per_bin"]["p90"],
                  b9["bars_per_bin"]["max"]))
    print("     A span near 1.00 is the rule working AS DESIGNED -- and it is also the")
    print("     condition under which the four methods cannot disagree. Read the 0.5x")
    print("     and 2.0x rows below before believing a 'not material' verdict.")

    print("\n[04] sec b.9 across the FULL {} sample (n_breakout = {:,}):".format(
        cfg.partition, b9["n_breakout"]))
    for k in ("d_risk", "d_POC", "d_VAH", "d_VAL"):
        print("     {:<8s} ticks   p50 {:5.1f}   p90 {:5.1f}   max {:5.1f}".format(
            k, b9[k]["p50"], b9[k]["p90"], b9[k]["max"]))
    print("     median risk_to_hard_stop = {:.1f} ticks".format(
        b9["median_risk_to_hard_stop_ticks"]))
    print("     E1 fill rate by method: " + "  ".join(
        "{} {:.1f}%".format(m, v) for m, v in b9["fill_rates"].items()))
    print("     E1 fill COUNT by method: " + "  ".join(
        "{} {:,}".format(m, n) for m, n in b9["fill_counts"].items()))
    print("     d_fill_rate  = {:.1f} percentage points".format(b9["d_fill_rate"]))
    print("     d_fill_count = {:,} sessions  ({:.1f}% of the {:,} trades the primary"
          " method fills)".format(
              b9["d_fill_count"],
              (100.0 * b9["d_fill_count"] / b9["fill_counts"]["volume_uniform"]
               if b9["fill_counts"]["volume_uniform"] else float("nan")),
              b9["fill_counts"]["volume_uniform"]))
    print("     ^ sec b.10: the assumption moves the TRADE COUNT, not only risk_R."
          " S_filled is")
    print("       the denominator of every Layer 1 per-trade statistic.")
    for cond, tripped in b9["gate"].items():
        print("     [{}] {}".format("TRIP" if tripped else "ok  ", cond))
    print("     VERDICT: {}".format(
        "MATERIAL -- Layer 1 downgraded (sec b.9)" if b9["MATERIAL"]
        else "not material on this sample"))
    # The gate verdict is the ONE statistic the positive control may source.
    assert_reportable(kind, "b9_gate_verdict")
    for line in b9_caveat(null_synth, pos_synth, b9["MATERIAL"]):
        print("     " + line)

    # ---- bin-width multiplier sensitivity (sec g.0.1) -----------------------
    # The primary rule makes the median bar span ~1 bin by construction, which is
    # the condition that forces the methods to agree. These two rows are what
    # separates "the profile is stable" from "the bin width was chosen to make it
    # look stable". They are a SENSITIVITY -- they never replace the primary.
    print("\n[04] sec b.9 bin-width sensitivity (labelled, NOT a primary, NOT tuned):")
    b9_sens = {}
    for mult in GRID_BIN_WIDTH_MULTS:
        r9 = b9 if mult == b9["bin_mult"] else b9_sensitivity(sessions, cfg,
                                                              bin_mult=mult)
        b9_sens[mult] = r9
        print("     mult {:>4.1f}{}  bin {:4.1f}t  span {:4.2f} bins  d_risk p50 {:5.1f}"
              "  d_POC p50 {:5.1f}  d_fill_ct {:>4,}  -> {}".format(
                  mult, " (PRIMARY)" if mult == b9["bin_mult"] else "         ",
                  r9["bin_width_ticks"]["p50"], r9["bars_per_bin"]["p50"],
                  r9["d_risk"]["p50"], r9["d_POC"]["p50"], r9["d_fill_count"],
                  "MATERIAL" if r9["MATERIAL"] else "not material"))
    # ---- sec b.9 MULTIPLIER RESOLUTION RULE -- pre-registered blind ---------
    # Written into sec b.9 before any real number existed. The primary rule sets
    # the bin TO the median bar range, so the median bar spans ~1 bin BY
    # CONSTRUCTION -- the lever sits at the position that maximises agreement.
    # A lone "not material" at 1.0x is therefore not evidence of a stable profile,
    # it is evidence that the rule works as designed. So:
    #
    #   MATERIAL at ANY of {0.5, 1.0, 2.0}  ->  the RESOLVED verdict is MATERIAL
    #   a PASS requires "not material" at ALL THREE
    #
    # No other combination is a pass. This is NOT moving the primary onto a
    # sensitivity row (that would be selection, sec g.0.1) -- the primary is still
    # the only row that can pass on its own terms. It is a conjunction: the
    # neighbours can only ever VETO, never rescue.
    resolved_material = any(r["MATERIAL"] for r in b9_sens.values())
    trip_mults = sorted(m for m, r in b9_sens.items() if r["MATERIAL"])
    print("\n[04] sec b.9 RESOLVED VERDICT (pre-registered multiplier rule):")
    print("     rule: MATERIAL at ANY of {0.5, 1.0, 2.0} -> MATERIAL."
          "  A pass needs all three clear.")
    print("     RESOLVED: {}".format(
        "MATERIAL -- Layer 1 downgraded (sec b.9)   tripped at mult {}".format(
            ", ".join("{:.1f}x".format(m) for m in trip_mults))
        if resolved_material
        else "not material at 0.5x, 1.0x AND 2.0x -- PASS"))
    if resolved_material and not b9["MATERIAL"]:
        print("     *** The primary passes and a neighbouring bin width does NOT.")
        print("     *** That is the construction warning in sec b.2 showing up in the")
        print("     *** data: the pass is partly the rule's own doing. The resolution")
        print("     *** rule vetoes it. Do NOT move the primary -- that is selection.")

    # =====================================================================
    # CHART 1 -- four annotated sessions
    # =====================================================================
    wanted = [
        ("a_textbook_long",
         lambda r: r["scenario"] == EXIT_TP1 and r["direction"] == 1,
         "CHART 1(a)   TEXTBOOK LONG -- break up, retrace to VAH, fill, TP1"),
        ("b_no_fill",
         lambda r: r["scenario"] == "no_fill",
         "CHART 1(b)   NO FILL -- price never came back. Layer 1 sits out, "
         "Layer 0 keeps the move"),
        ("c_stopped_out",
         lambda r: r.get("exit_reason") == CLOSE_INVALIDATION,
         "CHART 1(c)   CLOSE_INVALIDATION -- filled, then a 5-min CLOSE beyond "
         "the far value-area edge"),
        ("d_textbook_short",
         lambda r: r["scenario"] == EXIT_TP1 and r["direction"] == -1,
         "CHART 1(d)   TEXTBOOK SHORT -- the mirror of (a)"),
    ]
    # fallback so (c) always has a picture -- but it is a DIFFERENT category and
    # the caption says so; the two are never merged into one "stopped out" bucket.
    fallbacks = {"c_stopped_out": (
        lambda r: r.get("exit_reason") == HARD_STOP,
        "CHART 1(c)   HARD_STOP -- filled, then the sec c.1 hard stop fired "
        "(no close_invalidation example in this sample)")}

    if pos_synth and not args.session_date:
        # sec b.11 QUARANTINE. Chart 1 normally picks its four example sessions BY
        # OUTCOME (a TP1 long, a no_fill, a close_invalidation, a TP1 short). On a
        # file that was tuned until sec b.9 passed, selecting sessions by outcome is
        # outcome selection on top of outcome selection. So the positive control gets
        # ONE session, chosen on IB range alone, and its scenario label is withheld.
        r = sorted(rows, key=lambda r: (abs(r["ib_range"] - med_ib),
                                        str(r["session_date"])))[0]
        wanted = [("q_geometry_only", None,
                   "CHART 1   POSITIVE CONTROL -- geometry only. Session picked on IB "
                   "range alone; outcome WITHHELD (sec b.11)")]
        chosen = {"q_geometry_only": r}
    elif args.session_date:
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
        subtitle="{}   ONE session, for legibility. The gate is decided on the "
                 "full-sample distribution below.   |   {}".format(
                     str(s.session_date.date()), src_note),
        notes=["sec b.9 GATE, full {} sample, n_breakout = {:,}   "
               "(the gate is keyed on d_risk and d_fill_rate, sec b.10)".format(
                   cfg.partition, b9["n_breakout"]),
               "  d_risk  ticks   p50 {:5.1f}   p90 {:5.1f}   max {:5.1f}      "
               "median risk_to_hard_stop = {:.1f} ticks".format(
                   b9["d_risk"]["p50"], b9["d_risk"]["p90"], b9["d_risk"]["max"],
                   b9["median_risk_to_hard_stop_ticks"]),
               "  d_POC   ticks   p50 {:5.1f}   p90 {:5.1f}   max {:5.1f}      "
               "d_VAH p50 {:.1f}   d_VAL p50 {:.1f}  (reported, not the trigger)".format(
                   b9["d_POC"]["p50"], b9["d_POC"]["p90"], b9["d_POC"]["max"],
                   b9["d_VAH"]["p50"], b9["d_VAL"]["p50"]),
               "  E1 fill rate by method: " + "   ".join(
                   "{} {:.1f}%".format(m.replace("volume_", "").replace("_minute", ""), v)
                   for m, v in b9["fill_rates"].items())
               + "      d_fill_rate = {:.1f} pp".format(b9["d_fill_rate"]),
               "  E1 fill count by method: " + "   ".join(
                   "{} {:,}".format(m.replace("volume_", "").replace("_minute", ""), n)
                   for m, n in b9["fill_counts"].items())
               + "      d_fill_count = {:,} sessions  (sec b.10: the assumption "
                 "moves S_filled, not only risk_R)".format(b9["d_fill_count"]),
               "  VERDICT: {}".format(
                   "MATERIAL -- Layer 1 downgraded (sec b.9)" if b9["MATERIAL"]
                   else "not material on this sample")]
              + ([""] + b9_caveat(null_synth, pos_synth, b9["MATERIAL"])
                 if synthetic else []))
    written.append(viz.save(f, outdir / "02_profile_methods.png"))

    # =====================================================================
    # CHARTS 3-5 -- sec b.11 QUARANTINE GATE
    # ---------------------------------------------------------------------
    # Charts 3, 4 and 5 are pure statistics: the sample funnel, the MFE
    # distribution with TP1, and the Layer 3 cell counts. None of them has any part
    # in proving that the sec b.9 gate's pass branch executes, which is the one and
    # only thing the positive control is allowed to source. They are therefore not
    # drawn at all on that file. Refusing to draw them is the enforcement -- a
    # caveat printed under a chart is a note somebody has to read and remember.
    # =====================================================================
    if pos_synth:
        print("\n[04] sec b.11: CHARTS 3, 4 and 5 NOT DRAWN on the positive control.")
        print("     Funnel counts, the MFE distribution, TP1 and the Layer 3 cell")
        print("     counts are reported statistics. This file was tuned until sec b.9")
        print("     returned 'not material', so every statistic in it was selected")
        print("     alongside that verdict. Run them on data/raw/synthetic.parquet")
        print("     (negative control) or on real NQ bars.")
    else:
        # =====================================================================
        # CHART 3 -- sample funnel (real Step 1 code)
        # =====================================================================
        df = run_strategy(sessions, feats, cfg)
        s_all = len(df)
        s_break = int((df["skip_reason"].isin(["", "no_breakout", "ambiguous_breakout"])
                       & (df["traded"] == True)).sum())  # noqa: E712
        s_filled = len(filled)

        # S_ib_broke -- the PHYSICAL event: the IB broke cleanly, filters ignored.
        # b9_sensitivity() counts exactly this, and Chart 3 used to skip the stage, so
        # the two numbers disagreed with nothing on the page to explain the gap.
        # run_strategy applies the sec (f) no-trade filters BEFORE find_breakout, so a
        # session can break its IB and still never become a trade. That difference is
        # now a bar, and the filter responsible is named.
        s_ib_broke = b9["n_breakout"]
        # sec 0.2.4 quality stage, shown as its own line so the count is visible and
        # is never confused with a strategy filter. It is the only stage removed for
        # a reason that has nothing to do with the market.
        n_degraded = b9.get("n_degraded_excluded", 0)
        lost = s_ib_broke - s_break
        broke = b9["broke_dates"]
        by_filter = (df[df["session_date"].isin(broke) & (df["traded"] == False)]  # noqa: E712
                     ["skip_reason"].value_counts().to_dict())
        filter_lines = ["  {:<22s} {:>5,d}".format(k or "(none)", v)
                        for k, v in sorted(by_filter.items(), key=lambda kv: -kv[1])]
        reconciled = sum(by_filter.values()) == lost

        brk_pct = 100.0 * s_break / s_all if s_all else float("nan")
        notes3 = [
            "sec 0.2.4 VENDOR QUALITY: {:,} session(s) excluded BEFORE any stage below, "
            "because".format(n_degraded),
            "Databento does not mark the day `available`. See data/raw/degraded_days.csv.",
            "Excluded, never repaired: a degraded day can be missing messages, which",
            "narrows the observed IB and therefore moves ib_range_atr, the profile, and",
            "risk_R -- with every downstream number still looking self-consistent.",
            "",
            "S_ib_broke is the PHYSICAL event (find_breakout fires, unambiguous), with the",
            "sec (f) no-trade filters IGNORED. It is the denominator sec b.9 uses.",
            "S_breakout is S_ib_broke minus the sessions the no-trade filters removed, and",
            "it is the denominator for Layer 0 vs Layer 1 (sec h.1). The two are NOT equal.",
            "",
            "{:,} sessions broke the IB but were never traded. Removed by:".format(lost),
        ]
        notes3 += filter_lines
        notes3 += [
            "  {} {:,} accounted for, {:,} lost".format(
                "RECONCILES:" if reconciled else "*** DOES NOT RECONCILE:",
                sum(by_filter.values()), lost),
            "  run_strategy() applies these at IB close, BEFORE find_breakout is called.",
            "",
            "S_filled is from the ILLUSTRATIVE Layer 1 resolver, not a tested backtest.",
            "It is drawn under S_breakout but is resolved WITHOUT the no-trade filters,",
            "so it belongs to S_ib_broke. Step 3 must apply the same filters to both.",
            "no_fill sessions are carried as zero-PnL, never dropped (sec b.8).",
            "",
            "exit taxonomy of the {:,} fills (sec c / c.1) -- the two adverse".format(
                s_filled),
            "categories are counted apart, never merged:",
        ]
        notes3 += ["  " + line.strip() for line in format_frequency(freq).splitlines()]
        notes3 += [
            "",
            "sec b.10: (VAL - hard_stop) over all fills, ticks: p10 {:.1f} / p50 {:.1f} "
            "/ p90 {:.1f}".format(b10["p10"], b10["p50"], b10["p90"]),
            "  close_invalidation fired {:.1f}% of exits. The rule cannot shrink risk_R,".format(
                b10["ci_pct"]),
            "  so what is left of Layer 1 is the ENTRY PRICE alone.",
            "",
            "touch-only fills (sec b.7): {:.1f}% of fills. {}".format(
                touch_pct,
                "ABOVE 30% -> require_penetration_ticks = 1 becomes PRIMARY."
                if touch_pct > 30.0 else
                "Below 30% -> front-of-queue stays primary."),
            "",
            "RE-CHECK ON REAL BARS: S_breakout = {:.1f}% of S_all. A random walk breaks".format(
                brk_pct),
            "a range more readily than real price does, so this rate is expected to be",
            "HIGH here. sec h.1 assumed ~80%. If it is still above ~90% on real NQ bars,",
            "breakout_buffer_ticks = 1 is too small and the filter is not filtering.",
        ]
        f = viz.chart_funnel(
            [("S_all\nsessions in partition", s_all),
             ("S_ib_broke\nIB broke, filters ignored", s_ib_broke),
             ("S_breakout\ntrade actually taken", s_break),
             ("S_filled\nreload zone also touched", s_filled)],
            title="CHART 3   Sample funnel (IVB-SPEC.md sec h.1)",
            subtitle="{}   {}".format(cfg.partition, src_note),
            notes=notes3)
        written.append(viz.save(f, outdir / "03_funnel.png"))

        print("\n[04] sec h.1 funnel: S_all {:,} -> S_ib_broke {:,} -> S_breakout {:,}"
              " -> S_filled {:,}".format(s_all, s_ib_broke, s_break, s_filled))
        print("     {:,} sessions broke the IB but were not traded. Removed by:".format(lost))
        for line in filter_lines:
            print("   " + line)
        if not reconciled:
            print("     *** DOES NOT RECONCILE: {:,} accounted for vs {:,} lost. BUG."
                  .format(sum(by_filter.values()), lost))

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
            notes=["sec h.5: HIT RATE IS NOT A RESULT. TP1 is DEFINED as the {:.1f}th".format(
                       TP1_PCT),
                   "percentile, so ~{:.1f}% of trades reach it in ANY distribution --".format(
                       100 - TP1_PCT),
                   "random walk, real market, or noise. The number is an identity, not",
                   "evidence. The only admissible Layer 3 metric is expectancy net of",
                   "costs, benchmarked against fixed R multiples (sec h.5).",
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
            notes=["SCALE BEFORE CONCLUDING. These counts come from {:,} synthetic".format(
                       s_all),
                   "sessions (~2.5 years). The real primary sample is ~2,900 sessions,",
                   "about 4.6x this. Multiply every bar by ~4.6 before judging a design.",
                   "On that scaling the 6-cell design is THIN, not dead. The 18-cell",
                   "design is dead either way (sec h.3), so quantile regression stays a",
                   "CO-PRIMARY next to bucket_empirical -- not an escalation after it fails.",
                   "",
                   "Counts shown are WHOLE-SAMPLE. Walk-forward splits them across 8 test",
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
