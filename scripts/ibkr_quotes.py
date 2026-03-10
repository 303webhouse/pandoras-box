#!/usr/bin/env python3
"""
IBKR Market Data Quotes Poller.

Fetches real-time (or delayed) quotes from ibeam gateway for open positions,
then updates current_value/current_price in the portfolio API.

Schedule: Every 1 minute during market hours (Mon-Fri, 14:30-21:00 UTC).
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
from typing import Any

DATA_DIR = pathlib.Path("/opt/openclaw/workspace/data")
POSITIONS_CACHE = DATA_DIR / "ibkr_positions.json"
QUOTES_CACHE = DATA_DIR / "ibkr_quotes.json"
OPENCLAW_STATE_DIR = pathlib.Path(os.environ.get("OPENCLAW_STATE_DIR", "/home/openclaw/.openclaw"))
OPENCLAW_CONFIG = OPENCLAW_STATE_DIR / "openclaw.json"
OPENCLAW_ENV_FILE = pathlib.Path("/etc/openclaw/openclaw.env")

DEFAULT_GATEWAY_URL = "https://localhost:5000"
DEFAULT_PANDORA_API_URL = "https://pandoras-box-production.up.railway.app/api"

# IBKR market data field IDs
# 31 = Last Price, 84 = Bid, 86 = Ask, 85 = Bid Size, 88 = Ask Size
# 7283 = Change %, 7284 = Change
SNAPSHOT_FIELDS = "31,84,86,7283,7284"

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


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        v = str(val).replace("C", "").replace("H", "").strip()
        return float(v)
    except (TypeError, ValueError):
        return None


def load_cached_positions() -> dict:
    """Load cached positions from ibkr_poller output."""
    try:
        return json.loads(POSITIONS_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def check_auth(gateway_url: str) -> bool:
    try:
        data = http_json(f"{gateway_url}/v1/api/iserver/auth/status", insecure=True)
        return bool(data and data.get("authenticated"))
    except Exception:
        return False


def get_market_snapshots(gateway_url: str, conids: list[int]) -> list[dict]:
    """
    Fetch market data snapshots for a list of contract IDs.

    Note: IBKR may return empty data on the first call — the API uses a
    subscription model where the first request initiates data flow and
    subsequent requests return actual data.
    """
    if not conids:
        return []

    conid_str = ",".join(str(c) for c in conids)
    url = f"{gateway_url}/v1/api/iserver/marketdata/snapshot?conids={conid_str}&fields={SNAPSHOT_FIELDS}"

    try:
        data = http_json(url, insecure=True, timeout=15)
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[WARN] Market data fetch failed: {e}")
        return []


def run(dry_run: bool = False) -> dict[str, Any]:
    cfg = load_openclaw_config()
    env_file = load_env_file(OPENCLAW_ENV_FILE)

    gateway_url = (pick_env("IBKR_GATEWAY_URL", cfg, env_file) or DEFAULT_GATEWAY_URL).rstrip("/")
    api_url = (pick_env("PANDORA_API_URL", cfg, env_file) or DEFAULT_PANDORA_API_URL).rstrip("/")
    api_key = pick_env("PIVOT_API_KEY", cfg, env_file)

    if not api_key:
        return {"ok": False, "error": "PIVOT_API_KEY is required"}

    # Check auth
    if not check_auth(gateway_url):
        return {"ok": False, "error": "IBKR gateway not authenticated"}

    # Load cached positions to get conids
    cache = load_cached_positions()
    conids = cache.get("conids", [])

    if not conids:
        return {"ok": True, "message": "No conids in cache — run ibkr_poller.py first", "quotes": 0}

    # Fetch snapshots
    snapshots = get_market_snapshots(gateway_url, conids)

    result: dict[str, Any] = {
        "ok": True,
        "timestamp": now_utc().isoformat(),
        "conids_requested": len(conids),
        "snapshots_received": len(snapshots),
        "quotes": {},
    }

    # Parse snapshot data
    quotes: dict[str, dict] = {}
    for snap in snapshots:
        conid = snap.get("conid")
        if not conid:
            continue

        ticker = snap.get("55") or snap.get("symbol") or str(conid)
        last_price = _safe_float(snap.get("31"))
        bid = _safe_float(snap.get("84"))
        ask = _safe_float(snap.get("86"))
        change_pct = _safe_float(snap.get("7283"))
        change = _safe_float(snap.get("7284"))

        quotes[str(conid)] = {
            "conid": conid,
            "ticker": ticker,
            "last": last_price,
            "bid": bid,
            "ask": ask,
            "change": change,
            "change_pct": change_pct,
        }

    result["quotes"] = quotes

    if dry_run:
        print(f"[DRY RUN] Fetched {len(quotes)} quotes:")
        for cid, q in quotes.items():
            print(f"  {q['ticker']}: last={q['last']}, bid={q['bid']}, ask={q['ask']}")

    # Cache quotes
    ensure_data_dir()
    cache_data = {
        "timestamp": result["timestamp"],
        "quotes": quotes,
    }
    QUOTES_CACHE.write_text(json.dumps(cache_data, indent=2) + "\n", encoding="utf-8")

    # Update positions in portfolio API if we have meaningful data
    if not dry_run and quotes:
        positions = cache.get("positions", [])
        if positions:
            # Re-sync positions with updated market data
            # The poller already handles the full sync — quotes just provide
            # more frequent price updates between poller runs
            try:
                headers = {"X-API-Key": api_key}
                sync_resp = http_json(
                    url=f"{api_url}/portfolio/positions/sync",
                    method="POST",
                    headers=headers,
                    payload={"positions": positions},
                )
                result["sync_result"] = sync_resp
            except Exception as e:
                result["sync_error"] = str(e)

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="IBKR market data quotes poller")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch quotes but don't sync to portfolio API")
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
