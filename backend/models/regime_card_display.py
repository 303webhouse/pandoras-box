"""The card's display-only text, read from its own config. R-IV.1303(b).

WHY THIS MODULE EXISTS. The cost line used to be served from `regime_rules.<version>.json`, on
the reasoning that a sentence describing the rules should sit beside the rules so it cannot
drift from them. That was wrong in one specific way, and R-IV.1297(e) is where it bit:

    the rules file is a CLASSIFICATION artifact -- stamped, hashed, byte-identical, immutable
    the cost line is a DISPLAY fact    -- it changes whenever someone GRADES the classifier

Holding both in one file meant the only way to correct the sentence was to edit a file pinned to
`4bc6d895...`, and R-IV.1043(c) makes a ferried artifact immutable. Two instructions, one file,
no way to satisfy both. R-IV.1303(b) splits them: the rules file stays byte-identical and its
own `hysteresis.stated_cost` IS NOT DISPLAYED.

WHAT ABSENT MEANS, and why it is not an error. A version with no line shows NO cost line. That
is a deliberate state today, not a gap: QUERY supplies v2.1's line under R-IV.1301(c), and the
previous wording was found misleading by R-IV.1280 -- it called QUERY's own graded figures
"ungraded" and dropped the censoring. BUILD does not author a cost line (R-IV.925(b)); a claim
about measured behaviour belongs to whoever measured it.

So `cost_lines(...)` returns an empty list rather than a placeholder, and the card renders
nothing at all -- not a heading with nothing under it, which reads as a failed load.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

#: Beside the rules files it deliberately does not read.
DISPLAY_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "config", "regime_card_display.v1.json")

#: What a caller gets when the file itself cannot be read. NOT an exception: a display-text
#: read must cost the card its cost line, never its label. The same rule
#: `services/read_only/regime_strategy.py` already states for its own leaf reads.
_EMPTY: Dict[str, Any] = {"version": None, "cost_lines": {}}


def load_display_config(path: Optional[str] = None) -> Dict[str, Any]:
    """The display config, or an empty one. Never raises."""
    try:
        with open(path or DISPLAY_PATH, encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else dict(_EMPTY)
    except Exception:                                               # noqa: BLE001
        return dict(_EMPTY)


def cost_lines(rules_version: Optional[str] = None,
               config: Optional[Dict[str, Any]] = None) -> List[str]:
    """The cost line(s) for `rules_version`, oldest-stated first. Empty when there is none.

    A LIST, because the card's "COSTS, STATED" block is a list and §2 does not promise exactly
    one sentence. A single string in the config is accepted and wrapped, so a later editor
    cannot produce a card that renders the characters of a sentence as separate bullets -- which
    is what `list("abc")` would have done.

    NEVER FALLS BACK TO ANOTHER VERSION. Showing v2's line under a v2.1 label would attribute a
    measurement to a classifier that did not produce it, which is the exact fault R-IV.1280
    found in the old wording.
    """
    cfg = config if config is not None else load_display_config()
    lines = (cfg or {}).get("cost_lines") or {}
    if not isinstance(lines, dict):
        return []
    got = lines.get(str(rules_version or ""))
    if got is None:
        return []
    if isinstance(got, str):
        return [got] if got.strip() else []
    if isinstance(got, (list, tuple)):
        return [str(x) for x in got if str(x).strip()]
    return []


def has_cost_line(rules_version: Optional[str] = None,
                  config: Optional[Dict[str, Any]] = None) -> bool:
    """Whether the card should render the block at all."""
    return bool(cost_lines(rules_version, config))
