"""
Pivot Position Manager skill.
Callable from VPS for structured position operations.

Usage: python manage.py <command> [args]

Commands:
    list                    -- Show all open positions
    summary                 -- Portfolio risk summary
    open <json>             -- Open a new position
    close <position_id> <exit_price>  -- Close a position
    update <position_id> <field=value>  -- Update a position field
    mark-to-market          -- Refresh all prices via yfinance
    reconcile <json>        -- Screenshot reconciliation
    bulk <json>             -- Bulk create/update from CSV import
"""

import sys
import os
import json
import urllib.request
import urllib.error

API_URL = (os.getenv("PANDORA_API_URL") or "https://pandoras-box-production.up.railway.app").rstrip("/")


def api_call(method: str, path: str, data: dict = None) -> dict:
    """Make an API call to the unified positions endpoint."""
    url = f"{API_URL}/api{path}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, method=method)
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.readable() else str(e)
        return {"error": error_body, "status_code": e.code}
    except Exception as e:
        return {"error": str(e)}


def cmd_list():
    result = api_call("GET", "/v2/positions?status=OPEN")
    positions = result.get("positions", [])
    if not positions:
        print("No open positions")
        return
    print(f"{'TICKER':<8} {'STRUCTURE':<22} {'QTY':>4} {'ENTRY':>8} {'MAX LOSS':>9} {'DTE':>5}")
    print("-" * 60)
    for p in positions:
        ticker = p.get("ticker", "?")
        structure = (p.get("structure") or "equity")[:20]
        qty = p.get("quantity", 0)
        entry = p.get("entry_price")
        entry_str = f"${entry:.2f}" if entry else "--"
        ml = p.get("max_loss")
        ml_str = f"${ml:.0f}" if ml else "--"
        dte = p.get("dte")
        dte_str = str(dte) if dte is not None else "--"
        print(f"{ticker:<8} {structure:<22} {qty:>4} {entry_str:>8} {ml_str:>9} {dte_str:>5}")


def cmd_summary():
    result = api_call("GET", "/v2/positions/summary")
    if "error" in result:
        print(f"Error: {result['error']}")
        return
    print(f"Account: ${result.get('account_balance', 0):,.0f}")
    print(f"Positions: {result.get('position_count', 0)}")
    print(f"Capital at risk: ${result.get('capital_at_risk', 0):,.0f} ({result.get('capital_at_risk_pct', 0):.1f}%)")
    print(f"Net direction: {result.get('net_direction', 'FLAT')}")
    nearest = result.get("nearest_dte")
    if nearest is not None:
        print(f"Nearest expiry: {nearest} DTE")


def cmd_open(json_str: str):
    data = json.loads(json_str)
    result = api_call("POST", "/v2/positions", data)
    if result.get("status") == "created":
        pos = result["position"]
        print(f"Created: {pos['position_id']} — {pos['ticker']} {pos.get('structure', 'equity')}")
        if pos.get("max_loss"):
            print(f"  Max loss: ${pos['max_loss']:.0f}")
    else:
        print(f"Error: {json.dumps(result, indent=2)}")


def cmd_close(position_id: str, exit_price: str):
    result = api_call("POST", f"/v2/positions/{position_id}/close", {
        "exit_price": float(exit_price)
    })
    if result.get("status") == "closed":
        pnl = result.get("realized_pnl", 0)
        outcome = result.get("trade_outcome", "?")
        print(f"Closed: {position_id} — {outcome} — P&L: ${pnl:+.2f}")
        if result.get("trade_id"):
            print(f"  Trade record: #{result['trade_id']}")
    else:
        print(f"Error: {json.dumps(result, indent=2)}")


def cmd_update(position_id: str, *field_values):
    updates = {}
    for fv in field_values:
        if "=" not in fv:
            print(f"Invalid field=value: {fv}")
            return
        field, value = fv.split("=", 1)
        try:
            updates[field] = float(value)
        except ValueError:
            updates[field] = value
    result = api_call("PATCH", f"/v2/positions/{position_id}", updates)
    if result.get("status") == "updated":
        print(f"Updated: {position_id}")
    else:
        print(f"Error: {json.dumps(result, indent=2)}")


def cmd_mark_to_market():
    result = api_call("POST", "/v2/positions/mark-to-market")
    print(f"Updated {result.get('updated', 0)} positions")
    prices = result.get("prices", {})
    for ticker, price in prices.items():
        if price:
            print(f"  {ticker}: ${price:.2f}")


def cmd_reconcile(json_str: str):
    data = json.loads(json_str)
    result = api_call("POST", "/v2/positions/reconcile", data)
    summary = result.get("summary", {})
    print(f"Matched: {summary.get('matched_count', 0)}")
    print(f"Created: {summary.get('created_count', 0)}")
    print(f"Missing: {summary.get('missing_count', 0)}")
    for m in result.get("missing", []):
        print(f"  Missing: {m['ticker']} ({m.get('structure', '?')})")


def cmd_bulk(json_str: str):
    data = json.loads(json_str)
    result = api_call("POST", "/v2/positions/bulk", data)
    print(f"Created: {result.get('created', 0)}")
    print(f"Errors: {result.get('errors', 0)}")
    for err in result.get("error_details", []):
        print(f"  Error: {err['ticker']} — {err['error']}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    commands = {
        "list": lambda: cmd_list(),
        "summary": lambda: cmd_summary(),
        "open": lambda: cmd_open(args[0]) if args else print("Usage: open <json>"),
        "close": lambda: cmd_close(args[0], args[1]) if len(args) >= 2 else print("Usage: close <position_id> <exit_price>"),
        "update": lambda: cmd_update(args[0], *args[1:]) if args else print("Usage: update <position_id> <field=value>"),
        "mark-to-market": lambda: cmd_mark_to_market(),
        "reconcile": lambda: cmd_reconcile(args[0]) if args else print("Usage: reconcile <json>"),
        "bulk": lambda: cmd_bulk(args[0]) if args else print("Usage: bulk <json>"),
    }

    if cmd in commands:
        commands[cmd]()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
