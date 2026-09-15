"""CHART 1(a) -- LAYER 1 geometry for EVERY session of ONE MONTH. CENSUS, not sample.

===========================================================================
THIS SCRIPT READS SEALED DATA. It is the second file allowed to, after
scripts/05_unseal_charts.py, and it is bounded by the same written decision:
FORWARD_HOLDOUT 2026-01-01 .. 2026-08-31, unsealed 2026-09-15, recorded in
docs/IVB-SPEC.md sec 0.2.3b, UNSEAL #1. Those sessions are IN-SAMPLE from that
date. Nothing restores them.

--month is validated to lie ENTIRELY INSIDE that window and is refused
otherwise. The code may not widen what the written decision covers.
===========================================================================

WHY A CENSUS AND NOT A SAMPLE
scripts/05 draws a random sample from the sessions that FILLED. That answers
"what does a Layer 1 trade look like". It cannot answer "what does Layer 1 do
with a month", because the sessions it never draws -- the no-breakouts, the
walkaways, the filtered days -- are most of the month. This script draws all of
them, in date order, so the month can be read end to end.

WHAT IT PRODUCES, AND WHAT IT REFUSES TO PRODUCE
Produces:  one picture per session, and one index row per session.
Refuses:   every aggregate. No win rate, no expectancy, no fill rate, no PnL
           sum, no counts by outcome. There is no code path here that computes
           one. The index table lists per-session values and sums nothing.

Does NOT run:  b9_sensitivity(), run_strategy(), or any Step 1-5 evaluation.
               Nothing here writes a research artifact. Nothing here may be
               quoted as a result.

FILTERED SESSIONS ARE DRAWN, BUT THEIR OUTCOME IS NOT INDEXED
A session dropped by half_day / vendor_degraded / min_ib_range_atr is drawn with
its full geometry, because seeing what was skipped is the point. The chart
carries a NOT TRADED banner naming the filter. The index table leaves its exit
reason, R and net as "n/a (filtered)": P0 never takes that trade, and a
scannable R column is exactly where a never-taken number gets misread as a
taken one.

Usage:
    python scripts/06_month_charts.py data/raw/nq_ohlcv1m_2010-07-01_2026-08-31.parquet \
        --roll-calendar data/roll_calendar_6635298.csv --month 2026-01
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from ivb.config import DATA, OUT, P0, TICK_SIZE                       # noqa: E402
from ivb.data import load                                             # noqa: E402
from ivb.partitions import UNSEAL_TOKEN, select                       # noqa: E402
from ivb.provenance import REAL, classify                             # noqa: E402
from ivb.quality import degraded_dates                                # noqa: E402
from ivb.rolls import ROLL_FILE, front_month_bars                     # noqa: E402
from ivb.sessions import build_sessions, daily_features               # noqa: E402
from ivb.timestamps import assert_verified                            # noqa: E402
from src import viz                                                   # noqa: E402

# The Layer 1 resolver is IMPORTED, never re-implemented. A second copy of the
# geometry would be free to drift from the one the other charts use, and then
# two pictures of the same rule could disagree.
_c04 = importlib.import_module("04_charts")
illustrate_layer1_trade = _c04.illustrate_layer1_trade

UNSEAL_START = pd.Timestamp("2026-01-01")
UNSEAL_END = pd.Timestamp("2026-08-31")
UNSEAL_DATE = "2026-09-15"
UNSEAL_REF = "IVB-SPEC.md sec 0.2.3b UNSEAL #1"

# Human labels for the title. The keys are the filename tokens.
OUTCOME_LABEL = {
    "tp1": "TP1 HIT",
    "hard_stop": "HARD STOP",
    "close_invalidation": "CLOSE INVALIDATION",
    "time_stop": "TIME STOP (flat at 11:30 ET)",
    "no_fill": "NO FILL -- IB broke, price never returned to the reload zone",
    # A title is a headline, not a definition. The long form of each of these
    # sits in the note block on the same chart, which has room to wrap.
    # "never broken" would be loose. P0 triggers on breakout_trigger=close_through,
    # so a bar may TRADE through the IB and still leave the session a no-breakout.
    # 2026-02-25 is exactly that case: 2 bars printed a high above IB_high + 1 tick,
    # none closed above it. The label has to say which of the two it means.
    "no_breakout": "NO BREAKOUT -- no bar CLOSED beyond the IB",
    "ambiguous_breakout": "AMBIGUOUS BREAKOUT -- both IB sides taken in one bar",
    "zero_risk": "DEGENERATE ZONE -- risk_to_hard_stop <= 0, no trade definable",
}


def filter_reason(s, atr: float, degraded: set, cfg) -> str:
    """Which sec (f) / sec 0.2.4 filter drops this session, or "".

    Order matches ivb/backtest.run_strategy exactly. Vendor quality runs ahead of
    min_ib_range_atr on purpose: a degraded day can have a narrowed IB, which is
    the input to that very filter.
    """
    if cfg.exclude_half_days and s.is_half_day:
        return "half_day"
    if s.session_date in degraded:
        return "vendor_degraded"
    ratio = s.ib_range / atr if atr and np.isfinite(atr) and atr > 0 else np.nan
    if np.isfinite(ratio) and ratio < cfg.min_ib_range_atr:
        return "min_ib_range_atr"
    if cfg.min_ib_range_ticks and s.ib_range < cfg.min_ib_range_ticks * TICK_SIZE:
        return "min_ib_range_ticks"
    return ""


def geometry_check(s, r) -> list:
    """Per-session profile resolution, printed on the chart.

    NOT an aggregate: these are this session's own numbers.

    RE-RUN NOTE, 2026-09-15. These three lines were added to make a DEFECT
    visible: under the original sec b.2 rule the grid was anchored at absolute
    price zero and the bin width came from the median IB bar range, so the IB
    carried ~5 bins and a value-area edge could sit almost a full bin OUTSIDE
    the initial balance it was built from. BOTH are now fixed -- sec b.2
    AMENDMENT 1 (bin = IB range / 20) and AMENDMENT 2 (grid anchored at
    ib_low, VAH/VAL/POC clamped into the IB).

    The lines are KEPT, not removed, for two reasons. They are the only visible
    proof on the face of a chart that the fix actually holds on THIS session
    (expect ~20 bins and both VA offsets <= 0.00), and they let a post-fix chart
    be read against its superseded twin in PRE_RULE_A/. A check that only prints
    when it fails is a check nobody can audit.
    """
    prof = r["profile"]
    bs = float(prof.bin_size)
    n_bins = s.ib_range / bs if bs > 0 else float("nan")
    return [
        "GEOMETRY CHECK (this session only):",
        "  IB range {:,.2f} pt   bin width {:,.2f} pt   -> {:.1f} bins across the "
        "whole initial balance.".format(s.ib_range, bs, n_bins),
        "  VAH - IB_high = {:+,.2f} pt      IB_low - VAL = {:+,.2f} pt      "
        "(positive = that VA edge lies OUTSIDE the IB).".format(
            r["vah"] - s.ib_high, s.ib_low - r["val"]),
    ]


def contract_block(date, cmap: dict) -> list:
    """Which contract THIS session's bars are, printed on the chart.

    NOT an aggregate. A month that spans a quarterly roll is drawn from two
    different futures, and NQH6 and NQM6 do not trade at the same absolute
    price -- the spread between them is real, not a rounding artefact. A POC of
    25,327 on one contract is not the same location as 25,327 on the other.
    Without this line a reader scanning a month of charts cannot tell where the
    price series handed over, and would read a roll gap as a market move.

    front_month_bars() takes ONE contract per session and never splices inside a
    session (ivb/rolls.py, Series A), so every level on a single chart comes from
    a single contract. The handover happens BETWEEN charts, never inside one.
    """
    row = cmap.get(pd.Timestamp(date))
    if row is None:
        return ["CONTRACT: not in the roll calendar -- this session should not "
                "have been drawn.", ""]
    sym, iid, eff, prev = row["sym"], row["iid"], row["eff"], row["prev"]
    out = ["CONTRACT (this session only):"]
    iid_s = "" if iid is None else "   instrument_id {}".format(iid)
    out.append("  front month {}{}   -- bars matched on instrument_id, one "
               "contract for the whole session, never spliced.".format(sym, iid_s))
    if eff:
        out += [
            "  *** QUARTERLY ROLL EFFECTIVE TODAY: {} -> {}. ***".format(prev, sym),
            "  The previous session's chart is {} and this one is {}. The two "
            "contracts trade at DIFFERENT absolute".format(prev, sym),
            "  prices, so a level carried across this boundary by eye is wrong.",
            "  P0 applies NO roll-day filter -- this session is traded like any "
            "other. Whether it should be is an",
            "  open question, not a settled one.",
        ]
    return out + [""]


def caveats(src_name: str) -> list:
    """The caveat block that goes on EVERY chart this script draws."""
    return [
        "ILLUSTRATIVE, NOT A RESULT. These bars are UNSEALED HOLDOUT data:",
        "  FORWARD_HOLDOUT {} .. {}, unsealed {} ({}).".format(
            UNSEAL_START.date(), UNSEAL_END.date(), UNSEAL_DATE, UNSEAL_REF),
        "  They are IN-SAMPLE from that date. Any statistic taken from this range"
        " must say so.",
        "SOURCE: {}  --  REAL NQ 1-minute bars.".format(src_name),
        "  NOT synthetic.parquet and NOT the synthetic_structured.parquet positive"
        " control.",
        "SELECTION: NONE. This is a CENSUS -- every RTH session of the month is"
        " drawn, in date order,",
        "  including no-breakouts, walkaways and filtered days. Nothing was chosen"
        " and nothing was left out.",
        "UNKNOWN STABILITY: the sec b.9 profile-method sensitivity gate has NEVER"
        " been run on real",
        "  bars. VAH / VAL / POC above come from ONE allocation rule"
        " (volume_uniform, sec b.2).",
        "  A different rule could move all three. Nothing here measures how much.",
        "GEOMETRY: illustrate_layer1_trade() -- a plain reading of the spec FOR"
        " DRAWING ONLY.",
        "  Step 3 does not exist. No unit tests, no cost sweep, no walk-forward,"
        " no control.",
        "NO AGGREGATE was computed on this month. Per-session numbers only.",
    ]


def no_trade_block(reason_line: str) -> list:
    """The stats block for a session that never produced a Layer 1 entry."""
    return [
        "direction      NONE",
        "entry          n/a   -- {}".format(reason_line),
        "invalidation   n/a",
        "hard stop      n/a",
        "",
        "risk_to_hard_stop  n/a",
        "risk_to_VAL        n/a",
        "Layer 0 risk       n/a   -- Layer 0 takes no trade on this session either",
        "",
        "TP1            n/a",
        "achieved       n/a",
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", help="the REAL bars parquet")
    ap.add_argument("--roll-calendar", default=None,
                    help="READ a roll calendar from this path instead of "
                         "data/roll_calendar.csv. Nothing is written or rebuilt.")
    ap.add_argument("--month", default="2026-01",
                    help="YYYY-MM. Must lie entirely inside the unsealed window.")
    ap.add_argument("--outdir", default=None,
                    help="default: output/charts/<month>")
    args = ap.parse_args()

    cfg = P0

    # ---- the month must be inside the written unseal -----------------------
    try:
        m_start = pd.Timestamp(args.month + "-01")
    except ValueError:
        print("[06] --month must be YYYY-MM, got {!r}".format(args.month))
        return 2
    m_end = m_start + pd.offsets.MonthEnd(0)
    if m_start < UNSEAL_START or m_end > UNSEAL_END:
        print("[06] {} is NOT inside the unsealed window {} .. {}.".format(
            args.month, UNSEAL_START.date(), UNSEAL_END.date()))
        print("     Drawing it would read data that is still sealed. Refused.")
        print("     Widening the window is a written decision (sec 0.2.3b), "
              "not a flag.")
        return 2

    outdir = Path(args.outdir) if args.outdir else (OUT / "charts" / args.month)
    outdir.mkdir(parents=True, exist_ok=True)

    # ---- provenance gate ---------------------------------------------------
    kind = classify(args.path)
    if kind != REAL:
        print("[06] {} classifies as {}. This script draws REAL unsealed holdout "
              "bars only.".format(Path(args.path).name, kind))
        print("     Pointing it at a control file would put the unsealed-holdout "
              "caveat on a chart that is not holdout data. Refused.")
        return 2

    print("\n" + "=" * 78)
    print("[06] READING UNSEALED HOLDOUT DATA -- MONTH CENSUS")
    print("     month      {}  ({} .. {})".format(
        args.month, m_start.date(), m_end.date()))
    print("     unsealed   {}  ({})".format(UNSEAL_DATE, UNSEAL_REF))
    print("     status     IN-SAMPLE from that date. This is not a result and may")
    print("                not be reported as one.")
    print("     remaining sealed: FORWARD_HOLDOUT 2024-05-02 .. 2025-12-31.")
    print("                       BACKWARD_HOLDOUT is dead (unfit, sec 0.2.3).")
    print("=" * 78)

    assert_verified()
    bars = load(args.path)

    # ---- artifacts, READ-ONLY ----------------------------------------------
    roll_path = Path(args.roll_calendar) if args.roll_calendar else ROLL_FILE
    daily = DATA / "daily_adjusted.parquet"
    missing = [p for p in (roll_path, daily) if not p.exists()]
    if missing:
        print("[06] missing: {}".format(", ".join(str(p) for p in missing)))
        return 2
    cal = pd.read_csv(roll_path, parse_dates=["session_date"])
    print("\n[06] roll calendar: {}  ({:,} rows, {} .. {})".format(
        roll_path, len(cal), str(cal["session_date"].min().date()),
        str(cal["session_date"].max().date())))
    if roll_path != ROLL_FILE:
        print("     *** NOT the default data/roll_calendar.csv. Every level drawn")
        print("     *** below is conditional on THIS calendar.")
    # Per-session contract, straight off the calendar. front_month_bars() drops
    # front_symbol after matching on instrument_id, so the calendar is the only
    # place the symbol still exists.
    _c = cal.sort_values("session_date").reset_index(drop=True)
    _prev = _c["front_symbol"].shift(1)
    _has_eff = "roll_effective" in _c.columns
    cmap = {}
    for i, rw in _c.iterrows():
        eff = bool(rw["roll_effective"]) if _has_eff else (
            i > 0 and rw["front_symbol"] != _prev.iloc[i])
        cmap[pd.Timestamp(rw["session_date"])] = {
            "sym": str(rw["front_symbol"]),
            "iid": (int(rw["front_instrument_id"])
                    if "front_instrument_id" in _c.columns else None),
            "eff": eff,
            "prev": (str(_prev.iloc[i]) if i > 0 else "-"),
        }

    cd = cal["session_date"]
    if int(((cd >= m_start) & (cd <= m_end)).sum()) == 0:
        print("[06] this calendar has NO row inside {} .. {}. It cannot select a "
              "front month.".format(m_start.date(), m_end.date()))
        print("     Pass --roll-calendar data/roll_calendar_6635298.csv")
        return 2

    # ---- the month ---------------------------------------------------------
    front = front_month_bars(bars, cal)
    front = select(front, "FORWARD_HOLDOUT", unseal=UNSEAL_TOKEN)
    d = pd.to_datetime(front["session_date"])
    front = front[(d >= m_start) & (d <= m_end)].copy()

    sessions = build_sessions(front, cfg)
    if not sessions:
        print("[06] no sessions in {}. Check the roll calendar.".format(args.month))
        return 2

    # NOTHING is excluded here. Half-days and vendor-degraded days stay in the
    # list and are drawn with a filter banner -- that is the whole point of a
    # census. scripts/05 drops them before building; this one does not.
    feats = daily_features(pd.read_parquet(daily), cfg).set_index("session_date")
    degraded = degraded_dates()

    src_name = Path(args.path).name
    src_note = ("REAL BARS, source: {}   |   UNSEALED HOLDOUT {} .. {} -- "
                "IN-SAMPLE since {}".format(
                    src_name, UNSEAL_START.date(), UNSEAL_END.date(), UNSEAL_DATE))
    base_caveats = caveats(src_name)

    index_rows = []
    written = []

    print("\n[06] drawing every RTH session, in date order:")
    for s in sessions:
        date = s.session_date
        ds = str(date.date())
        atr = float(feats["atr14"].get(date, np.nan))
        filt = filter_reason(s, atr, degraded, cfg)

        r = illustrate_layer1_trade(s, cfg)
        r["session_date"] = date
        scen = r.get("scenario", "no_breakout")
        direction = int(r.get("direction", 0) or 0)
        filled = r.get("entry_idx") is not None

        token = "filtered_" + filt if filt else scen
        fname = "{}_{}.png".format(ds, token)

        head = ("ILLUSTRATIVE, NOT A RESULT -- UNSEALED HOLDOUT DATA   |   "
                "CHART 1(a) LAYER 1")
        label = OUTCOME_LABEL.get(scen, scen.upper())
        cinfo = cmap.get(pd.Timestamp(date), {})
        csym = cinfo.get("sym", "?")
        if filt:
            title = ("{}   |   {}   DROPPED BY FILTER: {}   (NOT TRADED BY P0)"
                     .format(head, ds, filt))
        else:
            title = "{}   |   {}   {}".format(head, ds, label)
        if cinfo.get("eff"):
            title += "   ||   ROLL {}->{}".format(cinfo.get("prev"), csym)

        notes = []
        if filt:
            notes += [
                "NOT TRADED BY P0. This session is dropped by the {} filter "
                "(sec {}).".format(
                    filt, "0.2.4" if filt == "vendor_degraded" else "f"),
                "  The geometry below is drawn so the skipped session can be "
                "inspected. P0 takes no position here,",
                "  and the index table records no exit reason, no R and no net "
                "for it.",
                "",
            ]
        if direction == 0:
            why = ("no bar CLOSED beyond the IB +/- {} tick buffer before 11:30 "
                   "ET (P0 trigger = close_through). A bar may still have TRADED "
                   "through the IB; that does not trigger P0.".format(
                       cfg.breakout_buffer_ticks)
                   if scen == "no_breakout" else
                   "both IB sides were taken inside one bar; the sequence is "
                   "unknowable (sec a.3)")
            notes += no_trade_block(why) + [""]
        elif scen == "zero_risk":
            r["no_fill_reason"] = "degenerate zone: risk_to_hard_stop <= 0"
        notes += (contract_block(date, cmap) + geometry_check(s, r)
                  + [""] + base_caveats)

        win = s.bars.iloc[:s.trade_end_idx + 1]
        levels = {"ib_high": s.ib_high, "ib_low": s.ib_low, "vah": r["vah"],
                  "poc": r["poc"], "val": r["val"], "ib_end_idx": s.ib_close_idx,
                  "zone_bottom": r.get("zone_bottom"),
                  "zone_top": r.get("zone_top")}
        # The filter banner is repeated in the SUBTITLE as well as in the note
        # block. viz.chart_session appends extra_notes BELOW its own per-trade
        # block, so on a filtered session the banner would otherwise sit under a
        # stats block quoting an R multiple -- which is the one place a
        # never-taken number gets read as a taken one.
        roll_tag = ("  *** ROLL DAY: {} -> {} ***".format(cinfo.get("prev"), csym)
                    if cinfo.get("eff") else "")
        sub = "{}   contract {}{}   IB{}m, E1 limit at the near VA edge, " \
              "close_plus_hard exit, R=2.0   |   {}".format(
                  ds, csym, roll_tag, cfg.ib_minutes, src_note)
        if filt:
            sub = "NOT TRADED BY P0 -- dropped by the {} filter. The numbers " \
                  "below describe a trade P0 NEVER TAKES.   ||   {}".format(
                      filt, sub)
        fig = viz.chart_session(
            win, levels, r if direction != 0 else None, r["profile"], title=title,
            subtitle=sub, extra_notes=notes, fit_title=True)
        written.append(viz.save(fig, outdir / fname))

        dir_s = "LONG" if direction == 1 else ("SHORT" if direction == -1 else "-")
        csent = ("**{}** (ROLL: {} -> {})".format(csym, cinfo.get("prev"), csym)
                 if cinfo.get("eff") else csym)
        if filt:
            row = [ds, csent, "filtered:" + filt, dir_s, "n/a (filtered)",
                   "n/a (filtered)", "n/a (filtered)"]
        elif filled:
            row = [ds, csent, scen, dir_s, r["exit_reason"],
                   "{:+.2f}R".format(r["r_multiple"]),
                   "{:+,.2f} pt".format(r["net_points"])]
        else:
            row = [ds, csent, scen, dir_s, "-", "-", "-"]
        index_rows.append(row)
        print("     {}  {:<5s}{:<6s} {:<26s} {:<6s} {}".format(
            ds, csym, " ROLL" if cinfo.get("eff") else "", token, dir_s, fname))

    # ---- index.md ----------------------------------------------------------
    # Per-session rows only. Nothing in this file is summed, averaged or counted
    # by outcome. There is deliberately no totals row.
    hdr = ["date", "contract", "outcome", "direction", "exit reason",
           "R achieved", "net"]
    lines = [
        "# {} -- LAYER 1 session census".format(args.month),
        "",
        "**ILLUSTRATIVE, NOT A RESULT -- UNSEALED HOLDOUT DATA.**",
        "",
        "Source: `{}` -- REAL NQ 1-minute bars.".format(src_name),
        "",
        "Range: FORWARD_HOLDOUT {} .. {}, unsealed {} ({}).".format(
            UNSEAL_START.date(), UNSEAL_END.date(), UNSEAL_DATE, UNSEAL_REF),
        "These sessions are IN-SAMPLE from that date. Any statistic taken from "
        "this range must say so.",
        "",
        "Geometry: `illustrate_layer1_trade()` -- a plain reading of the spec FOR "
        "DRAWING ONLY. Step 3 does not exist.",
        "The sec b.9 profile-method sensitivity gate has NEVER been run on real "
        "bars, so every VAH / VAL / POC behind these rows is of unknown "
        "stability.",
        "",
        "**This table sums nothing.** No totals, no win rate, no expectancy, no "
        "counts by outcome. One row per session, per-session values only.",
        "",
        "Filtered sessions are drawn but carry no exit reason, R or net: P0 never "
        "takes those trades.",
        "",
        "The `contract` column is the front month those bars come from. One "
        "contract per session, never spliced inside a session. Where a quarterly "
        "roll falls inside the month, the handover row is marked **ROLL**: the "
        "two contracts trade at DIFFERENT absolute prices, so a level must not be "
        "carried across that row by eye. P0 applies no roll-day filter.",
        "",
        "| " + " | ".join(hdr) + " |",
        "|" + "|".join(["---"] * len(hdr)) + "|",
    ]
    for row in index_rows:
        lines.append("| " + " | ".join(row) + " |")
    lines += ["", "Charts: `{}`".format(outdir.as_posix()), ""]

    # If a superseded set was archived beside these charts, say so IN the index.
    # index.md is regenerated on every run, so a hand-added pointer would be
    # silently erased by the next redraw and the archive would become invisible.
    if (outdir / "PRE_RULE_A").is_dir():
        lines += [
            "---",
            "",
            "**A superseded set of charts for this month is archived in "
            "`PRE_RULE_A/`.** Those files were drawn under the ORIGINAL sec b.2 "
            "bin-width rule and the zero-anchored grid, both replaced on "
            "2026-09-15 (sec b.2 AMENDMENT 1 and AMENDMENT 2). They are VOID: "
            "kept as the record of the defect, quotable as evidence about "
            "nothing. `VOID.md` in this folder explains why and maps each "
            "superseded chart to the chart that replaced it.",
            "",
        ]
    idx = outdir / "index.md"
    idx.write_text("\n".join(lines), encoding="utf-8")

    print("\n[06] {} session(s) drawn -- every RTH session in {}, none skipped."
          .format(len(written), args.month))
    print("[06] charts   {}".format(outdir.resolve()))
    print("[06] index    {}".format(idx.resolve()))
    print("\n[06] NOT RUN, deliberately: b9_sensitivity(), run_strategy(), any")
    print("     Step 1-5 evaluation, any aggregate statistic. No research artifact")
    print("     was written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
