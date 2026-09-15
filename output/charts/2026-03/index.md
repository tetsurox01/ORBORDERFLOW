# 2026-03 -- LAYER 1 session census

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
| 2026-03-02 | NQH6 | time_stop | LONG | time_stop | -0.18R | -19.10 pt |
| 2026-03-03 | NQH6 | hard_stop | SHORT | hard_stop | -1.01R | -102.35 pt |
| 2026-03-04 | NQH6 | tp1 | LONG | tp1 | +1.99R | +162.40 pt |
| 2026-03-05 | NQH6 | hard_stop | LONG | hard_stop | -1.01R | -95.60 pt |
| 2026-03-06 | NQH6 | tp1 | LONG | tp1 | +1.98R | +124.40 pt |
| 2026-03-09 | NQH6 | no_fill | LONG | - | - | - |
| 2026-03-10 | NQH6 | hard_stop | SHORT | hard_stop | -1.02R | -64.10 pt |
| 2026-03-11 | NQH6 | hard_stop | LONG | hard_stop | -1.02R | -58.35 pt |
| 2026-03-12 | NQH6 | time_stop | SHORT | time_stop | +0.60R | +81.15 pt |
| 2026-03-13 | NQH6 | no_fill | SHORT | - | - | - |
| 2026-03-16 | NQH6 | filtered:vendor_degraded | LONG | n/a (filtered) | n/a (filtered) | n/a (filtered) |
| 2026-03-17 | **NQM6** (ROLL: NQH6 -> NQM6) | no_breakout | - | - | - | - |
| 2026-03-18 | NQM6 | no_fill | SHORT | - | - | - |
| 2026-03-19 | NQM6 | time_stop | LONG | time_stop | +0.05R | +6.15 pt |
| 2026-03-20 | NQM6 | no_fill | SHORT | - | - | - |
| 2026-03-23 | NQM6 | time_stop | LONG | time_stop | +0.21R | +25.40 pt |
| 2026-03-24 | NQM6 | time_stop | LONG | time_stop | +0.63R | +76.65 pt |
| 2026-03-25 | NQM6 | hard_stop | SHORT | hard_stop | -1.01R | -127.10 pt |
| 2026-03-26 | NQM6 | no_breakout | - | - | - | - |
| 2026-03-27 | NQM6 | time_stop | SHORT | time_stop | -0.09R | -9.60 pt |
| 2026-03-30 | NQM6 | time_stop | SHORT | time_stop | -0.16R | -26.35 pt |
| 2026-03-31 | NQM6 | hard_stop | LONG | hard_stop | -1.01R | -130.10 pt |

Charts: `C:/Users/user/Desktop/ORB + Order flow/output/charts/2026-03`
