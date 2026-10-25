"""B9: the global markets + commodities tracker. Its vocabulary, its lint, and its fixture.

GOVERNING DOCUMENT, verified before any work started (R-IV.1265(e)):

    C:\\temp\\cc-query-handoff\\GLOBAL-MARKETS-TRACKER-2026-10-18-v3.md
    sha256 3c9c2850825f4477b7885f0dd160c0ab4d129169611e72e3dcbb39681784fd1c   27,642 bytes

Verified two ways (sha256sum and PowerShell Get-FileHash). The `5c97eeea...` copy that was on
this machine before the ferry is the TWICE-SUPERSEDED one, and building from it would have
committed the error R-IV.1224(f)'s re-verification clause exists to prevent.

THE DOCUMENT'S OWN CAVEAT IS CARRIED ONTO THE SURFACE, not left in the document: "every
historical figure below is the seats' recollection. No live data or web was used. Each must be
verified before anything is displayed." A panel built from recalled figures that does not say so
is a panel that launders recollection into data. The one figure that IS measured -- the race
footnote, from QUERY 2026-10-18 -- names its source in its own sentence, which is why it is the
only historical claim this module will print.

AND THE REFRAME SUPERSEDES THE ASIA FRAMING. Nick's 08:51 reframe is in the same document and
replaces the "Asia thesis" panel with the market-neutral "A NEW LEADER IS REAL IF", and the
meltdown panel with the RECOVERY RACE over every market including SPY and QQQ. The bias check
says why in one line: "The tool must be as loud when SPY reclaims first as when Asia does." So
there is no Asia-specific panel here at all, and the keep-out list below enforces it.

THE DRY-RUN LINE "1 of 10" IS WITHDRAWN and no panel states it.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from services.regime_playbook import order_findings, walk_texts

#: R-IV.1364(c): the B9 mock fixture (world_mock.v1.json) and its loader were removed in the
#: no-mock sweep; B9 is live (services/b9_live.py, /api/b9/world).

DOC_SHA256 = "3c9c2850825f4477b7885f0dd160c0ab4d129169611e72e3dcbb39681784fd1c"
DOC_FILE = "GLOBAL-MARKETS-TRACKER-2026-10-18-v3.md"
DOC_SUPERSEDED = ("5c97eeea6cc0d7d00c6c983af8a3d04a53ec5c3355d52a7cb95fd0d6f2275f7d",
                  "75c4ba39")

#: Amendment 1: THE RACE IS EQUITY ONLY. "A race is a comparison, and comparing an equity
#: index's recovery with gold's is a comparison of two different things on one axis."
RACE_UNIVERSE = ("EWJ", "FXI", "EWY", "EWT", "INDA", "EEM", "VGK", "SPY", "QQQ")

#: The four commodity ETFs, which are a SEPARATE CONTEXT LIST and are never raced.
COMMODITIES = ("GLD", "CPER", "USO", "DBA")

#: Amendment 4: FXI stands, MCHI is superseded. One China proxy, chosen, not both.
SUPERSEDED_TICKERS = ("MCHI",)

#: Amendment 2: every computation uses Adj Close, and the label is the point -- a reader who
#: assumes price return will misread a year of a high-yielding index like VGK.
RETURN_BASIS = "USD total return"
RETURN_BASIS_NOTE = ("Adj Close, so dividends are included; a price-return reading of the same "
                     "window would be lower by the yield, which matters most on VGK")

#: Amendment 3: the labels are B3's, and each carries its MEASURED fires per year. A threshold
#: whose frequency is not stated is a threshold nobody can calibrate against.
UNUSUAL = "UNUSUAL"
EXTREME = "EXTREME"
UNUSUAL_Z = 2.0
EXTREME_Z = 3.0
FIRES_PER_YEAR = {UNUSUAL: "14-16/yr", EXTREME: "2.6-3.8/yr"}

#: The z-score window, and the one thing about it that is easy to get wrong: TODAY IS EXCLUDED
#: from the 60 days it is scored against. Included, a large move inflates its own denominator
#: and scores lower than it should -- the move the test exists to catch is the one it would
#: understate.
Z_WINDOW = 60
Z_EXCLUDES_TODAY = True

#: Amendment 6: the race's column order, which is also an order of AUTHORITY. The footnote says
#: the first column is the one history supports and the last is the one it does not.
RACE_COLUMNS = ("gained most since SPY's low", "first back above 200d",
                "first to accept higher prices", "fell least")

#: Amendment 7: the footnote, VERBATIM. Not paraphrased, not reflowed. It is also a worked
#: example of Convention #37 as clarified by R-IV.1224(g): source, universe and as-of in the
#: same sentence as the figure.
RACE_FOOTNOTE = (
    "US selloffs since 2003 (9 episodes; equity ETFs; USD total return; QUERY 2026-10-18): "
    "the 'gained most' leader still led SPY 6 months later in 8 of 9, 'fell least' in 2 of 9. "
    "History, not a forecast.")

#: The document's own caveat, carried onto the surface.
RECOLLECTION_CAVEAT = ("Every historical figure in B9's source document is the seats' "
                       "recollection, not a measurement. Only the race footnote below is "
                       "measured, and it names its source.")

#: Meltdown mode arms here (the PIVOT synthesis's figure, not THALES's 15%).
MELTDOWN_DRAWDOWN_PCT = 10.0
MELTDOWN_HIGH_SESSIONS = 252

#: The currency-gap flag: the ETF's USD return minus the local index return, over one month.
CURRENCY_GAP_FLAG_PP = 1.5

#: The commodity cross-reads' flags.
CRUDE_ATR_FLAG = 2.0
USDJPY_5D_FLAG_PCT = -3.0

#: The overnight tape's label, verbatim from the synthesis.
OVERNIGHT_LABEL = "reacting to the prior US close \u00b7 context, not a forecast"

#: THE KEEP-OUT LIST, from the synthesis's own "Keep out" block. Each entry is a phrase a panel
#: must never print. These are not the no-orders lint's business -- they are not instructions,
#: they are CLAIMS the document rules out -- so they get their own check, exactly as NOTABLES'
#: sales wording did.
KEEP_OUT_PHRASES = (
    "buy asia", "generational buy", "dominance score", "thesis score",
    "asian dominance", "asian century", "predicts the us open",
)

#: Single words that would only appear as part of a ruled-out claim. Kept separate from the
#: phrases so a finding says which kind it was.
KEEP_OUT_WORDS = ("gdp",)

#: What the keep-out list does NOT forbid, written down because an exception that is not stated
#: is a hole. "Asia" alone is a region and appears in a ticker's own description; the document
#: rules out the LABELS, not the continent.
KEEP_OUT_ALLOWED = ("asia", "china", "japan", "dominant")

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9\-']*")


def keep_out_findings(text: str) -> List[str]:
    """Every reason `text` breaks the document's keep-out list. Empty means it does not.

    PHRASES ARE MATCHED AS PHRASES and the one word as a word, so "Asia" on its own -- a region,
    and part of a ticker's description -- is untouched while "buy Asia" is not. A substring ban
    on "asia" would forbid the panel from naming the markets it tracks.
    """
    low = (text or "").lower()
    out = []
    for phrase in KEEP_OUT_PHRASES:
        if phrase in low:
            out.append("keep-out phrase: %r" % phrase)
    words = {w.lower() for w in _WORD.findall(low)}
    for word in KEEP_OUT_WORDS:
        if word in words:
            out.append("keep-out word: %r" % word)
    return out


def lint_findings(obj: Any) -> List[str]:
    """Both lints over every string in `obj`, each finding naming its dotted path.

    `order_findings` is reused UNCHANGED: B9 is held to the no-orders bar like every other
    surface, and a second implementation of "is this an order?" would eventually disagree with
    the first.
    """
    out: List[str] = []
    for path, text in walk_texts(obj):
        for f in order_findings(text):
            out.append("%s: %s" % (path, f))
        for f in keep_out_findings(text):
            out.append("%s: %s" % (path, f))
    return out


def label_for(z: Optional[float]) -> Optional[str]:
    """Amendment 3's label for a z-score, or None when there is no z.

    |z| IS THE TEST, so a 3-sigma fall and a 3-sigma rise carry the same label -- the panel's
    arrow carries the direction. None rather than a label when z is absent: a missing z is not a
    normal day.
    """
    if z is None:
        return None
    try:
        a = abs(float(z))
    except (TypeError, ValueError):
        return None
    if a != a:
        return None
    if a >= EXTREME_Z:
        return EXTREME
    if a >= UNUSUAL_Z:
        return UNUSUAL
    return None


def tooltip_for(label: Optional[str]) -> Optional[str]:
    """Amendment 3: the label's MEASURED fires per year, in the tooltip."""
    if label not in FIRES_PER_YEAR:
        return None
    return ("%s: |z| over %.0f against the prior %d sessions excluding today, which fires %s"
            % (label, UNUSUAL_Z if label == UNUSUAL else EXTREME_Z, Z_WINDOW,
               FIRES_PER_YEAR[label]))


def race_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The race, equity only and in amendment 6's column order. Refuses a commodity.

    A COMMODITY IN THE RACE IS A REFUSAL, NOT A FILTER. Silently dropping it would leave a
    caller believing it had raced eleven markets when it raced seven -- and the amendment's
    reason is that the comparison itself is wrong, which a filter hides.
    """
    out = []
    for r in rows:
        t = str(r.get("ticker") or "").upper()
        if t in COMMODITIES:
            raise ValueError("%s is a commodity: amendment 1 keeps it out of the race, in the "
                             "separate context list" % t)
        if t in SUPERSEDED_TICKERS:
            raise ValueError("%s is superseded by FXI (amendment 4): one China proxy, chosen"
                             % t)
        if t not in RACE_UNIVERSE:
            raise ValueError("%s is not in the race universe %s" % (t, RACE_UNIVERSE))
        out.append(dict(r, ticker=t))
    return out
