"""Central configuration. Every parameter in IVB-SPEC.md sec (f) lives here.

Nothing in this project reads a magic number from anywhere else. If a value is not
in this file, it is a bug.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "output"

# --------------------------------------------------------------------------
# Instrument economics -- IVB-SPEC.md sec 0.2.5
# Levels always come from NQ. Only the dollar multiplier differs.
# --------------------------------------------------------------------------
TICK_SIZE = 0.25  # index points, NQ and MNQ alike

COST_MODELS = {
    "NQ": {"point_value": 20.0, "tick_value": 5.00},
    "MNQ": {"point_value": 2.0, "tick_value": 0.50},
}


@dataclass(frozen=True)
class Config:
    # ---- Layer 0 / P0 primary configuration (sec g.0) --------------------
    ib_minutes: int = 30
    breakout_trigger: str = "close_through"   # or "trade_through"
    breakout_buffer_ticks: int = 1
    entry_fill: str = "next_bar_open"          # or "trigger_price"
    baseline_stop: str = "opposite_ib_extreme"  # or "k_ib_range"
    baseline_stop_k: float = 0.50
    r_mult: float = 2.0

    # ---- No-trade filter (sec f) -----------------------------------------
    min_ib_range_atr: float = 0.15
    min_ib_range_ticks: int = 0

    # ---- Session clock ----------------------------------------------------
    rth_open: time = time(9, 30)
    trade_end: time = time(11, 30)   # hard flat
    rth_close: time = time(16, 0)

    # ---- Costs ------------------------------------------------------------
    cost_model: str = "MNQ"          # kill criteria judged on MNQ
    commission_per_side: float = 0.85
    slippage_ticks_market: int = 1

    # ---- Execution realism -------------------------------------------------
    intrabar: str = "pessimistic"     # or "optimistic" (diagnostic only)

    # ---- Sample ------------------------------------------------------------
    partition: str = "DEVELOPMENT"
    exclude_half_days: bool = True
    exclude_covid: bool = False       # kept in, flagged
    atr_period: int = 14

    # ---- Statistics ---------------------------------------------------------
    bootstrap_block: str = "month"
    bootstrap_n: int = 10_000
    n_shuffles: int = 1_000
    seed: int = 20260101

    # ---- Gates ---------------------------------------------------------------
    ambiguous_bar_gate: float = 0.15

    label: str = "P0"

    @property
    def point_value(self) -> float:
        return COST_MODELS[self.cost_model]["point_value"]

    @property
    def tick_value(self) -> float:
        return COST_MODELS[self.cost_model]["tick_value"]

    @property
    def buffer_points(self) -> float:
        return self.breakout_buffer_ticks * TICK_SIZE

    @property
    def slippage_points(self) -> float:
        return self.slippage_ticks_market * TICK_SIZE

    def with_(self, **kw) -> "Config":
        return replace(self, **kw)


P0 = Config()

# The 16-configuration sensitivity grid (sec g.0.1). NOT an optimisation.
GRID_R_MULTS = (1.0, 1.5, 2.0, 3.0)
GRID_STOPS = ("opposite_ib_extreme", "k_ib_range")
GRID_TRIGGERS = ("close_through", "trade_through")


def sensitivity_grid() -> list[Config]:
    """All 16 configs. Reported as a table; never as a best case."""
    out = []
    for r in GRID_R_MULTS:
        for s in GRID_STOPS:
            for t in GRID_TRIGGERS:
                out.append(
                    P0.with_(
                        r_mult=r,
                        baseline_stop=s,
                        breakout_trigger=t,
                        label=f"R{r}_{s}_{t}",
                    )
                )
    return out
