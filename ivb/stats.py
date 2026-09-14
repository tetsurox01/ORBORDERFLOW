"""Metrics and the block bootstrap -- IVB-SPEC.md sec (i).

Monthly blocks, because trading-day outcomes are NOT independent: volatility
clusters and regimes persist for weeks. An i.i.d. daily bootstrap would produce an
interval perhaps 2-3x too narrow and make a noisy result look significant.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def metrics(df: pd.DataFrame, *, s_all: int | None = None) -> dict:
    """Headline metrics. `s_all` sets the denominator; defaults to len(df)."""
    n_sessions = s_all if s_all is not None else len(df)
    traded = df[df.get("traded", False) == True]  # noqa: E712
    pnl = df["net_dollars"].fillna(0.0)

    wins = traded[traded["net_dollars"] > 0]["net_dollars"]
    losses = traded[traded["net_dollars"] < 0]["net_dollars"]
    gross_win = float(wins.sum())
    gross_loss = float(-losses.sum())

    equity = pnl.cumsum()
    dd = float((equity - equity.cummax()).min()) if len(equity) else 0.0

    return {
        "sessions": int(n_sessions),
        "trades": int(len(traded)),
        "duty_cycle": len(traded) / n_sessions if n_sessions else np.nan,
        "total_dollars": float(pnl.sum()),
        "exp_per_session": float(pnl.sum()) / n_sessions if n_sessions else np.nan,
        "exp_per_trade": float(traded["net_dollars"].mean()) if len(traded) else np.nan,
        "exp_r": float(traded["r_multiple"].mean()) if "r_multiple" in traded and len(traded) else np.nan,
        "win_rate": len(wins) / len(traded) if len(traded) else np.nan,
        "profit_factor": gross_win / gross_loss if gross_loss > 0 else np.inf,
        "max_drawdown": dd,
        "avg_mfe": float(traded["mfe_points"].mean()) if "mfe_points" in traded and len(traded) else np.nan,
        "avg_mae": float(traded["mae_points"].mean()) if "mae_points" in traded and len(traded) else np.nan,
    }


def _month_key(dates: pd.Series) -> pd.Series:
    return pd.to_datetime(dates).dt.to_period("M").astype(str)


def block_bootstrap_ci(
    df: pd.DataFrame, *, n: int = 10_000, seed: int = 20260101, alpha: float = 0.05
) -> dict:
    """95% CI on expectancy per session, resampling whole calendar months."""
    d = df.copy()
    d["_m"] = _month_key(d["session_date"])
    groups = [g["net_dollars"].fillna(0.0).to_numpy() for _, g in d.groupby("_m")]
    if len(groups) < 4:
        return {"point": np.nan, "lo": np.nan, "hi": np.nan, "n_blocks": len(groups)}

    rng = np.random.default_rng(seed)
    k = len(groups)
    stats = np.empty(n)
    for i in range(n):
        pick = rng.integers(0, k, size=k)
        vals = np.concatenate([groups[j] for j in pick])
        stats[i] = vals.mean()

    point = float(np.concatenate(groups).mean())
    return {
        "point": point,
        "lo": float(np.quantile(stats, alpha / 2)),
        "hi": float(np.quantile(stats, 1 - alpha / 2)),
        "n_blocks": k,
    }


def paired_block_bootstrap_ci(
    a: pd.DataFrame, b: pd.DataFrame, *, n: int = 10_000, seed: int = 20260101,
    alpha: float = 0.05,
) -> dict:
    """95% CI on (a - b) expectancy per session, PAIRED on the same months.

    Pairing removes the shared market-regime variance and is far more powerful
    than comparing two independent intervals. Two overlapping individual CIs do
    NOT mean the difference is insignificant -- this is the correct test.
    """
    aa = a[["session_date", "net_dollars"]].copy()
    bb = b[["session_date", "net_dollars"]].copy()
    aa["_m"] = _month_key(aa["session_date"])
    bb["_m"] = _month_key(bb["session_date"])

    months = sorted(set(aa["_m"]) & set(bb["_m"]))
    ga = {m: g["net_dollars"].fillna(0.0).to_numpy() for m, g in aa.groupby("_m") if m in months}
    gb = {m: g["net_dollars"].fillna(0.0).to_numpy() for m, g in bb.groupby("_m") if m in months}
    if len(months) < 4:
        return {"point": np.nan, "lo": np.nan, "hi": np.nan, "n_blocks": len(months),
                "excludes_zero": False}

    rng = np.random.default_rng(seed)
    k = len(months)
    stats = np.empty(n)
    for i in range(n):
        pick = rng.integers(0, k, size=k)
        va = np.concatenate([ga[months[j]] for j in pick])
        vb = np.concatenate([gb[months[j]] for j in pick])
        stats[i] = va.mean() - vb.mean()

    point = float(np.concatenate([ga[m] for m in months]).mean()
                  - np.concatenate([gb[m] for m in months]).mean())
    lo = float(np.quantile(stats, alpha / 2))
    hi = float(np.quantile(stats, 1 - alpha / 2))
    return {"point": point, "lo": lo, "hi": hi, "n_blocks": k,
            "excludes_zero": bool(lo > 0 or hi < 0), "positive": bool(lo > 0)}


def percentile_rank(value: float, dist: np.ndarray) -> float:
    return float((dist < value).mean() * 100)


def ambiguous_rate(df: pd.DataFrame) -> dict:
    traded = df[df.get("traded", False) == True]  # noqa: E712
    if not len(traded) or "ambiguous" not in traded:
        return {"rate": np.nan, "by_case": {}}
    rate = float(traded["ambiguous"].mean())
    by_case = traded[traded["ambiguous"]]["ambiguous_case"].value_counts().to_dict()
    return {"rate": rate, "by_case": by_case, "n": int(len(traded))}
