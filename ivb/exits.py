"""Exit taxonomy for Layer 1 -- IVB-SPEC.md sec (c), c.1, c.2.

The whole Layer 1 case rests on ONE number: how often a close-beyond-the-far-VA-edge
exit fires INSTEAD of the hard stop. If those two are conflated -- in a string, in a
"scenario" label, or on a chart -- that number cannot be read, so the taxonomy is
pinned here as a closed enum and nothing else is allowed to invent a category.

    tp1                 the R-multiple target filled (limit order)
    close_invalidation  sec (c): a TF_inval CLOSE beyond the far VA edge;
                        exit at the next 1-minute bar OPEN, market
    hard_stop           sec c.1: the resting stop at far_edge -/+ hard_stop_ticks
    time_stop           flat at trade_end (11:30 ET), market

HARD-STOP DOMINANCE
    A close_invalidation can only be *reported* as such if its market exit price is
    strictly better than the hard stop. If the next bar opens at or beyond the hard
    stop, the resting stop order was already filled -- calling that exit an
    invalidation would move a loss out of the hard_stop bucket and into the
    close_invalidation bucket, which is precisely the count sec c.3 turns on.
    `resolve` enforces that. It is a classification rule, not a price rule: the
    fill price is the same either way.
"""
from __future__ import annotations

from collections import Counter

TP1 = "tp1"
CLOSE_INVALIDATION = "close_invalidation"
HARD_STOP = "hard_stop"
TIME_STOP = "time_stop"

LAYER1_EXIT_REASONS = (TP1, CLOSE_INVALIDATION, HARD_STOP, TIME_STOP)

#: ivb/backtest.py is Layer 0 -- one stop, no invalidation rule -- and keeps its
#: own short strings. This maps them into the shared vocabulary for reporting.
LAYER0_TO_LAYER1 = {"target": TP1, "stop": HARD_STOP, "time": TIME_STOP}

#: Which reasons are losses by construction. tp1 is a win; time_stop is either.
ADVERSE_EXITS = (CLOSE_INVALIDATION, HARD_STOP)


def validate(reason: str) -> str:
    if reason not in LAYER1_EXIT_REASONS:
        raise ValueError(
            "unknown exit_reason {!r}; expected one of {}".format(
                reason, LAYER1_EXIT_REASONS))
    return reason


def resolve(direction: int, reason: str, exit_price: float, hard_stop: float) -> str:
    """Apply hard-stop dominance, then validate. See the module docstring."""
    validate(reason)
    if reason != CLOSE_INVALIDATION:
        return reason
    beyond = (exit_price <= hard_stop) if direction == 1 else (exit_price >= hard_stop)
    return HARD_STOP if beyond else CLOSE_INVALIDATION


def frequency(reasons) -> dict:
    """Counts for EVERY enum member, zeros included, plus the total.

    Zeros are kept deliberately: "close_invalidation fired 0 times" is a result,
    and a dict that silently omits the key reads as "not measured".
    """
    c = Counter(validate(r) for r in reasons)
    out = {k: int(c.get(k, 0)) for k in LAYER1_EXIT_REASONS}
    out["total"] = int(sum(out.values()))
    return out


def format_frequency(freq: dict) -> str:
    """One line per reason: count and percent of resolved exits."""
    n = max(1, freq.get("total", 0))
    return "\n".join(
        "     {:<20s} {:>6,d}   {:5.1f}%".format(k, freq[k], 100.0 * freq[k] / n)
        for k in LAYER1_EXIT_REASONS)
