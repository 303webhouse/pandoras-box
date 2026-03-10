#!/usr/bin/env python3
"""
IBKR Position & Balance Poller.

Polls the ibeam gateway for account positions and balances,
then syncs them to the Railway portfolio API.

Schedule: Every 5 minutes during market hours (Mon-Fri, 14:30-21:00 UTC).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import ssl
import urllib.error
import urllib.request
from collections import defaultdict
from typing import Any

DATA_DIR = pathlib.Path("/opt/openclaw/workspace/data")
POSITIONS_CACHE = DATA_DIR / "ibkr_positions.json"
OPENCLAW_STATE_DIR = pathlib.Path(os.environ.get("OPENCLAW_STATE_DIR", "/home/openclaw/.openclaw"))
OPENCLAW_CONFIG = OPENCLAW_STATE_DIR / "openclaw.json"
OPENCLAW_ENV_FILE = pathlib.Path("/etc/openclaw/openclaw.env")

DEFAULT_GATEWAY_URL = "https://localhost:5000"
DEFAULT_PANDORA_API_URL = "https://pandoras-box-production.up.railway.app/api"

# ibeam uses a self-signed cert — skip verification for localhost calls
_INSECURE_CTX = ssl.create_default_context()
_INSECURE_CTX.check_hostname = False
_INSECURE_CTX.verify_mode = ssl.CERT_NONE


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
    insecure: bool = False,
) -> Any:
    body = None
    req_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")

    req = urllib.request.Request(url=url, method=method, headers=req_headers, data=body)
    ctx = _INSECURE_CTX if insecure else None
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        raw = resp.read().decode("utf-8")
    if not raw:
        return None
    return json.loads(raw)


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


# ── IBKR Gateway Calls ──

def check_auth(gateway_url: str) -> bool:
    """Check if ibeam gateway is authenticated."""
    try:
        data = http_json(f"{gateway_url}/v1/api/iserver/auth/status", insecure=True)
        return bool(data and data.get("authenticated"))
    except Exception as e:
        print(f"[WARN] Auth check failed: {e}")
        return False


def reauthenticate(gateway_url: str) -> bool:
    """Attempt to re-authenticate via tickle + reauthenticate."""
    try:
        http_json(f"{gateway_url}/v1/api/tickle", method="POST", insecure=True)
        http_json(f"{gateway_url}/v1/api/iserver/reauthenticate", method="POST", insecure=True)
        return True
    except Exception as e:
        print(f"[WARN] Reauthenticate failed: {e}")
        return False


def get_accounts(gateway_url: str) -> list[dict]:
    """Get list of IBKR accounts."""
    data = http_json(f"{gateway_url}/v1/api/portfolio/accounts", insecure=True)
    return data if isinstance(data, list) else []


def get_account_summary(gateway_url: str, account_id: str) -> dict:
    """Get account balance summary."""
    data = http_json(
        f"{gateway_url}/v1/api/portfolio/{account_id}/summary",
        insecure=True,
    )
    return data if isinstance(data, dict) else {}


def get_positions(gateway_url: str, account_id: str) -> list[dict]:
    """Get all positions for an account."""
    data = http_json(
        f"{gateway_url}/v1/api/portfolio/{account_id}/positions/0",
        insecure=True,
    )
    return data if isinstance(data, list) else []


# ── Mapping IBKR → Portfolio API ──

def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _parse_ibkr_expiry(raw: str | None) -> str | None:
    """Convert IBKR expiry format (YYYYMMDD) to ISO date (YYYY-MM-DD)."""
    if not raw:
        return None
    raw = str(raw).strip()
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return raw


def map_positions(ibkr_positions: list[dict]) -> list[dict]:
    """
    Map IBKR positions to portfolio API format.

    Groups option legs by (ticker, expiry) to detect spreads.
    """
    options: list[dict] = []
    stocks: list[dict] = []
    for p in ibkr_positions:
        asset_class = (p.get("assetClass") or "").upper()
        if asset_class == "OPT":
            options.append(p)
        elif asset_class == "STK":
            stocks.append(p)

    mapped: list[dict] = []

    # Map stocks
    for p in stocks:
        pos_qty = p.get("position", 0)
        if pos_qty == 0:
            continue
        avg_cost = _safe_float(p.get("avgCost"))
        mapped.append({
            "ticker": p.get("ticker") or p.get("contractDesc", "").split()[0],
            "position_type": "short_stock" if pos_qty < 0 else "stock",
            "direction": "SHORT" if pos_qty < 0 else "LONG",
            "quantity": abs(int(pos_qty)),
            "cost_basis": round(avg_cost * abs(pos_qty), 2) if avg_cost else None,
            "cost_per_unit": avg_cost,
            "current_value": _safe_float(p.get("mktValue")),
            "current_price": _safe_float(p.get("mktPrice")),
            "unrealized_pnl": _safe_float(p.get("unrealizedPnl")),
        })

    # Group options by (ticker, expiry) to detect spreads
    opt_groups: dict[tuple, list[dict]] = defaultdict(list)
    for p in options:
        ticker = p.get("ticker") or p.get("contractDesc", "").split()[0]
        expiry = _parse_ibkr_expiry(p.get("expiry"))
        opt_groups[(ticker, expiry)].append(p)

    for (ticker, expiry), legs in opt_groups.items():
        if len(legs) == 1:
            _map_single_option(mapped, legs[0], ticker, expiry)
        elif len(legs) == 2:
            _map_spread(mapped, legs, ticker, expiry)
        else:
            # 3+ legs — complex position, map individually
            for leg in legs:
                _map_single_option(mapped, leg, ticker, expiry,
                                   notes=f"Leg of {len(legs)}-leg complex position")

    return mapped


def _map_single_option(mapped: list, leg: dict, ticker: str, expiry: str | None,
                       notes: str | None = None) -> None:
    pos_qty = leg.get("position", 0)
    if pos_qty == 0:
        return
    put_call = (leg.get("putOrCall") or "").upper()
    option_type = "Put" if put_call == "P" else "Call"
    entry = {
        "ticker": ticker,
        "position_type": "option_single",
        "direction": "SHORT" if pos_qty < 0 else "LONG",
        "quantity": abs(int(pos_qty)),
        "option_type": option_type,
        "strike": _safe_float(leg.get("strike")),
        "expiry": expiry,
        "current_value": _safe_float(leg.get("mktValue")),
        "current_price": _safe_float(leg.get("mktPrice")),
        "unrealized_pnl": _safe_float(leg.get("unrealizedPnl")),
    }
    if notes:
        entry["notes"] = notes
    mapped.append(entry)


def _map_spread(mapped: list, legs: list[dict], ticker: str, expiry: str | None) -> None:
    leg_a, leg_b = legs
    put_call_a = (leg_a.get("putOrCall") or "").upper()
    put_call_b = (leg_b.get("putOrCall") or "").upper()

    # Different option types = not a standard vertical spread
    if put_call_a != put_call_b:
        for leg in legs:
            _map_single_option(mapped, leg, ticker, expiry)
        return

    option_type = "Put" if put_call_a == "P" else "Call"
    pos_a = leg_a.get("position", 0)
    pos_b = leg_b.get("position", 0)

    # Identify long leg (positive position) and short leg (negative position)
    if pos_a > 0 and pos_b < 0:
        long_leg, short_leg = leg_a, leg_b
    elif pos_b > 0 and pos_a < 0:
        long_leg, short_leg = leg_b, leg_a
    else:
        # Both same direction — map individually
        for leg in legs:
            _map_single_option(mapped, leg, ticker, expiry)
        return

    long_strike = _safe_float(long_leg.get("strike")) or 0
    short_strike = _safe_float(short_leg.get("strike")) or 0

    # Determine spread direction
    if option_type == "Put":
        # Put debit spread: long higher strike, short lower = bearish (SHORT)
        direction = "SHORT" if long_strike > short_strike else "LONG"
        spread_type = "debit" if long_strike > short_strike else "credit"
    else:
        # Call debit spread: long lower strike, short higher = bullish (LONG)
        direction = "LONG" if long_strike < short_strike else "SHORT"
        spread_type = "debit" if long_strike < short_strike else "credit"

    total_pnl = (_safe_float(long_leg.get("unrealizedPnl")) or 0) + \
                (_safe_float(short_leg.get("unrealizedPnl")) or 0)
    total_value = (_safe_float(long_leg.get("mktValue")) or 0) + \
                  (_safe_float(short_leg.get("mktValue")) or 0)

    mapped.append({
        "ticker": ticker,
        "position_type": "option_spread",
        "direction": direction,
        "quantity": abs(int(long_leg.get("position", 0))),
        "option_type": option_type,
        "strike": long_strike,
        "expiry": expiry,
        "spread_type": spread_type,
        "short_strike": short_strike,
        "current_value": total_value,
        "unrealized_pnl": total_pnl,
    })


def extract_balance(summary: dict) -> dict:
    """Extract balance fields from IBKR account summary."""
    def _val(key: str) -> float | None:
        entry = summary.get(key)
        if isinstance(entry, dict):
            return _safe_float(entry.get("amount"))
        return _safe_float(entry)

    return {
        "account_name": "Interactive Brokers",
        "balance": _val("netliquidation") or 0.0,
        "cash": _val("totalcashvalue"),
        "buying_power": _val("buyingpower"),
        "margin_total": _val("grosspositionvalue"),
    }


# ── Sync to Railway ──

def sync_balances(api_url: str, api_key: str, balance: dict) -> dict:
    """POST balance update to portfolio API."""
    headers = {"X-API-Key": api_key}
    return http_json(
        url=f"{api_url}/portfolio/balances/update",
        method="POST",
        headers=headers,
        payload=balance,
    )


def sync_positions(api_url: str, api_key: str, positions: list[dict]) -> dict:
    """POST position sync to portfolio API."""
    headers = {"X-API-Key": api_key}
    return http_json(
        url=f"{api_url}/portfolio/positions/sync",
        method="POST",
        headers=headers,
        payload={"positions": positions},
    )


# ── Main ──

def run(dry_run: bool = False) -> dict[str, Any]:
    cfg = load_openclaw_config()
    env_file = load_env_file(OPENCLAW_ENV_FILE)

    gateway_url = (pick_env("IBKR_GATEWAY_URL", cfg, env_file) or DEFAULT_GATEWAY_URL).rstrip("/")
    api_url = (pick_env("PANDORA_API_URL", cfg, env_file) or DEFAULT_PANDORA_API_URL).rstrip("/")
    api_key = pick_env("PIVOT_API_KEY", cfg, env_file)

    if not api_key:
        return {"ok": False, "error": "PIVOT_API_KEY is required"}

    # 1. Check auth
    if not check_auth(gateway_url):
        reauthenticate(gateway_url)
        if not check_auth(gateway_url):
            return {"ok": False, "error": "IBKR gateway not authenticated"}

    # 2. Get accounts
    accounts = get_accounts(gateway_url)
    if not accounts:
        return {"ok": False, "error": "No IBKR accounts found"}

    account_id = pick_env("IBKR_ACCOUNT_ID", cfg, env_file)
    if not account_id:
        account_id = accounts[0].get("accountId") or accounts[0].get("id", "")

    raw_positions = []
    result: dict[str, Any] = {
        "ok": True,
        "timestamp": now_utc().isoformat(),
        "account_id": account_id,
        "positions_count": 0,
        "balance_synced": False,
        "positions_synced": False,
        "sync_result": None,
    }

    # 3. Get & sync balance
    try:
        summary = get_account_summary(gateway_url, account_id)
        balance = extract_balance(summary)
        result["balance"] = balance

        if not dry_run:
            sync_resp = sync_balances(api_url, api_key, balance)
            result["balance_synced"] = True
            result["balance_sync_response"] = sync_resp
        else:
            print(f"[DRY RUN] Would sync balance: {json.dumps(balance, indent=2)}")
            result["balance_synced"] = True
    except Exception as e:
        result["balance_error"] = str(e)

    # 4. Get & sync positions
    try:
        raw_positions = get_positions(gateway_url, account_id)
        mapped = map_positions(raw_positions)
        result["positions_count"] = len(mapped)
        result["positions"] = mapped

        if not dry_run:
            sync_resp = sync_positions(api_url, api_key, mapped)
            result["positions_synced"] = True
            result["sync_result"] = sync_resp
        else:
            print(f"[DRY RUN] Would sync {len(mapped)} positions:")
            for p in mapped:
                print(f"  {p['ticker']} {p['position_type']} {p['direction']}")
            result["positions_synced"] = True
    except Exception as e:
        result["positions_error"] = str(e)

    # 5. Cache results
    ensure_data_dir()
    cache = {
        "timestamp": result["timestamp"],
        "account_id": account_id,
        "positions": result.get("positions", []),
        "balance": result.get("balance", {}),
        "conids": [p.get("conid") for p in raw_positions if p.get("conid")],
    }
    POSITIONS_CACHE.write_text(json.dumps(cache, indent=2) + "\n", encoding="utf-8")

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="IBKR position and balance poller")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be synced without calling APIs")
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
