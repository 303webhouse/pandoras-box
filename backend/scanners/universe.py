"""
Shared scan universe builder.
All scanners import from here instead of maintaining their own ticker lists.
"""
import logging
from typing import List

logger = logging.getLogger(__name__)

# Hardcoded fallbacks — used if DB is unavailable
SP500_EXPANDED = [
    # Mega Tech (but still good movers)
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "AVGO", "ORCL", "AMD",
    "CRM", "ADBE", "CSCO", "INTC", "QCOM", "INTU", "NOW", "PANW", "SNPS", "AMAT",
    # Financials
    "JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW", "AXP", "USB",
    "PNC", "TFC", "COF", "BK", "STT", "SPGI", "MCO", "ICE", "CME", "AON",
    # Healthcare
    "UNH", "JNJ", "LLY", "ABBV", "MRK", "PFE", "TMO", "ABT", "DHR", "BMY",
    "AMGN", "GILD", "ISRG", "REGN", "VRTX", "CI", "CVS", "ELV", "HUM", "ZTS",
    # Consumer Discretionary
    "HD", "MCD", "NKE", "SBUX", "TJX", "LOW", "BKNG", "MAR",
    # Consumer Staples
    "WMT", "PG", "KO", "PEP", "COST", "PM", "MO", "MDLZ", "CL", "GIS",
    # Industrials
    "CAT", "BA", "UNP", "UPS", "RTX", "HON", "GE", "DE", "MMC", "ITW",
    "WM", "EMR", "ETN", "FDX", "NSC", "CSX",
    # Energy
    "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "HAL",
    # Materials
    "LIN", "APD", "SHW", "ECL", "NEM", "FCX",
    # Utilities
    "NEE", "SO", "DUK", "AEP", "SRE", "D", "EXC",
    # Real Estate
    "PLD", "AMT", "EQIX", "PSA", "WELL", "SPG", "O", "CBRE",
    # Communication Services
    "NFLX", "DIS", "CMCSA", "T", "VZ", "TMUS",
]

RUSSELL_HIGH_VOLUME = [
    # High-volume mid-caps with good technical setups
    "PLTR", "SOFI", "RIVN", "LCID", "F", "SNAP", "COIN", "HOOD", "RBLX", "U",
    "ZM", "DOCU", "CRWD", "NET", "DDOG", "SNOW", "MDB", "HUBS", "ZS", "OKTA",
    "SQ", "PYPL", "SHOP", "ROKU", "PINS", "TWLO", "LYFT", "UBER", "DASH", "ABNB",
    "GME", "AMC", "BB", "TLRY", "SNDL", "MARA", "RIOT", "FUBO",
    "NIO", "XPEV", "LI", "BABA", "JD", "PDD", "BIDU",
    "AFRM", "UPST", "LMND", "OPEN",
    "PLUG", "FCEL", "BE", "QS", "BLNK", "CHPT",
]


async def build_scan_universe(
    max_tickers: int = 200,
    include_scanner_universe: bool = True,
    respect_muted: bool = True,
) -> List[str]:
    """
    Build deduplicated scan universe in priority order:
    1. Active position tickers (priority='high')
    2. Manual watchlist tickers (source='manual', not muted)
    3. Scanner universe tickers (source='scanner', not muted)
    4. Fallback to hardcoded lists if DB unavailable
    """
    universe: List[str] = []
    seen = set()

    def add_unique(tickers: List[str]) -> None:
        for ticker in tickers:
            if ticker in seen:
                continue
            seen.add(ticker)
            universe.append(ticker)

    try:
        from database.postgres_client import get_postgres_client

        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT symbol FROM watchlist_tickers "
                "WHERE priority = 'high' AND muted = false "
                "ORDER BY added_at"
            )
            add_unique([r["symbol"] for r in rows])

            rows = await conn.fetch(
                "SELECT symbol FROM watchlist_tickers "
                "WHERE source = 'manual' AND muted = false AND priority != 'high' "
                "ORDER BY added_at"
            )
            add_unique([r["symbol"] for r in rows])

            if include_scanner_universe:
                muted_filter = "AND muted = false" if respect_muted else ""
                rows = await conn.fetch(
                    f"SELECT symbol FROM watchlist_tickers WHERE source = 'scanner' {muted_filter} ORDER BY added_at"
                )
                add_unique([r["symbol"] for r in rows])

    except Exception as e:
        logger.warning(f"DB unavailable for universe build, using hardcoded fallback: {e}")
        add_unique(SP500_EXPANDED)
        add_unique(RUSSELL_HIGH_VOLUME)

    return universe[:max_tickers]
