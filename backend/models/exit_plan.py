"""A position's exit plan, as fields. R-IV.571 / gap 3, restated by R-IV.597(b).

WHY THIS EXISTS. Trade Analysis writes an exit plan onto each open row as a sentence in `notes`:

    EXIT: invalidation <text> · time stop <date|none> · stop <none|broker order> — <prose>

Prose is not a field. It cannot be queried, it cannot be counted, and R-IV.568's exit block would
have to parse it on every read — which means every reader parsing it slightly differently. The
plan moves into three columns and `notes` is left exactly as it is, so the sentence remains the
record of what was written and the fields become the thing code reads.

THE LINE IS NOT ONE FIXED FORMAT, and that is measured, not assumed. Of the four open rows
carrying it on 2026-09-26, two put the stop inside the trailing prose rather than in the third
slot:

    RAMZ / SRTY   ... · time stop 2026-10-24 · stop none — written daily-close level...
    PDBC / WRTH   ... · time stop none — D5 sleeve position · stop none; counts to T1...

So the parser looks for `stop <x>` anywhere in the line rather than only in the third position. A
parser that assumed the stated shape would have silently read `stop_type` as unknown on half the
rows it was written for.

WHAT `stop_type` MEANS, NARROWLY. It records HOW an exit is enforced, taken from the line's own
`stop` token and from nothing else (R-IV.597(b)2: "infer nothing from other prose"). All four
rows say `stop none`, meaning **no resting order at the broker**. Two of them separately describe
their invalidation as a "written daily-close level" — but that is prose about the invalidation,
not the stop field, so it is NOT read as `daily_close` here. The distinction is flagged rather
than decided: `daily_close` exists in the vocabulary for a line that says so.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, Optional

BROKER_ORDER = "broker_order"
DAILY_CLOSE = "daily_close"
NONE = "none"

STOP_TYPES = (BROKER_ORDER, DAILY_CLOSE, NONE)

# The line Trade Analysis writes. Anchored on `EXIT: invalidation` because that is the only part
# every row shares.
EXIT_LINE_MARKER = "EXIT: invalidation"

_INVALIDATION = re.compile(r"EXIT:\s*invalidation\s+(.*?)(?=\s+·\s*time stop\b)", re.I | re.S)
_TIME_STOP = re.compile(r"·\s*time stop\s+([^·—\n]+)", re.I)
# `stop` ANYWHERE after the marker, but not the words `time stop`, which the negative lookbehind
# excludes -- without it every row's `time stop` would be read as its stop type.
_STOP = re.compile(r"(?<!time )\bstop\s+([^·;—\n]+)", re.I)

_ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def has_exit_line(notes: Optional[str]) -> bool:
    return EXIT_LINE_MARKER.lower() in (notes or "").lower()


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    out = value.strip().strip("·—-").strip()
    return out or None


def _stop_type_from(token: Optional[str]) -> Optional[str]:
    """`broker_order`, `daily_close`, `none`, or None when the line does not say.

    None is a real answer: a row whose line omits the stop has NOT declared one, and defaulting
    that to `none` would state that the principal chose to have no stop when nobody wrote it
    down. The loss alert already treats an unknown broker stop as unknown rather than absent
    (R-IV.526), and this keeps the two consistent.
    """
    if not token:
        return None
    text = token.strip().lower()
    if text.startswith("none") or text == "no":
        return NONE
    if "broker" in text:
        return BROKER_ORDER
    if "daily close" in text or "daily_close" in text:
        return DAILY_CLOSE
    return None


def parse_exit_line(notes: Optional[str]) -> Dict[str, Any]:
    """The three fields, plus what could not be read. Never raises.

    `unparsed` lists the parts the line did not yield, so a partial migration reports which rows
    need a human rather than writing a confident NULL.
    """
    out: Dict[str, Any] = {"invalidation": None, "time_stop": None, "stop_type": None,
                           "unparsed": []}
    text = notes or ""
    if not has_exit_line(text):
        out["unparsed"].append("no EXIT line")
        return out

    # The line runs from the marker to the end of that note segment.
    start = text.lower().index(EXIT_LINE_MARKER.lower())
    line = text[start:].split(" | ")[0]

    m = _INVALIDATION.search(line)
    if m:
        out["invalidation"] = _clean(m.group(1))
    else:
        out["unparsed"].append("invalidation")

    m = _TIME_STOP.search(line)
    if m:
        token = _clean(m.group(1))
        if token and token.lower().startswith("none"):
            out["time_stop"] = None
        else:
            d = _ISO_DATE.search(token or "")
            if d:
                out["time_stop"] = date.fromisoformat(d.group(1))
            else:
                out["unparsed"].append("time_stop=%r" % token)
    else:
        out["unparsed"].append("time stop")

    m = _STOP.search(line)
    if m:
        stop_type = _stop_type_from(m.group(1))
        out["stop_type"] = stop_type
        if stop_type is None:
            out["unparsed"].append("stop=%r" % _clean(m.group(1)))
    else:
        out["unparsed"].append("stop")

    return out


def stop_type_check_sql(constraint: str = "unified_positions_stop_type_check") -> str:
    """Generated from STOP_TYPES rather than retyped."""
    values = ", ".join("'" + s + "'" for s in STOP_TYPES)
    return ("ALTER TABLE unified_positions ADD CONSTRAINT %s CHECK "
            "(stop_type IS NULL OR stop_type IN (%s))" % (constraint, values))
