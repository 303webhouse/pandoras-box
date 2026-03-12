#!/usr/bin/env python3
"""
Signal Notifier — Lightweight signal alert poster.

System cron job (no OpenClaw, no LLM). Runs every 15 min during market hours.
1. Fetches active signals from Railway API
2. Deduplicates against seen_signal_ids.json
3. Posts lightweight Discord embeds with "Run Committee" button
4. Saves signal data to pending_signals.json for the button handler

Zero LLM cost — pure REST API calls.

Schedule: */15 14-21 * * 1-5  (market hours UTC, Mon-Fri)
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

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
OPENCLAW_STATE_DIR = pathlib.Path(os.environ.get("OPENCLAW_STATE_DIR", "/home/openclaw/.openclaw"))
OPENCLAW_CONFIG = OPENCLAW_STATE_DIR / "openclaw.json"
OPENCLAW_ENV_FILE = pathlib.Path("/etc/openclaw/openclaw.env")

SEEN_FILE = DATA_DIR / "seen_signal_ids.json"
PENDING_SIGNALS_FILE = DATA_DIR / "pending_signals.json"

DEFAULT_PANDORA_API_URL = "https://pandoras-box-production.up.railway.app/api"
DEFAULT_CHANNEL_ID = "1470164076049989785"  # #📊-signals
DISCORD_API_BASE = "https://discord.com/api/v10"

SIGNAL_MAX_AGE_MIN = 60  # Ignore signals older than 60 min


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_iso_ts(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.timezone.utc)
    except Exception:
        return None


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
    payload: dict[str, Any] | None = None,
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


def load_seen_ids() -> list[str]:
    ensure_data_dir()
    if not SEEN_FILE.exists():
        SEEN_FILE.write_text("[]\n", encoding="utf-8")
        return []
    try:
        data = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [str(x) for x in data if str(x).strip()]
    except Exception:
        pass
    return []


def save_seen_ids(seen_ids: list[str]) -> None:
    ensure_data_dir()
    trimmed = seen_ids[-500:]
    SEEN_FILE.write_text(json.dumps(trimmed, indent=2) + "\n", encoding="utf-8")


def load_pending_signals() -> dict:
    try:
        if PENDING_SIGNALS_FILE.exists():
            return json.loads(PENDING_SIGNALS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def save_pending_signal(signal_id: str, signal: dict) -> None:
    """Store signal for on-demand committee run."""
    ensure_data_dir()
    pending = load_pending_signals()
    pending[signal_id] = {
        "signal": signal,
        "context": {},  # Context will be built fresh when committee runs
        "stored_at": now_utc().isoformat(),
    }
    if len(pending) > 50:
        sorted_keys = sorted(pending.keys(), key=lambda k: pending[k].get("stored_at", ""))
        for k in sorted_keys[:-50]:
            del pending[k]
    PENDING_SIGNALS_FILE.write_text(json.dumps(pending, default=str, indent=2), encoding="utf-8")


def fetch_signals(api_url: str, api_key: str) -> list[dict]:
    base = api_url.rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}"}

    for path in ("/signals/active", "/signals/queue"):
        try:
            data = http_json(url=base + path, method="GET", headers=headers, timeout=30)
        except Exception:
            continue

        if isinstance(data, dict) and isinstance(data.get("signals"), list):
            return [s for s in data["signals"] if isinstance(s, dict)]

    return []


def load_discord_token(cfg: dict[str, Any], env_file: dict[str, str]) -> str:
    env_token = os.environ.get("DISCORD_BOT_TOKEN", "").strip() or env_file.get("DISCORD_BOT_TOKEN", "").strip()
    if env_token:
        return env_token
    token = (((cfg.get("channels") or {}).get("discord") or {}).get("token") or "").strip()
    if token:
        return token
    raise RuntimeError("Discord token not found")


def _get_score_tier(score: float) -> str:
    if score >= 90:
        return "ELITE"
    elif score >= 80:
        return "STRONG"
    elif score >= 75:
        return "SOLID"
    return "MODERATE"


def post_signal_alert(token: str, channel_id: str, signal: dict, signal_id: str) -> dict | None:
    """Post a rich signal alert embed with Analyze + Dismiss buttons to #signals."""
    ticker = str(signal.get("ticker") or "???")
    direction = str(signal.get("direction") or "???").upper()
    score = signal.get("score_v2") or signal.get("score") or 0
    score_num = float(score) if score else 0
    score_tier = _get_score_tier(score_num)
    strategy = signal.get("strategy", signal.get("signal_type", "N/A"))
    timeframe = signal.get("timeframe", "N/A")
    source = signal.get("source", signal.get("alert_type", "N/A"))
    bias = signal.get("bias_alignment", signal.get("bias_level", "N/A"))

    # Entry / stop / target levels
    entry = signal.get("entry_price")
    stop = signal.get("stop_loss")
    target = signal.get("target_1")

    desc_lines = [
        f"**Strategy:** {strategy}",
        f"**Score:** {score_num:.0f}/100 ({score_tier})",
        f"**Bias:** {bias}",
        f"**Timeframe:** {timeframe}",
    ]

    if entry or stop or target:
        levels = []
        if entry:
            levels.append(f"Entry: ${float(entry):.2f}")
        if stop:
            levels.append(f"Stop: ${float(stop):.2f}")
        if target:
            levels.append(f"Target: ${float(target):.2f}")
        desc_lines.append(" | ".join(levels))

        # R:R calculation
        if entry and stop and target:
            try:
                risk = abs(float(entry) - float(stop))
                reward = abs(float(target) - float(entry))
                if risk > 0:
                    rr = reward / risk
                    desc_lines.append(f"**R:R:** {rr:.1f}:1")
            except (ValueError, ZeroDivisionError):
                pass

    desc_lines.append(f"\nSource: {source}")

    # Color: green for LONG, red for SHORT
    color = 0x00e676 if direction in ("LONG", "BUY", "BULLISH") else 0xe5370e

    embed = {
        "title": f"\U0001f4e1 NEW SIGNAL: {ticker} {direction}",
        "description": "\n".join(desc_lines),
        "color": color,
        "timestamp": now_utc().isoformat(),
        "footer": {"text": f"Signal ID: {signal_id}"},
    }

    components = [
        {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 3,  # Green
                    "label": "Analyze",
                    "custom_id": f"analyze_{signal_id}",
                    "emoji": {"name": "\U0001f52c"},
                },
                {
                    "type": 2,
                    "style": 4,  # Red
                    "label": "Dismiss",
                    "custom_id": f"dismiss_{signal_id}",
                    "emoji": {"name": "\u274c"},
                },
            ],
        }
    ]

    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": "Pivot-SignalNotifier/1.0",
        "Content-Type": "application/json",
    }
    payload = {"embeds": [embed], "components": components}

    try:
        return http_json(url=url, method="POST", headers=headers, payload=payload, timeout=30)
    except Exception as e:
        print(f"[ERROR] Failed to post Discord alert for {ticker}: {e}")
        return None


def post_crypto_signal_alert(token: str, channel_id: str, signal: dict, signal_id: str) -> dict | None:
    """Post a crypto-specific signal alert embed with Take/Pass/Watching buttons."""
    ticker = str(signal.get("ticker") or "BTCUSDT")
    direction = str(signal.get("direction") or "???").upper()
    score = signal.get("score_v2") or signal.get("score") or 0
    score_num = float(score) if score else 0
    strategy = signal.get("strategy", signal.get("signal_type", "N/A"))

    entry = signal.get("entry_price")
    stop = signal.get("stop_loss")
    target = signal.get("target_1")

    # Parse enrichment_data for market structure and sizing
    enrichment = {}
    raw_enrichment = signal.get("enrichment_data")
    if isinstance(raw_enrichment, str):
        try:
            enrichment = json.loads(raw_enrichment)
        except Exception:
            pass
    elif isinstance(raw_enrichment, dict):
        enrichment = raw_enrichment

    ms = enrichment.get("market_structure", {})
    sizing = enrichment.get("position_sizing", {})

    # Direction emoji
    dir_emoji = "\U0001f7e2" if direction in ("LONG", "BUY") else "\U0001f534"

    # Build description
    desc_lines = []

    # Entry / Stop / Target line
    levels = []
    if entry:
        levels.append(f"Entry: ${float(entry):,.2f}")
    if stop:
        levels.append(f"Stop: ${float(stop):,.2f}")
    if target:
        levels.append(f"Target: ${float(target):,.2f}")
    if levels:
        desc_lines.append(" | ".join(levels))

    # R:R and risk
    if entry and stop and target:
        try:
            risk = abs(float(entry) - float(stop))
            reward = abs(float(target) - float(entry))
            if risk > 0:
                rr = reward / risk
                risk_usd = sizing.get("risk_usd", risk)
                risk_pct = sizing.get("risk_pct", "?")
                desc_lines.append(f"**R:R:** {rr:.1f}:1 | **Risk:** ${float(risk_usd):,.0f} ({risk_pct}%)")
        except (ValueError, ZeroDivisionError):
            pass

    # Market structure context
    if ms.get("context_label"):
        ms_emoji = {"STRONG": "\U0001f7e2", "NEUTRAL": "\U0001f7e1", "WEAK": "\U0001f7e0", "AVOID": "\U0001f534"}.get(ms["context_label"], "\u26aa")
        ms_parts = [f"{ms_emoji} **Market Structure: {ms['context_label']}**"]
        detail_parts = []
        if ms.get("poc"):
            detail_parts.append(f"POC: ${float(ms['poc']):,.0f}")
        if ms.get("cvd_direction"):
            detail_parts.append(f"CVD: {ms['cvd_direction']}")
        if ms.get("book_imbalance"):
            detail_parts.append(f"Book: {ms.get('book_imbalance', '?')}x")
        if detail_parts:
            ms_parts.append("   " + " | ".join(detail_parts))
        desc_lines.append("\n".join(ms_parts))

    # Breakout sizing
    if sizing.get("contracts"):
        leverage = sizing.get("leverage", "?")
        contracts = sizing.get("contracts", 0)
        safe_flag = " \u2705" if sizing.get("safe") else " \u26a0\ufe0f"
        desc_lines.append(f"\U0001f4b0 **Size:** {contracts} BTC ({leverage}x leverage){safe_flag}")

    # Session and score
    session = enrichment.get("current_session") or enrichment.get("session", "")
    session_label = f" | Session: {session.title()}" if session else ""
    desc_lines.append(f"\u23f0 Score: {score_num:.0f}/100{session_label}")

    # Color: green for LONG, red for SHORT
    color = 0x00e676 if direction in ("LONG", "BUY", "BULLISH") else 0xe5370e

    embed = {
        "title": f"{dir_emoji} {direction} {ticker} | {strategy}",
        "description": "\n".join(desc_lines),
        "color": color,
        "timestamp": now_utc().isoformat(),
        "footer": {"text": f"Signal ID: {signal_id} | Crypto"},
    }

    # Take / Pass / Watching buttons (no Analyze — crypto is too fast for committee)
    components = [
        {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 3,  # Green
                    "label": "Take",
                    "custom_id": f"take_{signal_id}",
                    "emoji": {"name": "\u2705"},
                },
                {
                    "type": 2,
                    "style": 2,  # Grey
                    "label": "Watching",
                    "custom_id": f"watching_{signal_id}",
                    "emoji": {"name": "\U0001f440"},
                },
                {
                    "type": 2,
                    "style": 4,  # Red
                    "label": "Pass",
                    "custom_id": f"pass_{signal_id}",
                    "emoji": {"name": "\u274c"},
                },
            ],
        }
    ]

    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": "Pivot-SignalNotifier/1.0",
        "Content-Type": "application/json",
    }
    payload = {"embeds": [embed], "components": components}

    try:
        return http_json(url=url, method="POST", headers=headers, payload=payload, timeout=30)
    except Exception as e:
        print(f"[ERROR] Failed to post crypto Discord alert for {ticker}: {e}")
        return None


def is_signal_crypto(signal: dict) -> bool:
    """Check if a signal is crypto (by asset_class or signal_id prefix)."""
    ac = str(signal.get("asset_class") or "").upper()
    if ac == "CRYPTO":
        return True
    sid = str(signal.get("signal_id") or "")
    return sid.startswith("CRYPTO_")


def is_signal_too_old(signal: dict) -> bool:
    ts_raw = signal.get("timestamp")
    if not ts_raw:
        return False
    sig_ts = parse_iso_ts(str(ts_raw))
    if not sig_ts:
        return False
    return (now_utc() - sig_ts).total_seconds() > SIGNAL_MAX_AGE_MIN * 60


def classify_signal(signal: dict) -> str:
    """Basic routing: skip zone shifts and circuit breakers."""
    strategy = str(signal.get("strategy") or "").lower()
    signal_type = str(signal.get("signal_type") or "").upper()

    if "ZONE" in signal_type or "ZONE" in strategy.upper():
        return "zone"
    if any(kw in strategy for kw in ("circuit_breaker", "circuitbreaker", "circuit")):
        return "circuit_breaker"
    return "trade"


def main() -> int:
    parser = argparse.ArgumentParser(description="Signal notifier for Discord")
    parser.add_argument("--crypto", action="store_true", help="Crypto-only mode (24/7 schedule)")
    args = parser.parse_args()

    crypto_mode = args.crypto

    cfg = load_openclaw_config()
    env_file = load_env_file(OPENCLAW_ENV_FILE)

    api_url = pick_env("PANDORA_API_URL", cfg, env_file) or DEFAULT_PANDORA_API_URL
    api_key = pick_env("PIVOT_API_KEY", cfg, env_file)
    channel_id = pick_env("DISCORD_SIGNAL_CHANNEL_ID", cfg, env_file) or DEFAULT_CHANNEL_ID

    if not api_key:
        print(json.dumps({"ok": False, "error": "PIVOT_API_KEY is required"}))
        return 1

    try:
        discord_token = load_discord_token(cfg, env_file)
    except RuntimeError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1

    # Fetch signals
    signals = fetch_signals(api_url, api_key)

    # Load seen IDs
    seen_ids = load_seen_ids()
    seen_set = set(seen_ids)

    mode_label = "crypto" if crypto_mode else "equity"
    result = {
        "ok": True,
        "mode": mode_label,
        "timestamp": now_utc().isoformat(),
        "signals_fetched": len(signals),
        "new_signals": 0,
        "alerts_posted": 0,
        "skipped_old": 0,
        "skipped_non_trade": 0,
        "skipped_wrong_class": 0,
    }

    for signal in signals:
        signal_id = str(signal.get("signal_id") or "").strip()
        if not signal_id:
            continue
        if signal_id in seen_set:
            continue

        # Filter by asset class based on mode
        sig_is_crypto = is_signal_crypto(signal)
        if crypto_mode and not sig_is_crypto:
            continue
        if not crypto_mode and sig_is_crypto:
            result["skipped_wrong_class"] += 1
            continue

        seen_ids.append(signal_id)
        seen_set.add(signal_id)
        result["new_signals"] += 1

        # Skip non-trade signals
        route = classify_signal(signal)
        if route != "trade":
            result["skipped_non_trade"] += 1
            continue

        # Skip old signals
        if is_signal_too_old(signal):
            result["skipped_old"] += 1
            continue

        # Post alert to Discord (use crypto embed for crypto signals)
        if sig_is_crypto:
            resp = post_crypto_signal_alert(discord_token, channel_id, signal, signal_id)
        else:
            resp = post_signal_alert(discord_token, channel_id, signal, signal_id)

        if resp:
            result["alerts_posted"] += 1
            # Save signal for button handler (committee for equity, decision log for crypto)
            save_pending_signal(signal_id, signal)

    # Save seen IDs
    save_seen_ids(seen_ids)

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
