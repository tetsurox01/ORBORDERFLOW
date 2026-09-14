# IVB Research Plan v0.1

Companion to `IVB-SPEC.md`. Order is fixed. A step may not start until the step
above it has produced a reported result, pass or fail.

**Reporting standard for every step:** sample size, expectancy in R and in $,
profit factor, win rate, max drawdown, MAE and MFE distributions, results split by
year and by session type, and the cost assumptions used. Never a single headline
number.

---

## Step 1 — Baseline: plain IB breakout (the null hypothesis)

### Hypothesis

> The first side to break the 30-minute NY initial balance produces positive
> expectancy per session on NQ, after commission and slippage, with a fixed R
> target and a flat exit at 11:30 ET.

### What is run

**P0, the pre-registered primary configuration** (`IVB-SPEC.md` §g.0):
`ib=30, close_through, buffer=1 tick, entry=next_bar_open, stop=opposite_ib_extreme,
R_mult=2.0, min_ib_range_atr=0.15, MNQ costs, pessimistic intrabar, DEVELOPMENT`.

**Kill criteria apply to P0 alone.** Everything below is a labelled sensitivity
appendix that can never pass, fail, or rescue a gate:

- The 16-configuration grid: 4 R-targets x 2 stop variants x 2 triggers. Reported
  as a full table plus `grid_robustness` (§g.0.1). **Never as a best case.**
- `ib_minutes` in {15, 60}: run ONCE, at the very end, after P0 is finalised (§g.1).
- Results broken out **by IB-range decile** (§f reporting requirement).
- Both cost models (NQ and MNQ) side by side; MNQ judges.

### Output tables

1. Per-configuration summary (N trades, expectancy R, expectancy $, PF, win rate,
   max DD, avg MAE, avg MFE).
2. Per-year breakdown for the primary configuration.
3. Split by direction (long vs short) — critical, see adversarial checks.
4. Split by release day vs non-release day.
5. `ambiguous_bar_pct` — the intrabar-sequence problem rate (§a.5).
6. Breakout timing histogram: minutes from `IB_close_t` to break.
7. `remaining_range_after_IB / IB_range` by `ib_minutes` — the N = 60 kill test.

### Control suite — four controls, each isolating a different claim

The strategy makes one core claim: **the side that breaks the IB first carries
directional information.** Each control below removes one alternative explanation.
All four run at the same costs, same stops, same targets, same intrabar rule.

#### C1 — Drift control: "buy the window"

```
Enter long at IB_close_t every session. Flat at 11:30 ET. No stop, no target.
```
Removes: *"NQ just goes up during the morning."*
The source video compares to buy-and-hold S&P — that is this trap, and it is not a
valid control because it does not match the holding period.

Also run a **stop-matched** variant (same stop and target structure, always long)
so the comparison is not confounded by the exit rules.

#### C2 — Coin-flip direction

```
At the breakout bar, take the trade in a RANDOM direction (p = 0.5),
independent of which side actually broke.
Same entry price, same stop distance, same target, same intrabar rule.
1000 independent shuffles -> a full distribution of outcomes.
```
Removes: *"any trade with this stop/target geometry at this time of day makes
money."*

Reports the strategy's **percentile rank** within the 1000-run distribution, and a
one-sided empirical p-value. This is the closest thing to a significance test that
respects the actual trade structure.

Note: C2 must **re-randomise the direction, not the timing**. Entry time, stop
distance and target distance stay identical to the real strategy, so the *only*
thing being tested is the direction signal.

#### C3 — Inversion: fade the break

You caught a genuine contradiction in the previous draft: the code block said "same
stop distance, same target distance" while the prose said "stop and target swap
roles". Those are two different experiments. **Resolved — the same-distance reading
is pre-registered, and the swap reading is rejected.**

```
C3 "GEOMETRY-PRESERVING INVERSION"  -- pre-registered

Take the opposite SIDE of every real signal, holding geometry fixed.
  Real:    break above IB_high -> LONG  at entry E, stop E - d, target E + 2d
  C3:      break above IB_high -> SHORT at entry E, stop E + d, target E - 2d

Same entry price. Same stop DISTANCE d. Same target DISTANCE 2d.
Same R_mult, same time stop, same intrabar rule, same costs.
ONLY the sign of the direction changes.
```

**Why the swap reading is rejected.** Under it, the inverted trade would use the
real trade's target level as its stop, giving a 2R stop and a 1R target at
`R_mult = 2.0`. That is a structurally different bet — different win rate, different
payoff ratio, different exposure to the intrabar rule. Differencing it against the
strategy would mix *direction* with *geometry*, and the resulting number would
answer neither question. The same-distance reading isolates direction, which is the
only thing C3 exists to test.

```
direction_value = (PnL_strategy - PnL_inverse) / 2
```

**This formula is valid ONLY under the same-distance reading.** If C3 is ever re-run
under the swap reading, `direction_value` must not be computed from it.

Two things still do **not** cancel between the two legs, and must be stated when the
result is reported:

1. **Costs are paid twice, not negated.** Both legs pay full commission and
   slippage, so `PnL(strategy) + PnL(inverse) ≈ -2 × total costs` even under a pure
   coin flip. So the test is *not* "did the strategy beat its inverse" — both can
   lose. `direction_value` is the correct read because it differences the shared
   cost drag out.
2. **The pessimistic intrabar rule (`IVB-SPEC.md` §a.5) is not symmetric.** The long
   leg's stop sits below entry and the short leg's above, so a given bar resolves
   differently for each. The rule penalises whichever leg is in the trade and does
   not cancel.

If `direction_value` is not clearly positive — **95% paired block-bootstrap CI
excluding zero** (`IVB-SPEC.md` §i.2) — and stable across years, the breakout
direction carries no information, and everything above Layer 0 is decoration.

#### C4 — Random-time control

```
Same direction rule, but enter at a RANDOM minute after IB_close_t
rather than at the breakout.
```
Removes: *"the level does not matter, only being in the market at that hour does."*

#### Denominator for all controls — CONFIRMED: `S_all`

**Confirmed as you specified.** All four controls and the strategy are evaluated on
**`S_all`**, with non-breakout days entering the strategy's numerator as **zero**.

Your reasoning is right, and it is worth recording why, because C1 differs from the
other three:

| Control | Opportunity set | Does the denominator choice matter? |
|---|---|---|
| **C1** drift | **`S_all`** — trades every session | **Yes, decisively.** C1 trades days the strategy sits out. Comparing on `S_breakout` would silently delete C1's performance on exactly those days. Apples to oranges, as you said. |
| C2 coin-flip | `S_breakout` | No — identical zeros added to both sides, identical denominators. `S_all` used anyway for one common basis. |
| C3 inversion | `S_breakout` | No — same reason. |
| C4 random-time | `S_breakout` | No — same reason. |

So `S_all` is **required** for C1 and **harmless** for C2/C3/C4. Using it everywhere
gives one common basis at no cost.

**This is not an exception to `IVB-SPEC.md` §g.2 — it is that rule applied.** §g.2
says: use the denominator of the **wider** of the two things being compared. For the
controls, C1 is wider (`S_all`), so `S_all` wins. For Layer 0 vs Layer 1, Layer 0 is
wider (`S_breakout`), so `S_breakout` wins. One rule, two comparisons.

One consequence to carry through: expectancy per `S_all` session is a **smaller
number** than expectancy per breakout session, because ~20% of days contribute zero.
The block-bootstrap CIs (`IVB-SPEC.md` §i) must be computed on the **same basis** as
the point estimate they sit next to. Never mix bases within a table.

#### Control results table — report all together

All rows on `S_all`, MNQ cost model, P0 configuration.

| | Expectancy / `S_all` session | PF | Max DD | 95% paired CI vs P0 | Gate |
|---|---|---|---|---|---|
| **P0 strategy (primary)** | | | | — | — |
| C1 drift, stop-matched | | | | | CI must exclude zero |
| C2 coin-flip (median of 1000) | | | | percentile rank + p-value | P0 above 90th pct |
| C3 inversion | | | | `direction_value` CI | must exclude zero |
| C4 random-time | | | | | |

### Other adversarial checks

| Check | Why |
|---|---|
| **Long/short split** | NQ has a strong upward drift over most samples. If the whole edge sits in the longs, this may be drift, not a breakout edge. C1 and C3 partly control for it, but the split must still be shown. |
| **Cost sensitivity** | Re-run at 0, 1, 2, 3 ticks of slippage. If the edge dies at 2 ticks, it is not tradeable on a stop order in NQ. |
| **Zero-cost delta** | Report the gross-versus-net gap explicitly. A large gap means the strategy lives or dies on execution quality. |
| **First vs second half of sample** | Split by date. A result present in only one half is a regime artefact. |
| **Pessimistic vs optimistic intrabar** | Per §a.5. If the gap between the two runs exceeds the edge, there is no measurable edge at 1-minute resolution. |
| **With vs without roll days** | Per §0.1.4. A material difference means roll handling is doing work it should not. |

### Kill criteria — fixed in advance

Layer 0 is declared **not an edge** and the project stops if **any** of these holds:

1. The **95% paired block-bootstrap CI** of `(P0 - C1_stop_matched)` does not
   exclude zero on the positive side. A point estimate that beats C1 with a CI
   straddling zero is **not a pass**.
2. P0 sits **below the 90th percentile** of the **C2** coin-flip distribution.
3. The **95% paired CI** of `direction_value` from **C3** does not exclude zero, or
   the sign flips between the first and second half of the sample.
4. `ambiguous_bar_pct` exceeds 15% **and** the pessimistic/optimistic gap exceeds
   the measured edge.
5. `grid_robustness` falls in the **1-4 of 16 "spike" band** (`IVB-SPEC.md` §g.0.1)
   — a narrow spike is evidence AGAINST P0 even when P0 passes 1-4 in isolation.

All criteria are evaluated at **P0 only**, on **`S_all`**, under the **MNQ** cost
model, on the **DEVELOPMENT** partition. Holdouts stay sealed.

Say so plainly and stop. Layers 1–3 cannot rescue a non-existent directional base —
they only reshape how a zero-expectancy signal is traded.

### Data required

1-minute OHLCV NQ, RTH plus the overnight session (for `on_range_atr`), with prior
RTH closes. **You have this.** Runnable now.

---

## Step 2 — Rebuild the "protection level" as a conditional MFE distribution

This is the central quantitative deliverable.

### Framing

The source calls it a proprietary algo-derived level with a claimed 65–70% hit
rate. Restated as a statistics problem:

> Given a breakout with features known **at breakout time**, what is the
> distribution of maximum favourable excursion (MFE) before the stop is hit or the
> session ends? TP1 is the excursion level whose conditional exceedance probability
> is 0.65–0.70. TP2 is the extended tail.

Note the arithmetic: a level hit 67.5% of the time is the **32.5th percentile** of
the MFE distribution. Quantile estimation, not classification.

### Target variable — TWO quantities, because one does not transfer

You identified a real defect: MFE-before-stop is measured under the **Layer 0** stop
(opposite IB extreme), but Step 3 moves the stop to **VAL**. A quantile fitted under
one stop geometry is not valid under another — a wider stop lets more paths survive
to make new highs, so it mechanically produces a larger MFE distribution. Carrying
that TP1 into Step 3 would overstate the target.

**Resolution: define both, use each for its own job.**

```
MFE_raw          = max favourable excursion from entry_price to 11:30 ET,
                   WITH NO STOP APPLIED.
                   A property of the MARKET. Geometry-independent.
                   Transfers across layers unchanged.

MFE_net(g)       = max favourable excursion from entry_price until the stop is hit
                   under geometry g, or 11:30 ET, whichever comes first.
                   A property of the STRATEGY. Geometry-specific.
                   Does NOT transfer. Must be re-estimated per geometry.
```

### Which is used where

| Use | Quantity | Why |
|---|---|---|
| Comparing geometries to each other | `MFE_raw` | The only common yardstick. Layer 0 and Layer 1 excursions are measurable on the same scale. |
| Feature selection, bucket design, model form | `MFE_raw` | The *method* is what transfers. Developing it on the stop-free series avoids re-doing the work per layer. |
| **TP1 actually traded in Step 1 (Layer 0)** | **`MFE_net(Layer 0)`** | Fitted under the opposite-IB-extreme stop. |
| **TP1 actually traded in Step 3 (Layer 1)** | **`MFE_net(Layer 1)`** | **Re-estimated from scratch** under the VAL stop. |

> **The method transfers. The number does not.** Step 2 delivers a fitting
> procedure plus a TP1 valid for Layer 0 geometry. Step 3 re-runs that same
> procedure under Layer 1 geometry and produces a different TP1. Any Step 3 result
> that reuses the Step 1 TP1 number is invalid.

### The bias in `MFE_raw`, stated plainly

`MFE_raw` ignores the stop, so it counts excursion on paths where the trader would
already have been stopped out and could never have reached it. It is therefore an
**upper bound**, and it is optimistic.

Mandatory reporting whenever `MFE_raw` appears:

```
shrinkage(g) = quantile(MFE_net(g), 0.325) / quantile(MFE_raw, 0.325)
```

Report `shrinkage` for both geometries. If it is near 1.0, the stop rarely binds
before the excursion and the two measures nearly agree. If it is far below 1.0, the
stop is doing most of the work and `MFE_raw` must never be quoted as a target.

`MFE_raw` is a **research instrument only**. It is never quoted as a tradeable TP1.

Compute MFE in four normalisations and test which is most stationary across years:
`points`, `ib_range` units, `ATR14` units, `R` units. The right normalisation is
the empirical question — do not assume `R`.

### Features available at breakout time

The `IVB-SPEC.md` §e.1 list, all of it. No feature may use any bar after the
breakout bar. Explicitly banned:

- The day's own realised ATR or range — must use **prior** close ATR.
- Session VWAP computed over the whole session — only expanding VWAP to the
  breakout bar.
- Full-sample quantiles, means, or medians for any normalisation — every
  normalising statistic must come from an expanding window over prior days only.
- Any bucket boundary fitted on the full sample.

### Method, in escalation order

1. **`bucket_empirical` (start here).** Coarse buckets on two or three features
   (`ib_range_atr`, `brk_delay`, direction). Within each bucket take the empirical
   32.5th percentile of MFE. Requires `min_obs_per_bucket >= 100`, which is the
   real constraint on how many features can be used.
2. **`quantile_reg`.** Linear quantile regression at tau = 0.325. Escalate only if
   it beats (1) out of sample.
3. **`gbm_quantile`.** Gradient boosting with pinball loss. Escalate only if it
   beats (2) out of sample by a margin large enough to survive the extra degrees of
   freedom. Default expectation: it will not.

### Validation without leaking

```
Walk-forward, expanding, by calendar year:
    fit on years 1..k  ->  predict year k+1  ->  never refit on k+1
```

No shuffled k-fold. Adjacent trading days share regime, overnight gaps, and open
positions in the wider market, so shuffling leaks.

### Calibration is the acceptance test

The claim is a **hit rate**, so the test is a calibration test, not a PnL test:

> On out-of-sample data, what fraction of trades actually reached the predicted
> TP1?

- Target 0.65–0.70. Report the realised rate with a binomial confidence interval.
- Report a reliability curve: predicted exceedance probability in deciles versus
  realised frequency.
- If the realised rate is near 0.50, the conditional model adds nothing over an
  unconditional quantile, and the honest answer is "use a flat TP1".
- **Also report the unconditional model as the control.** A single global 32.5th
  percentile of MFE is the thing the conditional model must beat. If it does not,
  the conditioning is noise.

### Second deliverable: is TP1 even the right objective?

A 67.5% hit rate is not the same as maximum expectancy. Once the MFE distribution
exists, directly compute expectancy across a sweep of fixed target levels and show
where the expectancy-maximising target sits relative to the 67.5% level. If they
disagree sharply, the "protection level" is a comfort metric, not an optimum. Say
so.

### Data required

Same 1-minute OHLCV. **Runnable now** — with one honest caveat: MFE measured from
1-minute bar highs/lows slightly overstates capturable excursion, because it
assumes an exit at a bar extreme. Report MFE both at the bar extreme and at the bar
close as a conservative bound.

---

## Step 3 — Add Layer 1 (profile entry and invalidation) and measure the delta

### Hypothesis

> Entering on the retracement into the `[VA edge, POC]` zone, with invalidation on
> a close beyond the far VA boundary, raises expectancy **per session** over the
> Layer 0 baseline — not merely R:R per trade.

### Gate before any PnL is computed

Run, in this order, and report all three **before** any Layer 1 PnL exists:

1. **POC stability across bin size** (`IVB-SPEC.md` §b.4).
2. **Profile method sensitivity** (`IVB-SPEC.md` §b.9) — the decisive one. It
   measures how far **VAH** (the entry) and **VAL** (the stop) move across the four
   allocation methods, against thresholds fixed in advance.
3. **TPO control** (§b.5) — the assumption-free comparison.

**If §b.9 returns MATERIAL, Layer 1 is downgraded to Layer 2 status:** not testable
with current data, results labelled `ASSUMPTION-SENSITIVE` only, and not usable as
the base for Layer 2 attribution. That consequence is fixed before the number is
seen so the threshold cannot be renegotiated afterwards.

### Also test the structural selection effect

The reload zone lies **inside** the IB (`IVB-SPEC.md` §b.1), so every Layer 1 trade
is a breakout that re-entered the range. Before trusting any Layer 1 result,
compare forward MFE for breakouts that re-enter the IB against those that do not.
If re-entering breakouts are materially worse, Layer 1 is trading an adversely
selected subset and no stop placement can fix that.

### The comparison must be per session, not per trade

This is the whole attribution problem in one sentence:

> Layer 1 skips every day that breaks out and never retraces. Those are
> disproportionately the best Layer 0 days.

So:

- Every session that produced a Layer 0 breakout enters the comparison.
- Layer 1 `no_fill` sessions enter as **zero PnL**, never excluded.
- The headline metric is **expectancy per session**, with expectancy per trade
  reported alongside it.
- Report `fill_rate` — the share of breakout sessions where the zone was touched in
  time. This number alone decides whether Layer 1 can work.

### What is measured

| Metric | Layer 0 | Layer 1 | Delta |
|---|---|---|---|
| Sessions | | | |
| Trades taken | | | |
| Fill rate | 100% | | |
| Expectancy / session ($) | | | |
| Expectancy / trade (R) | | | |
| Realised R:R | | | |
| Stop-out rate | | | |
| Profit factor | | | |
| Max DD | | | |

Run all three exit regimes (`close_only`, `close_plus_hard`, `hard_only`) and all
three entry variants (E1, E2, E3). Report `touch_only_fills` separately and re-run
with `require_penetration_ticks = 1`.

### Kill criterion

If Layer 1 raises expectancy per trade but lowers expectancy per session, it is
cosmetic. Kill it, and say plainly that the 1:2 R:R claim is achieved by discarding
trades rather than by adding edge.

### Data required

Same 1-minute OHLCV, **plus an explicit caveat on every output**: the volume
profile is an estimate built by distributing bar volume across bar ranges. It is
not volume-at-price. This limitation cannot be removed without tick data.

---

## Step 4 — Add Layer 2 (order flow) and measure the delta

### Status: CANNOT BE RUN WITH CURRENT DATA

All three triggers require trade-level data with aggressor side. The 1-minute bar
proxies in `IVB-SPEC.md` §d are bar-pattern detectors, not order flow. Running them
would produce a number that is neither evidence for nor against the order flow
thesis, and having that number in the project would corrupt every later decision.

**Recommendation: do not run the proxies at all.** If they are run anyway, label
every output `PROXY — NOT ORDER FLOW` and exclude it from the attribution chain.

### Hypothesis for when data arrives

> Requiring an absorption, exhaustion, or aggression trigger inside the Layer 1
> zone raises expectancy per unit of risk, not merely trade count reduction.

### The test that matters

Layer 2 reduces trade count by construction. So the acceptance test is the same
shape as Layer 3's:

- Expectancy per session must rise, not just expectancy per trade.
- Each of the three triggers must be attributed **separately** before any
  combination is tested. A combined "any_of" rule that works while no individual
  trigger works is curve fitting.
- Report the no-confirmation trades as a control group: if trades *without*
  confirmation perform the same, the trigger carries no information.

### Data required (see §5)

Trades with aggressor side, minimum. Book depth for true absorption.

---

## Step 5 — Data requirements, step by step

### What you have

1-minute OHLCV NQ. Date range and vendor still unspecified — **please fill in**,
because sample size decides how much of Step 2 is viable.

### Sample size needed — and the funnel

Full funnel, bucket-cell counts and the fallback rules are in **`IVB-SPEC.md` §h**.
Summary of where it gets thin:

| Stage | 10 years | 5 years |
|---|---|---|
| `S_all` tradeable sessions | ~2,470 | ~1,235 |
| `S_breakout` (~80% [MEASURE]) | ~1,975 | ~990 |
| `S_filled` — breakout **and** retrace (~50% [MEASURE]) | ~990 | ~495 |
| Layer 2 confirmed (~50% [MEASURE]) | ~495 | ~250 |
| **Layer 3: mean obs per bucket cell (18 cells)** | ~110 | ~55 |
| **Layer 3: realistic smallest cell** | **~25–40** | **~12–20** |
| **Cells clearing `min_obs_per_bucket = 100`** | 6–9 of 18 | **0–2 of 18** |

| Purpose | Sessions needed | Years (approx) |
|---|---|---|
| Step 1 baseline, primary config | ~500 | 2 |
| Step 1 with per-year splits and the C2 shuffle | ~1,250 | 5 |
| Step 2, **unconditional** MFE quantile | ~400 breakouts | 2 |
| Step 2, **conditional** buckets at 100 obs/cell | ~1,800+ breakouts | 8–10 |
| Step 2 with walk-forward by year (needs several test folds) | ~2,000 breakouts | 8–10 |
| Step 3, Layer 1 delta (fill rate near 50% halves the sample) | ~2x Step 1 | 8–10 |

**Practical target: 8–10 years of 1-minute NQ.**

**Below 5 years, the conditional protection level is not estimable** and Step 2
runs in unconditional form only (`IVB-SPEC.md` §h.3 rule 4). That is a legitimate
result to report, not a failure — and it is far better than publishing a
conditional TP1 built on 15 observations per cell.

### Per-step data table

| Step | Data needed | Have it? | Honest verdict |
|---|---|---|---|
| 1 — Baseline | 1-min OHLCV RTH + overnight, prior RTH close, holiday/half-day calendar, economic release calendar, **contract roll calendar** | Yes, except the three calendars | **Runnable.** Calendars are easy to source. The roll calendar is required, not optional — see `IVB-SPEC.md` §0.1. |
| 2 — Protection level | Same as Step 1 | Yes | **Runnable**, with the bar-extreme MFE caveat. Needs the full date range to be confirmed. |
| 3 — Layer 1 | Same as Step 1 | Yes | **Runnable only if the §b.9 gate passes.** The profile is estimated, not measured, and a 30-min IB gives just 30 bars. If VAH/VAL move materially across allocation methods, Layer 1 joins Layer 2 as not-testable. Labelled as an approximation everywhere regardless. |
| 4 — Layer 2 | Trades with aggressor side; book depth for true absorption | No | **NOT RUNNABLE. Do not fake it.** |
| 5 — Classifier | Same as Step 1 | Yes | **Runnable.** |
| 6 — Inverse model | Layer 2 triggers at the IB extremes | No | **NOT RUNNABLE** — the entry requires absorption/exhaustion confirmation. A version without confirmation can be run as a crude control. |

### Things you also need that are not price data

1. **CME holiday and early-close calendar** — for the whole sample. Half days
   distort both the IB and the 11:30 exit.
2. **US economic release calendar** — at minimum the 08:30 and 10:00 ET releases,
   and FOMC days. Needed for the `is_release_day` feature and for the N = 15
   hazard split in §a.6.
3. **Contract roll dates** — volume-crossover based. Only needed to pick the right
   front month per session; no price adjustment is required, since every
   measurement is intra-session.

### For Step 4, what to buy and what it unlocks

| Data level | Example source | Unlocks |
|---|---|---|
| Trades with aggressor side | Databento `GLBX.MDP3` `trades` schema | Real delta, footprint imbalance (§d.3), a workable absorption ratio (§d.1) |
| Top of book | `mbp-1` | Better absorption — lets you see size resting at the touch |
| Full book | `mbo` | True absorption: resting size being consumed, iceberg behaviour, queue dynamics |

**Recommendation:** start with the `trades` schema. It unlocks §d.3 fully and §d.1
usefully, at a fraction of the storage and cost of MBO. Buy a **6-month sample
first** and confirm the triggers can even be computed and that they fire often
enough to produce a usable sample, before buying ten years.

Cost warning: a decade of NQ tick data is large. Do not buy it before Steps 1–3
have shown there is a directional base worth confirming. If Step 1 fails, Step 4
never happens and the data spend is saved.

---

## Sequencing summary

```
Step 1  Baseline           -> runnable now   -> gate: must beat drift + shuffle controls
Step 2  Protection level   -> runnable now   -> gate: out-of-sample calibration 0.65-0.70
Step 5  Classifier         -> runnable now   -> gate: must beat the 3-bucket ATR rule
Step 3  Layer 1 delta      -> runnable now   -> gate: expectancy PER SESSION must rise
------------------------------ tick data purchase decision point ------------------------------
Step 4  Layer 2            -> blocked        -> gate: each trigger attributed separately
Step 6  Inverse model      -> blocked
```

The tick data decision comes **after** Steps 1, 2, 3 and 5. That ordering exists
specifically so a failed baseline costs nothing.
