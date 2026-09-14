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
python tests/test_exits.py             # 17 exit-taxonomy tests (sec c / c.1)
python tests/test_controls.py          # 33 control tests (sec b.2 / b.9 / b.10 / b.11 / h.1)
python tests/make_synthetic.py both    # BOTH synthetic files
python scripts/00_verify_timestamps.py data/raw/synthetic.parquet
python scripts/02_build_rolls.py       data/raw/synthetic.parquet
python scripts/03_run_step1.py         data/raw/synthetic.parquet
python scripts/04_charts.py            # defaults to the synthetic file
python scripts/04_charts.py data/raw/synthetic_structured.parquet --outdir output/charts_structured
```

Expect `9/9`, `13/13`, `17/17`, `33/33`.

### Two synthetic files, because a gate that can only fail has never been tested

```
data/raw/synthetic.parquet              NEGATIVE control  (structure="random_walk")
data/raw/synthetic_structured.parquet   POSITIVE control  (structure="anchored_volume")
```

The **negative control** is a driftless random walk whose bar volume is drawn
independently of price. It has **no breakout edge by construction**, so Step 1
*should* report FAIL on it — a pipeline that finds an edge in random data has a bug.
Because volume carries no price information, the §b.9 profile gate **must** trip on
it. It does: `MATERIAL`, `n_breakout = 604`.

The **positive control** puts a real POC in the IB window — price mean-reverts around
a slowly drifting anchor and volume concentrates near it — so §b.9 **must not** trip.
It does not: `not material`, `n_breakout = 606`. Before this file existed, §b.9 had
only ever been run on data where it was forced to trip, so its pass branch had never
executed and `MATERIAL` was the only answer it could give.

Neither verdict is admissible as a finding about NQ. §b.9 is **decided on real bars
only**. The controls establish that the gate can answer in both directions, which is
what makes a real-data verdict mean something.

### The positive control is QUARANTINED (§b.11)

Its generator was **tuned until §b.9 returned `not material`**, so it was selected to
produce an outcome — and every other statistic in it was selected alongside that
verdict, as a side effect, without anyone deciding to select it. So:

> The positive control may source **exactly one thing**: proof that the §b.9 gate's
> pass branch executes. Never a fill rate, an exit mix, a `close_invalidation`
> frequency, a funnel count, an MFE quantile, or PnL.

Enforced in `ivb/provenance.py`, not in a paragraph: `scripts/03_run_step1.py`
refuses to run on it, `ivb/report.py` re-checks at the artifact writer, and
`scripts/04_charts.py` prints `[QUARANTINED -- positive control]` in place of every
withheld figure and **does not draw charts 3, 4 and 5 at all** (2 charts instead of
8). The negative control is *not* quarantined — it was never tuned to a verdict —
but its numbers are still synthetic and still not findings about NQ.

### Bin width is RELATIVE (§b.2), pre-registered blind

`bin_width` = median 1-minute bar range over that session's IB window, rounded to the
nearest tick, floored at 1 tick. A width fixed in **points** is a different fraction
of a bar in 2015 (NQ ~4,200) than in 2026 (several times that), so the §b.9 verdict
would become a function of the calendar. Bin width is also the lever that decides
whether §b.9 passes, so it was fixed **before any real bar was loaded**.

Stated weakness, registered in advance: the rule makes the median bar span ~1 bin
*by construction*, which is exactly the condition that forces the four allocation
methods to agree. So `bin_width_mult` ∈ {0.5, 1.0, 2.0} is reported next to every
verdict, and a `not material` at 1.0 alone is weak evidence.

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
| Exit taxonomy is a closed enum | `ivb/exits.py` | `validate` raises on any string outside `{tp1, close_invalidation, hard_stop, time_stop}` |
| `close_invalidation` never absorbs a hard stop | `ivb/exits.py` | An invalidation exit at or through the hard stop is reclassified as `hard_stop` (§c.1 dominance) |
| Hit rate is not a Layer 3 result | §h.5 + `src/viz.py` | The MFE chart prints the rate labelled **by construction**; expectancy net of costs is the only admissible metric |

---

## Charts

`scripts/04_charts.py` draws the spec so it can be looked at. It writes PNGs to
`output/charts/` (self-ignoring; never commit them).

| File | What it shows |
|---|---|
| `01_a_textbook_long.png` | Break up, retrace to VAH, fill, TP1 |
| `01_b_no_fill.png` | Break, no retrace — Layer 1 sits out, Layer 0 keeps the move |
| `01_c_stopped_out.png` | Filled, then a 5-minute close beyond the far VA edge (`close_invalidation`) |
| `01_d_textbook_short.png` | The mirror of (a) |
| `02_profile_methods.png` | §b.9 — one session under M1–M4, plus the full-sample gate (p50/p90/max of `d_risk`, `d_fill_rate`) |
| `03_funnel.png` | §h.1 — S_all → S_ib_broke → S_breakout → S_filled, exit-reason frequencies, touch-only fill rate |
| `04_mfe_tp1.png` | MFE before stop, TP1 at the 32.5th percentile, bootstrap CI |
| `05_cell_counts.png` | §h.3 — cells per Layer 3 design against `min_obs_per_bucket` |

Charts 3, 4 and 5 come from `ivb.backtest.run_strategy`, the real Step 1 code, so
they cannot drift from the backtest.

`scripts/04_charts.py` also prints four diagnostics to the console that are not
plotted: the Layer 1 exit-reason frequencies; the §b.10 invalidation window; the
touch-only fill fraction against the 30% rule (§b.7); and the §b.9 gate computed
over the whole partition. On either synthetic file the §b.9 verdict is **not
admissible** and the script says so, with different text for each control.

The **§b.10 window** is `|VAL - hard_stop|` — the only band in which the
close-beyond-VAL rule can fire, since below the hard stop the resting stop has
already filled. It is `p10 = p50 = p90 = 8.0` ticks, a constant equal to
`hard_stop_ticks`, and it is printed on every run so a number that is constant *by
construction* is shown to be constant rather than assumed. Combined with the fact
that the close rule cannot shrink `risk_R` at all, and that it fires on only **5.6%**
of exits on the negative control, **what remains of Layer 1 is the entry price
alone** (§b.10). (The positive control's firing rate used to be quoted here too; it
is withheld under §b.11.)

**The coupling (§b.10).** `risk_R = |entry − hard_stop| = (VAH − VAL) +
hard_stop_ticks`, exactly, on both sides — verified to 0.0 points over 240 profiles.
So `risk_R` *is* the value-area width plus a constant, and §b.9's `d_risk` is the
instability of that same width. **The hard stop adds a constant and therefore damps
nothing**: the profile's instability passes straight through into `risk_R`, into TP1
at 2R, and into every R multiple. On the negative control `hard_stop_ticks` is 18% of
`risk_R` and the profile is the other 82%. `hard_stop_ticks = 8` is a **free
parameter with no justification** — it is swept over {4, 8, 12, 16, 20} and reported,
never tuned.

**Chart 3 has four bars**, not three: `S_all -> S_ib_broke -> S_breakout ->
S_filled`. `S_ib_broke` is the physical event with the §f no-trade filters ignored —
the denominator §b.9 uses. `S_breakout` is what `run_strategy` actually traded. On
the negative control they are 604 and 581; the 23 lost sessions are all
`min_ib_range_atr`, named on the chart, and the reconciliation is asserted rather
than eyeballed.

**Charts 1 and 2 use `illustrate_layer1_trade` in `scripts/04_charts.py`.** Step 3
has not been written, so that function is a plain reading of the spec with no
controls, no walk-forward and no cost sweep. Its numbers are labels on a picture,
not results. It is deliberately kept out of `ivb/` for that reason.

## Layout

```
docs/          spec and research plan
ivb/           config, data, timestamps, rolls, sessions, profile, exits, backtest, controls, stats, report
src/           viz.py -- chart drawing only, no research logic
scripts/       00 verify -> 01 download -> 02 rolls -> 03 step 1 -> 04 charts
tests/         intrabar, profile, exit-taxonomy and control tests; the two-mode fake data generator
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
