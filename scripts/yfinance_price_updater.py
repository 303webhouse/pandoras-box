#!/usr/bin/env python3
"""
YFinance Price Updater.

Fetches current stock/ETF prices via yfinance for all open positions
and updates current_price in the portfolio API.

For options: fetches underlying price so the dashboard shows where
the underlying is trading relative to strikes.

Schedule: Every 15 minutes during market hours (Mon-Fri, 14:30-21:00 UTC).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import urllib.error
import urllib.request
from typing import Any

DATA_DIR = pathlib.Path("/opt/openclaw/workspace/data")
PRICES_CACHE = DATA_DIR / "yfinance_prices.json"
OPENCLAW_STATE_DIR = pathlib.Path(os.environ.get("OPENCLAW_STATE_DIR", "/home/openclaw/.openclaw"))
OPENCLAW_CONFIG = OPENCLAW_STATE_DIR / "openclaw.json"
OPENCLAW_ENV_FILE = pathlib.Path("/etc/openclaw/openclaw.env")

DEFAULT_PANDORA_API_URL = "https://pandoras-box-production.up.railway.app/api"


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def load_openclaw_config() -> dict[str, Any]:
    try:
        return json.loads(OPENCLAW_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_env_file(path: pathlib.Path) -> dict[str, str]:
    data: dict[str, str] = {}
    try:
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()
    except Exception:
        pass
    return data


def pick_env(name: str, cfg: dict[str, Any], env_file: dict[str, str]) -> str:
    val = os.environ.get(name, "").strip()
    if val:
        return val
    cfg_env = cfg.get("env") or {}
    if isinstance(cfg_env, dict):
        cval = str(cfg_env.get(name) or "").strip()
        if cval:
            return cval
    return str(env_file.get(name) or "").strip()


def http_json(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | list | None = None,
    timeout: int = 30,
) -> Any:
    body = None
    req_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")

    req = urllib.request.Request(url=url, method=method, headers=req_headers, data=body)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    if not raw:
        return None
    return json.loads(raw)


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def fetch_positions(api_url: str) -> list[dict]:
    """Get all active positions from the portfolio API."""
    try:
        data = http_json(f"{api_url}/portfolio/positions")
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[ERROR] Failed to fetch positions: {e}")
        return []


def get_unique_tickers(positions: list[dict]) -> list[str]:
    """Extract unique tickers from positions."""
    tickers = set()
    for p in positions:
        ticker = p.get("ticker", "").strip().upper()
        if ticker:
            tickers.add(ticker)
    return sorted(tickers)


def fetch_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch current prices for a list of tickers using yfinance."""
    import yfinance as yf

    if not tickers:
        return {}

    prices: dict[str, float] = {}
    try:
        data = yf.download(tickers, period="1d", interval="1m", progress=False, threads=True)
        if data.empty:
            # Fallback: try individual fetches
            for ticker in tickers:
                try:
                    t = yf.Ticker(ticker)
                    info = t.fast_info
                    price = getattr(info, "last_price", None) or getattr(info, "previous_close", None)
                    if price:
                        prices[ticker] = round(float(price), 2)
                except Exception:
                    pass
            return prices

        # Extract last available close/price for each ticker
        if len(tickers) == 1:
            # Single ticker: data columns are flat
            ticker = tickers[0]
            close_col = "Close"
            if close_col in data.columns:
                last_val = data[close_col].dropna().iloc[-1] if not data[close_col].dropna().empty else None
                if last_val is not None:
                    prices[ticker] = round(float(last_val), 2)
        else:
            # Multiple tickers: multi-level columns
            for ticker in tickers:
                try:
                    if ("Close", ticker) in data.columns:
                        col = data[("Close", ticker)].dropna()
                        if not col.empty:
                            prices[ticker] = round(float(col.iloc[-1]), 2)
                except Exception:
                    pass

    except Exception as e:
        print(f"[WARN] Batch download failed: {e}")
        # Fallback to individual
        for ticker in tickers:
            try:
                import yfinance as yf
                t = yf.Ticker(ticker)
                info = t.fast_info
                price = getattr(info, "last_price", None) or getattr(info, "previous_close", None)
                if price:
                    prices[ticker] = round(float(price), 2)
            except Exception:
                pass

    return prices


def run(dry_run: bool = False) -> dict[str, Any]:
    cfg = load_openclaw_config()
    env_file = load_env_file(OPENCLAW_ENV_FILE)

    api_url = (pick_env("PANDORA_API_URL", cfg, env_file) or DEFAULT_PANDORA_API_URL).rstrip("/")
    api_key = pick_env("PIVOT_API_KEY", cfg, env_file)

    if not api_key:
        return {"ok": False, "error": "PIVOT_API_KEY is required"}

    # 1. Fetch current positions
    positions = fetch_positions(api_url)
    if not positions:
        return {"ok": True, "message": "No active positions", "updated": 0}

    # 2. Get unique tickers
    tickers = get_unique_tickers(positions)
    if not tickers:
        return {"ok": True, "message": "No tickers to update", "updated": 0}

    # 3. Fetch current prices
    prices = fetch_prices(tickers)

    result: dict[str, Any] = {
        "ok": True,
        "timestamp": now_utc().isoformat(),
        "tickers_requested": len(tickers),
        "prices_fetched": len(prices),
        "prices": prices,
        "positions_updated": 0,
    }

    if dry_run:
        print(f"[DRY RUN] Fetched {len(prices)} prices:")
        for ticker, price in sorted(prices.items()):
            print(f"  {ticker}: ${price}")
        # Cache even in dry run
        ensure_data_dir()
        PRICES_CACHE.write_text(json.dumps({
            "timestamp": result["timestamp"],
            "prices": prices,
        }, indent=2) + "\n", encoding="utf-8")
        return result

    # 4. Update positions with current prices
    # Build updated positions list for sync
    updated_positions = []
    for p in positions:
        ticker = p.get("ticker", "").strip().upper()
        price = prices.get(ticker)
        if price is None:
            continue

        pos_data = {
            "ticker": p["ticker"],
            "position_type": p["position_type"],
            "direction": p["direction"],
            "quantity": p["quantity"],
            "option_type": p.get("option_type"),
            "strike": p.get("strike"),
            "expiry": p.get("expiry"),
            "spread_type": p.get("spread_type"),
            "short_strike": p.get("short_strike"),
            "cost_basis": p.get("cost_basis"),
            "cost_per_unit": p.get("cost_per_unit"),
            "current_price": price,
            "current_value": p.get("current_value"),
            "unrealized_pnl": p.get("unrealized_pnl"),
            "unrealized_pnl_pct": p.get("unrealized_pnl_pct"),
            "notes": p.get("notes"),
        }
        updated_positions.append(pos_data)

    if updated_positions:
        try:
            headers = {"X-API-Key": api_key}
            sync_resp = http_json(
                url=f"{api_url}/portfolio/positions/sync",
                method="POST",
                headers=headers,
                payload={"positions": updated_positions},
            )
            result["sync_result"] = sync_resp
            result["positions_updated"] = len(updated_positions)
        except Exception as e:
            result["sync_error"] = str(e)

    # 5. Cache results
    ensure_data_dir()
    PRICES_CACHE.write_text(json.dumps({
        "timestamp": result["timestamp"],
        "prices": prices,
    }, indent=2) + "\n", encoding="utf-8")

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="YFinance price updater for open positions")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch prices but don't sync to portfolio API")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = run(dry_run=args.dry_run)
        print(json.dumps(result, ensure_ascii=False, default=str))
        return 0 if result.get("ok") else 1
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
