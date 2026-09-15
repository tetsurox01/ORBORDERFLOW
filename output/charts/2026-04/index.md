# 2026-04 -- LAYER 1 session census

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
| 2026-04-01 | NQM6 | time_stop | LONG | time_stop | +0.86R | +85.40 pt |
| 2026-04-02 | NQM6 | no_fill | LONG | - | - | - |
| 2026-04-06 | NQM6 | no_breakout | - | - | - | - |
| 2026-04-07 | NQM6 | no_fill | SHORT | - | - | - |
| 2026-04-08 | NQM6 | time_stop | SHORT | time_stop | +0.71R | +60.65 pt |
| 2026-04-09 | NQM6 | no_fill | SHORT | - | - | - |
| 2026-04-10 | NQM6 | filtered:vendor_degraded | SHORT | n/a (filtered) | n/a (filtered) | n/a (filtered) |
| 2026-04-13 | NQM6 | time_stop | LONG | time_stop | +0.31R | +30.90 pt |
| 2026-04-14 | NQM6 | no_fill | LONG | - | - | - |
| 2026-04-15 | NQM6 | no_fill | LONG | - | - | - |
| 2026-04-16 | NQM6 | no_fill | LONG | - | - | - |
| 2026-04-17 | NQM6 | tp1 | LONG | tp1 | +1.98R | +101.90 pt |
| 2026-04-20 | NQM6 | no_fill | SHORT | - | - | - |
| 2026-04-21 | NQM6 | no_fill | LONG | - | - | - |
| 2026-04-22 | NQM6 | tp1 | LONG | tp1 | +1.98R | +90.90 pt |
| 2026-04-23 | NQM6 | no_fill | LONG | - | - | - |
| 2026-04-24 | NQM6 | hard_stop | LONG | hard_stop | -1.02R | -61.85 pt |
| 2026-04-27 | NQM6 | no_breakout | - | - | - | - |
| 2026-04-28 | NQM6 | no_fill | SHORT | - | - | - |
| 2026-04-29 | NQM6 | no_fill | LONG | - | - | - |
| 2026-04-30 | NQM6 | hard_stop | SHORT | hard_stop | -1.01R | -133.85 pt |

Charts: `C:/Users/user/Desktop/ORB + Order flow/output/charts/2026-04`
