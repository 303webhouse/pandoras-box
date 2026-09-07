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
from datetime import date as _date
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

CLASS_CASH_SETTLED_INDEX = "cash_settled_index"
CLASS_SINGLE_NAME = "single_name"
CLASS_UNMAPPED = "unmapped"

# S3 ETF SUB-CLASSES (R-IV.301(c)). Static maps, horizon stated below.
CLASS_ETF_BROAD = "etf_broad"
CLASS_ETF_SECTOR = "etf_sector"
CLASS_ETF_LEVERAGED_INVERSE = "etf_leveraged_inverse"
# NOT in the ruling, and argued rather than assumed. R-IV.301(c) names three ETF
# sub-classes; SIX OF THE FIFTEEN tickers on the measured bar path match none of
# them -- COPX, GLD, HYG, RSP, SMH, TLT -- and SMH is a member of H-CORE4.
#
# Those are not UNMAPPED: the vendor positively told us they are ETFs. Collapsing
# "known ETF, sub-class not in any static map" into "we do not know what this is"
# would discard a measured fact, and UNMAPPED is the bucket a reader trusts least.
# So they get their own honest bucket and the gap is reported, not absorbed.
CLASS_ETF_OTHER = "etf_other"

# NO COARSE `CLASS_ETF` ALIAS. The module is new, nothing imported it, and a name
# that silently changed meaning (SPY was 'etf', it is now 'etf_broad') is a worse
# trap than a missing one.

ALL_CLASSES = frozenset({
    CLASS_CASH_SETTLED_INDEX, CLASS_ETF_BROAD, CLASS_ETF_SECTOR,
    CLASS_ETF_LEVERAGED_INVERSE, CLASS_ETF_OTHER, CLASS_SINGLE_NAME, CLASS_UNMAPPED,
})

# ── STATIC MAPS: stated horizon, loud failure past it ─────────────────────
# Holidays are data, not logic -- and so is this. A static map that silently
# outlives its accuracy is the failure mode the calendar rule exists to prevent,
# so the horizon is explicit and expiry is LOUD (see static_map_expired()).
STATIC_MAP_VALID_THROUGH = _date(2027, 3, 31)

BROAD_INDEX_ETFS = frozenset({"SPY", "QQQ", "IWM", "DIA"})

# S4's ONE sector map (R-IV.301(b)). The 11 SPDR sector ETFs appear as a literal
# in ten declaration sites across nine files (measured 2026-09-05); THIS is the
# single source those supersede. Ticker -> sector name.
SPDR_SECTOR_ETFS = {
    "XLK": "Technology", "XLF": "Financials", "XLV": "Health Care",
    "XLY": "Consumer Discretionary", "XLC": "Communication Services",
    "XLI": "Industrials", "XLP": "Consumer Staples", "XLE": "Energy",
    "XLU": "Utilities", "XLRE": "Real Estate", "XLB": "Materials",
}

# Built from the repo's existing knowledge (api/stable.py _ETF_THEME), not invented.
LEVERAGED_INVERSE_ETFS = frozenset({
    "SOXL", "SOXS", "TQQQ", "SQQQ", "UPRO", "SPXL", "SPXS", "SH", "SDS",
    "TNA", "TZA", "LABU", "LABD", "FAS", "FAZ", "GUSH", "DRIP", "ERX", "ERY",
})

SECTOR_BROAD = "BROAD"


def static_map_expired(today=None) -> bool:
    """True once the static maps are past their stated horizon."""
    return (today or _date.today()) > STATIC_MAP_VALID_THROUGH

# DEF-TRITON-INDEX-UNGRADEABLE: cash-settled index symbols with no price series.
# These are the 15 rows inside the sealed holdout that can never be graded.
CASH_SETTLED_INDEX_SYMBOLS = frozenset({"SPX", "SPXW", "RUT", "RUTW", "VIX"})

# Observed live 2026-09-06. Extend only from a fresh live read, never from a guess.
ISSUE_TYPE_TO_CLASS: Dict[str, str] = {
    "etf": CLASS_ETF_OTHER,        # refined into a sub-class by classify()
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
    base = ISSUE_TYPE_TO_CLASS.get(key, CLASS_UNMAPPED)
    if base is not CLASS_ETF_OTHER:
        return base
    # Vendor says ETF; the static maps say which kind.
    if static_map_expired():
        logger.error(
            "instrument_class: STATIC MAPS EXPIRED (valid through %s) -- %s "
            "classified as %s rather than a stale sub-class",
            STATIC_MAP_VALID_THROUGH, sym, CLASS_ETF_OTHER)
        return CLASS_ETF_OTHER
    if sym in BROAD_INDEX_ETFS:
        return CLASS_ETF_BROAD
    if sym in SPDR_SECTOR_ETFS:
        return CLASS_ETF_SECTOR
    if sym in LEVERAGED_INVERSE_ETFS:
        return CLASS_ETF_LEVERAGED_INVERSE
    return CLASS_ETF_OTHER


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


def sector_for(ticker: Optional[str], instrument_class: str,
               info_sector: Optional[str] = None) -> Optional[str]:
    """S4's sector stratum (R-IV.301(b)). One map, four rules:

      broad-index ETF  -> "BROAD"       (keeps the stratum informative on an
                                         ETF-heavy universe instead of blanking it)
      SPDR sector ETF  -> its sector    (from SPDR_SECTOR_ETFS, the single source)
      single name      -> /info sector
      anything else    -> None (UNMAPPED)

    UNMAPPED ONLY when the vendor returns null for a single name, or the ticker
    matches no map. Measured 2026-09-06: /info returns sector=None for EVERY ETF,
    which is why ETFs are answered from the maps and not from the vendor.
    """
    sym = (ticker or "").strip().upper()
    if instrument_class == CLASS_ETF_BROAD or sym in BROAD_INDEX_ETFS:
        return SECTOR_BROAD
    if sym in SPDR_SECTOR_ETFS:
        return SPDR_SECTOR_ETFS[sym]
    if instrument_class == CLASS_SINGLE_NAME:
        s = (info_sector or "").strip()
        return s or None
    return None
