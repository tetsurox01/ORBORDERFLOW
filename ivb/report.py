"""Step 1 reporting. Never a single headline number."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import OUT, Config
from .stats import ambiguous_rate, metrics


def _fmt(v, nd=2):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "n/a"
    if isinstance(v, float):
        return f"{v:,.{nd}f}"
    return str(v)


def summary_line(name: str, m: dict) -> str:
    return (f"{name:<28} n={m['sessions']:>5}  trades={m['trades']:>5}  "
            f"exp/sess=${_fmt(m['exp_per_session']):>8}  "
            f"exp/trade=${_fmt(m['exp_per_trade']):>8}  "
            f"PF={_fmt(m['profit_factor'])!s:>6}  "
            f"win={_fmt(100 * m['win_rate'] if np.isfinite(m['win_rate']) else np.nan, 1)}%  "
            f"maxDD=${_fmt(m['max_drawdown'])}")


def by_year(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["year"] = pd.to_datetime(d["session_date"]).dt.year
    rows = []
    for y, g in d.groupby("year"):
        m = metrics(g, s_all=len(g))
        rows.append({"year": y, **{k: m[k] for k in
                                   ("sessions", "trades", "exp_per_session",
                                    "exp_per_trade", "profit_factor", "win_rate",
                                    "max_drawdown")}})
    return pd.DataFrame(rows)


def by_direction(df: pd.DataFrame) -> pd.DataFrame:
    t = df[df["traded"] == True]  # noqa: E712
    rows = []
    for d, g in t.groupby("direction"):
        m = metrics(g, s_all=len(g))
        rows.append({"direction": "long" if d == 1 else "short",
                     **{k: m[k] for k in ("trades", "exp_per_trade", "profit_factor",
                                          "win_rate", "avg_mfe", "avg_mae")}})
    return pd.DataFrame(rows)


def by_ib_decile(df: pd.DataFrame) -> pd.DataFrame:
    """Required reporting (sec f): diagnose wide/tight IB by looking, not filtering."""
    t = df[(df["traded"] == True) & df["ib_range_atr"].notna()].copy()  # noqa: E712
    if len(t) < 20:
        return pd.DataFrame()
    t["decile"] = pd.qcut(t["ib_range_atr"], 10, labels=False, duplicates="drop")
    rows = []
    for d, g in t.groupby("decile"):
        m = metrics(g, s_all=len(g))
        rows.append({"decile": int(d) + 1,
                     "ib_range_atr_lo": float(g["ib_range_atr"].min()),
                     "ib_range_atr_hi": float(g["ib_range_atr"].max()),
                     **{k: m[k] for k in ("trades", "exp_per_trade", "win_rate",
                                          "profit_factor")}})
    return pd.DataFrame(rows)


def skip_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    s = df["skip_reason"].replace("", "TRADED").value_counts().reset_index()
    s.columns = ["reason", "sessions"]
    s["pct"] = 100 * s["sessions"] / len(df)
    return s


def funnel(df: pd.DataFrame) -> dict:
    """The real S_all -> S_breakout funnel, replacing the [MEASURE] placeholders."""
    n_all = len(df)
    n_filtered = int((df["skip_reason"] == "min_ib_range_atr").sum())
    n_nobreak = int((df["skip_reason"] == "no_breakout").sum())
    n_traded = int((df["traded"] == True).sum())  # noqa: E712
    return {
        "S_all": n_all,
        "filtered_min_ib_range": n_filtered,
        "no_breakout": n_nobreak,
        "S_breakout": n_traded,
        "breakout_rate_of_eligible": n_traded / max(1, n_all - n_filtered),
    }


def write_step1(df: pd.DataFrame, cfg: Config, extras: dict) -> str:
    OUT.mkdir(parents=True, exist_ok=True)
    m = metrics(df, s_all=len(df))
    amb = ambiguous_rate(df)
    f = funnel(df)

    lines: list[str] = []
    add = lines.append
    add("=" * 78)
    add(f"STEP 1 -- BASELINE IB BREAKOUT   config={cfg.label}   cost_model={cfg.cost_model}")
    add(f"partition={cfg.partition}   ib={cfg.ib_minutes}min   trigger={cfg.breakout_trigger}   "
        f"R={cfg.r_mult}   intrabar={cfg.intrabar}")
    add("=" * 78)

    add("\n-- GATES (read these BEFORE the PnL) --")
    add(f"ambiguous_bar_pct   = {100 * amb['rate']:.2f}%  (gate: <= {100 * cfg.ambiguous_bar_gate:.0f}%)"
        if np.isfinite(amb.get("rate", np.nan)) else "ambiguous_bar_pct   = n/a")
    if amb.get("by_case"):
        for k, v in amb["by_case"].items():
            add(f"    {k:<20} {v}")
    gate_ok = np.isfinite(amb.get("rate", np.nan)) and amb["rate"] <= cfg.ambiguous_bar_gate
    add(f"GATE VERDICT: {'PASS' if gate_ok else 'FAIL -- result not trustworthy at 1-min resolution'}")

    add("\n-- SAMPLE FUNNEL (replaces the [MEASURE] placeholders in spec sec h.1) --")
    for k, v in f.items():
        add(f"{k:<30} {_fmt(v, 3) if isinstance(v, float) else v}")

    add("\n-- SKIP BREAKDOWN --")
    add(skip_breakdown(df).to_string(index=False))

    add("\n-- HEADLINE (denominator = S_all, non-breakout days count as zero) --")
    add(summary_line("P0 strategy", m))

    for name, cm in extras.get("controls", {}).items():
        add(summary_line(name, cm))

    add("\n-- PAIRED BLOCK-BOOTSTRAP CIs (monthly blocks) --")
    for name, ci in extras.get("cis", {}).items():
        verdict = "EXCLUDES ZERO" if ci.get("excludes_zero") else "straddles zero -> NOT a pass"
        add(f"{name:<34} diff=${_fmt(ci['point'])}  95% CI [{_fmt(ci['lo'])}, {_fmt(ci['hi'])}]  "
            f"blocks={ci['n_blocks']}  {verdict}")

    if "c2" in extras:
        c2 = extras["c2"]
        add(f"\nC2 coin-flip: P0 percentile rank = {c2['pct_rank']:.1f}  "
            f"(gate: > 90)  p = {c2['p_value']:.4f}  shuffles={c2['n']}")

    add("\n-- BY YEAR --")
    add(by_year(df).to_string(index=False))

    add("\n-- BY DIRECTION --")
    add(by_direction(df).to_string(index=False))

    d10 = by_ib_decile(df)
    if len(d10):
        add("\n-- BY IB-RANGE DECILE (diagnosis, not a filter) --")
        add(d10.to_string(index=False))

    add("\n-- COVID SPLIT --")
    for flag, label in ((False, "excluding 2020-02-15..04-30"), (True, "COVID window only")):
        g = df[df["covid_flag"] == flag]
        if len(g):
            add(summary_line(label, metrics(g, s_all=len(g))))

    if "grid" in extras:
        add("\n-- 16-CONFIG SENSITIVITY GRID (never a best case) --")
        add(extras["grid"].to_string(index=False))
        pos = int((extras["grid"]["exp_per_session"] > 0).sum())
        add(f"\ngrid_robustness = {pos}/16 positive")
        if pos == 0:
            add("  -> NO CONFIGURATION IS POSITIVE. Not a spike -- a clean, uniform fail.")
        elif pos <= 4:
            add("  -> SPIKE BAND. A narrow spike is evidence AGAINST P0 (spec sec g.0.1).")
        elif pos >= 13:
            add("  -> robust to parameter choice.")
        else:
            add("  -> mixed. Report honestly.")

    text = "\n".join(lines)
    (OUT / f"step1_{cfg.label}.txt").write_text(text, encoding="utf-8")
    df.to_parquet(OUT / f"step1_{cfg.label}_sessions.parquet")
    return text
