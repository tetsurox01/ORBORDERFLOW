"""Sample partitions with the holdouts sealed IN CODE -- IVB-SPEC.md sec 0.2.3.

Requesting holdout data raises unless an explicit unseal token is passed. The token
is deliberately awkward to type. Opening a holdout should be a decision, never an
accident.

=============================================================================
STANDING FACT -- BACKWARD_HOLDOUT IS NOT USABLE DATA. DO NOT PLAN A TEST ON IT.
Measured 2026-09-15 on the front-month series the backtest actually consumes.
=============================================================================

Do not read the sealed/unsealed distinction as "sealed but sound". The backward
holdout is sealed AND its underlying bars are unfit. Two independent measured
defects, either of which alone would disqualify it:

1. THE FRONT MONTH IS THE WRONG CONTRACT ALMOST EVERY SESSION.
   Share of sessions where the roll calendar's front month is NOT the
   highest-volume outright that day:

       2010 100.0%   2011 98.5%   2012 87.0%   2013 82.3%   2014 72.3%
       ---- backward holdout ends -------------------------------------
       2015  26.9%   2016 20.2%   2017+ ~1.6% (see below)

   From 2016-06-13 the residual ~1.6% is four sessions a year -- the roll day
   itself, where the calendar switches one session after volume crosses over.
   That is a deliberate one-day lag, not a defect. Everything before 2015 is a
   defect: the series is stitched from contracts that were barely trading.

2. THE BARS ARE MOSTLY ABSENT ANYWAY.
   Median RTH bars per session in the front-month series, out of 390:

       2010   15      2011   18      2012    8      2013   20      2014  103
       2015  390      2016  390      2017+ 390

   On the raw pull (all symbols, before the roll calendar) the medians are 40 /
   33 / 107 / 402 / 442, and the share of volume timestamped in the 19:00 ET
   hour is 47.1% / 38.3% / 29.3% for 2010-2012 against <5% from 2013. So part of
   the loss is vendor sparsity and part is defect 1 concentrating the series on
   dead contracts. Both point the same way.

CONSEQUENCE, BINDING. `BACKWARD_HOLDOUT` cannot serve its stated purpose -- a
second out-of-sample regime check -- because there is no usable price series
behind it. Unsealing it would answer nothing. It is left registered and sealed
rather than deleted so the record stays honest, and `select()` refuses it with
this finding attached even when the correct unseal token is supplied.

Re-running `scripts/02_build_rolls.py` does NOT fix this. See IVB-SPEC.md sec
0.1.5 (defect D4) for the roll-selection bug and its measured DEVELOPMENT
impact.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import pandas as pd

from .config import DATA

# GLBX.MDP3 coverage begins 2010-06-06; 2010-07-01 is the first clean month
# boundary after it and is the REGISTERED pull start (IVB-SPEC sec 0.2.3).
# "2010-2014" in prose therefore means 2010-07-01 .. 2014-12-31.
BACKWARD_COVERAGE_START = pd.Timestamp("2010-06-06")  # vendor limit, not a choice
BACKWARD_START = pd.Timestamp("2010-07-01")
DEV_START = pd.Timestamp("2015-01-01")
DEV_FRACTION = 0.80  # of the 2015->present sample, BY SESSION COUNT

UNSEAL_TOKEN = "I_ACCEPT_THAT_OPENING_A_HOLDOUT_IS_IRREVERSIBLE"

# The backward holdout has a SECOND lock, because it has a second problem: its
# bars are unfit (see the module docstring). The normal token is not enough --
# opening it is not merely irreversible, it is uninformative. Measured
# 2026-09-15; this string is deliberately harder to type than the first one.
BACKWARD_UNFIT_TOKEN = (
    "I_ACCEPT_THAT_OPENING_A_HOLDOUT_IS_IRREVERSIBLE"
    "_AND_THAT_THE_2010_2014_BARS_ARE_MEASURED_UNFIT"
)

# Share of sessions whose calendar front month is NOT that day's top-volume
# outright. From 2016-06-13 the residual is the deliberate one-day roll lag.
FRONT_MONTH_MISMATCH_RATE = {
    2010: 1.000, 2011: 0.985, 2012: 0.870, 2013: 0.823, 2014: 0.723,
    2015: 0.269, 2016: 0.202, 2017: 0.016, 2018: 0.016, 2019: 0.016,
    2020: 0.015, 2021: 0.012, 2022: 0.016, 2023: 0.016, 2024: 0.015,
    2025: 0.016, 2026: 0.012,
}

# Median RTH bars per session in the FRONT-MONTH series, out of 390.
FRONT_MONTH_MEDIAN_RTH_BARS = {
    2010: 15, 2011: 18, 2012: 8, 2013: 20, 2014: 103,
    2015: 390, 2016: 390, 2017: 390, 2018: 390, 2019: 390,
    2020: 390, 2021: 390, 2022: 390, 2023: 390, 2024: 390,
    2025: 390, 2026: 390,
}

PARTITION_FILE = DATA / "partitions.json"


class SealedPartitionError(RuntimeError):
    pass


@dataclass(frozen=True)
class Partitions:
    backward_end: pd.Timestamp     # last date of BACKWARD_HOLDOUT
    dev_start: pd.Timestamp
    dev_end: pd.Timestamp          # last date of DEVELOPMENT
    forward_start: pd.Timestamp

    def to_json(self) -> dict:
        return {
            "BACKWARD_HOLDOUT": [str(BACKWARD_START.date()), str(self.backward_end.date())],
            "DEVELOPMENT": [str(self.dev_start.date()), str(self.dev_end.date())],
            "FORWARD_HOLDOUT": [str(self.forward_start.date()), "present"],
            "dev_fraction": DEV_FRACTION,
            "note": "Computed once by session count. Never recompute after Step 1 begins.",
        }


def build_partitions(session_dates: pd.Series) -> Partitions:
    """Compute the 80% split point by SESSION COUNT, not calendar date.

    Written once to data/partitions.json and never recomputed.
    """
    dates = pd.Series(pd.to_datetime(sorted(set(session_dates))))
    modern = dates[dates >= DEV_START].reset_index(drop=True)
    if len(modern) < 100:
        raise ValueError(f"Only {len(modern)} sessions from {DEV_START.date()}; need far more.")

    split_idx = int(len(modern) * DEV_FRACTION)
    dev_end = modern.iloc[split_idx - 1]
    forward_start = modern.iloc[split_idx]

    backward = dates[dates < DEV_START]
    backward_end = backward.iloc[-1] if len(backward) else DEV_START - pd.Timedelta(days=1)

    p = Partitions(
        backward_end=backward_end,
        dev_start=DEV_START,
        dev_end=dev_end,
        forward_start=forward_start,
    )
    PARTITION_FILE.parent.mkdir(parents=True, exist_ok=True)
    PARTITION_FILE.write_text(json.dumps(p.to_json(), indent=2), encoding="utf-8")
    return p


def load_partitions() -> Partitions:
    if not PARTITION_FILE.exists():
        raise FileNotFoundError(
            f"{PARTITION_FILE} missing. Run scripts/02_build_rolls.py first."
        )
    d = json.loads(PARTITION_FILE.read_text(encoding="utf-8"))
    return Partitions(
        backward_end=pd.Timestamp(d["BACKWARD_HOLDOUT"][1]),
        dev_start=pd.Timestamp(d["DEVELOPMENT"][0]),
        dev_end=pd.Timestamp(d["DEVELOPMENT"][1]),
        forward_start=pd.Timestamp(d["FORWARD_HOLDOUT"][0]),
    )


def select(df: pd.DataFrame, partition: str, *, date_col: str = "session_date",
           unseal: str | None = None) -> pd.DataFrame:
    """Filter to a partition. Holdouts require the unseal token."""
    p = load_partitions()
    d = pd.to_datetime(df[date_col])

    if partition == "DEVELOPMENT":
        return df[(d >= p.dev_start) & (d <= p.dev_end)].copy()

    if partition in ("BACKWARD_HOLDOUT", "FORWARD_HOLDOUT"):
        # BACKWARD_UNFIT_TOKEN clears this first gate too -- it is the normal
        # token plus an extra acknowledgement, not a way around it.
        if unseal not in (UNSEAL_TOKEN, BACKWARD_UNFIT_TOKEN):
            raise SealedPartitionError(
                f"\n{partition} is SEALED (IVB-SPEC.md sec 0.2.3).\n"
                "It may be opened ONCE, at the end, together with the other holdout.\n"
                "Opening it early destroys its value permanently and there is no recovery.\n"
                f"If that is genuinely what you want, pass unseal='{UNSEAL_TOKEN}'."
            )
        if partition == "BACKWARD_HOLDOUT":
            # Second lock. Sealed is about spending the sample once; THIS is
            # about the sample not being worth spending. See module docstring.
            if unseal != BACKWARD_UNFIT_TOKEN:
                raise SealedPartitionError(
                    "\nBACKWARD_HOLDOUT is sealed AND its bars are MEASURED UNFIT.\n"
                    "  - front month is the wrong contract on 72-100% of sessions,"
                    " every year 2010-2014\n"
                    "  - median RTH coverage 8-103 bars per session out of 390\n"
                    "It cannot answer the regime question it was registered for, so"
                    " opening it\nbuys nothing and still burns the holdout. If you"
                    " have read ivb/partitions.py\nand IVB-SPEC.md sec 0.1.5 and"
                    " still want the raw window:\n"
                    f"    unseal='{BACKWARD_UNFIT_TOKEN}'"
                )
            return df[(d >= BACKWARD_START) & (d <= p.backward_end)].copy()
        return df[d >= p.forward_start].copy()

    if partition == "ALL":
        raise SealedPartitionError(
            "partition='ALL' would silently include both holdouts. Refused. "
            "Name the partition explicitly."
        )

    raise ValueError(f"Unknown partition {partition!r}")
