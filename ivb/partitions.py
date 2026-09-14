"""Sample partitions with the holdouts sealed IN CODE -- IVB-SPEC.md sec 0.2.3.

Requesting holdout data raises unless an explicit unseal token is passed. The token
is deliberately awkward to type. Opening a holdout should be a decision, never an
accident.
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
        if unseal != UNSEAL_TOKEN:
            raise SealedPartitionError(
                f"\n{partition} is SEALED (IVB-SPEC.md sec 0.2.3).\n"
                "It may be opened ONCE, at the end, together with the other holdout.\n"
                "Opening it early destroys its value permanently and there is no recovery.\n"
                f"If that is genuinely what you want, pass unseal='{UNSEAL_TOKEN}'."
            )
        if partition == "BACKWARD_HOLDOUT":
            return df[(d >= BACKWARD_START) & (d <= p.backward_end)].copy()
        return df[d >= p.forward_start].copy()

    if partition == "ALL":
        raise SealedPartitionError(
            "partition='ALL' would silently include both holdouts. Refused. "
            "Name the partition explicitly."
        )

    raise ValueError(f"Unknown partition {partition!r}")
