# IVB — Initial Balance + Volume profile + Orderflow

Rules-based intraday research on NQ. Specification first, code second.

- **`docs/IVB-SPEC.md`** — the rulebook. Every rule, parameter, default and gate.
- **`docs/RESEARCH-PLAN.md`** — step order, controls, kill criteria, data requirements.

Nothing here is validated. The whole point of Step 1 is to find out whether the
directional base exists at all.

---

## Setup

```powershell
python -m pip install -r requirements.txt
$env:DATABENTO_API_KEY = 'db-...'
```

## Run order

```powershell
# 1. Download NQ 1-minute bars (costs money; prints an estimate and asks first)
python scripts/01_download.py 2015-01-01 2026-09-01
$env:IVB_CONFIRM_SPEND = 'yes'      # only after reviewing the printed cost
python scripts/01_download.py 2015-01-01 2026-09-01

# 2. VERIFY THE TIMESTAMP CONVENTION. Do this before anything else.
python scripts/00_verify_timestamps.py data/raw/nq_ohlcv1m_2015-01-01_2026-09-01.parquet

# 3. Build the roll calendar and seal the partitions (once, never again)
python scripts/02_build_rolls.py data/raw/nq_ohlcv1m_2015-01-01_2026-09-01.parquet

# 4. Run Step 1: baseline, four controls, kill criteria
python scripts/03_run_step1.py data/raw/nq_ohlcv1m_2015-01-01_2026-09-01.parquet

# 5. Draw the charts (optional, any time after step 3)
python scripts/04_charts.py data/raw/nq_ohlcv1m_2015-01-01_2026-09-01.parquet
python scripts/04_charts.py <path> --session-date 2019-06-12   # one named session
```

Exit code 0 means the kill criteria passed. Exit code 1 means stop.

## Test without spending money

```powershell
python tests/test_backtest.py          # 9 synthetic tests of the intrabar rule
python tests/test_profile.py           # 13 hand-built volume profile tests
python tests/make_synthetic.py         # fake NQ-shaped bars, random walk
python scripts/00_verify_timestamps.py data/raw/synthetic.parquet
python scripts/02_build_rolls.py       data/raw/synthetic.parquet
python scripts/03_run_step1.py         data/raw/synthetic.parquet
python scripts/04_charts.py            # defaults to the synthetic file
```

The synthetic price process is a random walk with **no breakout edge by
construction**, so Step 1 *should* report FAIL on it. A pipeline that finds an edge
in random data has a bug. This is the plumbing check.

---

## Design rules enforced in code, not just documented

| Rule | Where | What happens |
|---|---|---|
| Timestamp convention must be verified | `ivb/timestamps.py` | Every load raises until `scripts/00` passes |
| Holdouts are sealed | `ivb/partitions.py` | Requesting one raises unless an explicit unseal token is passed |
| `partition="ALL"` | `ivb/partitions.py` | Refused — it would silently include both holdouts |
| Pessimistic intrabar sequencing | `ivb/backtest.py` | All five ambiguity cases resolve against the trade |
| Roll adjustment audit | `ivb/rolls.py` | Raises if any adjusted day moves more than 8× ATR14 |
| Databento spend | `ivb/data.py` | Refuses to download without `IVB_CONFIRM_SPEND=yes` |
| `S_all` denominator | `ivb/backtest.py` | Non-breakout days are emitted as zero-PnL rows, never dropped |

---

## Charts

`scripts/04_charts.py` draws the spec so it can be looked at. It writes PNGs to
`output/charts/` (self-ignoring; never commit them).

| File | What it shows |
|---|---|
| `01_a_textbook_long.png` | Break up, retrace to VAH, fill, TP1 |
| `01_b_no_fill.png` | Break, no retrace — Layer 1 sits out, Layer 0 keeps the move |
| `01_c_stopped_out.png` | Filled, then a 5-minute close beyond the far VA edge |
| `01_d_textbook_short.png` | The mirror of (a) |
| `02_profile_methods.png` | §b.9 — the same session under M1–M4 allocation |
| `03_funnel.png` | §h.1 — S_all → S_breakout → S_filled |
| `04_mfe_tp1.png` | MFE before stop, TP1 at the 32.5th percentile, bootstrap CI |
| `05_cell_counts.png` | §h.3 — cells per Layer 3 design against `min_obs_per_bucket` |

Charts 3, 4 and 5 come from `ivb.backtest.run_strategy`, the real Step 1 code, so
they cannot drift from the backtest.

**Charts 1 and 2 use `illustrate_layer1_trade` in `scripts/04_charts.py`.** Step 3
has not been written, so that function is a plain reading of the spec with no
controls, no walk-forward and no cost sweep. Its numbers are labels on a picture,
not results. It is deliberately kept out of `ivb/` for that reason.

## Layout

```
docs/          spec and research plan
ivb/           config, data, timestamps, rolls, sessions, profile, backtest, controls, stats, report
src/           viz.py -- chart drawing only, no research logic
scripts/       00 verify -> 01 download -> 02 rolls -> 03 step 1 -> 04 charts
tests/         synthetic intrabar tests, profile tests, fake data generator
data/          raw bars, roll_calendar.csv, partitions.json, timestamp_convention.json
output/        step 1 reports; charts/ holds the PNGs
```

## Status

| Step | State |
|---|---|
| 1 — Baseline + controls | **Code complete, tested on synthetic data. Awaiting real bars.** |
| 2 — Protection level (conditional MFE) | Not started |
| 3 — Layer 1 (profile) | Not started; gated on the §b.9 sensitivity test |
| 4 — Layer 2 (order flow) | **Blocked** — needs tick data with aggressor side |
