"""Databento download and load -- IVB-SPEC.md sec 0.2.1.

GLBX.MDP3 / ohlcv-1m / NQ.FUT parent symbology -> INDIVIDUAL CONTRACTS.
A vendor continuous series is deliberately not used: the roll calendar in sec 0.1.1
is computed from per-contract volume, which a continuous series does not expose.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from .config import DATA

DATASET = "GLBX.MDP3"
SCHEMA = "ohlcv-1m"
PARENT = "NQ.FUT"
RAW_DIR = DATA / "raw"
ET = "America/New_York"


def download(start: str, end: str, *, out_dir: Path = RAW_DIR, force: bool = False) -> Path:
    """Pull ohlcv-1m for all NQ contracts between start and end (YYYY-MM-DD).

    Requires DATABENTO_API_KEY in the environment. Costs money -- check the
    cost estimate it prints before confirming.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"nq_ohlcv1m_{start}_{end}.parquet"
    if out.exists() and not force:
        print(f"[data] exists, skipping: {out}")
        return out

    try:
        import databento as db
    except ImportError as e:
        raise ImportError("pip install databento") from e

    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        raise RuntimeError(
            "DATABENTO_API_KEY not set.\n"
            "PowerShell:  $env:DATABENTO_API_KEY = 'db-...'"
        )

    client = db.Historical(key)

    cost = client.metadata.get_cost(
        dataset=DATASET, symbols=[PARENT], stype_in="parent",
        schema=SCHEMA, start=start, end=end,
    )
    size = client.metadata.get_billable_size(
        dataset=DATASET, symbols=[PARENT], stype_in="parent",
        schema=SCHEMA, start=start, end=end,
    )
    print(f"[data] {start} -> {end}: ${cost:.2f}, {size / 1e9:.2f} GB billable")
    if os.environ.get("IVB_CONFIRM_SPEND") != "yes":
        raise SystemExit(
            "Refusing to spend money without confirmation.\n"
            "Review the cost above, then:  $env:IVB_CONFIRM_SPEND = 'yes'"
        )

    store = client.timeseries.get_range(
        dataset=DATASET, symbols=[PARENT], stype_in="parent",
        schema=SCHEMA, start=start, end=end,
    )
    df = store.to_df()
    df.to_parquet(out)
    print(f"[data] wrote {len(df):,} rows -> {out}")
    return out


def load(path: str | Path) -> pd.DataFrame:
    """Load raw bars and normalise to the project's canonical frame.

    Returns columns: ts_et, symbol, open, high, low, close, volume, session_date
    """
    df = pd.read_parquet(path)
    df = df.reset_index()

    # Databento gives UTC nanosecond timestamps; the column name varies by version.
    ts_col = next(
        (c for c in ("ts_event", "ts_recv", "index", "timestamp") if c in df.columns),
        None,
    )
    if ts_col is None:
        raise ValueError(f"No timestamp column found in {list(df.columns)[:12]}")

    ts = pd.to_datetime(df[ts_col], utc=True)
    df["ts_et"] = ts.dt.tz_convert(ET)

    sym_col = "symbol" if "symbol" in df.columns else "raw_symbol"
    df["symbol"] = df[sym_col].astype(str)

    keep = ["ts_et", "symbol", "open", "high", "low", "close", "volume"]
    df = df[keep].copy()
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna(subset=["open", "high", "low", "close"])
    df["session_date"] = df["ts_et"].dt.normalize().dt.tz_localize(None)
    df = df.sort_values(["symbol", "ts_et"]).reset_index(drop=True)

    validate(df)
    return df


def validate(df: pd.DataFrame) -> None:
    """Cheap structural assertions. Loud failure beats a silent wrong number."""
    bad = df[(df["high"] < df["low"])
             | (df["high"] < df["open"]) | (df["high"] < df["close"])
             | (df["low"] > df["open"]) | (df["low"] > df["close"])]
    if len(bad):
        raise ValueError(f"{len(bad)} bars violate OHLC ordering. First:\n{bad.head()}")

    if (df["volume"] < 0).any():
        raise ValueError("Negative volume present.")

    dup = df.duplicated(subset=["symbol", "ts_et"]).sum()
    if dup:
        raise ValueError(f"{dup} duplicate (symbol, ts_et) rows.")
