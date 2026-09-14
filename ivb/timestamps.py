"""Empirical verification of the bar timestamp convention -- IVB-SPEC.md sec 0.2.2.

DO NOT ASSUME [09:30:00, 09:31:00) stamping. A one-minute error here silently leaks
the future into the initial balance and invalidates every result in this project.

Three independent checks:
  1. The RTH open volume spike must land on the bar stamped 09:30 (open-stamped).
  2. HALT BOUNDARY: the last volume-bearing bar before the CME daily maintenance
     halt must be 16:59 (open-stamped), not 17:00 (close-stamped).
  3. A full session must contain exactly 390 RTH bars.

CHECK 2 WAS REPLACED. THE OLD ONE WAS VOID. DO NOT REINSTATE IT.
    The old check 2 asserted "there must be no full-volume bar stamped 16:00,
    because RTH ends at 16:00:00". That reasoning is wrong for a FUTURES feed.
    16:00 ET is the equity cash close; NQ on GLBX keeps trading until 16:15 and
    reopens at 18:00. So a bar stamped 16:00 is full of real volume under BOTH
    conventions, and the check fired on every correct open-stamped feed. Measured:
    18/20 sessions tripped it, producing a CONFLICT against check 1 and a false
    DO-NOT-PROCEED on data that was in fact open-stamped.

    Check 3 cannot rescue it either: 09:30-15:59 and 09:31-16:00 are BOTH 390
    bars, so the bar count has no discriminating power between the conventions.
    It only detects missing minutes.

    The replacement uses the DAILY MAINTENANCE HALT (17:00-17:59 ET), where
    trading genuinely stops -- there is no "but futures keep going" escape. The
    two conventions give different answers there, which is what a check needs.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .config import DATA

CONVENTION_FILE = DATA / "timestamp_convention.json"


@dataclass
class TimestampVerdict:
    convention: str          # "open_stamped" | "close_stamped" | "UNKNOWN"
    sessions_tested: int
    spike_at_0930: int
    spike_at_0931: int
    spike_at_0929: int
    last_bar_before_halt_1659: int
    last_bar_before_halt_1700: int
    halt_sessions_tested: int
    median_rth_bar_count: float
    sessions_with_390_bars: int
    confident: bool
    notes: list[str]

    def save(self) -> None:
        CONVENTION_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONVENTION_FILE.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


def verify(bars: pd.DataFrame, n_sessions: int = 20, seed: int = 20260101) -> TimestampVerdict:
    """`bars` needs columns: ts_et (tz-aware America/New_York), volume.

    Returns a verdict and writes data/timestamp_convention.json.
    """
    b = bars.copy()
    b["ts_et"] = pd.to_datetime(b["ts_et"])

    # Parent symbology returns EVERY contract, so a session holds one row per
    # (timestamp, contract). Collapse to one row per timestamp before counting
    # minutes or locating the open spike -- otherwise the 390-bar check counts
    # contracts, not minutes.
    b = (b.groupby("ts_et", as_index=False)
           .agg(volume=("volume", "sum")))

    b["session_date"] = b["ts_et"].dt.date
    b["hm"] = b["ts_et"].dt.strftime("%H:%M")

    all_sessions = sorted(b["session_date"].unique())
    rng = np.random.default_rng(seed)
    # Full sessions only: a half day would fail check 3 for the wrong reason.
    counts = b.groupby("session_date").size()
    full = [d for d in all_sessions if counts.get(d, 0) > 380]
    if not full:
        full = all_sessions
    pick = rng.choice(full, size=min(n_sessions, len(full)), replace=False)

    spike_0929 = spike_0930 = spike_0931 = 0
    rth_counts: list[int] = []
    notes: list[str] = []

    for d in pick:
        s = b[b["session_date"] == d]
        window = s[s["hm"].between("09:25", "09:35")]
        if window.empty:
            continue
        top = window.loc[window["volume"].idxmax(), "hm"]
        if top == "09:29":
            spike_0929 += 1
        elif top == "09:30":
            spike_0930 += 1
        elif top == "09:31":
            spike_0931 += 1

        rth = s[s["hm"].between("09:30", "15:59")]
        rth_counts.append(len(rth))


    tested = len(pick)
    median_count = float(np.median(rth_counts)) if rth_counts else float("nan")
    n390 = sum(1 for c in rth_counts if c == 390)

    # ---- CHECK 2: the CME daily maintenance halt, 17:00-17:59 ET -----------
    # Trading genuinely STOPS here, so unlike 16:00 (equity close, futures still
    # trading) the boundary is unambiguous:
    #   open-stamped  -> last volume-bearing bar is 16:59; the 17:00 bar would
    #                    cover [17:00, 17:01) which is inside the halt -> empty.
    #   close-stamped -> last volume-bearing bar is 17:00, covering (16:59, 17:00].
    # Run over ALL Mon-Thu sessions, not the sample: a halt happens every weeknight
    # and one example proves nothing. Friday is excluded (weekend close, no reopen).
    vol = b[b["volume"] > 0]
    wk = vol[vol["ts_et"].dt.dayofweek < 4]
    band = wk[wk["hm"].between("16:30", "17:59")]
    last_hm = band.groupby(band["ts_et"].dt.normalize())["hm"].max()
    halt_n = int(len(last_hm))
    halt_1659 = int((last_hm == "16:59").sum())
    halt_1700 = int((last_hm == "17:00").sum())

    # ---- decide ----------------------------------------------------------
    convention = "UNKNOWN"
    confident = False
    if spike_0930 >= 0.8 * tested:
        convention = "open_stamped"
        confident = True
        notes.append("Open volume spike on the 09:30 bar. IVB-SPEC sec 0 stamping is CORRECT.")
    elif spike_0931 >= 0.8 * tested:
        convention = "close_stamped"
        notes.append(
            "CLOSE-STAMPED FEED. Every bar label is one minute LATE. "
            "The IB window must become (09:30, 09:30+N] on these labels, i.e. bars "
            "stamped 09:31..10:00 for a 30-minute IB. DO NOT PROCEED until the "
            "loader shifts timestamps back by one minute."
        )
    elif spike_0929 >= 0.8 * tested:
        convention = "UNKNOWN"
        notes.append(
            "Spike on the 09:29 bar. Neither convention explains this. Suspect a "
            "timezone or DST error in the loader. Investigate before proceeding."
        )
    else:
        notes.append(
            f"No clear spike location (09:29={spike_0929}, 09:30={spike_0930}, "
            f"09:31={spike_0931} of {tested}). Inconclusive; widen the sample."
        )

    # Compared as a RATIO, not against a fixed threshold: the residual sessions are
    # ones whose last pre-halt print simply landed earlier than 16:59 (thin evening
    # trade), which is neither evidence for nor against a convention. What matters is
    # which of the two candidate minutes dominates, and by how much.
    if halt_n and (halt_1659 + halt_1700) > 0:
        share = halt_1659 / (halt_1659 + halt_1700)
        notes.append(
            f"HALT BOUNDARY: last pre-halt bar is 16:59 on {halt_1659:,} sessions and "
            f"17:00 on {halt_1700:,} (of {halt_n:,} weeknights). "
            f"16:59 share = {share:.1%}."
        )
        if share >= 0.9:
            notes.append("16:59 dominates -> OPEN-STAMPED. Agrees with check 1.")
            if convention == "close_stamped":
                confident = False
                notes.append("CONFLICT: check 1 says close-stamped, check 2 says open. Do not proceed.")
        elif share <= 0.1:
            notes.append("17:00 dominates -> CLOSE-STAMPED.")
            if convention == "open_stamped":
                confident = False
                notes.append("CONFLICT: check 1 and check 2 disagree. Do not proceed.")
        else:
            confident = False
            notes.append("Halt boundary is ambiguous. Do not proceed.")
    else:
        confident = False
        notes.append("Halt boundary check found no usable sessions. Do not proceed.")

    if rth_counts and n390 < 0.8 * len(rth_counts):
        notes.append(
            f"Only {n390}/{len(rth_counts)} sessions have exactly 390 RTH bars "
            f"(median {median_count:.0f}). Expect 390. Check for missing bars: "
            "Databento omits minutes with zero trades, so gaps must be forward-filled "
            "or handled explicitly before the IB is computed."
        )
        confident = False

    v = TimestampVerdict(
        convention=convention,
        sessions_tested=tested,
        spike_at_0930=spike_0930,
        spike_at_0931=spike_0931,
        spike_at_0929=spike_0929,
        last_bar_before_halt_1659=halt_1659,
        last_bar_before_halt_1700=halt_1700,
        halt_sessions_tested=halt_n,
        median_rth_bar_count=median_count,
        sessions_with_390_bars=n390,
        confident=confident,
        notes=notes,
    )
    v.save()
    return v


def assert_verified() -> TimestampVerdict:
    """Called on every data load. Refuses to run unverified."""
    if not CONVENTION_FILE.exists():
        raise RuntimeError(
            "Timestamp convention not verified.\n"
            "Run: python scripts/00_verify_timestamps.py\n"
            "IVB-SPEC.md sec 0.2.2 -- this is the highest-value 15 minutes in the plan."
        )
    d = json.loads(CONVENTION_FILE.read_text(encoding="utf-8"))
    if not d.get("confident") or d.get("convention") != "open_stamped":
        raise RuntimeError(
            f"Timestamp verification did not pass cleanly: convention="
            f"{d.get('convention')!r}, confident={d.get('confident')}.\n"
            + "\n".join(d.get("notes", []))
        )
    return TimestampVerdict(**d)
