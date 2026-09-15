# PROVENANCE CHECKS — TradingView volume, MT5 volume, Databento live

Written 2026-09-15. Answers three empirical questions asked before any live-chart
work is authorised. **No signal logic anywhere in this document. Geometry only.**

Standing context, unchanged by anything here:
- Layer 0 (P0) FAILED: 1,971 trades, expectancy/trade −$2.882, PF 0.919. Kill
  criteria say stop. Nothing below changes that.
- §b.9 (profile-method sensitivity) has NEVER been run on real bars. Section A.5
  of this document is the first real-bar look at it, on ONE session, and it is
  not a §b.9 verdict.
- 2026-01-01 .. 2026-08-31 is UNSEALED HOLDOUT. The session used below is inside
  that window. It is IN-SAMPLE and ILLUSTRATIVE, not a result.

---

# A. TRADINGVIEW VOLUME PROVENANCE — COMPARISON SHEET

## A.1 The session, and why this one

**2026-04-15, contract NQM6, instrument_id 42004058.**

Chosen because it is the least confounded session available: 390 RTH bars (not a
half day), not in `data/raw/degraded_days.csv`, not a roll day, and it sits in the
middle of the NQM6 front-month period so TradingView's `NQ1!` and the explicit
contract symbol should resolve to the same future. If the feeds disagree HERE,
they disagree everywhere.

## A.2 The rule being compared — stated exactly

Computed by importing `ivb.profile`, the same module every chart and every
backtest uses. No second implementation.

| element | rule | source |
|---|---|---|
| session | NY cash, RTH bars 09:30–15:59 ET | `ivb/sessions.py` |
| IB window | first **30 minutes**, bars 09:30–09:59 ET inclusive (30 bars) | `P0.ib_minutes` |
| IB_high / IB_low | max high / min low of those 30 bars | `ivb/sessions.py` |
| bin width | `(IB_high − IB_low) / 20`, rounded half-up to the nearest 0.25 tick, floored at 1 tick | §b.2 RULE A |
| grid anchor | `edges[0] = IB_low` exactly; equal bins upward | §b.2 AMENDMENT 2 |
| allocation | **M1 `volume_uniform`** — each bar's volume spread EQUALLY over every bin its `[low, high]` touches | §b.9 primary |
| POC | highest-weight bin's CENTRE; tie → bin nearest IB mid; still tied → lower | §b.3 |
| value area | 70% of total, standard 2-bin expansion from POC; tie → upper pair | §b.3 |
| VAH / VAL | reported as bin EDGES, then clamped into `[IB_low, IB_high]` | §b.3 / §b.2 AM.2 |

## A.3 My numbers — 2026-04-15

```
IB_high    = 26072.25
IB_low     = 25982.25
IB_range   =    90.00 pt
IB volume  = 53,952 contracts (sum of the 30 one-minute bars)

bin_width  = 4.50 pt   (90.00 / 20)
n_bins     = 20        edges 25982.25 .. 26072.25
bins across IB = 20.00

M1 volume_uniform (PRIMARY):
  POC = 26025.00
  VAH = 26054.25
  VAL = 26004.75
  VAH − VAL = 49.50 pt
```

## A.4 THE SHEET — fill the right-hand columns from TradingView

The tiers matter. Fill them **in order** and stop at the first tier that fails.
A mismatch at tier 1 makes tiers 2–4 meaningless.

### TIER 0 — what you loaded (record it, do not skip)

| item | fill in |
|---|---|
| TradingView symbol string used | ____________________ |
| Is it the explicit contract (e.g. `CME_MINI:NQM2026`) or continuous (`NQ1!`)? | ____________________ |
| Chart timezone set to | ____________________ (must be `New York`) |
| Your TV data entitlement for CME | ____ real-time / ____ delayed / ____ free-tier |
| TV plan | ____________________ |
| Does the 09:30 bar carry the OPEN-time label? (09:30 bar = 09:30:00–09:30:59) | ____ yes / ____ no |
| Extended hours ON or OFF | ____________________ |

Note: extended hours ON/OFF must not change a 09:30–09:59 volume figure. If it
does, TV is re-aggregating, and that alone explains a mismatch.

### TIER 1 — BAR-BY-BAR VOLUME. This is the actual test.

This is the root question. Everything else is downstream. If these 30 numbers do
not match, the levels cannot match, and the two systems are looking at different
instruments regardless of what the ticker says.

| ET | my open | my high | my low | my close | **my volume** | **TV volume** | Δ |
|---|---|---|---|---|---|---|---|
| 09:30 | 26023.50 | 26040.50 | 26001.50 | 26020.25 | **5190** | | |
| 09:31 | 26020.25 | 26032.00 | 25995.25 | 25997.00 | **2599** | | |
| 09:32 | 25996.25 | 26023.25 | 25995.50 | 26023.25 | **1788** | | |
| 09:33 | 26022.75 | 26038.50 | 26021.50 | 26034.25 | **1939** | | |
| 09:34 | 26034.25 | 26039.50 | 26016.75 | 26019.50 | **1570** | | |
| 09:35 | 26019.00 | 26025.75 | 26009.25 | 26021.50 | **2164** | | |
| 09:36 | 26020.25 | 26036.50 | 26018.75 | 26026.75 | **1504** | | |
| 09:37 | 26026.50 | 26036.25 | 26012.50 | 26028.25 | **1558** | | |
| 09:38 | 26027.50 | 26049.75 | 26020.75 | 26045.50 | **2205** | | |
| 09:39 | 26044.00 | 26054.25 | 26033.50 | 26051.50 | **1947** | | |
| 09:40 | 26051.75 | 26059.75 | 26046.25 | 26054.00 | **2231** | | |
| 09:41 | 26054.25 | 26057.00 | 26042.50 | 26047.25 | **1292** | | |
| 09:42 | 26047.00 | 26049.50 | 26033.75 | 26035.00 | **1188** | | |
| 09:43 | 26035.50 | 26041.75 | 26018.75 | 26020.00 | **1948** | | |
| 09:44 | 26020.00 | 26032.75 | 25982.25 | 25989.00 | **3925** | | |
| 09:45 | 25990.00 | 26016.75 | 25990.00 | 26011.00 | **2698** | | |
| 09:46 | 26011.00 | 26027.50 | 26008.50 | 26018.50 | **1682** | | |
| 09:47 | 26018.25 | 26047.00 | 26018.25 | 26047.00 | **1741** | | |
| 09:48 | 26046.00 | 26050.00 | 26033.75 | 26037.50 | **1446** | | |
| 09:49 | 26036.75 | 26042.25 | 26027.50 | 26037.25 | **1089** | | |
| 09:50 | 26038.25 | 26055.50 | 26036.25 | 26049.00 | **1395** | | |
| 09:51 | 26049.25 | 26053.00 | 26042.25 | 26050.75 | **924** | | |
| 09:52 | 26050.25 | 26050.25 | 26025.50 | 26048.50 | **1652** | | |
| 09:53 | 26048.25 | 26062.25 | 26044.50 | 26053.75 | **1800** | | |
| 09:54 | 26052.50 | 26055.25 | 26039.25 | 26045.50 | **1152** | | |
| 09:55 | 26044.50 | 26057.00 | 26043.75 | 26047.50 | **846** | | |
| 09:56 | 26045.50 | 26053.00 | 26044.00 | 26049.50 | **612** | | |
| 09:57 | 26048.75 | 26065.00 | 26044.75 | 26062.25 | **1374** | | |
| 09:58 | 26061.50 | 26066.75 | 26056.25 | 26061.50 | **1214** | | |
| 09:59 | 26061.25 | 26072.25 | 26060.75 | 26068.50 | **1279** | | |
| **SUM** | | | | | **53952** | | |

Fill OHLC too if any bar's volume is off — a price mismatch and a volume
mismatch have different causes.

**How to read tier 1:**
- **Every bar matches exactly** → same instrument, same aggregation. Move to tier 2.
- **Volumes match, prices differ** → same tape, different rounding or a
  back-adjusted continuous contract. Reload the explicit contract symbol.
- **Prices match, volumes differ by a few percent** → same instrument, different
  trade-type inclusion (blocks, EFPs, spread legs). Record the size of the gap;
  this is survivable but must be written down.
- **Volumes differ by a large factor, or are round/smooth** → not the CME tape.
  Either a CFD, an aggregated index feed, or tick-count-as-volume. **Pine is a
  different instrument wearing the same ticker. Stop here.**

### TIER 2 — IB extremes

| item | mine | TV | match? |
|---|---|---|---|
| IB_high (max high 09:30–09:59) | 26072.25 | | |
| IB_low (min low 09:30–09:59) | 25982.25 | | |
| IB_range | 90.00 | | |
| IB total volume | 53952 | | |

### TIER 3 — the grid

Only meaningful if tier 1 and tier 2 pass.

| item | mine | TV | match? |
|---|---|---|---|
| bin width used | 4.50 pt | | |
| number of rows across the IB | 20 | | |
| lowest row's bottom edge | 25982.25 | | |
| highest row's top edge | 26072.25 | | |
| value area percent | 70% | | |

TradingView's **Volume Profile Fixed Range** sets rows by a "Row Size" input
(either `Number of rows` or `Ticks per row`). To make tier 3 comparable, set
**Number of rows = 20** and anchor the range to the 09:30 and 09:59 bars only.
If your plan does not expose Volume Profile Fixed Range, tier 3 cannot be filled
and this comparison ends at tier 2.

### TIER 4 — the levels

| level | mine (M1) | TV | Δ points |
|---|---|---|---|
| POC | 26025.00 | | |
| VAH | 26054.25 | | |
| VAL | 26004.75 | | |
| VAH − VAL | 49.50 | | |

## A.5 READ THIS BEFORE JUDGING ANY TIER-4 MISMATCH

Tier 4 is the weakest test in the sheet, and the reason is measured, not
theoretical. On this one session the four §b.9 allocation methods — all four
reading the **identical** 30 bars, with the **identical** 20-bin grid — place
the levels here:

| method | POC | VAH | VAL | VAH−VAL |
|---|---|---|---|---|
| M1 `volume_uniform` (primary) | 26025.00 | 26054.25 | 26004.75 | 49.50 |
| M2 `volume_triangular` | 26047.50 | 26049.75 | 26009.25 | 40.50 |
| M3 `volume_close_only` | 26020.50 | 26058.75 | 26018.25 | 40.50 |
| M4 `tpo_minute` (control) | 26043.00 | 26054.25 | 26013.75 | 40.50 |

Per-session §b.9 spreads, in ticks: **d_POC 108.0, d_VAH 36.0, d_VAL 54.0,
d_risk 36.0.**

**d_POC = 108 ticks = 27.25 points, on a 90-point IB.** The choice of allocation
assumption moves the POC by 30% of the initial balance. One session is not a
§b.9 verdict and must not be quoted as one — but it is the first real-bar
evidence, and it points the way §b.2 said it might: *"§b.9 therefore becomes a
real gate for the first time, AND IT MAY NOW FAIL."*

Two consequences for this sheet:

1. **A tier-4 mismatch is not evidence about TradingView's data.** TV uses its
   own intrabar allocation, and a POC that lands 20 points from mine is fully
   explained by allocation alone, with identical bars. Only tier 1 tests the
   feed.
2. This is a warning about the whole Layer 1 programme, not about TradingView.
   1-minute OHLCV does not resolve where inside a bar the volume traded. Every
   method above is an assumption, and on this session the assumptions do not
   agree. **Do not build a live chart around a POC before §b.9 has actually been
   run.**

---

# B. MT5 — DOES THE BROKER FEED CARRY REAL VOLUME?

## B.1 What you run

`MetaTrader5` is a Windows-only Python package and is **not currently installed**
(checked: Python 3.13.12, `MetaTrader5` absent). Install it, and if the wheel
does not build on 3.13, that answer is itself a finding — you would need a
second interpreter just for this.

```powershell
pip install MetaTrader5
```

Then, with the MT5 **terminal running and logged in**, run this probe.
It reads only. It places no order and writes no file.

```python
"""MT5 volume provenance probe. READ-ONLY. Places no order."""
import MetaTrader5 as mt5
import pandas as pd

if not mt5.initialize():
    raise SystemExit(f"initialize() failed: {mt5.last_error()}")

print("terminal :", mt5.terminal_info())
print("account  :", mt5.account_info()._asdict().get("server"))

# ---- STEP 1: what is this broker even calling the Nasdaq future? -------------
print("\n--- candidate symbols ---")
for pat in ("*NQ*", "*NAS*", "*US100*", "*USTEC*", "*NDX*"):
    for s in (mt5.symbols_get(pat) or []):
        print(f"  {s.name:<18} path={s.path:<40} digits={s.digits} "
              f"tick={s.trade_tick_size} contract={s.trade_contract_size}")

SYM = "NQ"        # <-- replace with the exact name printed above

# ---- STEP 2: symbol metadata ------------------------------------------------
mt5.symbol_select(SYM, True)
info = mt5.symbol_info(SYM)._asdict()
for k in ("name", "path", "description", "currency_profit", "trade_tick_size",
          "trade_contract_size", "digits", "session_volume", "volume",
          "volumehigh", "volumelow", "expiration_time", "trade_mode"):
    print(f"  {k:<22} {info.get(k)}")

# ---- STEP 3: THE ANSWER. real_volume on 1-minute bars -----------------------
r = mt5.copy_rates_range(SYM, mt5.TIMEFRAME_M1,
                         pd.Timestamp("2026-04-15 13:30"),   # 09:30 ET in UTC
                         pd.Timestamp("2026-04-15 14:00"))
df = pd.DataFrame(r)
df["time"] = pd.to_datetime(df["time"], unit="s")
print("\n--- M1 bars ---")
print(df[["time", "open", "high", "low", "close",
          "tick_volume", "real_volume", "spread"]].to_string())
print("\nreal_volume  sum =", int(df["real_volume"].sum()),
      " nonzero bars =", int((df["real_volume"] > 0).sum()), "/", len(df))
print("tick_volume  sum =", int(df["tick_volume"].sum()))

# ---- STEP 4: is there a trade tape at all, and an aggressor side? -----------
t = mt5.copy_ticks_range(SYM,
                         pd.Timestamp("2026-04-15 13:30"),
                         pd.Timestamp("2026-04-15 13:31"),
                         mt5.COPY_TICKS_ALL)
tk = pd.DataFrame(t)
print("\n--- ticks in one minute:", len(tk), "---")
if len(tk):
    print(tk.head(10).to_string())
    print("last>0 :", int((tk["last"] > 0).sum()), "/", len(tk))
    print("volume>0 :", int((tk["volume"] > 0).sum()), "/", len(tk))
    has_side = tk["flags"] & (mt5.TICK_FLAG_BUY | mt5.TICK_FLAG_SELL)
    print("ticks carrying BUY/SELL aggressor flag :",
          int((has_side > 0).sum()), "/", len(tk))

mt5.shutdown()
```

Note on the timestamps at step 3: MT5 returns and accepts **server time**, which
is usually not UTC and is almost never New York. `13:30`/`14:00` above assumes a
UTC server on a US-Eastern-daylight date. Check `mt5.symbol_info_tick(SYM).time`
against a known wall clock before trusting the window, or widen the range and
slice afterwards.

## B.2 What the answer looks like, either way

**Read `real_volume` at step 3. That single column is the whole answer.**

| observation | verdict | what it means for this project |
|---|---|---|
| `real_volume` sum = 0, every bar 0; `tick_volume` large | **TICK VOLUME ONLY.** The broker counts price *updates*, not contracts. | Unusable for a volume profile. A profile built on tick counts is TPO in disguise — that is M4, the CONTROL, not the primary. |
| `real_volume` nonzero and close to my Databento totals (e.g. ≈5190 for 09:30) | **REAL EXCHANGE VOLUME.** | Usable, and tier 1 of section A applies to MT5 too — run the same 30-row check against it. |
| `real_volume` nonzero but wildly different scale | Broker-internal volume — their own clients' fills, not the exchange. | Unusable. It is a different population, not a different unit. |
| step 1 only shows `US100` / `USTEC` / `NAS100`, with `trade_contract_size` not 20 and no expiry | **It is a CFD, not the CME future.** | Fails before volume even matters. Different instrument, synthetic price, broker-internal volume. |
| step 4: `last` all zero, `volume` all zero | Quote-only feed, no trade tape. | No volume and no order flow is possible, ever. Layer 2 is off the table on this feed. |
| step 4: BUY/SELL flag count > 0 | Aggressor side present — rare outside exchange-connected brokers. | This would be genuinely interesting for Layer 2 and worth a separate look. |

**Expected result, stated in advance so it can be wrong:** most retail MT5
brokers list the Nasdaq as a CFD and report `real_volume = 0`. If that is what
comes back, MT5 is eliminated on data grounds and no further MT5 work is
justified.

---

# C. DATABENTO LIVE — PRICING

## C.1 Method

Free metadata calls only. **Nothing was purchased.** Calls used:
`metadata.list_unit_prices`, `metadata.get_record_count`,
`metadata.get_billable_size`, `metadata.get_cost`. All are free; `get_cost`
returns an estimate and does not bill. Run 2026-09-15, `databento` 0.86.0.

## C.2 Is live a separate tier from historical pay-as-you-go?

**No — it is the same pay-as-you-go unit model, at a different unit price.**
`list_unit_prices("GLBX.MDP3")` returns three modes with the same schema list:

| schema | `historical` $/GB | `historical-streaming` $/GB | `live` $/GB |
|---|---|---|---|
| `ohlcv-1m` | 70.00 | 70.00 | **84.00** |
| `ohlcv-1s` | 70.00 | 70.00 | 84.00 |
| `mbo` | 1.80 | 1.80 | 2.16 |
| `trades` | 28.00 | 28.00 | 33.60 |
| `tbbo` | 28.00 | 28.00 | 33.60 |
| `mbp-10` | 0.50 | 0.50 | 0.60 |

Live is a flat **1.2×** the historical unit price across every schema. Same
account, same API key, same billing.

**The caveat, and it is the important one:** unit price is not total price.
Real-time CME data carries **exchange licence / market-data fees** that the unit
price does not include, and the API exposes no endpoint for them. That is the
one number in this section I could not verify from the API, and it is likely to
dominate. See C.5.

## C.3 What the data actually costs — NQ `ohlcv-1m`, measured

One month, 2026-04-01 .. 2026-05-01, `GLBX.MDP3`, schema `ohlcv-1m`:

| subscription | records | billable bytes | historical cost |
|---|---|---|---|
| one raw contract `NQM6` | 29,888 | 1,673,728 | $0.1091 |
| continuous front `NQ.v.0` | 29,888 | 1,673,728 | $0.1091 |
| parent `NQ.FUT` (all expiries + spreads) | 37,054 | 2,075,024 | $0.1353 |

Scaling the measured 1.674 MB/month at the live rate of $84/GB:

- **≈ $0.13 per month of NQ 1-minute bars, live.**
- ≈ $1.60 per year.
- Choosing the parent symbol instead of one contract costs ≈ $0.16/month — a
  rounding error in dollars, but it pulls in every expiry and every calendar
  spread, which is a correctness problem, not a cost problem.

**The bar data is effectively free. Cost is not the deciding factor here.**

## C.4 Smallest configuration that drives a real-time `06_month_charts.py`

`06_month_charts.py` needs exactly one thing per session: **the front contract's
RTH 1-minute OHLCV**. Nothing else. It computes the IB from bars, the profile
from bars, and the filters from bars plus two committed CSVs.

Minimum viable live setup:

| item | choice | why |
|---|---|---|
| dataset | `GLBX.MDP3` | same dataset as the study. Any other dataset is a different tape. |
| schema | `ohlcv-1m` | exactly what the study consumes. |
| symbols | **one** raw symbol, the current front (`NQM6`), `stype_in="raw_symbol"` | one contract, never spliced inside a session — matches `front_month_bars()` Series A. |
| alternative | `NQ.v.0`, `stype_in="continuous"` | identical byte count here, and it rolls itself. But it rolls on **Databento's** rule, not `data/roll_calendar_6635298.csv`. That is a second roll rule in the system. Prefer the raw symbol. |
| session window | you only need 09:30–11:30 ET | ~120 bars/day. Live subscriptions stream continuously, so this does not reduce cost much; it reduces what you keep. |
| client | `databento.Live(key)`, `.subscribe(...)`, iterate | one process. |
| still needed locally | `data/roll_calendar_6635298.csv`, `data/daily_adjusted.parquet` (for ATR14), `data/raw/degraded_days.csv` | the ATR filter needs prior-session dailies; the vendor-quality filter needs the degraded list. Neither is available live. |

**Two hard gaps that cost estimates hide:**

1. **ATR14 comes from `daily_adjusted.parquet`, shifted by one session.** A live
   chart needs yesterday's daily bar appended each day, or `min_ib_range_atr`
   cannot be evaluated and the chart cannot say whether P0 would trade. That is
   a second, daily, historical pull — trivial in cost, real in plumbing.
2. **`degraded_days.csv` is a vendor *post-hoc* statement.** `get_dataset_condition`
   cannot tell you a session is degraded while it is happening. A live chart can
   never carry the `vendor_degraded` banner in real time. It can only be
   back-stamped the next day. Say so on the chart rather than implying the
   filter ran.

## C.5 What I could NOT price — ask Databento directly

The unit prices above are real and were fetched live. These are not, and one of
them probably decides the whole question:

1. **CME real-time licence fee.** Exchange-mandated, passed through, not in the
   API. Retail/non-professional real-time CME fees at other vendors sit in the
   region of **$10–$30 per month per exchange group** — treat that as an
   unverified order of magnitude, not a quote. It will be many times the
   $0.13 data cost.
2. **Whether your account has live access enabled at all.** Historical access
   does not imply it.
3. **Any monthly minimum or platform fee on the live plan.**
4. **Professional vs non-professional classification.** Trading your own money
   normally qualifies as non-professional, but the vendor decides, and the fee
   difference is large.

**Exact question to send Databento support:** *"For a non-professional
individual, what is the total monthly cost of a live GLBX.MDP3 `ohlcv-1m`
subscription to a single NQ contract — including CME licence fees and any plan
minimum — and is live access enabled on my account?"*

---

# D. RECOMMENDATION — Pine vs MT5 vs extending this Python

## D.1 The one criterion that outranks the rest

Only option 3 shares an implementation with the study.

Options 1 and 2 are **reimplementations**. §b.2 RULE A, §b.2 AMENDMENT 2 (grid
anchored at `IB_low`, VAH/VAL/POC clamped into the IB), §b.3's tie-breaks (POC
tie → nearest IB mid, then lower bin; value-area tie → upper pair), the half-up
tick rounding that exists specifically because numpy rounds halves to even — all
of it would have to be rewritten in a second language, by hand.

`06_month_charts.py` already refuses to do this internally, and says why:

> "The Layer 1 resolver is IMPORTED, never re-implemented. A second copy of the
> geometry would be free to drift from the one the other charts use, and then
> two pictures of the same rule could disagree."

A live Pine or MQL5 chart is exactly that second copy — at the perimeter instead
of inside. And this project already knows what a silent geometry bug costs: the
§b.2 grid-anchor defect ran undetected across **2,365 sessions**, putting a value
area edge outside the initial balance on **46.6%** of them, and it was invisible
on a 2015 chart (+1.75 pt) while being obvious on a 2026 one (+27.25 pt). That
defect was findable because there was **one** implementation to audit. With two,
the same question — *which one is wrong?* — has no procedure that answers it.
You would be reduced to eyeballing.

## D.2 The three options

| | **1. Pine / TradingView** | **2. MT5 / MQL5** | **3. Extend this Python** |
|---|---|---|---|
| shares code with the study | **no** — full rewrite | **no** — full rewrite | **yes** — imports `ivb.profile` |
| data is the same tape | **unknown** — section A tier 1 decides | **probably not** — likely a CFD with `real_volume = 0` | **yes, by construction** — same dataset, schema and roll calendar |
| can express §b.2 RULE A | yes, arithmetic is simple | yes | already does |
| intrabar volume allocation | Pine has no volume-profile primitive; needs `request.security_lower_tf()` and still approximates | no profile primitive at all | all four §b.9 methods already implemented |
| honours `roll_calendar_6635298.csv` | no — TV's own continuous rule | no — broker's own symbol | yes |
| honours `degraded_days.csv` / ATR filter | no | no | yes (ATR needs a daily top-up) |
| data cost | included in TV plan | included by broker | ≈ $0.13/mo + unpriced CME licence |
| time to working chart | shortest | medium | longest |
| chart quality out of the box | best | poor | already acceptable — `src/viz.py` draws these today |
| answers "is the live chart or the research wrong?" | **never** | **never** | **not applicable — there is one answer** |

## D.3 Recommendation

**Option 3. Extend the existing Python. Do not write Pine or MQL5 for this.**

Reasoning, in order of weight:

1. **One implementation, one answer.** Options 1 and 2 create a second source of
   truth for the same geometry. When it disagrees with the study — and it will,
   because tie-breaks and rounding always drift — there is no experiment that
   resolves it. This is disqualifying on its own, and it is the reason you asked.
2. **Cost is not a differentiator.** $0.13/month for the bars. The decision does
   not turn on money. The unpriced CME licence fee (C.5) is the only real
   expense and it applies to any real-time data, from any vendor.
3. **The alternatives' data is unverified or likely wrong.** TradingView is
   unknown until section A tier 1 is filled in. MT5 is probably a CFD with tick
   volume only, which is fatal for a volume profile — it silently degrades the
   primary method M1 into the control method M4.
4. **The drawing code already exists.** `src/viz.py` and `06_month_charts.py`
   produce these charts now. A live version is a data-source swap and a loop,
   not a new renderer.

**Use TradingView and MT5 as they are actually useful: as independent probes, not
as implementations.** Section A tier 1 tells you whether TV's volume is the CME
tape. Section B tells you what the broker's feed really carries. Both are worth
knowing. Neither justifies rewriting the geometry.

## D.4 What blocks option 3, in order

This is not a to-do list and nothing below is authorised. It is the dependency
chain, so the order is not chosen by convenience later.

1. **P0 failed. 1,971 trades, expectancy −$2.882, PF 0.919.** Kill criteria say
   stop. A live chart of a strategy that loses money is a faster way to lose
   money. This is the standing blocker and it is above everything else here.
2. **§b.9 has never been run on real bars.** Section A.5 shows the four
   allocation methods disagreeing on the POC by 27.25 points on a 90-point IB,
   on one session. If that holds across sessions, the POC is not a location this
   data can resolve, and a live chart would be drawing a line with no referent.
3. **Section A tier 1 and section B** — cheap, and they are the answers to the
   questions actually asked. They cost nothing but your time at a screen.
4. **The CME licence fee** (C.5) — one email, and it is the only real number
   still missing.

Items 3 and 4 are independent of 1 and 2 and can be done at any time. Items 1
and 2 gate anything being built.

---
---

# E. FTMO MT5 — WHAT IS THE NASDAQ SYMBOL, ACTUALLY?

Added 2026-09-15, second pass. Section B was written before the broker was known.
This section replaces B for the FTMO case; B's generic table still applies.

## E.1 What FTMO is, structurally — read this before running anything

FTMO is a **proprietary trading firm**, not a broker and not an exchange member.
You are not given a CME clearing account, and no order you place there reaches
Globex as a futures order in your name. Their MT5 platform quotes **contracts for
difference**. A CFD is a bilateral contract with the firm that references a price;
it is not the instrument it references.

This matters for a specific reason, and it is not pedantry:

- A CFD has **no tape**. There is no exchange trade feed for a contract that only
  exists between you and one counterparty. There is therefore no volume to report.
- Symbols named `.fut` or `US100.fut` are still CFDs. The suffix says which
  reference price the CFD tracks (the future rather than the cash index). It does
  not mean you hold the future.
- Anything non-zero that does appear in a volume field is **the firm's own
  internal flow**, not the CME tape. That is a different population, not a
  different unit.

**Therefore the expected answer is `real_volume = 0` on every bar.** The probe
below exists to confirm that, not to discover it. Stating the expectation in
advance is what makes the probe falsifiable.

## E.2 The probe — Python `MetaTrader5` version (run this one)

Not installed here (Python 3.13.12). `pip install MetaTrader5` first, and note the
package is Windows-only. The MT5 terminal must be **running and logged in to the
FTMO account**; the Python API attaches to a live terminal, it does not log in on
its own.

Read-only. Places no order, writes no file, changes no chart.

```python
"""FTMO MT5 provenance probe. READ-ONLY. Places no order, writes no file."""
import MetaTrader5 as mt5
import pandas as pd

if not mt5.initialize():
    raise SystemExit(f"initialize() failed: {mt5.last_error()}")

ai = mt5.account_info()
print("server   :", ai.server, "| company:", ai.company)
print("currency :", ai.currency, "| leverage:", ai.leverage)
print("balance  :", ai.balance, "| equity:", ai.equity)

# ---- STEP 1 -- find FTMO's Nasdaq symbol. Do not assume the name. -----------
print("\n--- candidate symbols ---")
seen = set()
for pat in ("*US100*", "*USTEC*", "*NAS*", "*NQ*", "*NDX*", "*100*"):
    for s in (mt5.symbols_get(pat) or []):
        if s.name in seen:
            continue
        seen.add(s.name)
        print(f"  {s.name:<16} path={s.path}")

SYM = "US100.cash"        # <-- REPLACE with the exact name printed above

# ---- STEP 2 -- SYMBOL_PATH and description: CFD, or exchange-traded? --------
mt5.symbol_select(SYM, True)
si = mt5.symbol_info(SYM)
d = si._asdict()
print(f"\n--- {SYM} ---")
print("SYMBOL_PATH            :", d["path"])          # the CFD/vs/Futures tell
print("SYMBOL_DESCRIPTION     :", d["description"])
print("SYMBOL_ISIN            :", d.get("isin"))
print("SYMBOL_EXCHANGE        :", d.get("exchange"))  # empty => not exchange-traded
print("SYMBOL_CURRENCY_PROFIT :", d["currency_profit"])
print("SYMBOL_EXPIRATION_TIME :", d["expiration_time"])  # 0 => no expiry => not a future

# ---- STEP 3 -- tick size and contract size ---------------------------------
print("\nSYMBOL_TRADE_TICK_SIZE  :", d["trade_tick_size"])
print("SYMBOL_TRADE_TICK_VALUE :", d["trade_tick_value"])
print("SYMBOL_TRADE_CONTRACT_SIZE:", d["trade_contract_size"])
print("SYMBOL_POINT / digits   :", d["point"], "/", d["digits"])
print("SYMBOL_VOLUME_MIN/STEP/MAX:", d["volume_min"], d["volume_step"], d["volume_max"])

# ---- STEP 4 -- swap / overnight charges ------------------------------------
SWAP_MODE = {0: "DISABLED", 1: "POINTS", 2: "SYMBOL_CURRENCY",
             3: "MARGIN_CURRENCY", 4: "DEPOSIT_CURRENCY",
             5: "INTEREST_CURRENT", 6: "INTEREST_OPEN",
             7: "REOPEN_CURRENT", 8: "REOPEN_BID"}
print("\nSYMBOL_SWAP_LONG        :", d["swap_long"])
print("SYMBOL_SWAP_SHORT       :", d["swap_short"])
print("SYMBOL_SWAP_MODE        :", d["swap_mode"], SWAP_MODE.get(d["swap_mode"]))
print("SYMBOL_SWAP_ROLLOVER3DAYS:", d["swap_rollover3days"], "(3 = Wednesday, 5 = Friday)")

# ---- STEP 5 -- trading hours, per weekday ----------------------------------
DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
print("\n--- sessions (terminal/server time, NOT New York) ---")
for dow in range(7):
    q, t = [], []
    for i in range(8):
        r = mt5.symbol_info_session_quote(SYM, dow, i)
        if r is None:
            break
        q.append(f"{r[0]}-{r[1]}")
    for i in range(8):
        r = mt5.symbol_info_session_trade(SYM, dow, i)
        if r is None:
            break
        t.append(f"{r[0]}-{r[1]}")
    print(f"  {DAYS[dow]}  quote {q or '-'}   trade {t or '-'}")

# ---- STEP 6 -- THE ANSWER. real_volume vs tick_volume on M1 bars -----------
# NOTE: copy_rates_range takes SERVER time, which is usually not UTC and is
# never New York. Pull a wide window and slice, rather than trusting an offset.
r = mt5.copy_rates_range(SYM, mt5.TIMEFRAME_M1,
                         pd.Timestamp("2026-04-15 00:00"),
                         pd.Timestamp("2026-04-16 00:00"))
df = pd.DataFrame(r)
df["time"] = pd.to_datetime(df["time"], unit="s")
print("\n--- M1 bars:", len(df), "---")
print(df.head(5).to_string())
print("\nreal_volume  sum  =", int(df["real_volume"].sum()))
print("real_volume  nonzero bars =", int((df["real_volume"] > 0).sum()), "/", len(df))
print("tick_volume  sum  =", int(df["tick_volume"].sum()))
print("SYMBOL_VOLUME_REAL (last DEAL, not a bar) :", d.get("volume_real"))
print("SYMBOL_SESSION_VOLUME                     :", d.get("session_volume"))

mt5.shutdown()
```

**One precision point, because the names collide.** `SYMBOL_VOLUME_REAL` in MQL5
is the volume of the **last single deal** — one number, not a series. The per-bar
figure you actually need is the `real_volume` field of `MqlRates` / of the array
returned by `copy_rates_*`. Step 6 prints both, and they answer different
questions. The bar series is the one that decides this.

## E.3 The same probe in MQL5, if you would rather run it in the terminal

Save as a script, compile, drag onto a `US100` chart.

```mql5
//+------------------------------------------------------------------+
//| FTMO symbol provenance probe. READ-ONLY. Places no order.        |
//+------------------------------------------------------------------+
void OnStart()
{
   string sym = _Symbol;                       // run it on the Nasdaq chart
   PrintFormat("SYMBOL                    : %s", sym);
   PrintFormat("SYMBOL_PATH               : %s", SymbolInfoString(sym, SYMBOL_PATH));
   PrintFormat("SYMBOL_DESCRIPTION        : %s", SymbolInfoString(sym, SYMBOL_DESCRIPTION));
   PrintFormat("SYMBOL_EXCHANGE           : '%s'", SymbolInfoString(sym, SYMBOL_EXCHANGE));
   PrintFormat("SYMBOL_ISIN               : '%s'", SymbolInfoString(sym, SYMBOL_ISIN));
   PrintFormat("SYMBOL_EXPIRATION_TIME    : %s",
               TimeToString((datetime)SymbolInfoInteger(sym, SYMBOL_EXPIRATION_TIME)));

   PrintFormat("SYMBOL_TRADE_TICK_SIZE    : %g", SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE));
   PrintFormat("SYMBOL_TRADE_TICK_VALUE   : %g", SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE));
   PrintFormat("SYMBOL_TRADE_CONTRACT_SIZE: %g", SymbolInfoDouble(sym, SYMBOL_TRADE_CONTRACT_SIZE));
   PrintFormat("SYMBOL_VOLUME_MIN/STEP    : %g / %g",
               SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN),
               SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP));

   PrintFormat("SYMBOL_SWAP_LONG          : %g", SymbolInfoDouble(sym, SYMBOL_SWAP_LONG));
   PrintFormat("SYMBOL_SWAP_SHORT         : %g", SymbolInfoDouble(sym, SYMBOL_SWAP_SHORT));
   PrintFormat("SYMBOL_SWAP_MODE          : %d", (int)SymbolInfoInteger(sym, SYMBOL_SWAP_MODE));
   PrintFormat("SYMBOL_SWAP_ROLLOVER3DAYS : %d", (int)SymbolInfoInteger(sym, SYMBOL_SWAP_ROLLOVER3DAYS));

   // last-deal real volume -- ONE number, not the bar series
   PrintFormat("SYMBOL_VOLUME_REAL (last deal) : %g", SymbolInfoDouble(sym, SYMBOL_VOLUME_REAL));
   PrintFormat("SYMBOL_SESSION_VOLUME          : %g", SymbolInfoDouble(sym, SYMBOL_SESSION_VOLUME));

   // trading hours
   datetime f, t;
   string days[7] = {"Sun","Mon","Tue","Wed","Thu","Fri","Sat"};
   for(int d = 0; d < 7; d++)
      for(int i = 0; i < 8; i++)
        {
         if(!SymbolInfoSessionTrade(sym, (ENUM_DAY_OF_WEEK)d, i, f, t)) break;
         PrintFormat("TRADE SESSION %s #%d : %s - %s", days[d], i,
                     TimeToString(f, TIME_MINUTES), TimeToString(t, TIME_MINUTES));
        }

   // THE ANSWER: per-bar real volume
   MqlRates r[];
   int n = CopyRates(sym, PERIOD_M1, 0, 2000, r);
   long rv = 0, tv = 0; int nz = 0;
   for(int i = 0; i < n; i++)
     { rv += r[i].real_volume; tv += r[i].tick_volume; if(r[i].real_volume > 0) nz++; }
   PrintFormat("M1 bars %d | real_volume sum %I64d | nonzero bars %d | tick_volume sum %I64d",
               n, rv, nz, tv);
}
```

## E.4 How to read it — the verdict, pre-committed

**Look at one line: `real_volume nonzero bars`.**

### If it reads `0 / n` — and it almost certainly will

**Say it plainly: Layer 1 is impossible on FTMO. Stop there.**

Layer 1 is a **volume** profile. Its inputs are POC, VAH and VAL, and all three
are derived from contracts traded at a price. With no volume there is no profile.
There is no version of §b.2 or §b.3 that can be evaluated, because the quantity
they distribute does not exist in the feed.

**Do not design around it.** Specifically, do not:

- substitute `tick_volume` for volume. Tick volume counts price *updates*. A
  profile built on it is a time-at-price profile — that is **M4 `tpo_minute`,
  which is the CONTROL**, and §b.9 registers it as the assumption-free comparison
  against the volume methods. Swapping the primary for the control and keeping the
  name "volume profile" is how a study lies to itself.
- fall back to "close-only" allocation as a way of needing less volume. M3
  `volume_close_only` still needs per-bar volume. It needs the same missing number.
- fetch the profile from Databento and trade the geometry on FTMO's CFD. The levels
  would be computed on the CME tape and applied to a different instrument with a
  different price, a different spread, and no guarantee the two agree tick for
  tick. That is not Layer 1 on FTMO; it is Layer 1 on NQ with an execution error
  bolted on, and it hides the error rather than measuring it.

Layer 0 — the IB breakout — *is* computable on a CFD, because it needs only OHLC.
That is the one thing that survives. It is also the layer that already failed.

### If it reads non-zero

Do not celebrate. One question is answered and a harder one opens: **whose
volume is it?** Run section A tier 1 against it — the 30 numbers for 2026-04-15 —
and compare to the Databento column. If FTMO's figures are not the CME tape's
figures, the volume is FTMO's internal flow, and §b.2 would be profiling their
client book rather than the market. That is a different population, and the
research does not transfer to it.

### Other fields, and what they tell you

| field | CFD answer (expected) | exchange-traded answer |
|---|---|---|
| `SYMBOL_PATH` | `CFD\Indices\...` or `Indices\...` | `Futures\CME\...` or similar |
| `SYMBOL_EXCHANGE` | empty string | a venue code |
| `SYMBOL_ISIN` | empty | populated |
| `SYMBOL_EXPIRATION_TIME` | `0` / epoch — **no expiry** | a real quarterly date |
| `SYMBOL_TRADE_CONTRACT_SIZE` | typically `1` | `20` for NQ, `2` for MNQ |
| `SYMBOL_TRADE_TICK_SIZE` | often `0.01` or `0.1` index pt | `0.25` index pt |
| `SYMBOL_SWAP_MODE` | non-zero — overnight financing charged | usually `DISABLED` for futures |

**No expiry is the cleanest single tell.** A future expires. A CFD does not. If
`SYMBOL_EXPIRATION_TIME` is empty and `SYMBOL_SWAP_MODE` is not `DISABLED`, you
are holding a financed synthetic position, not a futures contract, whatever the
chart is labelled.

**On swap specifically:** it is charged for holding past the daily rollover, with
a triple charge on the day named by `SYMBOL_SWAP_ROLLOVER3DAYS`. The strategy is
09:30–11:30 ET and flat by the time stop, so swap should never be incurred. Record
the numbers anyway — a financing charge on a product means it is a financed
product, which is the classification evidence, independent of whether you ever pay
it.

---

# F. TRADEZERO — IS ANY CME FUTURE REACHABLE?

## F.1 The direct answer

**No. TradeZero is a US equities and options broker. No futures of any kind are
offered — not NQ, not MNQ, not any CME, CBOT, NYMEX or COMEX product.**

Futures require a Futures Commission Merchant registered with the CFTC and NFA,
which is a different registration from a securities broker-dealer. TradeZero's
product set is US-listed equities, ETFs and options on them. There is no account
type, no upgrade and no sub-account that reaches Globex.

This is not a data-feed question and no probe will change it. The instrument is
not on the menu.

## F.2 The closest proxy, and why it is not close

The nearest Nasdaq-100 exposure on an equities account:

| proxy | what it is | why it is not NQ |
|---|---|---|
| **QQQ** | ETF tracking the Nasdaq-100 | closest, and the rest of this section is about it |
| QQQM | same index, cheaper, thinner | much lower volume; worse for a volume profile |
| TQQQ / SQQQ | 3× leveraged | path-dependent; daily reset. Not the index. |
| QQQ options | derivative on the ETF | different risk object entirely |

Structural gaps between QQQ and NQ, all of which break the study's assumptions:

- **Different trading day.** NQ trades nearly 24 hours; QQQ's real liquidity is
  09:30–16:00 ET with thin pre/post. The IB window's relationship to the overnight
  session is not the same object.
- **Different tick and notional.** QQQ ticks $0.01 on a ~$600 share; NQ ticks 0.25
  index points at $5. The bin rule `IB_range / 20` still works arithmetically, but
  a "point" means something different, and every threshold expressed in ticks
  (`breakout_buffer_ticks`, `min_ib_range_ticks`, `hard_stop_ticks`) would need to
  be re-registered from scratch. That is a new pre-registration, not a conversion.
- **Creation/redemption flow.** An ETF's volume includes authorised-participant
  arbitrage against the basket. That flow is mechanical, not directional, and it is
  precisely the flow a "who won the volume battle" thesis wants to exclude.
- **PDT.** A US margin account under $25,000 is limited to three day trades in any
  five business days. A one-trade-per-session intraday strategy runs into that
  immediately. TradeZero's non-US entity is not subject to PDT — **which entity
  holds your account is a question you must answer before anything else here
  matters.**

## F.3 Consolidated tape or single venue — the NVDA problem, again

**What is true of US equities generally:** every trade in a US-listed security must
be reported to the consolidated tape. QQQ is Nasdaq-listed, so it reports under the
UTP plan. A consolidated last-sale feed therefore contains all lit-exchange prints
**plus** off-exchange prints reported through a FINRA Trade Reporting Facility —
wholesaler internalisation, ATS/dark venues, and blocks.

**What is not automatic:** that the feed your broker shows you is that consolidated
tape. Brokers variously display the SIP consolidated feed, a direct feed from one
exchange, or a vendor composite. They are different numbers for the same symbol,
and the difference is large — not a rounding artefact.

**This is exactly what killed NVDA in this project.** The open venue ruling records
`XNAS.ITCH` carrying **25.7% of the tape** — a single-venue feed seeing roughly a
quarter of the volume. A volume profile built on a quarter of the volume is a
profile of a sample, chosen by venue routing rather than at random, and routing is
correlated with order type and size. QQQ has the same structure. It is a more
heavily traded symbol, which changes the numbers, not the problem.

**I cannot tell you from here which feed TradeZero carries.** Their marketing
mentions real-time streaming quotes and Nasdaq TotalView Level 2, and TotalView is
explicitly a **single-venue** book — Nasdaq's own. That tells you what their depth
data is. It does not settle what their time-and-sales prints are, and the two are
routinely different products on the same screen.

**Ask them exactly this**, and keep the reply:

1. "Is the last-sale / time-and-sales data in ZeroPro the **consolidated tape**
   (UTP/CTA SIP), or a single-venue feed?"
2. "If consolidated: does the displayed daily volume include **off-exchange
   (FINRA TRF) prints**?"
3. "Is Level 2 depth Nasdaq TotalView only, or a multi-venue composite?"
4. "Is there any API or export for historical **1-minute bars with volume**, and
   from which feed?"
5. "Which entity holds my account — TradeZero America or TradeZero
   International — and does the PDT rule apply to it?"

**And note what the answer cannot buy you.** Even a perfect consolidated QQQ tape
leaves the off-exchange share — commonly a third to a half of US equity volume,
and worth measuring rather than assuming — as prints with no book behind them and
no reliable aggressor side. For Layer 1 that is survivable, because Layer 1 needs
only volume at price. For Layer 2 it is not: absorption and exhaustion need to see
resting size consumed on a venue, and a TRF print tells you a trade happened
somewhere, at some point, reported within seconds. **Layer 2 on QQQ is harder than
Layer 2 on NQ, not easier.**

If the QQQ route is ever taken seriously, the venue-share measurement done for NVDA
must be repeated for QQQ before anything is built. It costs money at Databento and
should not be run speculatively.

## F.4 Net

TradeZero cannot trade the researched instrument. The proxy it can trade is a
different instrument with a fragmented tape, a different session, a different tick
economics, and a possible three-trades-per-week regulatory cap. **Nothing in the
existing study transfers to it without a fresh pre-registration.**
