"""Instrument classification — T5, the SINGLE implementation (R-IV.279(e), R-IV.287).

Product type, not liquidity tier. Two inputs and no third:

  1. UW `/info` `issue_type`, per ticker (24h cached — one call also serves S4).
  2. The cash-settled index list carried in DEF-TRITON-INDEX-UNGRADEABLE.

`INDEX_TICKERS` IS NEVER CONSULTED. It is a $2M premium FLOW TIER whose nine
members include six single names (NVDA, AVGO, MSFT, GOOGL, AMZN, META); a reader
who takes it for an instrument class silently labels the largest single names in
the book as indices. Renaming it is part of this task -- while the name survives,
the next reader repeats the mistake.

VOCABULARY READ LIVE 2026-09-06, before this module was written (report contract
item 6, R-IV.289(d)). Out-of-band, key-safe, one-off:

    SPY   HTTP 200  issue_type "ETF"            sector None
    XLF   HTTP 200  issue_type "ETF"            sector None
    NVDA  HTTP 200  issue_type "Common Stock"   sector "Technology"
    SPX   HTTP 200  issue_type null             sector None

THREE FACTS THAT SHAPED THIS MODULE, none of them assumable from the field name:

  * `issue_type` IS NULL FOR SPX. The cash-settled list is therefore not a
    convenience; it is the only thing that classifies those symbols, which is why
    it is consulted FIRST rather than as a fallback.
  * `sector` IS NULL FOR EVERY ETF measured. S4's sector stratum will be UNMAPPED
    across most of the Triton universe, and that is a property of the vendor, not
    of the map -- it must be declared on the registration face, not discovered.
  * `/info` ANSWERED 200 while `/ohlc/1d` served nothing, which independently
    re-confirms DEF-UW-OHLC-DEAD is endpoint-specific rather than an auth or
    account failure.

UNKNOWN IS NEVER GUESSED. An unrecognised or absent `issue_type` on a ticker that
is not cash-settled yields UNMAPPED -- the same rule S4 gives sector. A guess here
would be indistinguishable from a measurement downstream.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

CLASS_CASH_SETTLED_INDEX = "cash_settled_index"
CLASS_ETF = "etf"
CLASS_SINGLE_NAME = "single_name"
CLASS_UNMAPPED = "unmapped"

ALL_CLASSES = frozenset({
    CLASS_CASH_SETTLED_INDEX, CLASS_ETF, CLASS_SINGLE_NAME, CLASS_UNMAPPED,
})

# DEF-TRITON-INDEX-UNGRADEABLE: cash-settled index symbols with no price series.
# These are the 15 rows inside the sealed holdout that can never be graded.
CASH_SETTLED_INDEX_SYMBOLS = frozenset({"SPX", "SPXW", "RUT", "RUTW", "VIX"})

# Observed live 2026-09-06. Extend only from a fresh live read, never from a guess.
ISSUE_TYPE_TO_CLASS: Dict[str, str] = {
    "etf": CLASS_ETF,
    "common stock": CLASS_SINGLE_NAME,
}


def classify(ticker: Optional[str], issue_type: Optional[str]) -> str:
    """Pure. The cash-settled list is checked FIRST because issue_type is NULL
    for those symbols -- consulting the vendor first would return UNMAPPED for
    exactly the class this build exists to separate out."""
    sym = (ticker or "").strip().upper()
    if not sym:
        return CLASS_UNMAPPED
    if sym in CASH_SETTLED_INDEX_SYMBOLS:
        return CLASS_CASH_SETTLED_INDEX
    key = (issue_type or "").strip().lower()
    if not key:
        return CLASS_UNMAPPED
    return ISSUE_TYPE_TO_CLASS.get(key, CLASS_UNMAPPED)


def is_gradeable(instrument_class: str) -> bool:
    """Cash-settled index rows have no price series and can never be graded.
    UNMAPPED is NOT excluded: we do not know what it is, and excluding on
    ignorance would silently shrink the population."""
    return instrument_class != CLASS_CASH_SETTLED_INDEX


async def classify_ticker(ticker: str) -> str:
    """Classify from the live (24h-cached) /info response. Never raises.

    Shares its call with S4's sector map: one /info fetch answers both, which is
    why they must be built together rather than as two per-ticker fetches.
    """
    sym = (ticker or "").strip().upper()
    if sym in CASH_SETTLED_INDEX_SYMBOLS:
        return CLASS_CASH_SETTLED_INDEX          # no vendor call needed
    try:
        from integrations.uw_api import _get_info_cached_long

        info: Dict[str, Any] = await _get_info_cached_long(sym) or {}
    except Exception as exc:
        logger.warning("instrument_class(%s): /info fetch failed: %s", sym, exc)
        return CLASS_UNMAPPED
    return classify(sym, info.get("issue_type"))
