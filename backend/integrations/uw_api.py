"""
UW (Unusual Whales) API Client — The Great Consolidation

Replaces Polygon equities + Polygon options + UW Discord scraper + FMP
with a single UW API Basic ($150/mo) + yfinance fallback for bars.

Binding conditions from committee review:
1. Circuit breaker: 5 consecutive failures -> 5min cooldown + Discord alert
2. Token bucket rate limiter: 120 req/min
3. Response normalization: output matches polygon_equities.py / polygon_options.py schemas
4. Redis caching with configurable TTL per endpoint type
5. Daily request counter with budget alerts at 50% (10K)
6. Retry with exponential backoff (max 3 retries)
7. Bearer token auth from UW_API_KEY env var
8. Health check via GET /api/uw/health
"""

import asyncio
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from integrations.uw_api_cache import (
    cache_get, cache_set, increment_daily_counter, get_daily_count, get_cache_stats,
)

logger = logging.getLogger("uw_api")

UW_API_KEY = os.getenv("UW_API_KEY", "")
UW_BASE = "https://api.unusualwhales.com"

# ── Circuit Breaker ──────────────────────────────────────────────
_cb_failures = 0
_cb_open_until = 0.0  # timestamp when circuit re-closes
CB_FAILURE_THRESHOLD = 5
CB_COOLDOWN_SECONDS = 300  # 5 minutes

# ── Token Bucket Rate Limiter (120 req/min) ──────────────────────
_bucket_tokens = 120.0
_bucket_max = 120.0
_bucket_refill_rate = 2.0  # tokens/sec = 120/60
_bucket_last_refill = time.time()
_bucket_lock = asyncio.Lock()


def _circuit_breaker_open() -> bool:
    """Check if circuit breaker is open (should NOT make requests)."""
    if _cb_open_until > 0 and time.time() < _cb_open_until:
        return True
    return False


def _record_success():
    global _cb_failures
    _cb_failures = 0


def _record_failure():
    global _cb_failures, _cb_open_until
    _cb_failures += 1
    if _cb_failures >= CB_FAILURE_THRESHOLD:
        _cb_open_until = time.time() + CB_COOLDOWN_SECONDS
        logger.error("UW API CIRCUIT BREAKER OPEN — %d consecutive failures, "
                      "cooling down for %ds", _cb_failures, CB_COOLDOWN_SECONDS)
        asyncio.ensure_future(_post_circuit_breaker_alert())


async def _post_circuit_breaker_alert():
    """Post circuit breaker event to Discord."""
    try:
        webhook = os.getenv("DISCORD_WEBHOOK_SIGNALS", "")
        if not webhook:
            return
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(webhook, json={
                "content": "**UW API CIRCUIT BREAKER TRIPPED** — 5 consecutive failures. "
                           "Falling back to cached data for 5 minutes."
            })
    except Exception:
        pass


async def _consume_token():
    """Token bucket rate limiter. Blocks until a token is available."""
    global _bucket_tokens, _bucket_last_refill
    async with _bucket_lock:
        now = time.time()
        elapsed = now - _bucket_last_refill
        _bucket_tokens = min(_bucket_max, _bucket_tokens + elapsed * _bucket_refill_rate)
        _bucket_last_refill = now

        if _bucket_tokens < 1:
            wait = (1 - _bucket_tokens) / _bucket_refill_rate
            await asyncio.sleep(wait)
            _bucket_tokens = 0
        else:
            _bucket_tokens -= 1


async def _uw_request(path: str, params: dict = None) -> Optional[dict]:
    """
    Core UW API request with circuit breaker, rate limiter, retry, and counting.
    Returns parsed JSON or None on failure.
    """
    if not UW_API_KEY:
        logger.debug("UW_API_KEY not set — skipping request")
        return None

    if _circuit_breaker_open():
        logger.warning("UW API circuit breaker open — skipping %s", path)
        return None

    await _consume_token()
    await increment_daily_counter()

    url = f"{UW_BASE}{path}"
    headers = {"Authorization": f"Bearer {UW_API_KEY}", "Accept": "application/json"}

    last_error = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers=headers, params=params or {})
                if resp.status_code == 200:
                    _record_success()
                    return resp.json()
                elif resp.status_code == 429:
                    wait = 2 ** (attempt + 1)
                    logger.warning("UW API rate limited on %s, waiting %ds", path, wait)
                    await asyncio.sleep(wait)
                    continue
                else:
                    logger.error("UW API %s: HTTP %d — %s", path, resp.status_code, resp.text[:200])
                    _record_failure()
                    return None
        except Exception as e:
            last_error = e
            wait = 2 ** attempt
            logger.warning("UW API %s attempt %d failed: %s (retry in %ds)",
                           path, attempt + 1, e, wait)
            await asyncio.sleep(wait)

    logger.error("UW API %s failed after 3 retries: %s", path, last_error)
    _record_failure()
    return None


# ═════════════════════════════════════════════════════════════════
# NORMALIZED API FUNCTIONS
# Output schemas match polygon_equities.py and polygon_options.py
# ═════════════════════════════════════════════════════════════════


async def get_snapshot(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Get latest snapshot for a ticker. Matches polygon_equities.get_snapshot() schema:
    {ticker, day: {o, h, l, c, v}, prevDay: {o, h, l, c, v}, lastTrade: {p, s, t}, ...}
    """
    cached = await cache_get("quote", ticker.upper())
    if cached:
        return cached

    data = await _uw_request(f"/api/stock/{ticker.upper()}/info")
    if not data or "data" not in data:
        return None

    info = data["data"]
    # UW /info doesn't have OHLCV — supplement with yfinance for real-time
    price_data = await _get_yfinance_quote(ticker)

    result = {
        "ticker": ticker.upper(),
        "day": {
            "o": price_data.get("open"),
            "h": price_data.get("high"),
            "l": price_data.get("low"),
            "c": price_data.get("close"),
            "v": price_data.get("volume"),
        },
        "prevDay": {
            "c": price_data.get("prev_close"),
        },
        "lastTrade": {
            "p": price_data.get("close"),
        },
        "todaysChange": price_data.get("change"),
        "todaysChangePerc": price_data.get("change_pct"),
        # Extra UW fields
        "beta": _safe_float(info.get("beta")),
        "sector": info.get("sector"),
        "full_name": info.get("full_name"),
        "marketcap_size": info.get("marketcap_size"),
        "has_options": info.get("has_options"),
    }

    await cache_set("quote", ticker.upper(), result)
    return result


async def get_bars(
    ticker: str,
    multiplier: int = 1,
    timespan: str = "day",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch OHLCV bars via yfinance. Matches polygon_equities.get_bars() schema:
    List of dicts with keys: o, h, l, c, v, vw, t, n
    """
    cache_key = f"{ticker}|{multiplier}|{timespan}|{from_date}|{to_date}"
    cached = await cache_get("quote", cache_key)
    if cached:
        return cached

    try:
        loop = asyncio.get_event_loop()
        bars = await loop.run_in_executor(None, _fetch_yfinance_bars, ticker, from_date, to_date)
        if bars:
            await cache_set("quote", cache_key, bars)
        return bars
    except Exception as e:
        logger.error("yfinance bars failed for %s: %s", ticker, e)
        return None


async def get_bars_as_dataframe(ticker: str, days: int = 30):
    """Matches polygon_equities.get_bars_as_dataframe() — returns pandas DataFrame."""
    import pandas as pd
    today = date.today()
    from_date = (today - timedelta(days=int(days * 1.6) + 5)).isoformat()
    to_date = today.isoformat()

    bars = await get_bars(ticker, 1, "day", from_date, to_date)
    if not bars:
        return None

    rows = []
    timestamps = []
    for bar in bars:
        ts = bar.get("t")
        if ts is None:
            continue
        timestamps.append(pd.Timestamp(ts, unit="ms"))
        rows.append({
            "open": bar.get("o"),
            "high": bar.get("h"),
            "low": bar.get("l"),
            "close": bar.get("c"),
            "volume": bar.get("v"),
        })

    if not rows:
        return None

    df = pd.DataFrame(rows, index=timestamps[:len(rows)])
    df.index.name = "Date"
    if len(df) > days:
        df = df.iloc[-days:]
    return df


async def get_previous_close(ticker: str) -> Optional[Dict[str, Any]]:
    """Matches polygon_equities.get_previous_close() schema."""
    bars = await get_bars(ticker, 1, "day")
    if not bars or len(bars) < 2:
        return None
    prev = bars[-2]
    return {
        "results": [{
            "T": ticker.upper(),
            "o": prev["o"], "h": prev["h"], "l": prev["l"],
            "c": prev["c"], "v": prev["v"], "t": prev["t"],
        }]
    }


async def get_options_snapshot(
    underlying: str,
    expiration_date: Optional[str] = None,
    strike_gte: Optional[float] = None,
    strike_lte: Optional[float] = None,
    contract_type: Optional[str] = None,
) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch options chain. Matches polygon_options.get_options_snapshot() schema:
    List of contract dicts with: details, greeks, day, last_quote, implied_volatility, etc.
    """
    cache_key = f"{underlying}|{expiration_date}|{strike_gte}|{strike_lte}|{contract_type}"
    cached = await cache_get("option_contracts", cache_key)
    if cached:
        return cached

    data = await _uw_request(f"/api/stock/{underlying.upper()}/option-contracts")
    if not data or "data" not in data:
        return None

    uw_contracts = data["data"]
    normalized = []

    for c in uw_contracts:
        sym = c.get("option_symbol", "")
        # Parse option symbol: SPY260413P00679000
        parsed = _parse_option_symbol(sym)
        if not parsed:
            continue

        c_type = parsed["type"]
        c_strike = parsed["strike"]
        c_expiry = parsed["expiry"]

        # Apply filters
        if expiration_date and c_expiry != str(expiration_date)[:10]:
            continue
        if contract_type and c_type != contract_type:
            continue
        if strike_gte is not None and c_strike < strike_gte:
            continue
        if strike_lte is not None and c_strike > strike_lte:
            continue

        # Normalize to Polygon schema
        nbbo_bid = _safe_float(c.get("nbbo_bid"))
        nbbo_ask = _safe_float(c.get("nbbo_ask"))
        last_price = _safe_float(c.get("last_price"))
        iv = _safe_float(c.get("implied_volatility"))

        normalized.append({
            "details": {
                "contract_type": c_type,
                "strike_price": c_strike,
                "expiration_date": c_expiry,
                "ticker": sym,
            },
            "day": {
                "close": last_price,
                "volume": c.get("volume", 0),
                "open_interest": c.get("open_interest", 0),
                "vwap": _safe_float(c.get("avg_price")),
            },
            "last_quote": {
                "bid": nbbo_bid,
                "ask": nbbo_ask,
            },
            "last_trade": {
                "price": last_price,
            },
            "greeks": {
                "delta": _safe_float(c.get("delta")),
                "gamma": _safe_float(c.get("gamma")),
                "theta": _safe_float(c.get("theta")),
                "vega": _safe_float(c.get("vega")),
            },
            "implied_volatility": iv,
            "open_interest": c.get("open_interest", 0),
        })

    await cache_set("option_contracts", cache_key, normalized)
    return normalized


async def get_flow_recent(ticker: str) -> Optional[List[Dict[str, Any]]]:
    """Fetch recent options flow for a ticker."""
    cached = await cache_get("flow", ticker.upper())
    if cached:
        return cached

    data = await _uw_request(f"/api/stock/{ticker.upper()}/flow-recent")
    if not data:
        return None

    # UW returns list directly (not wrapped in "data")
    flow = data if isinstance(data, list) else data.get("data", data)
    await cache_set("flow", ticker.upper(), flow)
    return flow


async def get_greek_exposure(ticker: str) -> Optional[List[Dict[str, Any]]]:
    """Fetch GEX data for a ticker."""
    cached = await cache_get("gex", ticker.upper())
    if cached:
        return cached

    data = await _uw_request(f"/api/stock/{ticker.upper()}/greek-exposure")
    if not data or "data" not in data:
        return None

    result = data["data"]
    await cache_set("gex", ticker.upper(), result)
    return result


async def get_market_tide() -> Optional[Dict[str, Any]]:
    """Fetch market-wide options tide."""
    cached = await cache_get("market_tide", "market")
    if cached:
        return cached

    data = await _uw_request("/api/market/market-tide")
    if not data:
        return None

    await cache_set("market_tide", "market", data)
    return data


async def get_darkpool_recent() -> Optional[List[Dict[str, Any]]]:
    """Fetch recent dark pool prints."""
    cached = await cache_get("darkpool", "recent")
    if cached:
        return cached

    data = await _uw_request("/api/darkpool/recent")
    if not data or "data" not in data:
        return None

    result = data["data"]
    await cache_set("darkpool", "recent", result)
    return result


async def get_darkpool_ticker(ticker: str) -> Optional[List[Dict[str, Any]]]:
    """Fetch dark pool prints for a specific ticker."""
    cached = await cache_get("darkpool", ticker.upper())
    if cached:
        return cached

    data = await _uw_request(f"/api/darkpool/{ticker.upper()}")
    if not data or "data" not in data:
        return None

    result = data["data"]
    await cache_set("darkpool", ticker.upper(), result)
    return result


async def get_max_pain(ticker: str) -> Optional[Dict[str, Any]]:
    """Fetch max pain data for a ticker."""
    cached = await cache_get("max_pain", ticker.upper())
    if cached:
        return cached

    data = await _uw_request(f"/api/stock/{ticker.upper()}/max-pain")
    if not data or "data" not in data:
        return None

    result = data["data"]
    await cache_set("max_pain", ticker.upper(), result)
    return result


async def get_sector_etfs() -> Optional[List[Dict[str, Any]]]:
    """Fetch sector ETF flow data."""
    cached = await cache_get("sector_etfs", "market")
    if cached:
        return cached

    data = await _uw_request("/api/market/sector-etfs")
    if not data or "data" not in data:
        return None

    result = data["data"]
    await cache_set("sector_etfs", "market", result)
    return result


async def get_iv_rank(ticker: str) -> Optional[List[Dict[str, Any]]]:
    """Fetch IV rank data for a ticker."""
    cached = await cache_get("iv_rank", ticker.upper())
    if cached:
        return cached

    data = await _uw_request(f"/api/stock/{ticker.upper()}/iv-rank")
    if not data or "data" not in data:
        return None

    result = data["data"]
    await cache_set("iv_rank", ticker.upper(), result)
    return result


async def get_earnings_premarket() -> Optional[List[Dict[str, Any]]]:
    """Fetch premarket earnings data. TTL: 3600s (F.3)."""
    cached = await cache_get("earnings", "premarket")
    if cached:
        return cached

    data = await _uw_request("/api/earnings/premarket")
    if not data or "data" not in data:
        return None

    result = data["data"]
    await cache_set("earnings", "premarket", result)
    return result


async def get_earnings_afterhours() -> Optional[List[Dict[str, Any]]]:
    """Fetch afterhours earnings data. TTL: 3600s (F.3)."""
    cached = await cache_get("earnings", "afterhours")
    if cached:
        return cached

    data = await _uw_request("/api/earnings/afterhours")
    if not data or "data" not in data:
        return None

    result = data["data"]
    await cache_set("earnings", "afterhours", result)
    return result


async def get_earnings_dates(ticker: str) -> Optional[List[Dict[str, Any]]]:
    """Fetch historical + upcoming earnings dates for a ticker. TTL: 3600s (F.3)."""
    symbol = ticker.upper()
    cached = await cache_get("earnings", f"dates_{symbol}")
    if cached:
        return cached

    data = await _uw_request(f"/api/earnings/{symbol}")
    if not data or "data" not in data:
        return None

    result = data["data"]
    await cache_set("earnings", f"dates_{symbol}", result)
    return result


async def get_next_earnings_date(ticker: str) -> Optional[str]:
    """
    Return the next upcoming earnings date string for a ticker, or None.
    Tries get_earnings_dates first; falls back to None cleanly (F.3).
    """
    dates = await get_earnings_dates(ticker)
    if not dates:
        return None

    today = date.today().isoformat()
    future = []
    for row in dates:
        # Row may have 'report_date', 'date', or 'earnings_date' depending on UW schema
        d = row.get("report_date") or row.get("date") or row.get("earnings_date") or ""
        if d and d >= today:
            future.append(d)

    return min(future) if future else None


async def get_economic_calendar() -> Optional[List[Dict[str, Any]]]:
    """Fetch economic calendar events. TTL: 1800s (F.3)."""
    cached = await cache_get("calendar", "events")
    if cached:
        return cached

    data = await _uw_request("/api/market/economic-calendar")
    if not data or "data" not in data:
        return None

    result = data["data"]
    await cache_set("calendar", "events", result)
    return result


async def get_short_interest(ticker: str) -> Optional[List[Dict[str, Any]]]:
    """Fetch short interest / float data."""
    cached = await cache_get("short_interest", ticker.upper())
    if cached:
        return cached

    data = await _uw_request(f"/api/shorts/{ticker.upper()}/interest-float/v2")
    if not data or "data" not in data:
        return None

    result = data["data"]
    await cache_set("short_interest", ticker.upper(), result)
    return result


# ── News Headlines ───────────────────────────────────────────────

async def get_news_headlines(limit: int = 20, ticker: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
    """Fetch market news headlines, optionally filtered to a specific ticker (B.7 / F.3)."""
    cache_key = f"headlines_{ticker.upper() if ticker else 'all'}_{limit}"
    cached = await cache_get("news", cache_key)
    if cached:
        return cached

    params: Dict[str, Any] = {"limit": limit}
    if ticker:
        params["ticker"] = ticker.upper()
    data = await _uw_request("/api/news/headlines", params=params)
    if not data or "data" not in data:
        return None

    result = data["data"]
    await cache_set("news", cache_key, result)
    return result


# ── Insider Transactions ─────────────────────────────────────────

async def get_insider_transactions(ticker: Optional[str] = None, limit: int = 20) -> Optional[List[Dict[str, Any]]]:
    """Fetch insider transactions (all or per-ticker)."""
    cache_key = f"insider_{ticker or 'all'}_{limit}"
    cached = await cache_get("insider", cache_key)
    if cached:
        return cached

    if ticker:
        data = await _uw_request(f"/api/insider/{ticker.upper()}")
    else:
        data = await _uw_request("/api/insider/transactions", params={"limit": limit})

    if not data or "data" not in data:
        return None

    result = data["data"]
    await cache_set("insider", cache_key, result)
    return result


# ── Congressional Trading ────────────────────────────────────────

async def get_congressional_trades(limit: int = 20) -> Optional[List[Dict[str, Any]]]:
    """Fetch recent congressional trades."""
    cached = await cache_get("congress", f"trades_{limit}")
    if cached:
        return cached

    data = await _uw_request("/api/congress/recent-trades", params={"limit": limit})
    if not data or "data" not in data:
        return None

    result = data["data"]
    await cache_set("congress", f"trades_{limit}", result)
    return result


# ── MTM Valuation Functions (Polygon-compatible) ─────────────────
# These mirror polygon_options.py's spread/multi-leg/single/greeks functions.
# They operate on the chain data from get_options_snapshot() which is already
# normalized to Polygon schema.

def _find_contract(chain: list, strike: float, expiry: str, option_type: str) -> Optional[dict]:
    """Find a specific contract in the chain by strike/expiry/type."""
    norm_expiry = str(expiry)[:10]
    for c in chain:
        details = c.get("details", {})
        if not details:
            continue
        if (details.get("contract_type", "").lower() == option_type
            and str(details.get("expiration_date", ""))[:10] == norm_expiry
            and abs(float(details.get("strike_price", 0)) - strike) < 0.01):
            return c
    return None


def _get_contract_mid(contract: dict) -> Optional[float]:
    """Get mid-price from bid/ask, falling back to last trade, day close, vwap."""
    # 1. Bid/ask mid
    quote = contract.get("last_quote", {})
    bid = quote.get("bid")
    ask = quote.get("ask")
    if bid and ask and float(bid) > 0 and float(ask) > 0:
        return round((float(bid) + float(ask)) / 2, 4)
    # 2. Last trade
    trade = contract.get("last_trade", {})
    price = trade.get("price")
    if price and float(price) > 0:
        return float(price)
    # 3. Day close
    day = contract.get("day", {})
    close = day.get("close")
    if close and float(close) > 0:
        return float(close)
    # 4. VWAP
    vwap = day.get("vwap")
    if vwap and float(vwap) > 0:
        return float(vwap)
    return None


def _get_contract_greeks(contract: dict) -> dict:
    """Extract greeks from a contract dict."""
    greeks = contract.get("greeks", {})
    return {
        "delta": greeks.get("delta"),
        "gamma": greeks.get("gamma"),
        "theta": greeks.get("theta"),
        "vega": greeks.get("vega"),
        "iv": contract.get("implied_volatility"),
    }


async def get_spread_value(
    underlying: str,
    long_strike: float,
    short_strike: float,
    expiry: str,
    structure: str,
) -> Optional[Dict[str, Any]]:
    """Get current spread value from UW options chain. Matches polygon_options schema."""
    struct_lower = structure.lower()
    if "put" in struct_lower:
        opt_type = "put"
    elif "call" in struct_lower:
        opt_type = "call"
    else:
        return None

    chain = await get_options_snapshot(
        underlying,
        expiration_date=str(expiry)[:10],
        strike_gte=min(long_strike, short_strike) - 0.5,
        strike_lte=max(long_strike, short_strike) + 0.5,
        contract_type=opt_type,
    )
    if not chain:
        return None

    long_c = _find_contract(chain, long_strike, expiry, opt_type)
    short_c = _find_contract(chain, short_strike, expiry, opt_type)
    if not long_c or not short_c:
        logger.warning("spread_value: missing contract for %s %s/%s %s", underlying, long_strike, short_strike, expiry)
        return None

    long_mid = _get_contract_mid(long_c)
    short_mid = _get_contract_mid(short_c)
    if long_mid is None or short_mid is None:
        return None

    if "credit" in struct_lower:
        spread_value = round(short_mid - long_mid, 4)
    else:
        spread_value = round(long_mid - short_mid, 4)

    underlying_price = None
    for c in [long_c, short_c]:
        ua = c.get("underlying_asset", {})
        if ua and ua.get("price"):
            underlying_price = float(ua["price"])
            break

    return {
        "spread_value": spread_value,
        "long_mid": long_mid,
        "short_mid": short_mid,
        "long_greeks": _get_contract_greeks(long_c),
        "short_greeks": _get_contract_greeks(short_c),
        "underlying_price": underlying_price,
    }


async def get_single_option_value(
    underlying: str,
    strike: float,
    expiry: str,
    option_type: str,
) -> Optional[Dict[str, Any]]:
    """Get current value of a single option contract. Matches polygon_options schema."""
    chain = await get_options_snapshot(
        underlying,
        expiration_date=str(expiry)[:10],
        strike_gte=strike - 0.5,
        strike_lte=strike + 0.5,
        contract_type=option_type,
    )
    if not chain:
        return None

    contract = _find_contract(chain, strike, expiry, option_type)
    if not contract:
        return None

    mid = _get_contract_mid(contract)
    if mid is None:
        return None

    underlying_price = None
    ua = contract.get("underlying_asset", {})
    if ua and ua.get("price"):
        underlying_price = float(ua["price"])

    return {
        "option_value": mid,
        "greeks": _get_contract_greeks(contract),
        "underlying_price": underlying_price,
    }


async def get_multi_leg_value(
    underlying: str,
    legs: List[Dict[str, Any]],
    expiry: str,
) -> Optional[Dict[str, Any]]:
    """Get net mark for a multi-leg position. Matches polygon_options schema."""
    if not legs:
        return None

    strikes = [float(l.get("strike", 0)) for l in legs]
    strike_lo = min(strikes) - 0.5
    strike_hi = max(strikes) + 0.5

    opt_types = set(l.get("option_type", "").lower() for l in legs)
    ct_filter = None
    if opt_types == {"put"}:
        ct_filter = "put"
    elif opt_types == {"call"}:
        ct_filter = "call"

    chain = await get_options_snapshot(
        underlying,
        expiration_date=str(expiry)[:10],
        strike_gte=strike_lo,
        strike_lte=strike_hi,
        contract_type=ct_filter,
    )
    if not chain:
        return None

    net_mark = 0.0
    leg_details = []
    underlying_price = None

    for leg in legs:
        action = leg.get("action", "BUY").upper()
        opt_type = leg.get("option_type", "call").lower()
        strike = float(leg.get("strike", 0))
        qty = int(leg.get("quantity", 1))

        contract = _find_contract(chain, strike, expiry, opt_type)
        if not contract:
            logger.warning("multi_leg: missing %s %s %s %s", underlying, strike, expiry, opt_type)
            return None

        mid = _get_contract_mid(contract)
        if mid is None:
            return None

        sign = 1 if action == "BUY" else -1
        net_mark += mid * sign * qty

        if underlying_price is None:
            ua = contract.get("underlying_asset", {})
            if ua and ua.get("price"):
                underlying_price = float(ua["price"])

        leg_details.append({
            "action": action,
            "option_type": opt_type,
            "strike": strike,
            "quantity": qty,
            "mid": mid,
            "greeks": _get_contract_greeks(contract),
        })

    return {
        "net_mark": round(net_mark, 4),
        "leg_details": leg_details,
        "underlying_price": underlying_price,
    }


async def get_ticker_greeks_summary(
    underlying: str,
    positions: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Aggregate greeks for all positions in a ticker. Matches polygon_options schema."""
    chain = await get_options_snapshot(underlying)
    if not chain:
        return None

    total_delta = 0.0
    total_gamma = 0.0
    total_theta = 0.0
    total_vega = 0.0
    underlying_price = None

    for pos in positions:
        structure = (pos.get("structure") or "").lower()
        qty = int(pos.get("quantity") or pos.get("qty") or 1)
        expiry = pos.get("expiry") or pos.get("expiration")
        long_strike = pos.get("long_strike")
        short_strike = pos.get("short_strike")

        if not expiry or not long_strike:
            continue

        if "put" in structure:
            opt_type = "put"
        elif "call" in structure:
            opt_type = "call"
        else:
            continue

        # Long leg
        long_c = _find_contract(chain, float(long_strike), str(expiry), opt_type)
        if long_c:
            g = _get_contract_greeks(long_c)
            total_delta += (g.get("delta") or 0) * qty * 100
            total_gamma += (g.get("gamma") or 0) * qty * 100
            total_theta += (g.get("theta") or 0) * qty * 100
            total_vega += (g.get("vega") or 0) * qty * 100
            if underlying_price is None:
                ua = long_c.get("underlying_asset", {})
                if ua and ua.get("price"):
                    underlying_price = float(ua["price"])

        # Short leg
        if short_strike:
            short_c = _find_contract(chain, float(short_strike), str(expiry), opt_type)
            if short_c:
                g = _get_contract_greeks(short_c)
                total_delta -= (g.get("delta") or 0) * qty * 100
                total_gamma -= (g.get("gamma") or 0) * qty * 100
                total_theta -= (g.get("theta") or 0) * qty * 100
                total_vega -= (g.get("vega") or 0) * qty * 100

    return {
        "underlying_price": underlying_price,
        "net_delta": round(total_delta, 2),
        "net_gamma": round(total_gamma, 4),
        "net_theta": round(total_theta, 2),
        "net_vega": round(total_vega, 2),
    }


# ── Health check data ────────────────────────────────────────────

async def get_health() -> Dict[str, Any]:
    """Return health status for the /api/uw/health endpoint."""
    return {
        "status": "degraded" if _circuit_breaker_open() else "healthy",
        "circuit_breaker": {
            "open": _circuit_breaker_open(),
            "consecutive_failures": _cb_failures,
            "cooldown_remaining_s": max(0, round(_cb_open_until - time.time(), 1)),
        },
        "daily_requests": await get_daily_count(),
        "daily_budget": 20000,
        "cache": get_cache_stats(),
        "rate_limiter": {
            "tokens_available": round(_bucket_tokens, 1),
            "max_tokens": _bucket_max,
        },
    }


# ── Helpers ──────────────────────────────────────────────────────

def _safe_float(val) -> Optional[float]:
    """Safely convert a value to float. Returns None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _parse_option_symbol(sym: str) -> Optional[Dict[str, Any]]:
    """Parse UW option symbol like SPY260413P00679000 into components."""
    if not sym or len(sym) < 15:
        return None
    try:
        # Find where the date starts — scan for 6-digit date after ticker
        # Format: TICKER + YYMMDD + P/C + strike*1000 (8 digits)
        suffix = sym[-15:]  # YYMMDDX00000000
        yy = int(suffix[0:2])
        mm = int(suffix[2:4])
        dd = int(suffix[4:6])
        opt_type = "put" if suffix[6] == "P" else "call"
        strike = int(suffix[7:15]) / 1000.0
        expiry = f"20{yy:02d}-{mm:02d}-{dd:02d}"
        return {"type": opt_type, "strike": strike, "expiry": expiry}
    except (ValueError, IndexError):
        return None


async def _get_yfinance_quote(ticker: str) -> dict:
    """Get current price data from yfinance (fast_info)."""
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _yf_quote_sync, ticker)
    except Exception as e:
        logger.debug("yfinance quote failed for %s: %s", ticker, e)
        return {}


def _yf_quote_sync(ticker: str) -> dict:
    """Synchronous yfinance quote fetch."""
    import yfinance as yf
    tk = yf.Ticker(ticker)
    info = tk.fast_info
    hist = tk.history(period="2d")
    result = {}
    if info:
        result["close"] = info.get("lastPrice")
        result["prev_close"] = info.get("previousClose")
        result["open"] = info.get("open")
        result["high"] = info.get("dayHigh")
        result["low"] = info.get("dayLow")
        result["volume"] = info.get("lastVolume")
        if result.get("close") and result.get("prev_close"):
            result["change"] = round(result["close"] - result["prev_close"], 2)
            result["change_pct"] = round(result["change"] / result["prev_close"] * 100, 2)
    return result


def _fetch_yfinance_bars(ticker: str, from_date: str = None, to_date: str = None) -> List[Dict]:
    """Fetch daily bars from yfinance, return in Polygon-compatible format."""
    import yfinance as yf
    import pandas as pd

    today = date.today()
    if not from_date:
        from_date = (today - timedelta(days=60)).isoformat()
    if not to_date:
        to_date = today.isoformat()

    data = yf.download(ticker, start=from_date, end=to_date, interval="1d", progress=False)
    if data is None or data.empty:
        return []

    # Handle MultiIndex columns
    if hasattr(data.columns, 'nlevels') and data.columns.nlevels > 1:
        data.columns = data.columns.get_level_values(0)

    bars = []
    for idx in data.index:
        ts_ms = int(idx.timestamp() * 1000) if hasattr(idx, 'timestamp') else 0
        bars.append({
            "o": float(data.loc[idx, "Open"]),
            "h": float(data.loc[idx, "High"]),
            "l": float(data.loc[idx, "Low"]),
            "c": float(data.loc[idx, "Close"]),
            "v": int(data.loc[idx, "Volume"]),
            "vw": None,  # yfinance doesn't provide VWAP
            "t": ts_ms,
            "n": None,  # yfinance doesn't provide trade count
        })

    return bars
