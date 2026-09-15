# 2026-01 -- LAYER 1 session census

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
| 2026-01-02 | NQH6 | no_fill | SHORT | - | - | - |
| 2026-01-05 | NQH6 | no_fill | LONG | - | - | - |
| 2026-01-06 | NQH6 | no_fill | LONG | - | - | - |
| 2026-01-07 | NQH6 | time_stop | LONG | time_stop | +0.33R | +24.40 pt |
| 2026-01-08 | NQH6 | time_stop | SHORT | time_stop | -0.16R | -18.60 pt |
| 2026-01-09 | NQH6 | hard_stop | SHORT | hard_stop | -1.01R | -94.35 pt |
| 2026-01-12 | NQH6 | time_stop | LONG | time_stop | +0.31R | +25.65 pt |
| 2026-01-13 | NQH6 | tp1 | SHORT | tp1 | +1.98R | +101.90 pt |
| 2026-01-14 | NQH6 | time_stop | SHORT | time_stop | +0.19R | +22.90 pt |
| 2026-01-15 | NQH6 | hard_stop | SHORT | hard_stop | -1.02R | -63.85 pt |
| 2026-01-16 | NQH6 | no_fill | SHORT | - | - | - |
| 2026-01-19 | NQH6 | filtered:half_day | LONG | n/a (filtered) | n/a (filtered) | n/a (filtered) |
| 2026-01-20 | NQH6 | time_stop | LONG | time_stop | +0.80R | +61.15 pt |
| 2026-01-21 | NQH6 | no_fill | LONG | - | - | - |
| 2026-01-22 | NQH6 | time_stop | SHORT | time_stop | -0.74R | -74.60 pt |
| 2026-01-23 | NQH6 | no_fill | LONG | - | - | - |
| 2026-01-26 | NQH6 | time_stop | LONG | time_stop | +0.77R | +65.15 pt |
| 2026-01-27 | NQH6 | no_fill | LONG | - | - | - |
| 2026-01-28 | NQH6 | no_fill | SHORT | - | - | - |
| 2026-01-29 | NQH6 | no_fill | SHORT | - | - | - |
| 2026-01-30 | NQH6 | hard_stop | SHORT | hard_stop | -1.02R | -64.10 pt |

Charts: `C:/Users/user/Desktop/ORB + Order flow/output/charts/2026-01`

---

**A superseded set of charts for this month is archived in `PRE_RULE_A/`.** Those files were drawn under the ORIGINAL sec b.2 bin-width rule and the zero-anchored grid, both replaced on 2026-09-15 (sec b.2 AMENDMENT 1 and AMENDMENT 2). They are VOID: kept as the record of the defect, quotable as evidence about nothing. `VOID.md` in this folder explains why and maps each superseded chart to the chart that replaced it.
