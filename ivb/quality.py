"""Vendor data-quality days -- IVB-SPEC.md sec 0.2.4.

Databento marks some days as `degraded` in `metadata.get_dataset_condition`. The
download emits a BentoWarning listing a few of them and truncating the rest with
"...", so the warning must never be the source of truth -- the metadata endpoint is.

WHY THESE SESSIONS ARE EXCLUDED, NOT REPAIRED.
    A degraded day can be missing messages. Missing messages inside the IB window
    produce a NARROWER observed IB high/low, and every Layer 1 quantity is built on
    that window:

        IB range  ->  ib_range_atr, which drives the no-trade filter
        profile   ->  POC, VAH, VAL     (sec b.2 bin width is the MEDIAN IB BAR RANGE,
                                         so it shrinks too)
        risk_R    =   (VAH - VAL) + hard_stop_ticks     (sec b.10 identity)

    A narrow IB is also a MORE tradeable-looking session: a smaller IB breaks more
    easily and yields a tighter stop, so the bias is toward flattering results. None
    of it would raise a flag downstream -- the numbers are all internally consistent,
    just built on a window that did not really look like that.

    Repair is not available. Interpolating an absent high is inventing the one number
    the whole strategy keys on. Exclusion loses sessions; repair fabricates them.

The artifact `data/raw/degraded_days.csv` is COMMITTED provenance, not a cache. It
records what the vendor said and when the vendor last modified each day, so a later
re-pull that silently changes a day is detectable.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import DATA

DEGRADED_FILE = DATA / "raw" / "degraded_days.csv"


def load_degraded(path: Path | str | None = None) -> pd.DataFrame:
    """Read the committed degraded-day list. Empty frame if it is absent."""
    p = Path(path) if path is not None else DEGRADED_FILE
    if not p.exists():
        return pd.DataFrame(columns=["date", "condition", "vendor_last_modified",
                                     "is_rth_session", "partition"])
    df = pd.read_csv(p)
    df["date"] = pd.to_datetime(df["date"])
    return df


def degraded_dates(path: Path | str | None = None) -> set:
    """The set of session_date values to exclude.

    Every non-available day is returned, including the ones that are not RTH
    sessions. Those simply never match a session and cost nothing; filtering them
    out here would make the set depend on a calendar this module does not own.
    """
    df = load_degraded(path)
    if not len(df):
        return set()
    return set(pd.to_datetime(df["date"]))
