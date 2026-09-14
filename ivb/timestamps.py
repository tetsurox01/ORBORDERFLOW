"""Empirical verification of the bar timestamp convention -- IVB-SPEC.md sec 0.2.2.

DO NOT ASSUME [09:30:00, 09:31:00) stamping. A one-minute error here silently leaks
the future into the initial balance and invalidates every result in this project.

Three independent checks:
  1. The RTH open volume spike must land on the bar stamped 09:30 (open-stamped).
  2. There must be no full-volume bar stamped 16:00 (RTH ends at 16:00:00).
  3. A full session must contain exactly 390 RTH bars.
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
    bars_1600_with_volume: int
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
    bars_1600 = 0
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

        at1600 = s[s["hm"] == "16:00"]
        if not at1600.empty and float(at1600["volume"].iloc[0]) > 0:
            bars_1600 += 1

    tested = len(pick)
    median_count = float(np.median(rth_counts)) if rth_counts else float("nan")
    n390 = sum(1 for c in rth_counts if c == 390)

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

    if bars_1600 > 0:
        notes.append(
            f"{bars_1600}/{tested} sessions have volume on a bar stamped 16:00. "
            "That is consistent with CLOSE-stamping and contradicts open-stamping."
        )
        if convention == "open_stamped":
            confident = False
            notes.append("CONFLICT: check 1 and check 2 disagree. Do not proceed.")

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
        bars_1600_with_volume=bars_1600,
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
