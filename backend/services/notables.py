"""NOTABLES v2: the mock fixture and the lint that guards its wording. R-IV.1259.

DISPLAY ONLY (#42). Nothing here writes `signals` or `signal_outcomes`, and the mock step
writes nothing at all -- R-IV.1259(h) puts `notables_log` and `notables_outcomes` in the deploy
that first writes to them, so neither table is created yet.

TWO LINTS, NOT ONE, and the separation is the point.

`regime_playbook.order_findings` is reused unchanged for the instruction check: R-IV.1259(g)
holds NOTABLES to the no-orders bar, and a second implementation of "is this an order?" would
eventually disagree with the first -- the surface with the looser one being the one that ships
the instruction. That module's rule is GRAMMAR, and its docstring argues at length that a word
list cannot make the call it makes.

R-IV.1259(g) then asks for exactly a word list: "cheap", "opportunity", "setup", "entry",
"target" and "breakout coming". Those are not imperatives, so the grammar rule cannot see them;
they are a different fault -- SALES WORDING, a card presenting a measurement as a prospect. So
they get their own function and their own finding prefix, and `order_findings` keeps being what
its own docstring says it is.

ONE CONFLICT, REPORTED AND NOT RESOLVED HERE. R-IV.1259(f) specifies the IV-rank tag as
"cheap below 30, neutral 30-60, rich above 60", and (g) adds "cheap" to the banned list. The
same ruling therefore mandates and forbids the same word on the same card. The mock does not
have to choose -- neither approved mock renders a sub-30 rank, so no fixture string says
"cheap" -- and `SALES_WORDS` bans it as (g) writes it. The live strip WILL hit a sub-30 rank,
so (f) needs a replacement label before wiring. `IV_RANK_CONFLICT` records that in code rather
than only in a report, because a conflict noted in a comment and nowhere else is how it ships.

SCOPED TO NOTABLES TEXT. The sales list is not applied repo-wide: "setup" is River's own word
for a roster row ("No roster setup below A fired this cycle") and `entry_target` is a watchlist
column. Widening the ban to those would be a rewrite of surfaces this ruling does not touch.
"""
from __future__ import annotations

import io
import json
import os
import re
from typing import Any, Dict, Iterable, List, Tuple

from services.regime_playbook import order_findings, walk_texts

#: Under `frontend/assets/` because CLAUDE.md serves only that folder wholesale: the browser
#: and this lint read THE SAME BYTES. A second copy for the card would be a second place for a
#: text to drift away from the one that was checked.
ASSETS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "frontend", "assets", "notables")

MOCK_VERSION = "v1"
MOCK_FILE = "notables_mock.%s.json" % MOCK_VERSION

#: R-IV.1259(b): the two mocks Nick approved, by sha256 of their bytes. Recorded so the thing
#: built from them can be checked against them, rather than against a memory of them.
APPROVED_MOCKS = {
    "main": "3bfb1943eab1f8d0e9471484d694446747ed2c8f7657fa037b42630f707061ab",
    "states": "d78757ee6b5eabf832acee644c55d1996cdbf55ad23d22d6c4a8437b7388643f",
}

#: R-IV.1259(g)'s additions, verbatim. A card states what happened and what argues against it;
#: these words state what it is FOR, which is the reader's call and not the hub's.
SALES_WORDS = (
    "cheap", "opportunity", "setup", "entry", "target",
)

#: The one multi-word entry. Matched as a phrase, so "the breakout failed" -- a description of
#: what the tape did -- is untouched while "breakout coming" is not.
SALES_PHRASES = (
    "breakout coming",
)

#: THE CONFLICT, and its resolution, both kept. (f) mandated "cheap" as the sub-30 IV-rank label
#: while (g) banned the word, so one ruling required and forbade the same word on the same card.
#: R-IV.1265(c) settled it BY WORDING: the tag reads "IV LOW" / "IV MID" / "IV HIGH" and "cheap"
#: stays banned everywhere. The conflict text stays on the record rather than being deleted --
#: the next reader of a card that says "IV LOW" should be able to find out why it does not say
#: what (f) says.
IV_RANK_CONFLICT = (
    "R-IV.1259(f) labelled a sub-30 IV rank \"cheap\" and (g) banned the word \"cheap\". "
    "RESOLVED by R-IV.1265(c): the tag reads \"IV LOW\" (below 30), \"IV MID\" (30-60) and "
    "\"IV HIGH\" (above 60), and \"cheap\" stays banned everywhere. The bands live in "
    "models/notables_strip.py, which owns the edges."
)
IV_RANK_CONFLICT_RESOLVED_BY = "R-IV.1265(c)"

#: The v1 universe on screen, R-IV.1259(e). AMZN is NOT in it: the approved mock used it as
#: illustration and (b) says so explicitly, so a fixture that kept it would be the one place a
#: reader could learn the wrong universe from.
UNIVERSE = frozenset({
    "SPY", "QQQ", "IWM", "DIA", "RSP",
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLC", "XLRE",
    "SMH", "KRE", "TLT", "HYG", "GLD",
})

#: QQQ is excluded from cards 2 and 3 by R-IV.1258(a)4, cited in R-IV.1259(e).
NO_STRUCTURE_CARDS = frozenset({"QQQ"})

#: Card kinds the fixture must cover: the five cards of (c), then the six states of (d).
CARD_KINDS = ("loud_move", "value_moved", "failed_break", "trend_change")
STATE_KINDS = ("state_aging", "state_thin", "state_unverified", "state_loud_known",
               "state_quiet", "state_cap")

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9\-]*")


def sales_findings(text: str) -> List[str]:
    """Every reason `text` sells rather than reports. Empty list means it does not.

    WHOLE WORDS ONLY. A substring match would catch "entry" inside "entries" (fine) and also
    inside unrelated words, and it would catch "target" inside a column name a caption quotes.
    The words are matched as words; the one phrase is matched as a phrase.
    """
    low = (text or "").lower()
    words = set(w.lower() for w in _WORD.findall(low))
    out = []
    for w in SALES_WORDS:
        if w in words:
            out.append("sales wording: %r" % w)
    for p in SALES_PHRASES:
        if p in low:
            out.append("sales wording: %r" % p)
    return out


def lint_findings(obj: Any) -> List[str]:
    """Both lints over every string in `obj`, each finding naming its dotted path.

    EVERYTHING, not only the keys that look like copy: a text is not made safe by living under
    a key nobody expects to be displayed. `walk_texts` is reused for the same reason
    `order_findings` is -- one walker, one answer about what counts as text.
    """
    out: List[str] = []
    for path, text in walk_texts(obj):
        for f in order_findings(text):
            out.append("%s: %s" % (path, f))
        for f in sales_findings(text):
            out.append("%s: %s" % (path, f))
    return out


def mock_path() -> str:
    return os.path.join(ASSETS, MOCK_FILE)


def load_mock() -> Dict[str, Any]:
    """The fixture, parsed. Raises rather than returning a default: a mock that cannot be read
    must fail the build, not render as an empty surface that looks like a quiet day."""
    with io.open(mock_path(), encoding="utf-8") as fh:
        return json.load(fh)


def tickers_in(obj: Any) -> List[str]:
    """Every ticker-shaped value the fixture names on a card, for the universe check."""
    out = []
    for path, text in walk_texts(obj):
        if path.endswith("ticker"):
            out.append(text)
    return out


def cards(mock: Dict[str, Any]) -> Iterable[Tuple[str, Dict[str, Any]]]:
    """(kind, card) for every card in the fixture, context and states included."""
    loud = (mock.get("context") or {}).get("loud_move")
    if loud:
        yield loud.get("kind", "loud_move"), loud
    for c in mock.get("watch") or []:
        yield c.get("kind", "?"), c
    for s in mock.get("states") or []:
        yield s.get("kind", "?"), s
