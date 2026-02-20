#!/usr/bin/env python3
"""
market_data.py — Real-time market price lookup for Pivot II (OpenClaw).

Deploy to: /opt/openclaw/workspace/scripts/market_data.py

Usage:
    python market_data.py [TICKER]
    python market_data.py BTC
    python market_data.py SPY
    python market_data.py ETH

Reads PANDORA_API_URL and PIVOT_API_KEY from environment.
Outputs a plain-text price summary to stdout for OpenClaw to consume.

Env vars (set via openclaw config or /etc/openclaw/openclaw.env):
    PANDORA_API_URL   — e.g. https://pandoras-box-production.up.railway.app/api
    PIVOT_API_KEY     — bearer token for the Railway API
"""

import os
import sys
import json

try:
    import urllib.request
    import urllib.error
except ImportError:
    print("ERROR: urllib not available", file=sys.stderr)
    sys.exit(1)


PANDORA_API_URL = (os.getenv("PANDORA_API_URL") or "").rstrip("/")
PIVOT_API_KEY = os.getenv("PIVOT_API_KEY") or ""

# Crypto tickers that should route to /crypto/market instead of /hybrid/price
_CRYPTO_SYMBOLS = {"BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA", "AVAX", "LINK", "DOT"}


def _get(path: str, timeout: int = 10) -> dict:
    url = f"{PANDORA_API_URL}{path}"
    req = urllib.request.Request(url)
    if PIVOT_API_KEY:
        req.add_header("Authorization", f"Bearer {PIVOT_API_KEY}")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


def _fmt_price(value) -> str:
    if value is None:
        return "N/A"
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return str(value)


def fetch_crypto(symbol: str = "BTC") -> str:
    """Fetch BTC/crypto price from /crypto/market (Binance/OKX/Bybit)."""
    data = _get("/crypto/market")
    if "error" in data:
        return f"Error fetching crypto market data: {data['error']}"

    prices = data.get("prices") or {}
    spot = prices.get("binance_spot") or prices.get("coinbase_spot")
    perps = prices.get("perps") or {}
    perp_price = perps.get("binance") or perps.get("okx") or perps.get("bybit")
    basis_pct = prices.get("basis_pct")
    perp_source = (perps.get("source") or "unknown").upper()

    funding = data.get("funding") or {}
    primary_funding = funding.get("primary") or {}
    funding_rate = primary_funding.get("rate")
    funding_source = (primary_funding.get("source") or "unknown").upper()

    cvd = data.get("cvd") or {}
    cvd_direction = cvd.get("direction", "UNKNOWN")
    cvd_confidence = cvd.get("direction_confidence", "LOW")

    lines = [f"{symbol} Market Data:"]
    if spot is not None:
        lines.append(f"  Spot: {_fmt_price(spot)}")
    if perp_price is not None:
        lines.append(f"  Perp ({perp_source}): {_fmt_price(perp_price)}")
    if basis_pct is not None:
        try:
            lines.append(f"  Basis: {float(basis_pct):+.3f}%")
        except Exception:
            pass
    if funding_rate is not None:
        try:
            lines.append(f"  Funding ({funding_source}): {float(funding_rate) * 100:+.4f}%")
        except Exception:
            pass
    lines.append(f"  CVD: {cvd_direction} ({cvd_confidence})")

    errors = data.get("errors") or []
    if errors:
        lines.append(f"  Warnings: {'; '.join(str(e) for e in errors[:3])}")

    return "\n".join(lines)


def fetch_equity(ticker: str) -> str:
    """Fetch equity/ETF price from /hybrid/price/{ticker}."""
    data = _get(f"/hybrid/price/{ticker.upper()}")
    if "error" in data and data.get("price") is None:
        return f"Error fetching price for {ticker}: {data['error']}"

    price = data.get("price")
    if price is None:
        return f"{ticker.upper()}: price unavailable"

    return f"{ticker.upper()}: {_fmt_price(price)}"


def main():
    ticker = sys.argv[1].upper() if len(sys.argv) > 1 else "BTC"

    if not PANDORA_API_URL:
        print(
            "ERROR: PANDORA_API_URL not set. "
            "Run: openclaw config set env.PANDORA_API_URL https://pandoras-box-production.up.railway.app/api",
            file=sys.stderr,
        )
        sys.exit(1)

    # Strip common suffixes for routing decision
    base = ticker.replace("-USD", "").replace("USDT", "").replace("-PERP", "")
    if base in _CRYPTO_SYMBOLS:
        print(fetch_crypto(base))
    else:
        print(fetch_equity(ticker))


if __name__ == "__main__":
    main()
