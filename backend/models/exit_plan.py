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

# The line Trade Analysis writes. Anchored on `EXIT: invalidation` and NOT on a bare `EXIT:`.
# Measured 2026-10-07: 36 rows contain "EXIT:" and only 34 contain "EXIT: invalidation" -- the two
# extra are PROSE ("EXIT: open in the book for three days after the sale...", ids 404 and 406), so
# the shorter marker would admit two sentences as structured lines.
EXIT_LINE_MARKER = "EXIT: invalidation"

# R-IV.695 (TA-089): Trade Analysis standardises field text on ASCII with U+00B7 as the SEPARATOR.
# Existing rows keep their en dashes, em dashes and multiplication signs, so the parser splits on
# the separator and treats each field's text as OPAQUE: it never matches a literal harvest string
# to find a field, and never normalises a character inside one.
FIELD_SEPARATOR = "\u00b7"

# A notes column holds several blocks. The EXIT line ends at the next block break, and bounding it
# is not optional: measured on the 34 live lines, 23 have a " || " tail and 1 has a " | " tail, so
# an unbounded segment drags the following prose into the last field. (It did: the old parser's
# `stop` capture ran on past "stop none" into "|| R-IV.600(a) context displaced out of the fixed
# EXIT line: D5 sleeve position" and only survived because the vocabulary mapping read the first
# word.) 10 lines run to the end of the notes, so an absent tail is normal, not an error.
_BLOCK_SEPARATORS = (" || ", " | ")

# Each field opens with its own label. Removing a KNOWN LEADING LABEL from a field already
# identified by position is not the same act as searching the whole line for "time stop" to find
# out where a field is -- the first reads a format, the second guesses at content. The old parser
# did the second, which is why the phrase "time stop" occurring inside an invalidation would have
# broken it.
_FIELD_LABELS = (
    ("invalidation", EXIT_LINE_MARKER),      # field 0: "EXIT: invalidation <text>"
    ("time_stop", "time stop"),              # field 1: "time stop <text>"
    ("stop_type", "stop"),                   # field 2: "stop <text>"
)

_ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def has_exit_line(notes: Optional[str]) -> bool:
    """CONTAINMENT, not position. Measured: 30 of the 34 live lines do NOT begin the notes --
    437's reads `... || TA-052 EXIT: invalidation ...` at offset 751 of 2,649 -- so a startswith
    test, or a test on the start of a `||` block, misses almost all of them."""
    return EXIT_LINE_MARKER.lower() in (notes or "").lower()


def find_exit_segment(notes: Optional[str]) -> Optional[str]:
    """The EXIT line's own text: found by containment, bounded at the next block break.

    Returns None when there is no line. The segment still carries its field labels; nothing is
    stripped here, because stripping before the split is what lets a separator inside prose move
    a field.
    """
    text = notes or ""
    k = text.lower().find(EXIT_LINE_MARKER.lower())
    if k < 0:
        return None
    seg = text[k:]
    for sep in _BLOCK_SEPARATORS:
        cut = seg.find(sep)
        if cut >= 0:
            seg = seg[:cut]
    return seg


def _strip_label(field: str, label: str) -> Optional[str]:
    """Remove a known LEADING label. The remainder is returned untouched -- no character is
    stripped from it, so an em dash, an en dash or a multiplication sign inside the text survives
    exactly as Trade Analysis wrote it (R-IV.695)."""
    if field is None:
        return None
    f = field.strip()
    if f.lower().startswith(label.lower()):
        f = f[len(label):]
    # Only whitespace comes off, and only at the edges. NOT `.strip("\u00b7\u2014-")`, which the
    # old parser did and which silently deleted a trailing em dash from a field's own text.
    f = f.strip()
    return f or None


def _stop_type_from(token: Optional[str]) -> Optional[str]:
    """`broker_order`, `daily_close`, `none`, or None when the line does not say.

    None is a real answer: a row whose line omits the stop has NOT declared one, and defaulting
    that to `none` would state that the principal chose to have no stop when nobody wrote it
    down. Read from WITHIN an already-identified field, never used to find one.
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

    SPLIT ON U+00B7, FIELDS BY POSITION (R-IV.695, R-IV.696(b)). Measured on the 34 live lines:
    every one carries exactly two separators in its bounded segment, so position 0 is the
    invalidation, 1 the time stop and 2 the stop. A field the line does not carry is left EMPTY
    and named in `unparsed` -- never guessed.
    """
    out: Dict[str, Any] = {"invalidation": None, "time_stop": None, "stop_type": None,
                           "unparsed": []}
    seg = find_exit_segment(notes)
    if seg is None:
        out["unparsed"].append("no EXIT line")
        return out

    fields = seg.split(FIELD_SEPARATOR)

    # field 0 -- invalidation, opaque
    inval = _strip_label(fields[0], EXIT_LINE_MARKER) if len(fields) > 0 else None
    if inval:
        out["invalidation"] = inval
    else:
        out["unparsed"].append("invalidation")

    # field 1 -- time stop. The ISO date is read from INSIDE the field.
    if len(fields) > 1:
        token = _strip_label(fields[1], "time stop")
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

    # field 2 -- stop type, from the declared vocabulary, read inside the field
    if len(fields) > 2:
        token = _strip_label(fields[2], "stop")
        stop_type = _stop_type_from(token)
        out["stop_type"] = stop_type
        if stop_type is None:
            out["unparsed"].append("stop=%r" % token)
    else:
        out["unparsed"].append("stop")

    return out


def stop_type_check_sql(constraint: str = "unified_positions_stop_type_check") -> str:
    """Generated from STOP_TYPES rather than retyped."""
    values = ", ".join("'" + s + "'" for s in STOP_TYPES)
    return ("ALTER TABLE unified_positions ADD CONSTRAINT %s CHECK "
            "(stop_type IS NULL OR stop_type IN (%s))" % (constraint, values))
