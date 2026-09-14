"""Data provenance and the POSITIVE-CONTROL QUARANTINE -- IVB-SPEC.md sec b.11.

A control file that was TUNED until a gate returned the wanted verdict was selected
to produce an outcome. Every other number it carries was selected along with it, as
a side effect, without anyone deciding to select it. So the rule is not "be careful
with the positive control"; it is:

    THE POSITIVE CONTROL MAY SOURCE EXACTLY ONE THING: the proof that the sec b.9
    gate's PASS branch executes. It may never source a reported statistic.

That covers fill rates, exit mixes, touch-only fractions, close_invalidation
frequencies, funnel counts, MFE quantiles, cell counts, PnL -- everything. This
module makes the rule mechanical rather than a note in a document that a future
session has to remember.

The negative control is NOT quarantined in the same way. It was not tuned to a
verdict: it is a driftless random walk with i.i.d. volume, and its job is to be the
null. Its numbers are still synthetic and still inadmissible as findings about NQ,
which is a separate and weaker caveat carried by `banner`.
"""
from __future__ import annotations

from pathlib import Path

NEGATIVE_CONTROL = "negative_control"
POSITIVE_CONTROL = "positive_control"
REAL = "real"

#: The single permitted use of the positive control. Anything not on this list is
#: refused. It is a list of one on purpose -- see the module docstring.
POSITIVE_CONTROL_ALLOWED = frozenset({"b9_gate_verdict"})

QUARANTINED = "[QUARANTINED -- positive control]"


class QuarantineError(RuntimeError):
    """Raised when a statistic is sourced from the tuned positive control."""


def classify(path: str | Path) -> str:
    """Which file is this? Decided on the filename, which is what names the file's
    generator (`tests/make_synthetic.py` owns both synthetic names).
    """
    name = Path(path).name.lower()
    if "synthetic_structured" in name or "anchored" in name:
        return POSITIVE_CONTROL
    if "synthetic" in name:
        return NEGATIVE_CONTROL
    return REAL


def is_synthetic(kind: str) -> bool:
    return kind in (NEGATIVE_CONTROL, POSITIVE_CONTROL)


def assert_reportable(kind: str, statistic: str) -> None:
    """Gatekeeper. Call this before ANY number leaves a run as a reported figure.

    Raises QuarantineError if the run is sourced from the positive control and the
    statistic is not the one thing that file is allowed to produce.
    """
    if kind != POSITIVE_CONTROL:
        return
    if statistic in POSITIVE_CONTROL_ALLOWED:
        return
    raise QuarantineError(
        "sec b.11 QUARANTINE: {!r} may not be sourced from the POSITIVE CONTROL.\n"
        "That file's generator was tuned until the sec b.9 gate returned "
        "'not material', so it was SELECTED to produce an outcome, and every other "
        "statistic in it was selected along with it. The positive control may prove "
        "one thing only: that the gate's pass branch executes ({}).\n"
        "Re-run this on data/raw/synthetic.parquet (negative control) or on real NQ "
        "bars.".format(statistic, ", ".join(sorted(POSITIVE_CONTROL_ALLOWED)))
    )


def redact(kind: str, statistic: str, text: str) -> str:
    """Non-raising variant, for console lines that should still show their LABEL.

    Charts and console output on the positive control keep the row so the reader can
    see that the number exists and was deliberately withheld -- a silently missing
    line looks like the statistic was never computed.
    """
    if kind != POSITIVE_CONTROL or statistic in POSITIVE_CONTROL_ALLOWED:
        return text
    return QUARANTINED


def banner(kind: str) -> list[str]:
    """Header lines for any output derived from a control file."""
    if kind == POSITIVE_CONTROL:
        return [
            "*** POSITIVE CONTROL -- QUARANTINED (sec b.11).",
            "*** This file's generator was TUNED until sec b.9 returned 'not",
            "*** material'. It was selected to produce an outcome, so every other",
            "*** number in it was selected too. The ONLY admissible output of this",
            "*** file is the sec b.9 gate verdict, as proof the pass branch runs.",
            "*** All other statistics below are withheld, not missing.",
        ]
    if kind == NEGATIVE_CONTROL:
        return [
            "*** NEGATIVE CONTROL -- synthetic random walk. Not tuned to any verdict,",
            "*** so its statistics are not quarantined -- but they are still SYNTHETIC",
            "*** and are never findings about NQ. Shapes and plumbing only.",
        ]
    return []
