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
BACKWARD_HOLDOUT   2010-01-01 .. 2014-12-31     SEALED
DEVELOPMENT        2015-01-01 .. ~80% point     all of Steps 1-5 happen here
FORWARD_HOLDOUT    ~80% point .. present        SEALED
```

The 80% point is computed by **session count**, not calendar date, over the
2015-to-present sample, and written once to `data/partitions.json`. On a
2015→2026 sample it lands near **2024-05**.

| Partition | Approx. sessions | Purpose |
|---|---|---|
| `BACKWARD_HOLDOUT` 2010–2014 | ~1,255 | Second out-of-sample check. Different regime (post-GFC recovery, low vol, pre-2018 volmageddon). A strategy that works 2015+ but fails 2010–2014 is regime-dependent — a finding, not a disqualification, but it must be stated. |
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

1. **The sample is tiny.** A 30-minute IB gives **30 bars**. That is 30 volume
   observations spread over a range that, at `bin_size = 1.0 pt` and a typical NQ
   IB, is 30–60 bins. There are fewer observations than bins. A POC built from that
   is a weak statistic by construction, before any distribution assumption is even
   applied. At `ib_minutes = 15` it is 15 bars and the problem roughly doubles.
2. **The assumption sits directly on the decision boundaries.** VAH is the entry
   and VAL is the stop. A distribution assumption that shifts VAL by a few ticks
   shifts `risk_R` — and therefore every R multiple, the stop-out rate, and the
   headline R:R claim in §c.3.

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

### b.2 Volume distribution method

```
bin_size   DEFAULT 1.0 pt (4 ticks)      range 0.25 - 2.0 pt
bins       from floor(IB_low / bin) to ceil(IB_high / bin)
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
across `bin_size` in {0.5, 1.0, 2.0}, in ticks.

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

Measured on the synthetic preview: **21.4% of fills** (77 / 360). Below the
threshold, so front-of-queue stays primary — but this is random-walk data and the
number must be re-measured on real NQ bars before it decides anything.

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
d_fill_rate = max - min of the four fill rates, in percentage points
```

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

#### The gate is decided on REAL bars only

This test reads volume, so it can only be *decided* on real NQ bars. A synthetic
generator that draws bar volume independently of price — which the one in
`tests/make_synthetic.py` does, `rng.integers(200, 2000)` — leaves no volume
structure for a profile to find. `POC` is then a random draw, the four methods
disagree freely, and the gate trips every time. Running it on synthetic data is a
useful check that the gate *fires*; its verdict is not admissible.

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
| `bin_size_pts` | 1.0 | 0.25 – 2.0 | |
| `va_pct` | 0.70 | 0.60 – 0.80 | |
| `poc_tiebreak` | `nearest_ib_mid` | — | deterministic |
| `entry_variant` | `E1` | {E1, E2, E3} | E1 = VA edge |
| `require_penetration_ticks` | 0 | 0 – 2 | limit-fill realism |
| `min_zone_width_ticks` | 2 | 1 – 8 | degenerate zone guard |
| `reload_timeout_min` | 30 | 10 – 60 | |
| `tf_inval_min` | 5 | {1, 3, 5, 15} | |
| `inval_buffer_ticks` | 0 | 0 – 4 | |
| `hard_stop_ticks` | 8 | 4 – 20 | beyond the far VA boundary |
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
    bin_size_pts           = 1.0
    va_pct                 = 0.70
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

### g.1 The 15 / 60-minute IB check — CONFIRMED, once, at the end

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
BACKWARD_HOLDOUT  2010-2014          SEALED. Not touched by Steps 1-5.
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
| minus `min_ib_range_atr` filter | ~95% [MEASURE] | **~2,228** | new filter, §f |
| **Breakout fires by 11:30** (IB30, close-through) | **~80% [MEASURE]** (plausible 70–90%) | **~1,782 = `S_breakout`** | The 90-minute post-IB window is the binding constraint. |
| **Retrace touches the reload zone** in time | **~50% [MEASURE]** (plausible 35–65%) | **~891 = `S_filled`** | The zone is **inside** the IB (§b.1), so this needs a deep retrace. Most uncertain number here. |
| Layer 2 confirmation fires | ~50% [MEASURE] | ~446 | Not measurable without tick data. |

Sealed and untouched: `BACKWARD_HOLDOUT` ~1,255 sessions, `FORWARD_HOLDOUT` ~585.

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
