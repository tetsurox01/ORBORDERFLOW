# 2026-02 -- LAYER 1 session census

**ILLUSTRATIVE, NOT A RESULT -- UNSEALED HOLDOUT DATA.**

Source: `nq_ohlcv1m_2010-07-01_2026-08-31.parquet` -- REAL NQ 1-minute bars.

Range: FORWARD_HOLDOUT 2026-01-01 .. 2026-08-31, unsealed 2026-09-15 (IVB-SPEC.md sec 0.2.3b UNSEAL #1).
These sessions are IN-SAMPLE from that date. Any statistic taken from this range must say so.

Geometry: `illustrate_layer1_trade()` -- a plain reading of the spec FOR DRAWING ONLY. Step 3 does not exist.
The sec b.9 profile-method sensitivity gate has NEVER been run on real bars, so every VAH / VAL / POC behind these rows is of unknown stability.

**This table sums nothing.** No totals, no win rate, no expectancy, no counts by outcome. One row per session, per-session values only.

Filtered sessions are drawn but carry no exit reason, R or net: P0 never takes those trades.

The `contract` column is the front month those bars come from. One contract per session, never spliced inside a session. Where a quarterly roll falls inside the month, the handover row is marked **ROLL**: the two contracts trade at DIFFERENT absolute prices, so a level must not be carried across that row by eye. P0 applies no roll-day filter.

| date | contract | outcome | direction | exit reason | R achieved | net |
|---|---|---|---|---|---|---|
| 2026-02-02 | NQH6 | no_fill | LONG | - | - | - |
| 2026-02-03 | NQH6 | no_fill | SHORT | - | - | - |
| 2026-02-04 | NQH6 | time_stop | SHORT | time_stop | +1.09R | +124.90 pt |
| 2026-02-05 | NQH6 | no_fill | SHORT | - | - | - |
| 2026-02-06 | NQH6 | no_fill | LONG | - | - | - |
| 2026-02-09 | NQH6 | time_stop | LONG | time_stop | +1.14R | +175.65 pt |
| 2026-02-10 | NQH6 | time_stop | LONG | time_stop | -0.32R | -37.60 pt |
| 2026-02-11 | NQH6 | no_fill | SHORT | - | - | - |
| 2026-02-12 | NQH6 | tp1 | SHORT | tp1 | +1.99R | +269.40 pt |
| 2026-02-13 | NQH6 | time_stop | LONG | time_stop | +0.56R | +68.65 pt |
| 2026-02-16 | NQH6 | filtered:half_day | LONG | n/a (filtered) | n/a (filtered) | n/a (filtered) |
| 2026-02-17 | NQH6 | hard_stop | SHORT | hard_stop | -1.01R | -258.35 pt |
| 2026-02-18 | NQH6 | no_fill | LONG | - | - | - |
| 2026-02-19 | NQH6 | time_stop | LONG | time_stop | -0.09R | -7.85 pt |
| 2026-02-20 | NQH6 | time_stop | LONG | time_stop | +0.15R | +18.65 pt |
| 2026-02-23 | NQH6 | time_stop | SHORT | time_stop | +0.70R | +96.40 pt |
| 2026-02-24 | NQH6 | no_fill | LONG | - | - | - |
| 2026-02-25 | NQH6 | no_breakout | - | - | - | - |
| 2026-02-26 | NQH6 | no_fill | SHORT | - | - | - |
| 2026-02-27 | NQH6 | no_fill | LONG | - | - | - |

Charts: `C:/Users/user/Desktop/ORB + Order flow/output/charts/2026-02`
