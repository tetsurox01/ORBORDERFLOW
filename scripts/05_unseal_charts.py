"""CHART 1(a) -- LAYER 1 geometry on UNSEALED FORWARD_HOLDOUT bars.

===========================================================================
THIS SCRIPT READS SEALED DATA. IT IS THE ONLY ONE ALLOWED TO.
Range: FORWARD_HOLDOUT 2026-01-01 .. 2026-08-31, unsealed 2026-09-15 by an
explicit written decision recorded in docs/IVB-SPEC.md sec 0.2.3b, UNSEAL #1.
Those sessions are IN-SAMPLE from that date. Nothing restores them.
===========================================================================

WHAT THIS SCRIPT PRODUCES, AND WHAT IT REFUSES TO PRODUCE

Produces:  per-session pictures, and the per-session numbers printed on them.
Refuses:   every aggregate. No win rate, no expectancy, no fill rate, no PnL
           sum, no counts across sessions. There is no code path here that
           computes one -- the rule is enforced by absence, not by a flag.

Does NOT run:  b9_sensitivity(), run_strategy(), or any Step 1-5 evaluation.
               Nothing in this file writes a research artifact. Nothing here
               may be quoted as a result.

WHY THE PICTURES ARE WORTH SO LITTLE ON THEIR OWN
The Layer 1 geometry comes from `illustrate_layer1_trade()` in
scripts/04_charts.py -- a deliberately plain reading of the spec, for drawing
only. Step 3 has not been written. And sec b.9, the gate that decides whether
the value area is stable under a different volume-allocation rule, has NEVER
been run on real bars. So every VAH / VAL / POC drawn here is of unknown
stability. That caveat is printed on every chart.

SELECTION
  MAIN     8 sessions drawn uniformly at random, fixed seed, from the sessions
           in the window where the IB BROKE and price LATER TRADED BACK INTO
           the reload zone. Random only -- not best, not worst, not recent.
  WALKAWAY 1 session drawn at random from the sessions where the IB broke and
           price NEVER returned. Layer 1 takes no trade; Layer 0 does. Labelled
           separately because it is a different question, not a ninth sample.

Usage:
    python scripts/05_unseal_charts.py data/raw/nq_ohlcv1m_2010-07-01_2026-08-31.parquet \
        --roll-calendar data/roll_calendar_6635298.csv
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

from ivb.config import DATA, OUT, P0                                  # noqa: E402
from ivb.data import load                                             # noqa: E402
from ivb.partitions import UNSEAL_TOKEN, select                       # noqa: E402
from ivb.provenance import REAL, classify                             # noqa: E402
from ivb.quality import degraded_dates                                # noqa: E402
from ivb.rolls import ROLL_FILE, front_month_bars                     # noqa: E402
from ivb.sessions import build_sessions                               # noqa: E402
from ivb.timestamps import assert_verified                            # noqa: E402
from src import viz                                                   # noqa: E402

# The Layer 1 resolver is IMPORTED, never re-implemented. A second copy of the
# geometry would be free to drift from the one the other charts use, and then
# two pictures of the same rule could disagree.
_c04 = importlib.import_module("04_charts")
illustrate_layer1_trade = _c04.illustrate_layer1_trade

# ---------------------------------------------------------------------------
# The unsealed range is HARD-CODED to match docs/IVB-SPEC.md sec 0.2.3b exactly.
# It is not a command-line argument. An unseal is a written decision, and the
# code may not quietly widen what that decision covers.
# ---------------------------------------------------------------------------
UNSEAL_START = pd.Timestamp("2026-01-01")
UNSEAL_END = pd.Timestamp("2026-08-31")
UNSEAL_DATE = "2026-09-15"
UNSEAL_REF = "IVB-SPEC.md sec 0.2.3b UNSEAL #1"

N_MAIN = 8

# Scenario strings returned by illustrate_layer1_trade() for a session where the
# IB broke but price never came back to the zone.
NO_FILL = "no_fill"
NOT_A_BREAK = ("no_breakout", "ambiguous_breakout")


def qualify(rows: list) -> tuple:
    """Split resolved sessions into the two pools the charts are drawn from.

    filled   IB broke AND price later traded back into the reload zone.
             The fill price IS the near value-area edge, i.e. the zone's outer
             boundary, so "filled" and "re-entered the zone" are the same event.
    walked   IB broke and price NEVER returned. Layer 1 sits out.

    Everything else -- no breakout, an ambiguous breakout bar, a degenerate
    zero-width zone -- is in neither pool and is not drawn.
    """
    filled, walked = [], []
    for r in rows:
        if r.get("scenario") in NOT_A_BREAK or not r.get("direction"):
            continue
        if r.get("entry_idx") is not None:
            filled.append(r)
        elif r.get("scenario") == NO_FILL:
            walked.append(r)
    return filled, walked


def chart_notes(seed: int, src_name: str, selection: str) -> list:
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
        selection,
        "UNKNOWN STABILITY: the sec b.9 profile-method sensitivity gate has NEVER"
        " been run on real",
        "  bars. VAH / VAL / POC above come from ONE allocation rule"
        " (volume_uniform, sec b.2).",
        "  A different rule could move all three. Nothing here measures how much.",
        "GEOMETRY: illustrate_layer1_trade() -- a plain reading of the spec FOR"
        " DRAWING ONLY.",
        "  Step 3 does not exist. No unit tests, no cost sweep, no walk-forward,"
        " no control.",
        "NO AGGREGATE was computed on this window. Per-session numbers only.",
    ]


def draw(r, s, cfg, outdir: Path, fname: str, title: str, src_note: str,
         notes: list) -> Path:
    win = s.bars.iloc[:s.trade_end_idx + 1]
    levels = {"ib_high": s.ib_high, "ib_low": s.ib_low, "vah": r["vah"],
              "poc": r["poc"], "val": r["val"], "ib_end_idx": s.ib_close_idx,
              "zone_bottom": r.get("zone_bottom"), "zone_top": r.get("zone_top")}
    f = viz.chart_session(
        win, levels, r, r["profile"], title=title,
        subtitle="{}   IB{}m, E1 limit at the near VA edge, close_plus_hard exit, "
                 "R=2.0   |   {}".format(
                     str(r["session_date"].date()), cfg.ib_minutes, src_note),
        extra_notes=notes)
    return viz.save(f, outdir / fname)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", help="the REAL bars parquet")
    ap.add_argument("--roll-calendar", default=None,
                    help="READ a roll calendar from this path instead of "
                         "data/roll_calendar.csv. Nothing is written or rebuilt.")
    ap.add_argument("--outdir", default=str(OUT / "charts_unsealed_2026"))
    ap.add_argument("--seed", type=int, default=None,
                    help="session-sampling seed (default: Config.seed). Printed "
                         "with the chosen dates.")
    args = ap.parse_args()

    cfg = P0
    seed = cfg.seed if args.seed is None else args.seed
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / ".gitignore").write_text("*\n", encoding="utf-8")

    # ---- provenance gate ---------------------------------------------------
    kind = classify(args.path)
    if kind != REAL:
        print("[05] {} classifies as {}. This script draws REAL unsealed holdout "
              "bars only.".format(Path(args.path).name, kind))
        print("     Pointing it at a control file would put the unsealed-holdout "
              "caveat on a chart")
        print("     that is not holdout data. Refused.")
        return 2

    print("\n" + "=" * 78)
    print("[05] READING UNSEALED HOLDOUT DATA")
    print("     range      {} .. {}".format(UNSEAL_START.date(), UNSEAL_END.date()))
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
        print("[05] missing: {}".format(", ".join(str(p) for p in missing)))
        return 2
    cal = pd.read_csv(roll_path, parse_dates=["session_date"])
    print("\n[05] roll calendar: {}  ({:,} rows, {} .. {})".format(
        roll_path, len(cal), str(cal["session_date"].min().date()),
        str(cal["session_date"].max().date())))
    if roll_path != ROLL_FILE:
        print("     *** NOT the default data/roll_calendar.csv. Every level drawn")
        print("     *** below is conditional on THIS calendar.")
    # Coverage is judged on OVERLAP, not on the calendar's last date: the last
    # trading session of August is not 2026-08-31, so an end-date comparison
    # rejects a calendar that is in fact complete.
    cd = cal["session_date"]
    n_cover = int(((cd >= UNSEAL_START) & (cd <= UNSEAL_END)).sum())
    if n_cover == 0:
        print("[05] this calendar has NO row inside {} .. {}. It cannot select a "
              "front month for the unsealed window.".format(
                  UNSEAL_START.date(), UNSEAL_END.date()))
        print("     Pass --roll-calendar data/roll_calendar_6635298.csv")
        return 2

    # ---- the unseal itself -------------------------------------------------
    front = front_month_bars(bars, cal)
    front = select(front, "FORWARD_HOLDOUT", unseal=UNSEAL_TOKEN)
    d = pd.to_datetime(front["session_date"])
    front = front[(d >= UNSEAL_START) & (d <= UNSEAL_END)].copy()

    sessions = build_sessions(front, cfg)
    sessions = [s for s in sessions if not (cfg.exclude_half_days and s.is_half_day)]
    deg = degraded_dates()
    sessions = [s for s in sessions if s.session_date not in deg]
    if not sessions:
        print("[05] no sessions in the unsealed window. Check the roll calendar.")
        return 2
    print("[05] window built: {} .. {}   half-days and vendor-degraded days "
          "excluded (sec 0.2.4).".format(
              sessions[0].session_date.date(), sessions[-1].session_date.date()))

    # ---- resolve every session ---------------------------------------------
    rows = []
    for s in sessions:
        r = illustrate_layer1_trade(s, cfg)
        r["session_date"] = s.session_date
        rows.append(r)
    by_date = {str(s.session_date.date()): s for s in sessions}

    filled, walked = qualify(rows)
    filled.sort(key=lambda r: r["session_date"])
    walked.sort(key=lambda r: r["session_date"])

    # ---- sufficiency, and ONLY sufficiency ---------------------------------
    # The size of the `filled` pool is a count across sessions -- a fill rate in
    # disguise. The unseal was granted for pictures, not for that number, so it
    # is not printed. Insufficiency IS printed, because it changes what gets
    # drawn and the reader has to know.
    if len(filled) < N_MAIN:
        print("\n[05] ONLY {} SESSION(S) QUALIFY -- fewer than the {} asked for."
              .format(len(filled), N_MAIN))
        print("     Qualify = IB broke AND price later traded back into the reload")
        print("     zone. Drawing what exists.")
    else:
        print("\n[05] at least {} sessions qualify. The exact pool size is WITHHELD:"
              .format(N_MAIN))
        print("     it is a count across sessions, i.e. a fill rate, and the unseal")
        print("     covers pictures only (sec 0.2.3b). One line in qualify()'s caller")
        print("     would print it if you decide you want it.")
    if not walked:
        print("[05] NO session in this window had the IB break and price never "
              "return. The")
        print("     'what Layer 1 walks away from' chart cannot be drawn.")

    # ---- sampling ----------------------------------------------------------
    # ONE generator, fixed draw order: the 8 main sessions, then the walkaway.
    rng = np.random.default_rng(seed)
    k = min(N_MAIN, len(filled))
    main_idx = sorted(int(i) for i in rng.choice(len(filled), size=k, replace=False))
    picks = [("MAIN", n, filled[i]) for n, i in enumerate(main_idx, 1)]
    if walked:
        picks.append(("WALKAWAY", 1, walked[int(rng.integers(0, len(walked)))]))

    print("\n[05] sampling seed = {}  (numpy default_rng; draw order MAIN then "
          "WALKAWAY)".format(seed))
    print("[05] sessions chosen:")
    for grp, n, r in picks:
        print("     {:<9s} #{}  {}  {:<5s}  {}".format(
            grp, n, str(r["session_date"].date()),
            "LONG" if r["direction"] == 1 else "SHORT", r["scenario"]))

    # ---- draw --------------------------------------------------------------
    src_name = Path(args.path).name
    src_note = ("REAL BARS, source: {}   |   UNSEALED HOLDOUT {} .. {} -- "
                "IN-SAMPLE since {}".format(
                    src_name, UNSEAL_START.date(), UNSEAL_END.date(), UNSEAL_DATE))
    written = []
    for grp, n, r in picks:
        s = by_date[str(r["session_date"].date())]
        if grp == "MAIN":
            sel = ("SELECTION: {} of {}, drawn uniformly at random (seed {}) from the "
                   "sessions in this window".format(n, k, seed))
            sel2 = ("  where the IB broke AND price later traded back into the reload "
                    "zone. Not best, not worst, not recent.")
            title = ("ILLUSTRATIVE, NOT A RESULT -- UNSEALED HOLDOUT DATA   |   "
                     "CHART 1(a) LAYER 1   RANDOM SAMPLE {} of {}".format(n, k))
            fname = "01a_L1_unsealed_MAIN{}_{}.png".format(n, r["session_date"].date())
        else:
            sel = ("SELECTION: drawn at random (seed {}) from the sessions where the "
                   "IB BROKE and price".format(seed))
            sel2 = ("  NEVER returned to the reload zone. LAYER 1 TAKES NO TRADE HERE; "
                    "LAYER 0 DOES. This is what Layer 1 walks away from.")
            title = ("ILLUSTRATIVE, NOT A RESULT -- UNSEALED HOLDOUT DATA   |   "
                     "CHART 1(a) LAYER 1   WALKAWAY: IB broke, zone never touched, "
                     "NO LAYER 1 TRADE")
            fname = "01a_L1_unsealed_WALKAWAY_{}.png".format(r["session_date"].date())
        notes = chart_notes(seed, src_name, sel)
        notes.insert(notes.index(sel) + 1, sel2)
        written.append(draw(r, s, cfg, outdir, fname, title, src_note, notes))

    print("\n[05] wrote {} file(s):".format(len(written)))
    for p in written:
        print("     " + str(p.resolve()))
    print("\n[05] NOT RUN, deliberately: b9_sensitivity(), run_strategy(), any")
    print("     Step 1-5 evaluation, any aggregate statistic. No research artifact")
    print("     was written. Record the unseal, not the pictures.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
