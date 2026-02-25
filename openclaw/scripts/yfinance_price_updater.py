"""
yfinance Price Updater — Brief 10 Task 2

Fetches current market prices for non-IBKR positions using yfinance and updates
current_price + current_value on open positions via the portfolio sync API.

Runs every 15 min during market hours. Only updates positions where account != 'ibkr'
(IBKR positions get live quotes from ibkr_quotes.py instead).

Deploy path: /opt/openclaw/workspace/scripts/yfinance_price_updater.py
Schedule:    */15 14-21 * * 1-5  (every 15 min, market hours UTC)
             Adjust to 13-20 UTC when DST starts (March 9, 2026).

Usage:
    python3 yfinance_price_updater.py           # normal run
    python3 yfinance_price_updater.py --dry-run # print updates, no API write
    python3 yfinance_price_updater.py --verbose # extra logging
"""

import json
import logging
import os
import sys
import urllib.request
import urllib.error
from datetime import date, datetime, timedelta

try:
    import yfinance as yf
except ImportError:
    print("[yfinance_updater] ERROR: yfinance not installed. Run: pip install yfinance")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────

API_URL = os.getenv("PANDORA_API_URL", "https://pandoras-box-production.up.railway.app")
API_KEY = os.getenv("PIVOT_API_KEY", "")

DRY_RUN = "--dry-run" in sys.argv
VERBOSE = "--verbose" in sys.argv

logging.basicConfig(
    level=logging.DEBUG if VERBOSE else logging.INFO,
    format="%(asctime)s [yfinance_updater] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def http_get_json(url: str) -> list | dict:
    req = urllib.request.Request(url)
    if API_KEY:
        req.add_header("X-API-Key", API_KEY)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def http_post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


# ── Option price fetch ────────────────────────────────────────────────────────

def _mid_or_last(row) -> float | None:
    """Return mid price if bid/ask are valid, else lastPrice, else None."""
    bid = row.get("bid", 0) or 0
    ask = row.get("ask", 0) or 0
    last = row.get("lastPrice", 0) or 0
    if bid > 0 and ask > 0 and ask >= bid:
        return round((bid + ask) / 2, 4)
    if last > 0:
        return round(last, 4)
    return None


def _find_nearest_expiry(available: tuple[str, ...], target: str) -> str | None:
    """Find the closest expiry date in yfinance's available list."""
    if not available:
        return None
    try:
        target_d = date.fromisoformat(target)
    except ValueError:
        return None
    # Sort by distance from target
    sorted_expiries = sorted(available, key=lambda e: abs((date.fromisoformat(e) - target_d).days))
    nearest = sorted_expiries[0]
    gap = abs((date.fromisoformat(nearest) - target_d).days)
    if gap > 7:
        log.warning("Nearest expiry %s is %d days from target %s — skipping", nearest, gap, target)
        return None
    return nearest


def fetch_option_price(ticker: str, expiry: str, strike: float, option_type: str) -> float | None:
    """
    Fetch a single option's price from yfinance.
    option_type: 'Call' or 'Put'
    Returns price per share (divide by 100 for per-contract premium).
    """
    try:
        t = yf.Ticker(ticker)
        available = t.options
        if not available:
            log.warning("No options chain available for %s", ticker)
            return None

        expiry_str = _find_nearest_expiry(available, expiry)
        if not expiry_str:
            return None

        chain = t.option_chain(expiry_str)
        df = chain.calls if option_type.lower() in ("call", "c") else chain.puts

        # Find the closest strike
        df = df.copy()
        df["_diff"] = (df["strike"] - strike).abs()
        best = df.sort_values("_diff").iloc[0]
        strike_diff = float(best["_diff"])
        if strike_diff > 2.0:
            log.warning(
                "%s %s %s %.2f — nearest strike is %.2f (diff=%.2f) skipping",
                ticker, expiry, option_type, strike, float(best["strike"]), strike_diff,
            )
            return None

        row = best.to_dict()
        price = _mid_or_last(row)
        log.debug("%s %s %s %.2f → price=%.4f", ticker, expiry_str, option_type, strike, price or 0)
        return price
    except Exception as e:
        log.warning("Failed to fetch option price for %s %s %.2f %s: %s", ticker, expiry, strike, option_type, e)
        return None


def fetch_stock_price(ticker: str) -> float | None:
    """Fetch current price for a stock/ETF."""
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        price = getattr(info, "last_price", None) or getattr(info, "lastPrice", None)
        if price and price > 0:
            return round(float(price), 4)
        # Fallback to history
        hist = t.history(period="1d", interval="1m")
        if not hist.empty:
            return round(float(hist["Close"].iloc[-1]), 4)
        return None
    except Exception as e:
        log.warning("Failed to fetch stock price for %s: %s", ticker, e)
        return None


# ── Spread pricing ────────────────────────────────────────────────────────────

def price_spread_position(pos: dict) -> tuple[float | None, float | None]:
    """
    Compute current_price (per unit = per contract dollar value) and
    current_value (total position value) for an option spread.

    For debit spreads:
      Long leg = strike (the one we paid for)
      Short leg = short_strike (the one we collected on)
      spread value per unit = long_leg_price - short_leg_price

    Returns (current_price, current_value). current_price here is spread
    value in dollar terms (not per-share — already multiplied by 100).
    """
    ticker = pos["ticker"]
    expiry = pos.get("expiry", "")
    option_type = pos.get("option_type", "Call")
    strike = pos.get("strike")
    short_strike = pos.get("short_strike")
    quantity = pos.get("quantity", 1)
    spread_type = pos.get("spread_type", "debit")

    if not strike or not short_strike or not expiry:
        return None, None

    long_price = fetch_option_price(ticker, expiry, strike, option_type)
    short_price = fetch_option_price(ticker, expiry, short_strike, option_type)

    if long_price is None and short_price is None:
        return None, None

    long_price = long_price or 0.0
    short_price = short_price or 0.0

    if spread_type == "debit":
        spread_value_per_share = long_price - short_price
    else:
        # credit spread (we're net short)
        spread_value_per_share = short_price - long_price

    spread_value_per_contract = spread_value_per_share * 100
    total_value = round(spread_value_per_contract * quantity, 2)
    per_unit = round(spread_value_per_contract, 4)

    return per_unit, total_value


def price_single_option(pos: dict) -> tuple[float | None, float | None]:
    """Price a single-leg option position."""
    ticker = pos["ticker"]
    expiry = pos.get("expiry", "")
    option_type = pos.get("option_type", "Call")
    strike = pos.get("strike")
    quantity = pos.get("quantity", 1)

    if not strike or not expiry:
        return None, None

    price_per_share = fetch_option_price(ticker, expiry, strike, option_type)
    if price_per_share is None:
        return None, None

    price_per_contract = price_per_share * 100
    total_value = round(price_per_contract * quantity, 2)
    return round(price_per_contract, 4), total_value


def price_stock(pos: dict) -> tuple[float | None, float | None]:
    """Price a stock/ETF position."""
    ticker = pos["ticker"]
    quantity = pos.get("quantity", 1)
    price = fetch_stock_price(ticker)
    if price is None:
        return None, None
    return price, round(price * quantity, 2)


# ── Main pricing dispatch ─────────────────────────────────────────────────────

def price_position(pos: dict) -> tuple[float | None, float | None]:
    """Return (current_price, current_value) for a position. Either can be None."""
    ptype = pos.get("position_type", "")
    if ptype == "option_spread":
        return price_spread_position(pos)
    elif ptype == "option_single":
        return price_single_option(pos)
    elif ptype in ("stock", "short_stock"):
        return price_stock(pos)
    else:
        log.warning("Unknown position_type '%s' for %s — skipping", ptype, pos.get("ticker"))
        return None, None


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log.info("Starting — %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # ── Fetch active positions ──
    try:
        positions = http_get_json(f"{API_URL}/api/portfolio/positions")
    except Exception as e:
        log.error("Failed to fetch positions: %s", e)
        sys.exit(1)

    if not positions:
        log.info("No active positions — exiting.")
        return

    # ── Filter to non-IBKR positions ──
    rh_positions = [p for p in positions if (p.get("account") or "robinhood") != "ibkr"]
    if not rh_positions:
        log.info("No non-IBKR positions to update — exiting.")
        return

    log.info("Found %d non-IBKR position(s) to price", len(rh_positions))

    # ── Price each position ──
    # Group by account so we send separate syncs per account
    by_account: dict[str, list[dict]] = {}
    for pos in rh_positions:
        account = pos.get("account") or "robinhood"
        by_account.setdefault(account, []).append(pos)

    for account, acct_positions in by_account.items():
        log.info("Pricing %d position(s) for account=%s", len(acct_positions), account)
        updated_payload = []
        skipped = 0

        for pos in acct_positions:
            ticker = pos["ticker"]
            log.debug("Pricing %s %s %s", ticker, pos.get("position_type"), pos.get("expiry") or "")

            current_price, current_value = price_position(pos)

            if current_price is None and current_value is None:
                log.warning("Could not price %s — skipping", ticker)
                skipped += 1
                continue

            # Build minimal sync payload — only include pricing fields + identity fields
            entry = {
                "ticker": pos["ticker"],
                "position_type": pos["position_type"],
                "direction": pos["direction"],
                "quantity": pos["quantity"],
                "account": account,
            }
            # Identity fields for match
            if pos.get("option_type"):
                entry["option_type"] = pos["option_type"]
            if pos.get("strike") is not None:
                entry["strike"] = pos["strike"]
            if pos.get("expiry"):
                entry["expiry"] = pos["expiry"]
            if pos.get("spread_type"):
                entry["spread_type"] = pos["spread_type"]
            if pos.get("short_strike") is not None:
                entry["short_strike"] = pos["short_strike"]

            # Updated price fields
            if current_price is not None:
                entry["current_price"] = current_price
            if current_value is not None:
                entry["current_value"] = current_value

            # Preserve existing cost data (don't wipe it)
            if pos.get("cost_basis") is not None:
                entry["cost_basis"] = pos["cost_basis"]
            if pos.get("cost_per_unit") is not None:
                entry["cost_per_unit"] = pos["cost_per_unit"]

            updated_payload.append(entry)
            log.info(
                "  %s %s %s → price=%.4f value=%.2f",
                ticker,
                pos.get("expiry") or "",
                pos.get("option_type") or pos.get("position_type"),
                current_price or 0,
                current_value or 0,
            )

        log.info("Priced %d/%d positions (%d skipped)", len(updated_payload), len(acct_positions), skipped)

        if not updated_payload:
            log.info("Nothing to sync for account=%s", account)
            continue

        sync_payload = {
            "positions": updated_payload,
            "partial": True,
            "account": account,
        }

        if DRY_RUN:
            log.info("DRY RUN — would POST /api/portfolio/positions/sync:")
            print(json.dumps(sync_payload, indent=2))
        else:
            try:
                result = http_post_json(f"{API_URL}/api/portfolio/positions/sync", sync_payload)
                log.info("Sync result: added=%s updated=%s", result.get("added"), result.get("updated"))
            except Exception as e:
                log.error("Sync failed for account=%s: %s", account, e)

    log.info("Done.")


if __name__ == "__main__":
    main()
