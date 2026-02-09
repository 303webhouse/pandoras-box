"""
Shared sector configuration used by watchlist, scanners, and universe builder.
"""

SECTOR_ETF_MAP = {
    "Technology": {
        "etf": "XLK",
        "tickers": [
            "AAPL", "MSFT", "NVDA", "GOOGL", "AMD", "META", "AVGO", "ORCL",
            "CRM", "ADBE", "CSCO", "INTC", "QCOM", "INTU", "NOW", "PANW",
            "SNPS", "AMAT", "MU", "LRCX", "KLAC", "MRVL", "NXPI", "FTNT",
            "TXN", "NET", "SNOW", "PLTR",
        ],
    },
    "Consumer Discretionary": {
        "etf": "XLY",
        "tickers": [
            "AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "TJX", "LOW",
            "BKNG", "MAR", "NFLX", "CMG", "ORLY", "ROST",
        ],
    },
    "Financials": {
        "etf": "XLF",
        "tickers": [
            "JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW", "AXP",
            "USB", "PNC", "COF", "SPGI", "MCO", "ICE", "CME", "V", "MA",
        ],
    },
    "Healthcare": {
        "etf": "XLV",
        "tickers": [
            "UNH", "JNJ", "LLY", "ABBV", "MRK", "PFE", "TMO", "ABT",
            "DHR", "BMY", "AMGN", "GILD", "ISRG", "REGN", "VRTX", "CI", "CVS",
        ],
    },
    "Energy": {
        "etf": "XLE",
        "tickers": [
            "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "HAL",
        ],
    },
    "Industrials": {
        "etf": "XLI",
        "tickers": [
            "CAT", "BA", "UNP", "UPS", "RTX", "HON", "GE", "DE", "MMC",
            "ITW", "WM", "EMR", "ETN", "FDX", "LMT",
        ],
    },
    "Consumer Staples": {
        "etf": "XLP",
        "tickers": [
            "WMT", "PG", "KO", "PEP", "COST", "PM", "MO", "MDLZ", "CL",
        ],
    },
    "Communication Services": {
        "etf": "XLC",
        "tickers": [
            "META", "GOOGL", "NFLX", "DIS", "CMCSA", "T", "VZ", "TMUS",
        ],
    },
    "Utilities": {
        "etf": "XLU",
        "tickers": ["NEE", "SO", "DUK", "AEP", "SRE", "D", "EXC"],
    },
    "Real Estate": {
        "etf": "XLRE",
        "tickers": ["PLD", "AMT", "EQIX", "PSA", "WELL", "SPG", "O", "CBRE"],
    },
    "Materials": {
        "etf": "XLB",
        "tickers": ["LIN", "APD", "SHW", "ECL", "NEM", "FCX", "NUE", "DOW"],
    },
}


def detect_sector(symbol: str) -> str:
    """Return the sector for a given ticker symbol, or 'Uncategorized' if unknown."""
    for sector_name, data in SECTOR_ETF_MAP.items():
        if symbol in data["tickers"]:
            return sector_name
    return "Uncategorized"
