# 2026-02 -- LAYER 1 session census

**ILLUSTRATIVE, NOT A RESULT -- UNSEALED HOLDOUT DATA.**

Source: `nq_ohlcv1m_2010-07-01_2026-08-31.parquet` -- REAL NQ 1-minute bars.

Range: FORWARD_HOLDOUT 2026-01-01 .. 2026-08-31, unsealed 2026-09-15 (IVB-SPEC.md sec 0.2.3b UNSEAL #1).
These sessions are IN-SAMPLE from that date. Any statistic taken from this range must say so.

Geometry: `illustrate_layer1_trade()` -- a plain reading of the spec FOR DRAWING ONLY. Step 3 does not exist.
The sec b.9 profile-method sensitivity gate has NEVER been run on real bars, so every VAH / VAL / POC behind these rows is of unknown stability.

**This table sums nothing.** No totals, no win rate, no expectancy, no counts by outcome. One row per session, per-session values only.

Filtered sessions are drawn but carry no exit reason, R or net: P0 never takes those trades.

| date | outcome | direction | exit reason | R achieved | net |
|---|---|---|---|---|---|
| 2026-02-02 | no_fill | LONG | - | - | - |
| 2026-02-03 | no_fill | SHORT | - | - | - |
| 2026-02-04 | time_stop | SHORT | time_stop | +1.09R | +124.90 pt |
| 2026-02-05 | no_fill | SHORT | - | - | - |
| 2026-02-06 | no_fill | LONG | - | - | - |
| 2026-02-09 | time_stop | LONG | time_stop | +1.14R | +175.65 pt |
| 2026-02-10 | time_stop | LONG | time_stop | -0.32R | -37.60 pt |
| 2026-02-11 | no_fill | SHORT | - | - | - |
| 2026-02-12 | tp1 | SHORT | tp1 | +1.99R | +269.40 pt |
| 2026-02-13 | time_stop | LONG | time_stop | +0.56R | +68.65 pt |
| 2026-02-16 | filtered:half_day | LONG | n/a (filtered) | n/a (filtered) | n/a (filtered) |
| 2026-02-17 | hard_stop | SHORT | hard_stop | -1.01R | -258.35 pt |
| 2026-02-18 | no_fill | LONG | - | - | - |
| 2026-02-19 | time_stop | LONG | time_stop | -0.09R | -7.85 pt |
| 2026-02-20 | time_stop | LONG | time_stop | +0.15R | +18.65 pt |
| 2026-02-23 | time_stop | SHORT | time_stop | +0.70R | +96.40 pt |
| 2026-02-24 | no_fill | LONG | - | - | - |
| 2026-02-25 | no_breakout | - | - | - | - |
| 2026-02-26 | no_fill | SHORT | - | - | - |
| 2026-02-27 | no_fill | LONG | - | - | - |

Charts: `C:/Users/user/Desktop/ORB + Order flow/output/charts/2026-02`
