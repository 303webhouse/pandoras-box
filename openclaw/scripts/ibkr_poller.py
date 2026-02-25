"""
IBKR Position Poller — Brief 07 (original) / Brief 10 (fix: partial+account)

Polls the ibeam gateway for live IBKR positions and balances, then syncs them
to the portfolio API on Railway.

Deploy path: /opt/openclaw/workspace/scripts/ibkr_poller.py
Schedule:    */5 14-21 * * 1-5  (every 5 min during market hours UTC)
             Adjust to 13-20 UTC when DST starts (March 9, 2026).

Usage:
    python3 ibkr_poller.py           # normal run
    python3 ibkr_poller.py --dry-run # print payload, no API calls
"""

import json
import os
import sys
import urllib.request
import urllib.error
import urllib.parse
from datetime import date, datetime

# ── Config ────────────────────────────────────────────────────────────────────

IBEAM_BASE = os.getenv("IBEAM_BASE_URL", "https://localhost:5000/v1/api")
IBEAM_ACCOUNT = os.getenv("IBKR_ACCOUNT_ID", "")

API_URL = os.getenv("PANDORA_API_URL", "https://pandoras-box-production.up.railway.app")
API_KEY = os.getenv("PIVOT_API_KEY", "")

DRY_RUN = "--dry-run" in sys.argv


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def http_json(url, method="GET", headers=None, payload=None, verify_ssl=True):
    """Minimal HTTP helper that returns parsed JSON or raises on error."""
    import ssl
    ctx = ssl.create_default_context()
    if not verify_ssl:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    data = json.dumps(payload).encode() if payload else None
    req_headers = {"Content-Type": "application/json", **(headers or {})}

    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"HTTP {e.code} from {url}: {body}") from e


# ── IBKR helpers ──────────────────────────────────────────────────────────────

def get_accounts():
    """Return list of IBKR account IDs."""
    data = http_json(f"{IBEAM_BASE}/portfolio/accounts", verify_ssl=False)
    return [a["id"] for a in data]


def get_positions(account_id):
    """Return raw IBKR positions for the given account."""
    data = http_json(
        f"{IBEAM_BASE}/portfolio/{account_id}/positions/0",
        verify_ssl=False,
    )
    return data or []


def get_account_summary(account_id):
    """Return account summary (NAV, cash, etc.)."""
    data = http_json(
        f"{IBEAM_BASE}/portfolio/{account_id}/summary",
        verify_ssl=False,
    )
    return data or {}


# ── Position mapper ───────────────────────────────────────────────────────────

def _parse_expiry(ibkr_expiry: str) -> str | None:
    """Convert IBKR expiry 'YYYYMMDD' → 'YYYY-MM-DD'."""
    if not ibkr_expiry or len(ibkr_expiry) != 8:
        return None
    try:
        return date(
            int(ibkr_expiry[:4]),
            int(ibkr_expiry[4:6]),
            int(ibkr_expiry[6:8]),
        ).isoformat()
    except (ValueError, TypeError):
        return None


def map_ibkr_position(pos: dict) -> dict | None:
    """
    Convert an IBKR position object to a PositionData dict for the portfolio API.
    Returns None for non-tradable or zero-quantity positions.
    """
    sec_type = pos.get("assetClass", "")
    qty = pos.get("position", 0)
    if qty == 0:
        return None

    ticker = pos.get("ticker") or pos.get("symbol") or ""
    if not ticker:
        return None

    # Stock / ETF
    if sec_type == "STK":
        return {
            "ticker": ticker,
            "position_type": "short_stock" if qty < 0 else "stock",
            "direction": "SHORT" if qty < 0 else "LONG",
            "quantity": abs(int(qty)),
            "cost_basis": pos.get("avgCost", 0) * abs(qty),
            "cost_per_unit": pos.get("avgCost"),
            "current_price": pos.get("mktPrice"),
            "current_value": pos.get("mktValue"),
            "unrealized_pnl": pos.get("unrealizedPnl"),
        }

    # Options
    if sec_type == "OPT":
        right = pos.get("right", "").upper()
        option_type = "Call" if right == "C" else "Put"
        direction = "LONG" if qty > 0 else "SHORT"
        expiry_str = _parse_expiry(str(pos.get("expiry", "")))
        strike = pos.get("strike")

        # Options qty in IBKR is in contracts
        contracts = abs(int(qty))
        cost_basis = (pos.get("avgCost", 0) or 0) * contracts * 100
        cost_per_unit = pos.get("avgCost")

        return {
            "ticker": ticker,
            "position_type": "option_single",
            "direction": direction,
            "quantity": contracts,
            "option_type": option_type,
            "strike": float(strike) if strike else None,
            "expiry": expiry_str,
            "cost_basis": round(cost_basis, 2) if cost_basis else None,
            "cost_per_unit": float(cost_per_unit) if cost_per_unit else None,
            "current_price": pos.get("mktPrice"),
            "current_value": pos.get("mktValue"),
            "unrealized_pnl": pos.get("unrealizedPnl"),
        }

    # Skip futures, bonds, etc.
    return None


# ── Balance mapper ────────────────────────────────────────────────────────────

def map_ibkr_balance(summary: dict) -> dict | None:
    """Convert IBKR account summary to balance update payload."""
    nav = summary.get("netliquidation", {}).get("amount")
    cash = summary.get("totalcashvalue", {}).get("amount")
    buying_power = summary.get("buyingpower", {}).get("amount")

    if nav is None:
        return None

    return {
        "account_name": "IBKR",
        "balance": round(float(nav), 2),
        "cash": round(float(cash), 2) if cash is not None else None,
        "buying_power": round(float(buying_power), 2) if buying_power is not None else None,
    }


# ── Sync to portfolio API ─────────────────────────────────────────────────────

def sync_positions(positions: list[dict]) -> dict:
    """POST positions to portfolio API. Uses partial=False, account=ibkr (full IBKR sync)."""
    headers = {"X-API-Key": API_KEY}
    # Brief 10 fix: IBKR sends ALL positions so partial=False; tag account as ibkr
    return http_json(
        url=f"{API_URL}/api/portfolio/positions/sync",
        method="POST",
        headers=headers,
        payload={"positions": positions, "partial": False, "account": "ibkr"},
    )


def update_balance(balance: dict) -> dict:
    """POST balance update to portfolio API."""
    headers = {"X-API-Key": API_KEY}
    return http_json(
        url=f"{API_URL}/api/portfolio/balances/update",
        method="POST",
        headers=headers,
        payload=balance,
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"[ibkr_poller] {datetime.now().isoformat()} — starting")

    # Determine account
    account_id = IBEAM_ACCOUNT
    if not account_id:
        try:
            accounts = get_accounts()
            if not accounts:
                print("[ibkr_poller] No IBKR accounts found.")
                return
            account_id = accounts[0]
            print(f"[ibkr_poller] Using account: {account_id}")
        except Exception as e:
            print(f"[ibkr_poller] Failed to fetch accounts: {e}")
            return

    # Fetch positions
    try:
        raw_positions = get_positions(account_id)
        print(f"[ibkr_poller] Raw positions from IBKR: {len(raw_positions)}")
    except Exception as e:
        print(f"[ibkr_poller] Failed to fetch positions: {e}")
        return

    # Map positions
    positions = []
    for raw in raw_positions:
        mapped = map_ibkr_position(raw)
        if mapped:
            positions.append(mapped)

    print(f"[ibkr_poller] Mapped positions: {len(positions)}")

    if DRY_RUN:
        print("[ibkr_poller] DRY RUN — payload:")
        print(json.dumps({"positions": positions, "partial": False, "account": "ibkr"}, indent=2))
    else:
        try:
            result = sync_positions(positions)
            print(f"[ibkr_poller] Sync result: {result}")
        except Exception as e:
            print(f"[ibkr_poller] Sync failed: {e}")

    # Fetch and sync balance
    try:
        summary = get_account_summary(account_id)
        balance = map_ibkr_balance(summary)
        if balance:
            if DRY_RUN:
                print(f"[ibkr_poller] DRY RUN — balance payload: {balance}")
            else:
                bal_result = update_balance(balance)
                print(f"[ibkr_poller] Balance update result: {bal_result}")
    except Exception as e:
        print(f"[ibkr_poller] Balance update failed: {e}")

    print(f"[ibkr_poller] Done.")


if __name__ == "__main__":
    main()
