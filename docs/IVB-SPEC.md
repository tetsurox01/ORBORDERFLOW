# IVB Strategy Specification v0.1

Instrument **NQ / MNQ** · Session **09:30–11:30 ET** · Research stack **Python + pandas**
Data on hand: **1-minute OHLCV, no tick data**

Status: pre-registration document. Nothing here is validated. Every value marked
`DEFAULT` is a starting point chosen for plausibility, not for performance.

---

## 0. Conventions (fix these before any code)

| Item | Rule |
|---|---|
| Timezone | All timestamps converted to `America/New_York`, DST-aware. No naive UTC offsets. |
| Bar stamping | A bar labelled `09:30` covers `[09:30:00, 09:31:00)`. Stated explicitly because an off-by-one here silently leaks the future. |
| Tick size | NQ = 0.25 index points. 1 point = $20 (NQ) / $2 (MNQ). |
| Session days | RTH only. Exclude exchange holidays and early closes from the primary sample; keep them in a separate bucket. |
| Contract | **Two series are maintained — see §0.1.** Raw front-month for everything intraday; a separately built adjusted continuous series for cross-session features. Do not let this be decided implicitly in code. |
| Costs | Applied to every trade: commission `DEFAULT 0.85 $/side/contract` plus slippage `DEFAULT 1 tick per side` on stop/market orders, `0 ticks` on limit fills — but limit fills carry a fill-probability assumption, see §b.7. |
| Price rounding | Every computed level rounded to the nearest tick before use. A level at 20451.13 is not tradeable. |

---

## 0.2 Data source, sample partitions, instrument

### 0.2.1 Source

```
vendor    Databento
dataset   GLBX.MDP3
schema    ohlcv-1m                      (Step 4 later uses `trades`, same pipeline)
symbols   NQ.FUT, stype_in=parent       INDIVIDUAL CONTRACTS, never a pre-built
                                        continuous series
```

Individual contracts are mandatory: the §0.1.1 roll calendar is computed from
per-contract RTH volume, which a vendor-built continuous series does not expose.

#### Pricing: NEVER extrapolate a cost between schemas, in either direction

**Observed on this account: `ohlcv-1m` billed at roughly `$66 / GB`, not the
`$0.50 / GB` headline rate** — a factor of ~130. This is not an error and not a
surcharge. Databento prices an aggregated schema against the **underlying message
volume it was built from**, not against the bytes delivered. A 1-minute bar is a
heavy compression of the trades and quotes underneath it, so the delivered file is
small and the thing being paid for is not.

The binding consequence:

> **A bar cost predicts nothing about a tick cost, and a tick cost predicts nothing
> about a bar cost.** Do not reason "ticks are ~N× more data, so ~N× the price";
> do not reason from `$/GB` at all across schemas. The direction of the error is not
> even fixed — `trades` is raw, so it may well be *cheaper* per gigabyte than the
> aggregate built from it, which is the opposite of the intuition.

The only admissible number for any pull is the one `metadata.get_cost` returns for
that **exact** dataset, schema, symbology and date window. Both `get_cost` and
`get_billable_size` are free metadata calls, so there is never a reason to guess.

`scripts/01b_price_ticks.py` prices the Step 4 `trades` pull on this basis. It is
**estimate-only by construction** — it contains no `timeseries` request and no
`IVB_CONFIRM_SPEND` branch at all, so it cannot spend money even if run wrongly.
Acquiring tick data inside an expiring credit window is an **acquisition** decision;
it is independent of the §g.1 research gates and grants Layer 2 no standing
whatsoever. Cheap data is not evidence.

### 0.2.2 FIRST TASK — verify the bar timestamp convention empirically

**Do not assume §0's `[09:30:00, 09:31:00)` stamping is correct.** Databento
`ohlcv-1m` timestamps must be verified against observed behaviour before any other
code runs.

```
Test: on 20 randomly chosen non-holiday sessions, locate the RTH open volume spike.
      The cash open is 09:30:00 ET. The first RTH minute carries a volume far above
      its neighbours.

  If the spike sits on the bar stamped 09:30  -> OPEN-stamped, §0 is correct.
  If it sits on the bar stamped 09:31         -> CLOSE-stamped, EVERYTHING
                                                 shifts by one minute.

Second check: confirm there is no bar stamped 16:00 carrying a full minute of
      volume (RTH ends 16:00:00). A close-stamped feed puts the last minute at
      16:00; an open-stamped feed puts it at 15:59.

Third check: assert the count of RTH bars per session == 390 for a full session.
```

The result is written to `data/timestamp_convention.json` and asserted on every
subsequent load. **A one-minute error here silently leaks the future into the IB
and would invalidate every result in this project.** It is the single highest-value
15 minutes of work in the whole plan.

### 0.2.3 Sample partitions — three, fixed now

```
BACKWARD_HOLDOUT   2010-07-01 .. 2014-12-31     SEALED
DEVELOPMENT        2015-01-01 .. ~80% point     all of Steps 1-5 happen here
FORWARD_HOLDOUT    ~80% point .. present        SEALED
```

#### Why the backward holdout starts in JULY 2010, not January

Not a choice about regimes, and not a preference. Two separate facts, recorded
together so the partition is never mistaken for a judgement call:

```
2010-06-06    GLBX.MDP3 dataset coverage begins.
              Databento has NO data before this date. 2010-01-01 was never
              available to ask for. This is a vendor boundary, not a decision.

2010-07-01    REGISTERED PULL START.
              The first clean month boundary at or after coverage begins.
              Chosen so the sec (i) monthly block bootstrap gets whole blocks
              at BOTH ends of the sample, the same reason the end is 2026-08-31.
```

So the partition is labelled "2010–2014" in prose for brevity, and it is really
**2010-07-01 → 2014-12-31**: roughly 4.5 years, not 5. The ~24 sessions of June
2010 that *do* exist are deliberately not pulled — a partial month is worth less
than a clean bootstrap block, and the holdout is a regime check, not a
sample-size exercise.

Nothing downstream moves. `DEV_START` is hardcoded at `2015-01-01` in
`ivb/partitions.py` and the 80% split is computed over sessions ≥ 2015 only, so
the start date of the backward holdout cannot shift `DEVELOPMENT` or
`FORWARD_HOLDOUT` by a single session.

The 80% point is computed by **session count**, not calendar date, over the
2015-to-present sample, and written once to `data/partitions.json`. On a
2015→2026 sample it lands near **2024-05**.

| Partition | Approx. sessions | Purpose |
|---|---|---|
| `BACKWARD_HOLDOUT` 2010-07-01 → 2014-12-31 | ~1,130 | Second out-of-sample check. Different regime (post-GFC recovery, low vol, pre-2018 volmageddon). A strategy that works 2015+ but fails 2010–2014 is regime-dependent — a finding, not a disqualification, but it must be stated. |
| `DEVELOPMENT` 2015 → ~2024-05 | ~2,345 | Steps 1–5. Walk-forward validation happens **entirely inside this partition** (see §g.1.5). |
| `FORWARD_HOLDOUT` ~2024-05 → present | ~585 | Final check, opened once. |

**Both holdouts may be opened exactly once, together, at the end.** Opening either
one early destroys its value and there is no way to restore it.

### 0.2.4 COVID handling

```
covid_flag = True for sessions in 2020-02-15 .. 2020-04-30
exclude    DEFAULT False    # keep them, flagged
```

Kept in the primary sample and flagged. Every headline result is reported **with
and without** the flagged window. NQ realised volatility in that period was several
times normal, so it can dominate a points-based expectancy while contributing ~50
sessions out of ~2,345. If the edge lives there, that is the finding.

### 0.2.5 Instrument — NQ for measurement, MNQ for judgement

```
levels_instrument  = NQ      # data, IB, volume profile, all price levels
cost_models        = run BOTH, report BOTH:
                       NQ  : 1 pt = $20, tick = $5.00
                       MNQ : 1 pt = $2,  tick = $0.50
                     commission DEFAULT 0.85 $/side/contract for both
                     (MNQ commissions are often lower in practice — if your
                      broker quotes less, change the parameter, do not assume it)
```

All levels come from **NQ**. MNQ is the same contract at 1/10 size; its own bars are
thinner and would produce a noisier volume profile for no benefit.

**Kill criteria are judged on MNQ economics.** R-multiples are identical across the
two; only dollar expectancy and cost drag differ:

| | NQ | MNQ |
|---|---|---|
| Commission, round trip | $1.70 = **0.085 pt** | $1.70 = **0.85 pt** |
| Slippage, 2 ticks round trip | $10.00 = 0.50 pt | $1.00 = 0.50 pt |
| **Total cost drag** | **0.585 pt** | **1.35 pt** |
| Ratio | 1.0x | **2.3x** |

The 10x factor applies to the **commission component alone**. Slippage scales with
contract size and therefore cancels when expressed in points. Total drag is 2.3x
heavier on MNQ, which is still large enough to change the verdict.

MNQ is chosen as the judge because it is the stricter test and the realistic
starting size. **If the strategy passes on NQ but fails on MNQ, that is a position-
sizing result, not an edge result**, and it must be reported in exactly those words:
*"the edge exists but does not survive micro-contract commission drag at 1
contract."*

---

## 0.1 Futures continuation — explicit, not implicit

### 0.1.1 Roll rule

```
roll_criterion  = volume crossover
                  roll when the next quarterly contract's RTH volume exceeds the
                  current front month's RTH volume for 2 CONSECUTIVE sessions
roll_effective  = the session AFTER the second confirming session
                  (never intra-session; a session is never split across contracts)
contracts       = NQ quarterly cycle H, M, U, Z (Mar, Jun, Sep, Dec)
tiebreak        = if volume is exactly equal, use open interest crossover
fallback        = if the data vendor supplies no volume for the back month,
                  roll on a fixed calendar rule: the 8th calendar day of the
                  contract month. Log which rule was used per roll.
```

Roll dates are computed **once**, written to `data/roll_calendar.csv`, and version
controlled. They are never recomputed inside a backtest. A backtest that derives its
own roll dates on the fly is unreproducible.

### 0.1.2 Two series, different adjustment

**Series A — `intraday_raw`: front-month, UNADJUSTED.**
Used for: IB construction, breakout levels, volume profile, entry, stop, target,
MFE, MAE, and all PnL. Every one of these is a distance measured **within a single
session on a single contract**, so back-adjustment would change nothing and can
only introduce artefacts. Correct to leave raw.

**Series B — `daily_adjusted`: continuous, RATIO-adjusted (Panama-ratio), daily.**
Used for: `ATR14`, `gap_atr`, `prior_day_type`, and the 20/60-session rolling
medians (`ib_range_rel`, `ib_vol_rel`).

### 0.1.3 The bug this prevents

These features **cross session boundaries**:

| Feature | Crosses the roll? | Consequence if raw front-month is used |
|---|---|---|
| `gap_atr` | Yes — uses prior RTH close | On roll day, the "gap" is the calendar spread between two contracts, not a market gap. On NQ this can be tens of points of pure artefact. |
| `ATR14` | Yes — 14-day window | One roll inside the window injects a spread-sized false range into the ATR. |
| `prior_day_type` | Yes | Reads the wrong contract's session. |
| `ib_range_rel`, `ib_vol_rel` | Yes — 60/20-session medians | Volume is *structurally* lower in a back month before the roll, biasing `ib_vol_rel`. |

My earlier claim that "roll adjustment is never needed" was correct for the trade
mechanics and **wrong for the features**. Ratio adjustment on Series B fixes it.

### 0.1.4 Roll-day handling and the audit

```
roll_day_flag   = True on roll_effective and the session before it
exclude_rolls   DEFAULT False   # keep them, but flag them
```

Keep roll days in the sample but tag them. Then report the primary result **with
and without** roll days. If the two differ materially, roll handling is doing work
it should not be doing, and that is a finding.

**Mandatory audit before any backtest:** plot Series B's daily returns and assert
that no single-day return exceeds `8 * ATR14`. A spike at a roll date means the
adjustment is broken. Log the assertion result.

---

## (a) Layer 0 — Initial Balance definition

### a.1 IB construction

```
IB_window  = N minutes, N in {15, 30, 60}         DEFAULT N = 30
IB_bars    = all 1-min bars with open_time in [09:30, 09:30 + N)
IB_high    = max(high) over IB_bars
IB_low     = min(low)  over IB_bars
IB_range   = IB_high - IB_low
IB_mid     = (IB_high + IB_low) / 2
IB_close_t = 09:30 + N        # first moment a breakout may be evaluated
```

No breakout may be evaluated on any bar with `open_time < IB_close_t`. The bar at
`IB_close_t` is the first eligible bar.

### a.2 Breakout trigger — two variants, one pre-registered

**Trigger B (`close_through`) — PRE-REGISTERED PRIMARY**

```
LONG  signal on first bar t >= IB_close_t with  close(t) > IB_high + buffer
SHORT signal on first bar t >= IB_close_t with  close(t) < IB_low  - buffer
entry_price = open(t+1)          # next-bar open, market order
buffer      DEFAULT 1 tick (0.25 pt)
```

**Trigger A (`trade_through`) — SENSITIVITY ONLY**

```
LONG  on first bar with high(t) >= IB_high + buffer, entry at IB_high + buffer
SHORT on first bar with low(t)  <= IB_low  - buffer, entry at IB_low  - buffer
```

Trigger A assumes a resting stop order fills at the trigger price. That is
optimistic on a fast break and is exactly the kind of fill assumption that
manufactures fake edge. Report it; do not build on it.

### a.3 One-shot rule

- Only the **first** IB break of the session generates a Layer 0 trade.
- If the first break fails and the opposite side breaks later, that second break is
  **not traded** in the baseline. Log `reversal_day = True` and study it separately.
  It is the natural input to the inverse model (§e.5).
- Maximum one baseline trade per session.

### a.4 Exits (baseline only — Layer 3 replaces the target later)

```
stop_loss   = opposite IB extreme -/+ buffer      # variant S1
            | entry -/+ (k * IB_range)            # variant S2, k DEFAULT 0.5
take_profit = entry +/- (R_mult * risk),  R_mult in {1.0, 1.5, 2.0, 3.0}
time_stop   = flat at 11:30 ET, at market, no exceptions
```

### a.5 Intrabar sequencing — the pessimistic rule, all cases

A 1-minute bar reports only O, H, L, C. The **order** in which H and L were visited
is not recoverable. Whenever a single bar contains two events that would resolve
differently depending on their sequence, the ambiguity is resolved **against the
trade, every time, without exception.**

#### The five cases

| # | Case | Bar contains | Pessimistic resolution |
|---|---|---|---|
| 1 | **Stop vs target** | both `stop` and `target` | **Stop fills first.** Trade is a loss. |
| 2 | **Entry vs stop, same bar** | market entry, then `stop` inside the same bar | **Stop fills.** Immediate loss, full risk. |
| 3 | **Limit entry vs stop, same bar** (Layer 1) | limit entry price and `stop` | **Both fill, entry then stop.** Worst case: you get filled and stopped in one minute. Never "the limit was missed, so no loss". |
| 4 | **Limit entry vs target, same bar** | limit entry and `target` | **Entry fills, target does NOT.** The favourable half of the bar is assumed to have happened *before* the entry fill. |
| 5 | **Invalidation close vs hard stop** | `TF_inval` close is beyond VAL *and* the hard stop was touched in that window | **Hard stop fills first**, at the hard stop price plus slippage. The worse of the two exits always wins. |

#### MFE and MAE measurement under the same rule

```
MFE on the entry bar     = measured from entry_price, using that bar's extreme
                           ONLY IF the stop was not also touched in that bar.
                           If it was, that bar CONTRIBUTES 0 (case 2 applies).
MAE on any bar           = always the full adverse extreme of the bar.
MFE on a stop-out bar    = that bar CONTRIBUTES 0. The adverse extreme is assumed
                           to have come first.
```

**Clarification — "contributes 0" is per bar, not a reset.** MFE is the running
maximum over all bars from entry. A stop-out bar adds nothing to it, but excursion
the trade *genuinely achieved on earlier bars* is retained.

```
Entry at 100, stop 95, target 110.
  bar 1:  H=103, L=99.5   -> +3 genuinely achieved, stop untouched
  bar 2:  H=110, L=90     -> spans stop AND target -> pessimistic: stop fills

  MFE = 3.0   (bar 2 contributes 0; bar 1's real +3 is kept)
  NOT 0.0     (that would understate what the trade actually did)
  NOT 10.0    (that would credit an excursion the trader could not have taken)
```

Both wrong readings bias the Layer 3 protection level — one down, one up. This case
is covered by `tests/test_backtest.py::test_case1_retains_earlier_legitimate_excursion`.

This matters directly for Step 2: measuring MFE from a bar high on a bar that also
contained the stop would inflate the protection level with excursion the trader
could never have captured.

#### Mandatory reporting

```
ambiguous_bar_pct  = trades where ANY of cases 1-5 fired / total trades
                     reported per case, not just as a total
```

**Gate:** if `ambiguous_bar_pct` exceeds `DEFAULT 15%` of trades, the result is not
trustworthy at 1-minute resolution. The strategy is then living inside the bar, and
only tick data can resolve it. Report this number **before** the PnL, not after.

#### The optimistic counterfactual — report it, do not trade it

Also run every backtest with the sequencing rule inverted (target first, entry
without stop, favourable resolution throughout). The gap between the pessimistic
and optimistic runs is the **size of the uncertainty the data cannot resolve**. If
that gap is wider than the edge itself, there is no measurable edge at 1-minute
resolution, whatever the pessimistic run says.

### a.6 What breaks at 15 / 30 / 60 minutes — NQ specifics

These are failure modes to test, not claims.

**N = 15 (break window opens 09:45)**
- Most trades, most false breaks. The IB is measured over the single most volatile
  quarter-hour of the day, so `IB_range` is a poor estimate of the day's character.
- **Structural hazard:** US data releases at **10:00 ET** (ISM, JOLTS, Consumer
  Sentiment, Construction Spending) land *after* a 15-minute breakout is already
  entered. A clean 09:50 breakout gets reversed at 10:00 by information the model
  never saw. Test as a split: release days vs non-release days.
- A volume profile over 15 bars is very thin. POC is unstable (§b.4).

**N = 30 (break window opens 10:00) — PRE-REGISTERED PRIMARY**
- Matches the window used in the source video, so it is the fair reproduction.
- The 10:00 release now sits on the *boundary* of the IB and can distort the first
  eligible breakout bar. Test: suppress breakout triggers in 10:00–10:05 and see if
  results move.
- `IB_range` is wider, so stop-at-IB-extreme risk grows, and R-multiple targets
  become large in absolute points and less likely to be reached before 11:30.

**N = 60 (break window opens 10:30)**
- The killer is opportunity cost, and it is directly measurable. Compute
  `remaining_range_after_IB / IB_range` for each N. If that ratio collapses at
  N = 60, Layer 3 has nothing left to target and N = 60 is dead regardless of its
  hit rate.
- Only 60 minutes of tradeable time remain inside a 09:30–11:30 window, and many
  days never break after 10:30, so the sample shrinks sharply.

**Anti-sweep discipline:** N = 30 is the pre-registered primary. N = 15 and N = 60
are robustness checks. If N = 15 wins, that is a *finding to be re-tested out of
sample*, not a parameter choice. Never report "we optimised N".

---

## (b) Layer 1 — Fixed-range volume profile on the IB window

### b.1 The data limitation, stated up front — and why Layer 1 is not simply killed like Layer 2

You do **not** have volume-at-price. You have volume-per-minute-bar. Every profile
below is an *estimate* built by distributing bar volume across the bar's price
range. That is an assumption, not a measurement, and it must be flagged on every
chart and in every result table derived from it.

**Two things make this worse than it first looks:**

1. **The sample is tiny.** A 30-minute IB gives **30 bars** — 30 volume
   observations, however the bins are drawn. Under a fixed 1.0-point bin and a
   typical NQ IB that was 30–60 bins, i.e. fewer observations than bins. The §b.2
   relative rule improves the ratio (the bin scales with the bar, so the bin count
   is roughly the IB range measured in median bars) but it does not create
   observations: a POC built from 30 numbers is a weak statistic by construction,
   before any distribution assumption is applied. At `ib_minutes = 15` it is 15 bars
   and the problem roughly doubles.
2. **The assumption sits directly on the decision boundaries.** VAH is the entry
   and VAL is the stop. A distribution assumption that shifts either by a few ticks
   shifts `risk_R` — and, because `risk_R = (VAH − VAL) + hard_stop_ticks` exactly
   (§b.10), it shifts every R multiple, the stop-out rate, and the headline R:R
   claim in §c.3. The hard stop adds a constant; it damps nothing.

#### The asymmetry with Layer 2, stated explicitly

Layer 2 is killed outright while Layer 1 proceeds under test. That is not a double
standard, and here is the distinction:

| | Layer 1 (profile) | Layer 2 (order flow) |
|---|---|---|
| Required input | Which prices traded, and how much volume per minute | Which side was the **aggressor** |
| Present in 1-min OHLCV? | **Yes, both** — only the *within-bar allocation* is unknown | **No** — absent entirely, at any resolution |
| Nature of the gap | An **allocation assumption** over measured quantities | A **missing variable**, unrecoverable from bars |
| Can it be bounded? | **Yes** — run every allocation method and measure the spread | No. There is nothing to vary. |

So Layer 1 is testable *as an approximation whose error can be bounded*, and Layer 2
is not testable at all. **But that argument is only valid if the bound is actually
small.** §b.9 measures it, and §b.9 is a gate: if the boundaries move materially
across allocation methods, Layer 1 is downgraded to the same status as Layer 2 and
must wait for tick data.

#### A structural observation that must be tested, not assumed

The value area lies **inside** the IB by construction, so `VAH <= IB_high` and
`VAL >= IB_low`. Therefore the reload zone `[POC, VAH]` sits **entirely inside the
initial balance range**.

The consequence: for a long, price must break above `IB_high`, then retrace all the
way back **into** the IB to reach VAH. **Every Layer 1 trade is, by construction, a
breakout that failed to hold and re-entered the range.** That is a real and
non-obvious selection effect. Re-entry into the range is conventionally read as a
*failed* breakout, so Layer 1 may be systematically selecting the weaker breakouts.

Test directly: compare the forward MFE of breakouts that re-enter the IB against
those that do not. If re-entering breakouts have materially worse outcomes, Layer 1
is trading an adversely selected subset and the tighter stop cannot save it.

### b.2 Volume distribution method — and the bin width, which is RELATIVE

#### The bin width is a function of bar height, not a number of points

A bin width fixed in **points** is not the same object at both ends of the sample.
NQ traded ~4,200 in 2015 and several times that now, and a 1-minute bar's height
scales with the index. A bar that smeared across 3 bins in 2015 smears across 10 or
more in 2026 at the same fixed width. Two consequences, both fatal to the section
that follows:

1. **The §b.9 verdict would differ between 2015 and 2026 for a reason that has
   nothing to do with the market.** The profile would not be measuring one thing
   across the sample, so nothing measured on it would be comparable end to end.
2. **Bin width is the lever that decides whether §b.9 passes** (see the mechanism
   note in §b.9). Choosing it after looking at real bars is therefore selection on
   the outcome of a gate — the exact failure the gate exists to prevent.

So it is pre-registered here, **blind**, before any real bar was loaded:

```
PRE-REGISTERED PRIMARY (sec g.1)

    bin_width = median 1-minute bar range over THIS session's IB window,
                rounded to the nearest tick, floored at 1 tick

    bin_width_rule   = median_ib_bar_range
    bin_width_mult   = 1.0          PRIMARY
    bin_width_floor  = 1 tick
    rounding         = half-up, explicit (numpy rounds halves to even, which would
                       make the width depend on the parity of the tick count)
```

**Per session, not per sample.** A single sample-wide median drifts across the
sample exactly the way a fixed point value does; only a per-session width is
scale-free at both ends. It is computed from IB bars alone, so it is known at IB
close and carries **no lookahead**.

**Every other bin width is a labelled sensitivity, never the primary** (§g.0.1). The
reported sensitivity axis is the multiplier:

```
bin_width_mult in {0.5, 1.0, 2.0}      0.5 and 2.0 are REPORTED, never selected
bin_size_pts = 1.0                     the old fixed width, kept only as the
                                       "what it used to be" comparison row
```

For the **§b.9 gate specifically** the three multipliers are not read independently:
the pre-registered resolution rule in §b.9 requires `not material` at all three for a
pass, and any single `MATERIAL` resolves the whole verdict to `MATERIAL`. That is a
veto, not a selection — the primary is still never moved onto a neighbouring row.

#### The weakness this rule has, stated in advance

§b.9 records that the four allocation methods agree when an IB bar spans about
**one** bin. This rule sets the bin width **to** the median bar range, so the median
bar spans ~1 bin **by construction**. It therefore pushes the §b.9 gate toward
`not material` mechanically.

That is registered here rather than discovered afterwards, and it is the price of
scale-invariance — the alternative (a fixed point width) is worse, because it makes
the gate's answer a function of the calendar. The defence is the multiplier
sensitivity above:

> **A `not material` verdict at `mult = 1.0` alone is weak evidence.** Read the 0.5×
> and 2.0× rows next to it. A Layer 1 that is stable only at the multiplier which
> forces the methods to agree is stable **by construction, not by evidence**, and
> must be reported that way. The primary is still never changed on the strength of
> a sensitivity row — that would be selection.

**Measured effect on the two controls** (synthetic; see §b.9 and §b.11). Both
verdicts survived the switch from the fixed 1.0-point bin to the relative rule:

```
                       fixed 1.0 pt bin        relative bin (mult 1.0)
negative control       MATERIAL, 3 of 4        MATERIAL, 3 of 4   (full sample)
                       1 of 3                  1 of 3             (300-window draw)
positive control       not material, 0 of 3    not material, 0 of 3
```

So the predicted weakening did **not** show up as a changed verdict or a changed
trip count on synthetic data — though the condition carrying the negative control's
trip on the small draw moved from `d_risk p50` to `d_risk p90`. That is reassurance
about the implementation, **not** about real bars: the construction argument above
holds regardless of what a synthetic draw happens to show, which is why the
multiplier sensitivity is mandatory rather than optional.

#### The allocation itself

```
bins       from floor(IB_low / bin_width) to ceil(IB_high / bin_width)
for each IB bar:
    span = bins overlapped by [low, high]
    each overlapped bin receives volume / len(span)      # uniform
```

`uniform` is the pre-registered method because it makes the fewest assumptions.
Two alternatives run as robustness checks only:

- `triangular` — weight peaks at `(H+L+C)/3` and decays to the extremes.
- `close_only` — all volume at the close bin. Crude and spiky; a lower bound.

If POC location moves materially between `uniform` and `triangular`, Layer 1 is
sensitive to an untestable assumption and must be downgraded.

### b.3 POC and Value Area

```
POC = bin with maximum volume
      tie-break: the tied bin closest to IB_mid; if still tied, the lower bin.

Value Area, 70% of volume, standard expansion method:
    included = {POC}; cum = vol[POC]; target = va_pct * total_vol
    while cum < target:
        up2   = volume of the next 2 bins above the current included block
        down2 = volume of the next 2 bins below
        add the larger pair to included; cum += that volume
        tie-break: take the upper pair
        if one side is exhausted, take from the other side
VAH = upper edge of the highest included bin
VAL = lower edge of the lowest included bin
va_pct   DEFAULT 0.70     range 0.60 - 0.80
```

### b.4 POC stability test — a gate, not a nice-to-have

Before Layer 1 enters any backtest, compute per session the spread of POC location
across `bin_width_mult` in {0.5, 1.0, 2.0} — i.e. across half, one and two times the
session's own median IB bar range (§b.2), **not** across fixed point widths. Report
in ticks.

If the **median spread exceeds 4 ticks (`poc_stability_gate_ticks`)**, the POC is
noise and Layer 1 is built on sand. Report this distribution **before** reporting
any Layer 1 PnL.

### b.5 TPO variant — the assumption-free control

Run a parallel profile where each bin's score is **the count of 1-minute bars whose
`[low, high]` covers that bin**. This is a minute-TPO profile and needs no volume
at all. If `POC_volume` and `POC_TPO` disagree by more than a few ticks on most
days, the volume-distribution assumption is doing the work, not the market.

### b.6 The reload zone — exact bounds

For an **upside** break (long):

```
zone_top    = VAH
zone_bottom = POC
```

For a **downside** break (short):

```
zone_top    = POC
zone_bottom = VAL
```

Degenerate case: if `VAH == POC` (or `VAL == POC`) the zone has zero width. Rule:
expand to `POC +/- min_zone_width` (`DEFAULT 2 ticks`) and flag `degenerate_zone`.

### b.7 Entry inside the zone — three variants

For a long, the retracement arrives from above, so price touches **VAH** first and
**POC** second. For a short it touches **VAL** first and **POC** second.

| Variant | Long entry | Short entry | Trade-off |
|---|---|---|---|
| **E1 (PRIMARY)** | limit at `VAH` | limit at `VAL` | highest fill rate, worst price |
| E2 | limit at `POC` | limit at `POC` | best price, lowest fill rate |
| E3 | limit at zone midpoint | limit at zone midpoint | compromise |

Fill model for limit orders on 1-minute bars: filled if `low(t) <= limit` (long).
This is **optimistic** — it assumes a front-of-queue position. Record
`touch_only_fills` (fills where the bar's low exactly equalled the limit) and
**report that fraction with every Layer 1 result**, not only on request.

#### Which fill model is PRIMARY — decided by the measured fraction, in advance

```
touch_only_fills / total_fills <= 30%   front-of-queue stays PRIMARY;
                                        require_penetration_ticks = 1 is the
                                        sensitivity check.

touch_only_fills / total_fills  > 30%   require_penetration_ticks = 1 becomes
                                        PRIMARY; front-of-queue drops to the
                                        sensitivity check.
```

The reasoning: below 30% the optimistic assumption is decorating a minority of
trades and the headline barely moves. Above 30% the strategy's results are
substantially a claim about queue position — an unmodelled, unverifiable, and
almost certainly flattering one — and the conservative model has to carry the
headline instead. The threshold is fixed here, before the fraction is known, so it
cannot be renegotiated after the fact.

Measured on the **negative control** (random walk, relative bins): **20.7% of
fills** (85 / 411). Below the threshold, so front-of-queue stays primary — but this
is random-walk data and the number must be re-measured on real NQ bars before it
decides anything.

**This switch may never be read off the positive control.** That is not a special
rule for §b.7; it is the general quarantine in **§b.11**, which this section was the
first instance of.

### b.8 Retracement time limit

```
reload_timeout   DEFAULT 30 minutes after the breakout bar    range 10 - 60
```

If the zone is not touched within `reload_timeout`, or 11:30 ET arrives first, the
setup is cancelled and logged as `no_fill`.

**`no_fill` days must be carried into the attribution as zero-PnL sessions, never
dropped.** Dropping them is the single most likely way Layer 1 produces a fake
improvement: it silently removes exactly the runaway days that Layer 0 captures.

---

### b.9 Profile method sensitivity — a GATE on Layer 1

This test runs **before** any Layer 1 PnL is computed, and its result is reported
first. It measures how far the actual trading decisions move when the untestable
allocation assumption is varied.

#### The four methods compared

```
M1  volume_uniform      volume spread evenly across the bar's [low, high]   (primary)
M2  volume_triangular   weight peaks at (H+L+C)/3, decaying to the extremes
M3  volume_close_only   all bar volume assigned to the close bin
M4  tpo_minute          bar COUNT per bin; ignores volume entirely (control)
```

#### What is measured, per session — and over the WHOLE partition

For every session in DEVELOPMENT that produces a breakout, compute `POC`, `VAH`,
`VAL` and the zone under all four methods, then record the **spread**
(max − min across methods) in ticks:

```
d_POC   = spread of POC location, ticks
d_VAH   = spread of VAH location, ticks      # the ENTRY boundary
d_VAL   = spread of VAL location, ticks      # the far VA boundary
d_zone  = spread of zone WIDTH (VAH - POC for a long), ticks
d_risk  = spread of implied risk_to_hard_stop, ticks
          = spread of (VAH - VAL), since the +/- hard_stop_ticks constant cancels
```

Report **p50, p90 and max** of each, over the whole partition. One session is an
anecdote and must never be quoted as the result of this gate. The per-session
picture (Chart 2) exists to show the *mechanism*; the distribution decides.

Also compute, for each method, the **E1 fill rate** — the fraction of breakout
sessions where that method's near VA edge is touched inside `reload_timeout` — and:

```
d_fill_rate  = max - min of the four fill rates, in percentage points
d_fill_count = max - min of the four fill COUNTS, in sessions
```

**`d_fill_count` is reported next to `d_fill_rate`, always, never instead of it.**
The rate is the gate trigger; the count is what the rate means. A spread of a few
percentage points reads as small, and then multiplies by `n_breakout` into a large
absolute swing in `S_filled` — which is the denominator of every Layer 1 per-trade
statistic there is. The worked example in §b.10 is a 51-session, 14% swing in
`S_filled` produced by a bin-width change alone, at no change in the underlying
sessions. Report `d_fill_count` as a count and as a percentage of the primary
method's own fill count.

#### "Material" defined numerically, not by eye

**The gate is keyed on `risk_R` and on the fill rate, not on stop movement.** The
earlier version of this section keyed the primary trigger on `median(d_VAL)`, on the
reasoning that "VAL is the stop". Under the tradeable exit regime it is not: the
stop is `VAL - hard_stop_ticks` (§c.1), `risk_R` is measured to that hard stop
(§c.2), and the close-beyond-VAL rule cannot shrink `risk_R` at all (§b.10). So VAL
reaches `risk_R` only through `d_risk`, which already contains it.

Keying on `d_VAL` also *misses the case that actually occurs*. The first run of this
test returned `d_VAL = 0`, `d_POC = 0`, `d_VAH = 8 ticks`: the far boundary and the
POC stood still and the **entry** moved by two points. A `d_VAL`-keyed gate scores
that as clean. It is not clean — it changes the entry price, and therefore `risk_R`,
the fill rate, and which sessions get traded at all.

```
MATERIAL if ANY of the following holds:

  p50(d_risk)   > 0.20 * median(risk_to_hard_stop)   # R multiples are assumption-driven
  p90(d_risk)   > 0.40 * median(risk_to_hard_stop)   # the tail, not just the centre
  d_fill_rate   > 10 percentage points               # a different set of trades
  p50(d_POC)    > 4 ticks                            # the §b.4 stability gate
```

#### THE MULTIPLIER RESOLUTION RULE — pre-registered BLIND

Written here **before any real number exists**, because the reason it is needed is
structural and is already known.

The §b.2 rule sets `bin_width` **to** the median IB bar range. The median bar
therefore spans ~1 bin **by construction**, and ~1 bin per bar is exactly the
condition under which M1–M4 cannot disagree (mechanism note below). The primary
multiplier sits at the position that *maximises method agreement*. A lone
`not material` at `mult = 1.0` is consistent with a stable profile and equally
consistent with the bin rule doing its job — the single row cannot separate them.

So the verdict is resolved over the whole multiplier set, not read off the primary:

```
GRID:  bin_width_mult in {0.5, 1.0, 2.0}      (1.0 = the pre-registered primary)

  MATERIAL at ANY of the three   ->   the RESOLVED §b.9 VERDICT is MATERIAL
  a PASS requires "not material" at ALL THREE

  No other combination is a pass.
```

Three points about what this rule is and is not:

1. **It is a conjunction, not a selection.** The neighbours can only ever **veto**.
   They can never rescue a primary that trips, and the primary is never moved onto a
   neighbouring row — that would be selection on the outcome (§g.0.1). `mult = 1.0`
   remains the only row that carries the pre-registration.
2. **It is deliberately asymmetric, and that is the point.** It makes a pass strictly
   harder to obtain than a `MATERIAL`, because the by-construction bias runs in
   exactly one direction: toward agreement, toward a pass. The rule removes the free
   pass that bias would otherwise hand out.
3. **The consequence of `MATERIAL` is unchanged** — it is the downgrade written below
   under "Consequence of a MATERIAL result". A resolved `MATERIAL` triggered only by
   a neighbour carries the same consequence as one triggered by the primary. There is
   no lesser grade of failure here.

The rule is committed now, run **once** on real bars, and the answer is taken as it
comes. It is never re-opened after the number is seen.

#### The gate is decided on REAL bars only

This test reads volume, so it can only be *decided* on real NQ bars. Its verdict on
any synthetic file is **not admissible**. What synthetic data is for is showing that
the gate works **in both directions**.

#### TWO CONTROLS — because a gate that can only trip has never been tested

A gate that has only ever been run on data where it *must* trip has never executed
its pass branch. `MATERIAL` would then not be evidence about Layer 1; it would be
the only answer the test is capable of producing. Both controls are therefore
required, and both are run before the gate is believed.

```
NEGATIVE CONTROL   data/raw/synthetic.parquet              (structure="random_walk")
  Bar volume is rng.integers(200, 2000) -- i.i.d. and INDEPENDENT of price. No
  volume structure exists for a profile to find, POC is a random draw, the four
  methods disagree freely.
  REQUIRED RESULT: MATERIAL. If this does NOT trip, the gate is broken.
  MEASURED under the sec b.2 RELATIVE bin width (mult 1.0):
            MATERIAL. d_risk p50 10.0 / p90 26.0 ticks, d_POC p50 11.0,
            median risk_to_hard_stop 47.0 ticks, d_fill_rate 9.4 pp,
            n_breakout 604, realised bin width p50 11.0 ticks.
            Three of four conditions trip (d_fill_rate does not).
            Bin-width sensitivity: MATERIAL at mult 0.5, 1.0 and 2.0 alike.

POSITIVE CONTROL   data/raw/synthetic_structured.parquet   (structure="anchored_volume")
  Inside the IB window only: price is AR(1) around a slowly drifting anchor, and
  bar volume is a Gaussian kernel of the bar's distance from that anchor. A real
  POC therefore exists -- price spends most of its TIME near the anchor and most of
  its VOLUME there too. After the IB the process is the same driftless random walk,
  scaled so IB_range / ATR14 stays realistic.
  REQUIRED RESULT: not material. If this trips, the gate has still never passed.
  MEASURED under the sec b.2 RELATIVE bin width (mult 1.0):
            not material. d_risk p50 0.0 / p90 8.0 ticks, d_POC p50 3.0,
            median risk_to_hard_stop 23.0 ticks, d_fill_rate 2.1 pp,
            n_breakout 606, realised bin width p50 3.0 ticks.
            All four conditions clear.
            Bin-width sensitivity: not material at mult 0.5, 1.0 and 2.0 alike.

  QUARANTINED (sec b.11). The line above is the ONLY thing this file is permitted
  to source anywhere in this project. Its fill rates, exit mix, touch-only
  fraction, funnel counts, MFE distribution and PnL are all withheld in code.
```

Both controls pass, so from this point a `MATERIAL` verdict on real bars carries
information and a `not material` verdict does too.

#### What the positive control revealed about the gate's real mechanism

The anchored generator's parameters were tuned until the verdict came out
`not material`. That is what a positive control is for. **The gate's thresholds were
not touched** — tuning those would be fitting the gate to a verdict rather than
testing it.

Tuning it exposed what `d_POC` and `d_risk` are actually driven by, and it is worth
stating because it predicts how the gate will behave on real NQ:

> **The four methods agree when an IB bar spans about ONE profile bin.**
> When a bar's `[low, high]` covers a single bin, "where inside the bar did the
> volume trade" has nowhere to disagree, and M1, M2 and M3 collapse onto each other.
> The volume-versus-time structure then aligns M4 (pure bar count) with them. Under
> the old **fixed** 1.0-point bin this showed up as a difference in absolute bar
> height: the positive control held IB bar range near 0.9 points, the negative
> control's was 2.5–3.0 points, and it tripped.

**This mechanism is why §b.2 pre-registers the bin width blind.** Bin width is the
lever that decides the verdict, so picking it after seeing real bars would be
selection on the outcome of the gate itself.

**And it is why the §b.2 rule carries a stated weakness.** Setting
`bin_width = median IB bar range` makes the median bar span ~1 bin *by
construction*, i.e. it sets the lever to the position that maximises agreement.
Two consequences, both binding:

1. The two controls no longer separate on absolute bar height — the bin scales with
   the bar — so they now separate on **volume structure alone**, which is what they
   were always meant to test. Both verdicts survived the switch (§b.2).
2. **A `not material` verdict at `mult = 1.0` is weak on its own.** It must be read
   next to the `mult` ∈ {0.5, 2.0} rows. If the primary passes and a neighbour does
   not, the pass is partly the rule's own doing and must be reported as such. The
   primary is **never** moved onto a neighbour — that is selection (§g.0.1).

The `b7` touch-only fill rate and the exit-mix are **not** comparable across the two
files: the positive control's narrow bars make a limit fill almost always a graze.
Those rates are decided on real bars only, and `scripts/04_charts.py` refuses to
read a §b.7 switch off the positive control.

`d_VAL`, `d_VAH` and `d_zone` are still **reported** — they say *where* the movement
came from, which is what gets diagnosed if the gate trips — but they are not
triggers on their own.

The `d_risk` threshold is the important one. If `risk_R` is 20% assumption, then the
headline R:R claim in §c.3 is 20% assumption, and the "1:2 to 1:2.5" number is not a
measurement.

#### Consequence of a MATERIAL result — written in advance

> If the test comes back MATERIAL, Layer 1 is **downgraded to the same status as
> Layer 2**: not testable with current data, pending tick data. Its results may be
> reported only as clearly labelled `ASSUMPTION-SENSITIVE`, and Layer 1 may not be
> used as the base for Layer 2 attribution.

This consequence is fixed **now**, before the number is seen, so the threshold
cannot be renegotiated after the fact.

#### Secondary: PnL under all four methods

If the boundary test passes, still run the full Layer 1 backtest under M1–M4 and
report four PnL columns side by side. If M1 is profitable and M2/M3 are not, the
edge belongs to the allocation assumption, not to the market. M4 (TPO) is the
strongest control, since it uses no volume at all.

---

### b.10 Where Layer 1's advantage actually comes from — the ENTRY, not the stop

The source frames Layer 1's benefit as a **tighter stop**: trade from the value
area instead of the range extreme, so the distance to invalidation shrinks and the
same target becomes 1:2 or 1:2.5 instead of 1:1. That framing does not survive
contact with §c.1 and §c.2, and the correction matters because it changes what has
to be measured.

**Under the tradeable exit regime, the close-beyond-VAL rule cannot reduce
`risk_R`. Not by one tick.** §c.1 requires a hard stop behind the far VA boundary
and §c.2 requires `risk_R` to be measured to *the stop actually used*. So:

```
risk_R = |entry - hard_stop| = |entry - far_VA_edge| + hard_stop_ticks
```

is fixed the moment the limit fills. The close-based rule fires **later, or not at
all**, and its only effect is to realise a loss **smaller** than the full `risk_R`
by exiting early. It shortens losses; it does not shrink the denominator. Any
statement of the form "the VA stop gives us 1:2" is quoting a distance the strategy
does not actually risk.

**The real reduction is in the entry price.** Worked from a live example:

```
                         Layer 0                 Layer 1 (E1)
entry             IB_high + buffer, next        VAH, resting limit
                  bar open      = 4719.25       = 4714.00
stop              opposite IB extreme           VAL - 8 ticks
                                = 4705.25                = 4705.00
risk_R                         ~14.00 pt                  9.00 pt
```

Both stops sit in essentially the same place — 4705.25 against 4705.00, one tick
apart. The entire ~5-point risk reduction is the entry: **4714.00 instead of
4719.25.** Layer 1 is a *better-price* rule wearing a *tighter-stop* costume.

#### And the close rule barely fires, because it has almost no room to

`risk_R` is not the only thing the close rule fails to move. Measure the band it can
fire in at all. For a long, the rule needs a `TF_inval` close **below `VAL`**, but
at `VAL - hard_stop_ticks` the resting stop has already filled. So the rule lives
entirely inside:

```
inval_window = |far_VA_edge - hard_stop| = hard_stop_ticks
```

That is a **constant**, not a distribution. Measured over every fill on both
synthetic files: `p10 = p50 = p90 = min = max = 8.0 ticks`, exactly
`hard_stop_ticks`. It does not vary with the profile, the session, the value-area
width, or anything a market does. It is reported anyway, on every Layer 1 run,
because a number that is constant *by construction* should be shown to be constant
rather than assumed to be.

Against a median `risk_to_hard_stop` of 44 ticks on the negative control, that
window is ~18% of the distance to the stop, and it only fires if a 5-minute close
lands inside it without the low having touched the stop first. Observed firing rate:

```
close_invalidation share of all Layer 1 exits
  negative control (random walk)       23 / 411   =  5.6%
  positive control (structured vol)    WITHHELD -- sec b.11 quarantine
```

The positive control's rate was previously quoted here. It has been removed: that
file's generator was tuned until §b.9 returned `not material`, so every statistic in
it was selected alongside that verdict, and an exit mix is not the one thing it is
allowed to source (§b.11).

#### THE COUPLING: `risk_R` **is** the value area width

The two rules compose into an identity, and it is the most important sentence in
this section. For a long, entry is `VAH` and the hard stop is `VAL - hard_stop_ticks`;
for a short, entry is `VAL` and the hard stop is `VAH + hard_stop_ticks`. Either way:

```
risk_R = |entry - hard_stop| = (VAH - VAL) + hard_stop_ticks
```

Verified exactly, both directions, over 240 profiles drawn from both generators:
worst deviation 0.0 points (`tests/test_controls.py`).

So `risk_R` is the **value-area width plus a constant**, and every quantity built on
it is a linear function of that width:

```
risk_R  = VA_width + hard_stop_ticks
TP1     = entry +/- 2 * risk_R          = entry +/- 2 * (VA_width + hard_stop_ticks)
every R multiple, the stop-out rate, and the sec c.3 headline claim
```

`VA_width` is **exactly** the quantity §b.9 measures the instability of. `d_risk` is
defined there as the spread of `(VAH - VAL)` across the four allocation methods,
"since the +/- `hard_stop_ticks` constant cancels". It cancels in the *spread* — and
that is the point:

> **The hard stop does NOT insulate the strategy from the profile's instability.**
> It adds a constant. A constant shifts the level and cannot damp the spread by a
> single tick. Whatever §b.9 reports as `d_risk` passes straight through, undiluted
> in absolute terms, into `risk_R`, into TP1 at 2R, into every R multiple, and into
> the 1:2 / 1:2.5 claim §c.3 exists to test.
>
> Measured on the negative control: median `VA_width` = 36 ticks, median `risk_R` =
> 44 ticks, so `hard_stop_ticks` is **18%** of `risk_R` and the profile is the other
> **82%**. If §b.9 returns `MATERIAL` on real bars, Layer 1's risk denominator is
> assumption-driven and there is no part of the exit rule that repairs it.

#### WORKED EXAMPLE — the profile also moves the TRADE COUNT, not only `risk_R`

The coupling above is about the *size* of `risk_R`. There is a second channel, and it
is the one that is easy to miss because nothing in the identity shows it: the profile
decides **which sessions become trades at all**. The entry is a limit at the near VA
edge. Move the edge and a session that was filled is no longer filled, or the reverse.
`S_filled` is not a property of the market — it is a property of the assumption.

This was observed directly, on the **same file and the same sessions**, when the
§b.2 bin width changed from a fixed 1.0 point to the relative rule:

```
                                fixed 1.0-pt bin      relative bin (mult 1.0)
  S_sessions                          624                      624
  S_ib_broke                          604                      604
  S_passed_filters                    581                      581
  S_filled                            360                      411      <-- +51
```

Read what that is. The first three stages are **Layer 0 only** — no profile is built
yet — and they are identical to the session. Every one of the 51 extra trades is
produced by the bin-width rule and by nothing else. That is **+14.2% Layer 1 trades**
from a parameter that has no market meaning, on a fixed set of sessions, with no
price, no volume and no filter changed.

Four consequences, all binding:

1. **`S_filled` is never quoted without the bin-width rule that produced it.** A
   trade count is an assumption-conditional quantity in Layer 1, the same way an R
   multiple is.
2. **Every per-trade Layer 1 statistic has `S_filled` in its denominator** —
   expectancy per trade, win rate, profit factor, the exit-mix shares, the MFE
   quantiles. A 14% move in the denominator moves all of them, and it moves them
   *without any of them being wrong*. Two honest runs can disagree for this reason
   alone.
3. **A sample-size argument is now suspect.** "n is large enough" is not a defence
   when n itself is set by the assumption under test. `n_breakout` (Layer 0, real) and
   `S_filled` (Layer 1, assumption-conditional) are different kinds of number and are
   never used interchangeably — §h.1 already forbids merging those funnel stages, and
   this is why.
4. **§b.9 must therefore report `d_fill_count` next to `d_fill_rate`.** The rate is
   the gate trigger; the count is the consequence. On this example a change too small
   to trip a 10-percentage-point rate threshold still moved the trade count by 51.

Note the direction of the evidence: this example is a **bin-width** change, not a
**method** change, so it does not itself prove that M1–M4 disagree on real bars. What
it proves is that the fill count is *mechanically sensitive to the profile*, which is
the reason `d_fill_count` is measured at all. Whether the four methods actually move
it is decided on real bars by §b.9. The counts above are synthetic (negative control)
and are cited as a **mechanism demonstration only**, never as a magnitude.

#### `hard_stop_ticks = 8` is a FREE PARAMETER with no justification

It was chosen because a close-based rule needs *some* hard stop behind it (§c.1),
and 8 ticks = 2.0 points is a round number. There is no argument in this document,
or in the source transcript, for 8 rather than 5 or 12. It is the constant in the
identity above, so it sets what fraction of `risk_R` is *not* the profile — which
makes it the one knob that could be quietly tuned to make the coupling look smaller.

Binding rules:

1. `hard_stop_ticks` is **swept over its full §f range {4, 8, 12, 16, 20} and
   reported as a table**, on every Layer 1 result, next to `risk_R`,
   `close_invalidation` share and expectancy.
2. **It is never tuned.** P1 stays at 8. The sweep is a labelled sensitivity under
   §g.0.1 and can never pass, fail, or rescue a gate, and its argmax is never a
   headline.
3. A wider `hard_stop_ticks` mechanically dilutes the profile's share of `risk_R`.
   If Layer 1 only looks stable at a wide hard stop, that is the hard stop hiding
   §b.9, not Layer 1 working.

> **CONCLUSION, binding on Step 3.** Combine the two findings. The close-beyond-VAL
> rule (1) cannot shrink `risk_R` by one tick, and (2) fires on roughly 6–19% of
> exits, inside a window that is a fixed `hard_stop_ticks` wide. **Model 1's stated
> mechanism — the tighter VA-based stop — therefore contributes almost nothing.**
> What remains of Layer 1 is the **ENTRY PRICE alone**: `VAH` instead of
> `IB_high + buffer`.
>
> Step 3 must be built and reported as a test of *entry price*, not of stop
> placement. Its control is Layer 0's own entry and stop on the same sessions. The
> close rule is a **second-order effect** and is reported separately — its
> `close_invalidation` share and the average loss realised on those exits versus a
> full `risk_R` — never folded into the headline Layer 1 claim.
>
> If Layer 1 fails as an entry-price rule, it fails. There is no tighter-stop
> benefit left to rescue it.

Three consequences, all binding:

1. **Report two risk numbers on every Layer 1 trade, always:**
   `risk_to_hard_stop` (= `risk_R`, the only admissible denominator of an R
   multiple) and `risk_to_VAL` (the distance the source's framing quotes). Printing
   only the first hides the gap; printing only the second inflates every R multiple
   downstream. The gap between them is `hard_stop_ticks` by construction, and
   seeing it side by side is what keeps the two framings from being confused.
2. **The §c.3 test is a test of entry price, not of stop placement.** The right
   control is Layer 0's own entry and stop on the same sessions, which is why
   `layer0_risk_points` is carried alongside.
3. **The exit taxonomy must stay split** (§c, §c.1). `close_invalidation` and
   `hard_stop` are different events: the first realises less than `risk_R`, the
   second realises all of it. Merging them into one "stopped out" bucket destroys
   the only evidence that the close-based rule does anything at all. The four
   categories are closed and enumerated:
   `{tp1, close_invalidation, hard_stop, time_stop}`, and their **frequencies are
   reported with every Layer 1 result**, zero counts included.

---

### b.11 THE POSITIVE-CONTROL QUARANTINE — a general rule, enforced in code

§b.7 already refused to read its fill-model switch off the positive control. That
was the right instinct applied to one statistic. Generalised:

> **`data/raw/synthetic_structured.parquet` may be used for exactly ONE thing: to
> prove that the §b.9 gate's PASS branch executes. It may never source a reported
> statistic — not a fill rate, not an exit mix, not a `close_invalidation`
> frequency, not a funnel count, not an MFE quantile, not PnL.**

#### Why this is stronger than "be careful with synthetic data"

The negative control and the positive control are **not** equally compromised, and
collapsing them into one "it's synthetic" caveat gets the positive control wrong:

| | negative control | positive control |
|---|---|---|
| Generator | driftless random walk, volume i.i.d. and independent of price | AR(1) around a drifting anchor, volume a kernel of distance from it |
| How its parameters were set | written once to be the null | **tuned until §b.9 returned `not material`** |
| So its numbers are | synthetic, and not findings about NQ | synthetic, **and selected to produce an outcome** |
| Status | not quarantined; still inadmissible as a claim about NQ | **quarantined** |

The tuning targeted one verdict. Every other statistic in that file — the fill rate,
the exit mix, the `close_invalidation` share — moved as a *side effect* of that
tuning, without anyone deciding to select it. A number that was selected without
anyone noticing is worse than a number that was selected on purpose, because nothing
in the output marks it.

#### Enforcement

Prose caveats are a thing a future session has to read and remember. This one is
mechanical, in `ivb/provenance.py`:

```
classify(path)              -> negative_control | positive_control | real
assert_reportable(kind, s)  -> raises QuarantineError unless s == "b9_gate_verdict"
redact(kind, s, text)       -> replaces the VALUE, keeps the LABEL, so a withheld
                               number is visibly withheld rather than absent
POSITIVE_CONTROL_ALLOWED    = frozenset({"b9_gate_verdict"})   # a list of one
```

Wired in at four points:

1. **`scripts/03_run_step1.py` refuses to run at all** on the positive control.
   Step 1 is nothing but reported statistics.
2. **`ivb/report.py::write_step1` re-checks** `extras["source"]` — a second line of
   defence for any other caller that reaches the artifact writer.
3. **`scripts/04_charts.py` redacts every console statistic** on that file: the exit
   taxonomy, the §b.10 window, the §b.10 coupling numbers, the touch-only fraction.
   The §b.9 block prints in full, because that is the permitted use.
   **Edge case, stated so it is not mistaken later.** That block contains
   `fill_rates`, `fill_counts` and `d_fill_count`, and on the positive control they
   are still visible. They are **gate internals** — inputs to the one permitted
   output, the verdict — not reported fill statistics. They may be read as "how far
   apart are M1–M4 on this file" and for nothing else. The positive control's fill
   rate, fill count and `S_filled` may never be quoted as a property of the
   strategy, compared against the negative control, or carried into any funnel,
   denominator or per-trade figure. §b.7 already refuses to read a fill-model switch
   off this file for exactly this reason.
4. **Charts 3, 4 and 5 are not drawn at all** on the positive control — the funnel,
   the MFE distribution with TP1, and the Layer 3 cell counts are pure statistics
   with no part in proving the gate's pass branch. Chart 1 drops from four sessions
   to one, chosen on IB range alone, because the normal selection is **by outcome**
   (a TP1 long, a `no_fill`, a `close_invalidation`, a TP1 short) and outcome
   selection on a file tuned to an outcome is selection twice over.

Observed: `python scripts/04_charts.py data/raw/synthetic_structured.parquet` now
writes **2** charts and prints `[QUARANTINED -- positive control]` in place of every
withheld figure. The negative control still writes 8.

Covered by 6 assertions in `tests/test_controls.py`.

#### The rule that generalises past this one file

Any future control, dataset or fixture whose parameters were **tuned until a test
returned a wanted answer** is quarantined the same way, and is added to
`ivb/provenance.py` rather than to a paragraph. The test it was tuned for is the
only thing it may ever source.

---

## (c) Layer 1 — Invalidation rule, unambiguous

```
far_boundary(long)  = VAL
far_boundary(short) = VAH

TF_inval  = invalidation timeframe   DEFAULT 5-minute, clock-aligned
                                     (09:35, 09:40, ...), built from 1-min bars
                                     range {1, 3, 5, 15} minutes

LONG  invalidated at the CLOSE of the first TF_inval bar whose
      close < VAL - inval_buffer
SHORT invalidated at the CLOSE of the first TF_inval bar whose
      close > VAH + inval_buffer

inval_buffer  DEFAULT 0 ticks    range 0 - 4 ticks
exit_price    = open of the next 1-minute bar after that close, market,
                plus slippage
```

"Close" means the last traded price inside the `TF_inval` interval. The 5-minute
bar covering `[09:35, 09:40)` is aggregated from the 1-minute bars with open times
in that interval, and its close is the close of the `09:39` bar. Clock alignment is
anchored to the hour, **not** to the entry time.

### c.1 Mandatory hard stop (the transcript ignores this)

A close-based invalidation carries unbounded intrabar risk. On NQ that is not
survivable. So **both** rules run, whichever fires first:

```
hard_stop(long)  = VAL - hard_stop_ticks     DEFAULT 8 ticks (2.0 pt)
hard_stop(short) = VAH + hard_stop_ticks     range 4 - 20 ticks
```

Backtest three exit regimes and report all three:

1. `close_only` — the transcript's claim.
2. `close_plus_hard` — tradeable.
3. `hard_only` — control.

The cost of the hard stop is the honest price of tradeability. If (1) is profitable
and (2) is not, the claimed edge does not survive contact with risk management.

#### The exit taxonomy is a CLOSED enum, and its frequencies are a headline number

Every Layer 1 exit is logged as exactly one of:

```
tp1                 the R-multiple target filled (limit order, no slippage)
close_invalidation  a TF_inval CLOSE beyond the far VA edge (sec c);
                    exit at the next 1-minute bar OPEN, market, plus slippage
hard_stop           the resting stop at far_edge -/+ hard_stop_ticks
time_stop           flat at trade_end (11:30 ET), market
```

No other string is permitted, and **no report may merge `close_invalidation` with
`hard_stop`** into a combined "stopped out" bucket. Those two are the entire
subject of §c.3: the first realises less than `risk_R`, the second realises all of
it, and the whole claim for the close-based rule is how often the first fires
instead of the second. Report the count of all four, zeros included, next to every
Layer 1 result.

**Hard-stop dominance.** A `close_invalidation` may be logged as such only if its
market exit price is strictly better than the hard stop. If the next bar opens at
or through the hard stop, the resting stop order had already filled: the fill price
is identical either way, but the event belongs in the `hard_stop` bucket. Without
this rule a gap-through quietly moves a full-`risk_R` loss into the
`close_invalidation` column and flatters exactly the number §c.3 turns on.

### c.2 Risk definition for R multiples

```
risk_R = |entry_price - stop_price_actually_used|
```

Use the *actual* stop, not the theoretical one. If regime 2 is live, `risk_R` uses
`hard_stop`. Reporting R multiples off a tighter theoretical stop while trading a
wider real one inflates every downstream number.

**Two numbers, reported side by side, on every Layer 1 trade (§b.10):**

```
risk_to_hard_stop = |entry - hard_stop|      # = risk_R. The ONLY R denominator.
risk_to_VAL       = |entry - far_VA_edge|    # what the source's framing quotes.
```

They differ by `hard_stop_ticks` exactly. Both are printed so the gap between the
source's framing and ours is visible rather than argued about.

**And both are the value-area width in disguise** (§b.10):

```
risk_to_VAL       = VAH - VAL
risk_to_hard_stop = VAH - VAL + hard_stop_ticks      # = risk_R
```

So the §b.9 instability in `(VAH - VAL)` is the instability in `risk_R`. The hard
stop adds a constant and damps nothing.

### c.3 The claim to test directly

The source claims the tighter VA-based stop yields **1:2 to 1:2.5** instead of 1:1,
through a smaller denominator and the *same* target. The falsifiable test:

> On the same breakout days, does `E[PnL in $] per session` rise when the stop moves
> from the IB extreme to VAL, after accounting for the higher stop-out frequency
> **and** the `no_fill` sessions?

A tighter stop mechanically raises R:R **and** raises the stop-out rate. The claim
is true only if the first effect dominates. Measure both.

**Correction to the source's mechanism (§b.10).** Under the tradeable regime the
VA-based *stop* does not move `risk_R` at all — the hard stop sits a fixed
`hard_stop_ticks` behind the far VA edge, and `risk_R` is measured to it. The
smaller denominator comes from the **entry price**: `VAH` instead of
`IB_high + buffer`. So this test is a test of entry price, and the control is
Layer 0's own entry and stop on the same sessions. The close-based rule is tested
separately, and its only measurable effect is the `close_invalidation` share of
exits (§c.1) and the average loss realised on those exits versus a full `risk_R`.

---

## (d) Layer 2 — Order flow triggers

### d.0 Blocking data statement

**With 1-minute OHLCV, Layer 2 is not testable.** None of the three triggers below
can be evaluated. The bar proxies described are *bar-pattern detectors*, not order
flow. Any result from them must not be reported as evidence for or against order
flow. Recommendation: hold Layer 2 out entirely until trades-with-aggressor-side
data is available.

All triggers are armed **only** while price is inside the Layer 1 zone, and only
within `reload_timeout` of the breakout.

### d.1 ABSORPTION

*True definition — needs trades with aggressor side; book depth preferred:*

```
W          rolling window       DEFAULT 60 s    range 15 - 180 s
V_against  aggressive volume against the trade direction inside W
           (sell-aggressor volume for a long setup)
P_thresh   V_against >= 80th percentile of this session's per-W against-volume
           DEFAULT pct 0.80     range 0.70 - 0.95
D_move     |price(end W) - price(start W)| <= 4 ticks     range 2 - 8
D_extend   the zone low does not extend more than 2 ticks below its value at
           the start of W

ABSORPTION = P_thresh AND D_move AND D_extend

Continuous form (preferred, avoids a threshold cliff):
  absorption_ratio = |delta_price in ticks| / (V_against / 1000)
  lower = stronger absorption. The cut-off comes from the empirical
  per-session distribution of the ratio, not from a hard-coded number.
```

*Degraded proxy on 1-minute OHLCV:*

```
clv       = 2 * (close - low) / (high - low) - 1     # -1 .. +1
delta_est = volume * clv                             # signed-volume estimate

ABSORPTION_proxy(long) =
    volume(t) >= 80th pct of session bar volume
    AND (high - low) <= 6 ticks
    AND |close - open| <= 2 ticks
    AND low(t) inside the zone
```

**What this cannot do:** `clv` cannot separate "aggressive sellers absorbed by
passive buyers" from "aggressive buyers absorbed by passive sellers" — both print
the same bar. On 1-minute NQ bars, CLV-derived delta is a weak correlate of true
delta. This detects a wide-volume, narrow-body candle. State that every time it is
used.

### d.2 EXHAUSTION

*True definition:*

```
K   lookback windows     DEFAULT 5      range 3 - 10
E1  drop-off ratio       DEFAULT 0.40   range 0.25 - 0.60

EXHAUSTION(long) =
    V_sell_aggressor(current W) <= E1 * mean(V_sell_aggressor, prior K windows)
    AND no new low over the prior K windows
    AND price inside the zone
```

*Degraded proxy on 1-minute OHLCV:*

```
EXHAUSTION_proxy(long) =
    volume(t) <= 0.5 * mean(volume, prior 5 bars)
    AND low(t) >= min(low, prior 2 bars)
    AND price inside the zone
```

**What this cannot do:** on bars this reduces to "volume dried up", which also
happens late in the morning, before holidays, and on any slow tape. It carries no
aggressor information. **Mandatory correction if used at all:** normalise volume by
the historical mean volume for the same minute-of-day, on an expanding window over
*prior days only* — never the current day. Without that, the trigger is a
time-of-day detector.

### d.3 AGGRESSION / STACKED IMBALANCE

*True definition — needs footprint (bid and ask volume per price level):*

```
R_imb      imbalance ratio        DEFAULT 3.0     range 2.0 - 5.0
min_cell   volume floor per cell  DEFAULT 20      range 10 - 50
N_stack    consecutive levels     DEFAULT 3       range 2 - 5
F_follow   follow-through ticks   DEFAULT 4       range 2 - 10
T_follow   follow-through window  DEFAULT 120 s   range 30 - 300 s

bullish diagonal imbalance at level p:
    ask_vol(p) >= R_imb * bid_vol(p - 1 tick)
    AND ask_vol(p) >= min_cell
STACK      = N_stack consecutive levels, all bullish-imbalanced
AGGRESSION = STACK AND price trades >= F_follow ticks above the stack top
             within T_follow
```

*Degraded proxy on 1-minute OHLCV:*

```
AGGRESSION_proxy(long) =
    (high - low)(t) >= 75th pct of session bar range
    AND close(t) in the top 20% of the bar's range
    AND volume(t)   >= 75th pct of session bar volume
    AND close(t)    >  zone_top
```

**What this cannot do:** this is a momentum-candle filter. It contains no bid/ask
information whatsoever and is a *different object* from a stacked imbalance. Do not
call it "order flow" in any output.

### d.4 Combination rule

```
require_confirmation  DEFAULT True
confirmation_mode     DEFAULT "any_of"     # any one of the three triggers
                      alt: "abs_or_exh"      (mean-revert style entries)
                           "aggression_only" (momentum style entries)
no_confirm_action     DEFAULT "no_trade"   alt: "half_size"
confirm_timeout       DEFAULT 15 min after the first zone touch
```

The sequence is strict and enforced in code as a state machine:

```
AWAIT_IB_CLOSE -> AWAIT_BREAKOUT -> AWAIT_ZONE_TOUCH -> AWAIT_CONFIRMATION -> IN_TRADE
```

A trigger that fires before its predecessor state is reached is discarded.

---

## (e) Session classifier — directional vs consolidation

### e.1 Features — all computable at breakout time, none after

Every feature uses data up to and including the breakout bar, or prior sessions
only. No same-day forward information.

| Feature | Definition | Source window |
|---|---|---|
| `ib_range` | `IB_high - IB_low`, points | IB |
| `ib_range_atr` | `ib_range / ATR14_daily(prior close)` | prior days |
| `ib_range_rel` | `ib_range / median(ib_range, prior 60 sessions)` | prior days |
| `ib_vol_rel` | IB total volume / median IB volume, prior 20 sessions | prior days |
| `on_range_atr` | (overnight high − low, 18:00 → 09:30) / ATR14 | prior night |
| `gap_atr` | (09:30 open − prior RTH close) / ATR14 | prior close |
| `ib_close_pos` | `(close(last IB bar) - IB_low) / ib_range` | IB |
| `ib_extreme_touches` | count of IB bars setting a new IB high or low | IB |
| `ib_efficiency` | `abs(close(last IB bar) - open(first IB bar)) / sum(bar ranges)` | IB |
| `brk_delay` | minutes from `IB_close_t` to the breakout bar | IB → breakout |
| `brk_vol_rel` | breakout bar volume / mean IB bar volume | breakout |
| `prior_day_type` | prior session `abs(close-open) / range`, bucketed | prior day |
| `dow` | day of week | — |
| `is_release_day` | a scheduled 10:00 ET release is present | calendar |

`ib_efficiency` and `ib_extreme_touches` carry the one-way-versus-two-way auction
information, which is the thing actually being classified.

### e.2 Label — defined honestly as post-hoc

```
directional(session) = True if, after the first IB break,
    MFE in the break direction >= directional_label_mult * ib_range   (DEFAULT 1.0)
    is reached BEFORE price closes back inside the IB range
    and before 11:30 ET
else False
```

The label is knowable only after the fact — that is fine, it is the target. The
requirement is that **no feature** may use post-breakout information.

### e.3 Model, and the rule it must beat

```
Baseline rule (must be beaten, or the ML model is killed):
    3 buckets on ib_range_atr: low (<0.5) / mid (0.5-1.0) / high (>1.0)
    Run the directional model only in the bucket with the best OUT-OF-SAMPLE
    directional rate.

Model: logistic regression on the §e.1 features, L2 penalty, features
       standardised using training-fold statistics only.
Validation: walk-forward by calendar year. Fit years 1..k, predict year k+1.
       Never refit on the test year. No shuffled cross-validation — it leaks
       across adjacent days.
```

### e.4 Live switching rule

```
p_dir = P(directional | features at breakout)
p_hi  DEFAULT 0.60    range 0.50 - 0.75
p_lo  DEFAULT 0.40    range 0.25 - 0.50

p_dir >= p_hi  -> breakout (trend) model active
p_dir <= p_lo  -> inverse (fade the IB extremes) model active
otherwise      -> no trade
```

The dead band is deliberate. A classifier with no abstain region trades its own
noise.

### e.5 Inverse model (specified now, tested last)

```
Armed only while price has NOT broken the IB by more than `buffer` for
`fade_arm_delay_min` (DEFAULT 15) past IB_close_t, and p_dir <= p_lo.

Entry:  limit at IB_high (short) / IB_low (long), requiring an ABSORPTION or
        EXHAUSTION trigger (§d) — therefore NOT testable without tick data.
Stop:   IB extreme +/- fade_stop_ticks    DEFAULT 10 ticks
Target: IB_mid, then POC
Kill:   a confirmed close-through breakout cancels the fade and, if
        `flip_on_break = True`, hands control to the trend model.
```

---

## (f) Full parameter list

### Layer 0

| Param | Default | Range | Notes |
|---|---|---|---|
| `ib_minutes` | 30 | {15, 30, 60} | pre-registered 30 |
| `breakout_trigger` | `close_through` | {`close_through`, `trade_through`} | |
| `breakout_buffer_ticks` | 1 | 0 – 8 | |
| **`min_ib_range_atr`** | **0.15** | 0.00 – 0.40 | **No-trade filter.** Session is skipped if `IB_range < 0.15 * ATR14`. A very tight IB breaks instantly on a 1-tick buffer and produces pure noise trades. ATR-relative, not absolute, so it self-scales across vol regimes. Known at IB close — no leakage. |
| `min_ib_range_ticks` | 0 | 0 – 40 | Absolute floor, applied in addition. Default off; the ATR-relative filter is primary. |
| `max_ib_range_atr` | None | — | **Not a parameter.** A very wide IB leaves little room for excursion, but that is handled by reporting (below), not by filtering. Do not add a second filter without evidence. |
| `entry_fill` | `next_bar_open` | {`next_bar_open`, `trigger_price`} | |
| `session_end` | 11:30 ET | — | hard time stop |
| `one_trade_per_day` | True | — | |
| `trade_reversals` | False | — | logged, not traded |
| `baseline_stop` | `opposite_ib_extreme` | {extreme, `k*IB_range`} | |
| `baseline_stop_k` | 0.50 | 0.25 – 1.00 | for the k variant |
| `baseline_R_targets` | [1.0, 1.5, 2.0, 3.0] | — | reported as a grid, not optimised |
| `commission_per_side` | 0.85 $ | 0.5 – 1.5 | per contract |
| `slippage_ticks_market` | 1 | 0 – 3 | |
| `exclude_half_days` | True | — | |
| `cost_model` | `MNQ` | {`NQ`, `MNQ`} | **Kill criteria judged on MNQ.** Both always reported. §0.2.5 |
| `partition` | `DEVELOPMENT` | — | Holdouts sealed. §0.2.3 |
| `covid_flag` | True | — | Kept in sample, flagged, reported both ways. §0.2.4 |
| `intrabar` | `pessimistic` | {`pessimistic`, `optimistic`} | Optimistic run is a diagnostic only. §a.5 |
| `bootstrap_block` | `month` | — | Block bootstrap, 10,000 resamples. §i |

**Reporting requirement (not a parameter):** every Step 1 result is additionally
broken out **by IB-range decile**. That is how the wide-IB and tight-IB behaviour is
diagnosed — by looking, not by adding filters. If a monotonic relationship appears
across deciles, that is a Layer 3 feature, not a new filter.

### Layer 1

| Param | Default | Range | Notes |
|---|---|---|---|
| `profile_source` | `volume_uniform` | {`volume_uniform`, `volume_triangular`, `volume_close_only`, `tpo_minute`} | |
| **`bin_width_rule`** | **`median_ib_bar_range`** | — | **§b.2. Bin width is RELATIVE, pre-registered blind.** `bin_width` = median 1-minute bar range over this session's IB window, rounded to the nearest tick, floored at 1 tick. A width fixed in points is a different fraction of a bar in 2015 and in 2026, which would make the §b.9 verdict a function of the calendar. |
| **`bin_width_mult`** | **1.0** | {0.5, 1.0, 2.0} | **Sensitivity axis, never optimised (§g.0.1).** The primary makes the median bar span ~1 bin by construction, which is the condition that forces the four §b.9 methods to agree — so the 0.5× and 2.0× rows must be read next to any `not material` verdict. **For the §b.9 gate the three rows resolve by the pre-registered rule: `MATERIAL` at any one of them makes the verdict `MATERIAL`; a pass needs all three clear.** |
| `bin_width_floor_ticks` | 1 | — | A bin narrower than a tick is meaningless. |
| `bin_size_pts` | 1.0 | 0.25 – 2.0 | **No longer a primary.** The pre-relative fixed width, kept only as a labelled comparison row. |
| `va_pct` | 0.70 | 0.60 – 0.80 | |
| `poc_tiebreak` | `nearest_ib_mid` | — | deterministic |
| `entry_variant` | `E1` | {E1, E2, E3} | E1 = VA edge |
| `require_penetration_ticks` | 0 | 0 – 2 | limit-fill realism |
| `min_zone_width_ticks` | 2 | 1 – 8 | degenerate zone guard |
| `reload_timeout_min` | 30 | 10 – 60 | |
| `tf_inval_min` | 5 | {1, 3, 5, 15} | |
| `inval_buffer_ticks` | 0 | 0 – 4 | |
| **`hard_stop_ticks`** | **8** | 4 – 20 | Beyond the far VA boundary. **A FREE PARAMETER with no justification (§b.10)** — no argument exists here or in the source for 8 rather than 5 or 12. It is the constant in `risk_R = (VAH − VAL) + hard_stop_ticks`, so it sets what fraction of `risk_R` is *not* the profile (18% on the negative control). **Swept over {4, 8, 12, 16, 20} and reported on every Layer 1 result; never tuned.** A Layer 1 that only looks stable at a wide hard stop is the hard stop hiding §b.9. |
| `exit_regime` | `close_plus_hard` | {`close_only`, `close_plus_hard`, `hard_only`} | |
| `poc_stability_gate_ticks` | 4 | 2 – 8 | median; a gate, not a knob |

### Layer 2 (inert until tick data exists)

| Param | Default | Range |
|---|---|---|
| `require_confirmation` | True | — |
| `confirmation_mode` | `any_of` | {`any_of`, `abs_or_exh`, `aggression_only`} |
| `no_confirm_action` | `no_trade` | {`no_trade`, `half_size`} |
| `confirm_timeout_min` | 15 | 5 – 30 |
| `abs_window_s` | 60 | 15 – 180 |
| `abs_vol_pct` | 0.80 | 0.70 – 0.95 |
| `abs_max_move_ticks` | 4 | 2 – 8 |
| `exh_lookback_windows` | 5 | 3 – 10 |
| `exh_dropoff_ratio` | 0.40 | 0.25 – 0.60 |
| `imb_ratio` | 3.0 | 2.0 – 5.0 |
| `imb_min_cell_vol` | 20 | 10 – 50 |
| `imb_stack_levels` | 3 | 2 – 5 |
| `imb_follow_ticks` | 4 | 2 – 10 |
| `imb_follow_s` | 120 | 30 – 300 |

### Layer 3

| Param | Default | Range | Notes |
|---|---|---|---|
| `tp1_hit_rate_target` | 0.675 | 0.65 – 0.70 | equals the 32.5th pct of the MFE distribution. **The realised hit rate is an identity and may never be reported as a result — §h.5.** |
| `tp2_hit_rate_target` | 0.30 | 0.20 – 0.40 | the extended tail |
| `mfe_units` | `ib_range` | {`points`, `ib_range`, `atr`, `R`} | tested for stationarity |
| `quantile_method` | `bucket_empirical` **and** `quantile_reg`, CO-PRIMARY | {`bucket_empirical`, `quantile_reg`, `gbm_quantile`} | Both fitted on the same folds and compared head to head (§h.3). `gbm_quantile` is the only true escalation. |
| `min_obs_per_bucket` | 100 | 50 – 250 | |
| `walkforward` | `by_year_expanding` | — | never shuffled |

### Classifier

| Param | Default | Range |
|---|---|---|
| `directional_label_mult` | 1.0 | 0.75 – 1.50 |
| `p_hi` | 0.60 | 0.50 – 0.75 |
| `p_lo` | 0.40 | 0.25 – 0.50 |
| `fade_arm_delay_min` | 15 | 5 – 30 |
| `fade_stop_ticks` | 10 | 6 – 20 |

### Sizing (needs your input)

| Param | Default | Notes |
|---|---|---|
| `account_size` | **UNSET** | |
| `risk_per_trade_pct` | **UNSET** | |
| `contracts` | fixed 1 | **Use a fixed 1 contract for all research.** Compounding hides drawdown shape and flatters Sharpe. Sizing is applied once, after the edge is proven. |

---

## (g) Protocol rules — fixed in advance, not negotiable after seeing results

### g.0 THE PRIMARY CONFIGURATION — one config, named now

You were right that §g.1 pinned `ib_minutes` and then left 16 live configurations
under the same kill criteria. Passing in 1 of 16 is not passing. Fixed:

```
PRIMARY CONFIGURATION  (id: "P0")
    ib_minutes             = 30
    breakout_trigger       = close_through
    breakout_buffer_ticks  = 1
    entry_fill             = next_bar_open
    baseline_stop          = opposite_ib_extreme
    R_mult                 = 2.0
    time_stop              = 11:30 ET
    min_ib_range_atr       = 0.15          (see §f, new)
    cost_model             = MNQ
    intrabar               = pessimistic
    partition              = DEVELOPMENT

  Layer 1 extension (Step 3), id "P1" — P0 plus:
    entry_variant          = E1
    exit_regime            = close_plus_hard
    profile_source         = volume_uniform
    bin_width_rule         = median_ib_bar_range   (sec b.2, RELATIVE)
    bin_width_mult         = 1.0
    bin_width_floor_ticks  = 1
    va_pct                 = 0.70
    hard_stop_ticks        = 8                     (swept, never tuned -- sec b.10)
```

> **All kill criteria in this project apply to P0 (and P1) alone.**
> Every other configuration is a **labelled sensitivity appendix** and can never
> pass, fail, or rescue a gate.

### g.0.1 What the parameter grid is for — and the multiple-testing rule

Step 1 still runs 4 R-targets × 2 stop variants × 2 triggers = **16 configurations**.
Their purpose is **not** to find a winner. It is to answer one question:

> Is the result at P0 an isolated spike, or does the edge persist across
> neighbouring parameter values?

```
grid_robustness = fraction of the 16 configurations with positive expectancy
                  per session, net of MNQ costs

  13-16 of 16 positive  -> edge is robust to parameter choice. Good sign.
   8-12 of 16 positive  -> mixed. Report honestly, do not spin.
   1-4  of 16 positive  -> P0 sits on a spike. Treat P0 as NOISE even if it
                           passes its own kill criteria in isolation.
```

That last line matters: **a narrow spike is evidence against P0, not for it**, even
when P0 itself looks good. Parameter-space topology is a legitimate diagnostic; the
argmax of a grid is not.

#### Multiple-testing rule

```
1. Kill criteria are evaluated at P0 ONLY. No correction needed - one test.
2. The C2 coin-flip p-value is computed for P0 ONLY.
3. If any non-primary configuration is ever proposed to REPLACE P0, it must clear
   BOTH:
     a) a Bonferroni-corrected threshold, alpha = 0.05 / 16 = 0.0031, against
        its own C2 shuffle distribution, AND
     b) the sealed holdouts (§g.1.5), opened once.
4. Reporting a grid maximum as a headline result is forbidden. The grid is
   reported as a full table plus `grid_robustness`, never as a best case.
```

### g.1 The pre-registered primaries, and the checks that run once at the end

#### The register

Two parameters are pre-registered **blind** — fixed before the data that would
decide them was ever loaded — and this is the register of record for both:

```
ib_minutes       = 30                     pre-registered primary
                                          15 and 60 are run ONCE, at the end

bin_width_rule   = median_ib_bar_range    pre-registered primary (sec b.2)
bin_width_mult   = 1.0                    registered BLIND, before any real bar
                                          0.5 and 2.0 are a labelled sensitivity

sec b.9 MULTIPLIER RESOLUTION RULE        registered BLIND (sec b.9)
  MATERIAL at ANY of {0.5, 1.0, 2.0} -> the resolved verdict is MATERIAL
  a PASS requires "not material" at ALL THREE.  No other combination passes.
  The neighbours VETO only; they never rescue, and the primary is never moved.
```

`bin_width` is registered here for the same reason `ib_minutes` is: it is the lever
that decides whether the §b.9 gate passes, so choosing it after seeing real data
would be selection on the gate's own outcome. It is a **rule**, not a number of
points, because a number of points is not the same object at both ends of a sample
that spans a 5× move in the index (§b.2).

Run §b.9 **once**, at that rule, over all three multipliers, and resolve the verdict
by the rule registered above. Any other bin width is a labelled sensitivity, never the
primary, and the primary is never moved onto a sensitivity row.

#### The 15 / 60-minute IB check — CONFIRMED, once, at the end

**Confirmed as you specified.** Written as a binding protocol rule:

1. `ib_minutes = 30` is the **pre-registered primary**. All of Steps 1, 2, 3 and 5
   are run and reported at N = 30 only.
2. N = 15 and N = 60 are run **once**, **after** the primary result is finalised and
   written down, and are reported as a sensitivity appendix.
3. They may **not** be used to select the primary. They may not be run early "just
   to look".
4. **If N = 15 or N = 60 beats N = 30, nothing changes.** That is a *new hypothesis*,
   and it requires fresh out-of-sample data — or a pre-committed holdout untouched
   until that moment — before it can become the primary. Switching the primary on
   the strength of that comparison is selection, and it would invalidate every
   downstream result.
### g.1.5 Holdout vs walk-forward — the collision, resolved

You caught a direct conflict: §g.1 sealed the newest 20%, while Step 2 walk-forwards
by year and predicts year k+1. Both wanted the recent years. Resolution:

```
BACKWARD_HOLDOUT  2010-07-01 .. 2014-12-31   SEALED. Not touched by Steps 1-5.
                  Starts in JULY because GLBX.MDP3 coverage begins 2010-06-06
                  and 2010-07-01 is the first clean month boundary (sec 0.2.3).
DEVELOPMENT       2015 .. ~2024-05   ALL walk-forward happens INSIDE this window.
FORWARD_HOLDOUT   ~2024-05 .. now    SEALED. Not touched by Steps 1-5.
```

- **Walk-forward runs on the DEVELOPMENT partition only.** Fit years 1..k, test year
  k+1, entirely within 2015 → ~2024-05. That gives roughly **8 test folds**.
- The forward holdout is **never** a walk-forward test fold. It is not used for
  fitting, tuning, model selection, or threshold setting.
- Both holdouts are opened **once, together, at the very end**, and only to
  adjudicate: (a) does the final P0/P1 result survive out of sample, and (b) any
  post-hoc question such as "N = 15 looked better".
- Opening either early destroys it permanently. There is no recovery.

**Consequence, and it is a real cost:** the cell counts in §h.2 must be computed
against the DEVELOPMENT partition (~2,345 sessions), **not** the full sample. The
thin cells get thinner. §h.2 is written against development-set numbers for exactly
this reason.

The same rule governs every other parameter in §f. The defaults are pre-registered.
Ranges exist to describe plausible values and to run sensitivity, **not** to be
swept for a maximum.

### g.2 Denominators — how no-trade days are counted

This is the metric most easily gamed, so the definitions are fixed here.

#### The three session sets

```
S_all       every tradeable session in the sample
            (RTH, holidays and half-days excluded)

S_breakout  sessions where the Layer 0 breakout condition fired before 11:30 ET
            S_breakout is a SUBSET of S_all

S_filled    sessions in S_breakout where the Layer 1 reload zone was also touched
            within reload_timeout
            S_filled is a SUBSET of S_breakout
```

#### The rule

> **The head-to-head comparison between any two layers uses the denominator of the
> WIDER layer, never the narrower one.**

| Comparison | Denominator | Days counted as zero PnL |
|---|---|---|
| Layer 0 vs "do nothing" | `S_all` | no-breakout days |
| **Layer 0 vs Layer 1** | **`S_breakout`** | Layer 1's `no_fill` days |
| Layer 1 vs Layer 2 | `S_filled` | Layer 2's `no_confirmation` days |
| Any layer, absolute terms | `S_all` | everything it did not trade |

#### Why `S_breakout` and not `S_all` for the Layer 0 vs Layer 1 comparison

A no-breakout day is not an opportunity **either** layer had. Including it adds the
same zero to both numerators and the same count to both denominators — it shrinks
both numbers toward zero and makes a real difference harder to see, without
changing the sign. Excluding it keeps the comparison sharp.

A `no_fill` day is the opposite: it is a day Layer 0 **did** trade and Layer 1
**chose** not to. That day is Layer 1's decision and Layer 1 must be charged for it.
Dropping those days is the fake-improvement mechanism from §b.8.

#### Both are always reported

```
expectancy_per_breakout_session = total_PnL / |S_breakout|      # PRIMARY headline
expectancy_per_calendar_session = total_PnL / |S_all|           # capital efficiency
expectancy_per_trade            = total_PnL / n_trades          # ALWAYS alongside,
                                                                # never alone
duty_cycle                      = n_trades / |S_all|            # how often you work
```

**`expectancy_per_trade` may never be reported on its own.** It is the number that
makes trade-discarding look like edge. It always appears next to
`expectancy_per_breakout_session`.

---

## (h) Effective sample size — where it gets thin

Placeholder rates below are marked **[MEASURE]** — they are unmeasured guesses used
only to size the study. Step 1 replaces them with real numbers, and this table is
then re-computed for real before Step 2 begins.

### h.1 The funnel — computed on the DEVELOPMENT partition only

Holdouts are sealed, so the study sample is **2015 → ~2024-05**, not the full
history. All rates marked **[MEASURE]** are replaced by real numbers after Step 1.

| Stage | Rate | Sessions | Notes |
|---|---|---|---|
| Calendar trading days, 2015 → ~2024-05 | — | ~2,390 | ~9.4 years |
| minus holidays / half-days | ~98% | **~2,345 = `S_all`** | |
| **IB breaks by 11:30** (IB30, close-through), filters ignored | **~82% [MEASURE]** | **~1,923 = `S_ib_broke`** | The **physical** event. This is the denominator §b.9 uses. |
| minus the §f no-trade filters | ~95% [MEASURE] | **~1,827 = `S_breakout`** | `min_ib_range_atr`, then `min_ib_range_ticks`. |
| **Retrace touches the reload zone** in time | **~50% [MEASURE]** (plausible 35–65%) | **~914 = `S_filled`** | The zone is **inside** the IB (§b.1), so this needs a deep retrace. Most uncertain number here. |
| Layer 2 confirmation fires | ~50% [MEASURE] | ~457 | Not measurable without tick data. |

Sealed and untouched: `BACKWARD_HOLDOUT` ~1,255 sessions, `FORWARD_HOLDOUT` ~585.

#### `S_ib_broke` and `S_breakout` are DIFFERENT numbers — the stage that was missing

The funnel previously went `S_all → S_breakout → S_filled`, with the §f filter
folded into a row above the breakout. That hid a real discrepancy: §b.9 reported
**604** breakout sessions while the funnel chart reported **581**, and there was
nothing on the page to explain the 23.

Both were right. They count different things:

```
S_ib_broke   find_breakout() fires and is unambiguous. The no-trade filters are
             NOT applied. This is what b9_sensitivity() iterates -- it needs the
             IB profile of every session that produced a breakout, filtered or not.

S_breakout   the same event, MINUS the sessions run_strategy() had already
             skipped. run_strategy() applies min_ib_range_atr and
             min_ib_range_ticks at IB close, BEFORE it ever calls find_breakout,
             so a session can break its IB and never become a trade.
```

Measured on the negative control, under the §b.2 relative bin width:
`624 → 604 → 581 → 411`, and all **23** removed sessions are `min_ib_range_atr`. It
reconciles exactly. (`S_filled` was 360 under the old fixed 1.0-point bin; the first
three stages are Layer 0 only and did not move.)

**That 360 → 411 move is the §b.10 worked example, and it is a rule here too.** The
final stage is the only one that touches the profile, and it moved by 51 sessions —
14% — on identical sessions, from a bin-width change alone. So `S_filled` is
**assumption-conditional** and `S_ib_broke` is not. The two are never used
interchangeably, a funnel is never quoted without the bin-width rule that produced
it, and "the sample is large enough" is not an argument at the `S_filled` stage.

**Rules, binding.**
1. Chart 3 shows **four** bars, `S_all → S_ib_broke → S_breakout → S_filled`, and
   names the filter responsible for every session lost between stages two and three.
2. The reconciliation is **asserted**, not eyeballed: the per-`skip_reason` counts
   must sum to `S_ib_broke - S_breakout`. A mismatch prints `DOES NOT RECONCILE` and
   is treated as a bug, not a rounding note.
3. `S_breakout` remains the denominator for every Layer 0 and Layer 1 rate.
   `S_ib_broke` is the denominator for §b.9 and for nothing else. Neither number may
   be quoted without saying which one it is.
4. The illustrative Layer 1 resolver currently ignores the §f filters, so its
   `S_filled` belongs under `S_ib_broke`, not under `S_breakout`. **Step 3 must apply
   the same filters to both layers**, or the Layer 0 vs Layer 1 comparison is run on
   two different samples.

#### A number to re-check on real bars: the breakout rate

The synthetic preview returns **`S_breakout` = 93.1% of `S_all`**. That is well above
the ~80% this table assumed and above the top of its plausible band.

Expect it to be high on synthetic data: a random walk has no support, no resistance
and no participants defending a level, so it crosses a range boundary far more
readily than real price does. The synthetic number is therefore not evidence of a
bug and not evidence of an edge — it is close to what a driftless random walk should
produce over a 90-minute window against a 30-minute range.

**The decision rule, fixed now.** Re-measure on real NQ bars. If `S_breakout` is
still **above ~90%** there, then `breakout_buffer_ticks = 1` is not filtering
anything and "the IB broke" is not a selective event — nearly every session is a
signal, so Layer 0 has no directional filter and is closer to a coin flip on the
first move than to a breakout system. In that case raise `breakout_buffer_ticks`
through its declared range and report the funnel at each value, as a **reported
sensitivity, not an optimisation** (§g.0.1) — the primary stays at 1.

### h.2 Bucket boundaries — expanding terciles, not hard-coded cuts

The hard-coded cuts (`<0.5 / 0.5-1.0 / >1.0`) had two faults: they produce badly
unbalanced cells, and any cut chosen by looking at the full sample is a
full-sample-fitted boundary, which Step 2 explicitly bans. Both are fixed by the
same change.

```
bucket_method   = expanding_tercile        (replaces hard-coded thresholds)

For each session s, the tercile boundaries for a feature are the 33.3rd and 66.7th
percentiles of that feature computed over PRIOR sessions only:

    boundaries(s) = quantile(feature over sessions < s, [1/3, 2/3])

warmup          DEFAULT 250 prior sessions
                Sessions before warmup are unbucketed and excluded from the
                conditional study (they still appear in Step 1).
recompute       daily, expanding (never rolling, never full-sample)
```

This gives, by construction, **balanced cells** (~1/3 each per feature) **and**
satisfies the leakage ban — every boundary uses only past data. It also adapts to
the volatility regime, which a fixed `ib_range_atr = 0.5` cut does not.

### h.3 Where it actually breaks — cell counts on the development set

```
direction      2 cells   (long, short)
ib_range_atr   3 cells   (expanding terciles)
brk_delay      3 cells   (expanding terciles)
                         ------
                         18 cells
```

| | 18-cell design | 6-cell design (direction × `ib_range_atr`) |
|---|---|---|
| Breakouts in DEVELOPMENT, post-warmup | ~1,700 | ~1,700 |
| **Mean per cell** | ~94 | ~283 |
| **Smallest cell** (terciles balance this) | ~60–75 | ~220–260 |
| Cells clearing `min_obs_per_bucket = 100` | ~6–10 of 18 | **6 of 6** |
| **Walk-forward: 8 test folds → obs per cell PER FOLD** | **~12** | **~35** |

Expanding terciles fix the *imbalance* problem. They do **not** fix the *walk-forward
division* problem, and that is the binding constraint.

> **Conclusion, reached before running anything: the 18-cell design is not viable.**
> Twelve observations per cell per test fold cannot support a 32.5th-percentile
> estimate. **Step 2 starts at the 6-cell design** (direction × `ib_range_atr`), and
> `brk_delay` is added only if the 6-cell model demonstrably beats the unconditional
> control out of sample and cell counts still clear the threshold.

**The 6-cell design is thin, not dead.** ~35 observations per cell per test fold is
enough to see a 32.5th percentile, badly. It is not enough to see it precisely, and
the mandatory confidence intervals (§h.4, item 5) will say so. That is the reason for the next
paragraph.

**`quantile_reg` runs as a CO-PRIMARY, not as an escalation.** The parameter table
in §(f) says "escalate only when beaten", which sets up the wrong test: it would
mean fitting buckets, watching them fail on thin cells, and only then trying a
method that does not chop the sample into cells at all. Quantile regression pools
every session and spends its degrees of freedom on coefficients rather than on cell
boundaries, so it is the natural answer to *this specific* sample-size problem, not
a fallback from it. Both are fitted on the same folds and compared head to head on
out-of-sample expectancy (§h.5). `gbm_quantile` stays a true escalation — it is only
reached if both co-primaries beat the unconditional control and there is reason to
think the relationship is non-linear.

**Scaling note for any preview run.** Cell counts computed on a short or synthetic
sample must be scaled to the real primary sample before a design is judged. The
DEVELOPMENT partition is ~2,900 sessions; a 624-session synthetic preview is ~2.5
years, about **4.6×** smaller. Multiply before concluding. The 18-cell design fails
either way, which is why §h.3's conclusion does not depend on the scaling.

This is exactly the kind of thing worth knowing before writing the code rather than
after fitting a model to 12 points.

### h.4 Consequences, decided in advance

1. **Report the cell-count distribution before the quantile estimates** — minimum,
   10th percentile, and the count of cells below `min_obs_per_bucket`, **per test
   fold**, not pooled. Never the mean alone.
2. **Any cell below 100 observations in a fold is not reported as a conditional
   estimate.** It falls back to the pooled unconditional quantile, and the fallback
   is labelled in the output.
3. **Step 2 begins at the 6-cell design** (§h.3). `brk_delay` is added only if the
   6-cell model beats the unconditional control out of sample.
4. **If the 6-cell model does not beat the unconditional control, report the
   unconditional MFE quantile as the answer** and state plainly that a conditional
   "protection level" is not estimable at this sample size. That is a legitimate
   result, not a failure — and it directly contradicts the source's central claim,
   which is worth knowing.
5. Confidence intervals are mandatory on every quantile estimate — bootstrap, and
   report the interval width next to the point estimate. A TP1 of "42 points
   (95% CI: 28–61)" is an honest answer. "42 points" alone is not.

---

### h.5 HIT RATE IS NOT A RESULT — the admissible metrics for Layer 3

**Rule, binding, no exceptions: the TP1 hit rate may never be reported as a result
for Layer 3.**

TP1 is *defined* as the `(1 - tp1_hit_rate_target)`-th percentile of the MFE
distribution — the 32.5th percentile for the default 0.675. A quantile is hit
`100 - pct` percent of the time **in every distribution that exists**: a real market,
a random walk, a pile of uniform noise. "MFE ≥ TP1 in 68% of trades" is therefore an
identity, arithmetic restated, and it carries exactly zero information about whether
the strategy works.

This is not hypothetical. The first run of the MFE chart printed "MFE ≥ TP1 in
68.0%" on **synthetic random-walk bars with no edge by construction**. The number
was correct and completely empty. Anything that can print 68% on noise cannot be
evidence.

It is also the exact shape of the source's central claim — a "protection level"
with a "65–70% hit rate". That claim is unfalsifiable as stated, and reproducing the
number would prove nothing. Reproduce the *mechanism*, never the headline.

#### Admissible metrics — the complete list

Layer 3 is judged on **expectancy net of costs per breakout session**, and on
nothing else:

```
E[net PnL per session in $], costs included, no_fill sessions carried as zero
```

benchmarked against **fixed R multiples** as the control arm:

```
control: TP at a fixed 1.0R / 1.5R / 2.0R / 3.0R, same entries, same stops
test:    TP at the conditional MFE quantile
verdict: the conditional target must beat the BEST fixed-R control out of sample,
         on a PAIRED block bootstrap (sec i.2), or the conditional "protection
         level" is not established.
```

Supporting numbers that may accompany it: profit factor, max drawdown, the full
MAE/MFE distributions, and the per-fold cell counts (§h.4). Every one of these is
reported with a confidence interval (§i).

#### Where the hit rate may still appear

Only as a **diagnostic, explicitly labelled by construction**, to confirm the
quantile estimator is calibrated — i.e. that the realised rate on *held-out* data
matches the targeted rate. Calibration drift is a real signal. The level itself is
not. Any chart or table showing it carries the words "by construction" next to the
figure.

---

## (i) Uncertainty on every headline number — block bootstrap

Confidence intervals were required on the Layer 3 quantiles but not on
**expectancy per session**, which is the number every kill criterion actually turns
on. Fixed.

### i.1 Method

```
method        moving block bootstrap
block         1 CALENDAR MONTH          # respects autocorrelation and volatility
                                        # clustering; daily resampling would
                                        # understate the interval badly
n_resamples   10,000
statistic     expectancy per session ($, MNQ), and every metric in the kill criteria
output        point estimate + 95% percentile interval
```

Monthly blocks are used because trading-day outcomes are **not** independent:
volatility clusters, regimes persist for weeks, and a strategy conditioned on IB
range inherits that persistence. An i.i.d. daily bootstrap would produce an interval
perhaps 2–3x too narrow and make a noisy result look significant.

### i.2 PAIRED bootstrap for every control comparison

Strategy and control are computed **on the same resampled months**, and the
*difference* is the bootstrapped statistic:

```
for each of 10,000 resamples:
    sample months with replacement -> M*
    d* = expectancy_strategy(M*) - expectancy_control(M*)
report the 95% percentile interval of d*
```

Pairing removes the shared market-regime variance and is far more powerful than
comparing two independent intervals. **Two overlapping individual CIs do not mean
the difference is insignificant** — that is a common and serious error, and the
paired interval is the correct test.

### i.3 Kill criteria restated in CI terms

The §Step-1 kill criteria become:

```
PASS requires ALL of:
  1. 95% paired CI of (P0 - C1_stop_matched)  EXCLUDES zero, positive side
  2. P0 above the 90th percentile of the C2 shuffle distribution
  3. 95% paired CI of direction_value from C3  EXCLUDES zero, positive side
  4. ambiguous_bar_pct <= 15%, or the pessimistic/optimistic gap < the edge
  5. grid_robustness not in the 1-4 of 16 "spike" band (§g.0.1)
```

A point estimate that beats a control but whose paired interval straddles zero is
**not a pass**. It is a result consistent with no edge.

---

## Open items blocking full specification

1. `account_size` and `risk_per_trade` — needed for sizing only, not for research.
2. Exact data date range and data vendor.
3. Whether the broker tick feed provides **trades with aggressor side** only, or
   also **book depth**. Aggressor side unlocks §d.3 and a workable §d.1. Only book
   depth unlocks true absorption — seeing resting size consumed.
