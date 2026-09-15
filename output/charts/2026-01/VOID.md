# ***** VOID -- THE CHARTS IN `PRE_RULE_A/` SUPERSEDED, DO NOT READ THEIR LEVELS *****

**Voided 2026-09-15. Superseded by a redraw 2026-09-15. Nothing was deleted.**

## What happened, in order

1. **2026-09-15, voided.** Every chart then in this folder had been drawn under
   the ORIGINAL sec b.2 bin-width rule and the zero-anchored profile grid. Both
   were replaced the same day (IVB-SPEC.md sec b.2 AMENDMENT 1 and AMENDMENT 2).
   The charts were marked void and deliberately NOT redrawn.
2. **2026-09-15, redrawn.** All 21 sessions were redrawn on the FIXED grid.
   The 21 superseded PNGs were MOVED, byte-untouched and under their original
   filenames, into `PRE_RULE_A/`. The superseded index table was copied there as
   `PRE_RULE_A/index_VOID.md`. The void banner was then lifted from `index.md`,
   which now describes the post-fix charts in this folder.

## Why the superseded charts are wrong

1. **The volume profile had about 5 bins across the whole initial balance**, not
   20. Median measured over 2,365 real sessions was 5.28 to 5.97 bins in every
   year 2015-2026. A POC, a VAH and a VAL resolved on a 5-bin histogram are not
   locations.
2. **The value-area edges could sit OUTSIDE the initial balance they were built
   from.** 46.6% of measured sessions had VAH above IB_high or VAL below IB_low.
   On `2026-01-09` VAH sat **+27.25 pt above IB_high**.

So every POC, VAH, VAL, reload zone, entry, stop and TP1 line in `PRE_RULE_A/`
is wrong, and every R and net figure in `PRE_RULE_A/index_VOID.md` is wrong too
-- `risk_R` is the value-area width plus a constant (sec b.10), so a wrong value
area is a wrong denominator for every R there.

**Those files are kept as the record of the defect, nothing else.** They are not
evidence about NQ, about Layer 1, or about the strategy. Nothing in `PRE_RULE_A/`
may be quoted, summed or averaged.

## What the redraw measured

On the fixed grid, across all 21 January sessions: **19.7 to 20.5 bins** across
the IB (was ~5), and **no VAH above IB_high and no VAL below IB_low on any
session** -- the worst case is exactly 0.00, an edge clamped to the boundary,
which AMENDMENT 2 permits. Those are per-session geometry values, read off the
GEOMETRY CHECK line each chart still carries. They are a check on the fix, not a
result about the strategy.

**The trade DIRECTION is identical on all 21 sessions.** That is the expected
control: direction is Layer 0, which builds no profile, so a profile fix must
not move it. It did not.

## Supersession map -- which chart replaced which

Read across: the `PRE_RULE_A/` file on the left is replaced by the file on the
right. `outcome` and `R` differ wherever the value area moved the reload zone,
the invalidation or TP1.

| superseded (in `PRE_RULE_A/`) | supersedes it (this folder) | old outcome | new outcome | outcome | R achieved | direction |
|---|---|---|---|---|---|---|
| `2026-01-02_no_fill.png` | `2026-01-02_no_fill.png` | no_fill | no_fill | same | - | SHORT |
| `2026-01-05_no_fill.png` | `2026-01-05_no_fill.png` | no_fill | no_fill | same | - | LONG |
| `2026-01-06_time_stop.png` | `2026-01-06_no_fill.png` | time_stop | no_fill | **CHANGED** | -0.71R -> - | LONG |
| `2026-01-07_time_stop.png` | `2026-01-07_time_stop.png` | time_stop | time_stop | same | +0.20R -> +0.33R | LONG |
| `2026-01-08_time_stop.png` | `2026-01-08_time_stop.png` | time_stop | time_stop | same | -0.02R -> -0.16R | SHORT |
| `2026-01-09_hard_stop.png` | `2026-01-09_hard_stop.png` | hard_stop | hard_stop | same | -1.01R | SHORT |
| `2026-01-12_time_stop.png` | `2026-01-12_time_stop.png` | time_stop | time_stop | same | +0.17R -> +0.31R | LONG |
| `2026-01-13_time_stop.png` | `2026-01-13_tp1.png` | time_stop | tp1 | **CHANGED** | +0.19R -> +1.98R | SHORT |
| `2026-01-14_time_stop.png` | `2026-01-14_time_stop.png` | time_stop | time_stop | same | +0.03R -> +0.19R | SHORT |
| `2026-01-15_time_stop.png` | `2026-01-15_hard_stop.png` | time_stop | hard_stop | **CHANGED** | -0.36R -> -1.02R | SHORT |
| `2026-01-16_no_fill.png` | `2026-01-16_no_fill.png` | no_fill | no_fill | same | - | SHORT |
| `2026-01-19_filtered_half_day.png` | `2026-01-19_filtered_half_day.png` | filtered:half_day | filtered:half_day | same | n/a (filtered) | LONG |
| `2026-01-20_time_stop.png` | `2026-01-20_time_stop.png` | time_stop | time_stop | same | +0.64R -> +0.80R | LONG |
| `2026-01-21_no_fill.png` | `2026-01-21_no_fill.png` | no_fill | no_fill | same | - | LONG |
| `2026-01-22_time_stop.png` | `2026-01-22_time_stop.png` | time_stop | time_stop | same | -0.91R -> -0.74R | SHORT |
| `2026-01-23_no_fill.png` | `2026-01-23_no_fill.png` | no_fill | no_fill | same | - | LONG |
| `2026-01-26_no_fill.png` | `2026-01-26_time_stop.png` | no_fill | time_stop | **CHANGED** | - -> +0.77R | LONG |
| `2026-01-27_time_stop.png` | `2026-01-27_no_fill.png` | time_stop | no_fill | **CHANGED** | +0.67R -> - | LONG |
| `2026-01-28_time_stop.png` | `2026-01-28_no_fill.png` | time_stop | no_fill | **CHANGED** | +0.63R -> - | SHORT |
| `2026-01-29_no_fill.png` | `2026-01-29_no_fill.png` | no_fill | no_fill | same | - | SHORT |
| `2026-01-30_hard_stop.png` | `2026-01-30_hard_stop.png` | hard_stop | hard_stop | same | -1.01R -> -1.02R | SHORT |

Nothing above is summed, averaged or counted. It is a file-to-file map.

`PRE_RULE_A/index_VOID.md` keeps the superseded table verbatim, still under its
own void banner.
