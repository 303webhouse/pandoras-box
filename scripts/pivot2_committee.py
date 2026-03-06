#!/usr/bin/env python3
"""
Pivot II Trading Team — Gatekeeper + Pipeline (refactored)

Polls Railway API for signals, filters through Gatekeeper rules,
builds market context, runs committee on-demand (via Discord button),
posts recommendations to Discord.

Committee refactor changes:
- RISK agent replaced with TECHNICALS agent
- No position data sent to any agent
- All agents use Sonnet
- Committee runs on-demand via "Run Committee" button (not automatically)
- signal_notifier.py handles lightweight signal alerts (separate script)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import pathlib
import re
import urllib.error
import urllib.request
from typing import Any

# ── imports ──────────────────────────────────────────────────
from committee_prompts import (
    TORO_SYSTEM_PROMPT, URSA_SYSTEM_PROMPT,
    TECHNICALS_SYSTEM_PROMPT, PIVOT_SYSTEM_PROMPT,
)
from committee_parsers import (
    call_agent, parse_analyst_response,
    parse_pivot_response, DEFAULT_MODEL,
)
from committee_context import (
    format_signal_context,
    get_bias_challenge_context,
    format_technical_data,
    _get_agent_feedback_context,
)
from committee_decisions import (
    log_decision,
    save_pending,
    expire_stale_recommendations,
    rotate_log_if_needed,
    build_button_components,
    DECISION_LOG,
    COMMITTEE_LOG,
)

log = logging.getLogger("pivot2_committee")


# ── constants ────────────────────────────────────────────────
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
SESSION_STATE_FILE = SCRIPT_DIR.parent / "SESSION-STATE.md"

DEFAULT_PANDORA_API_URL = "https://pandoras-box-production.up.railway.app/api"
DEFAULT_CHANNEL_ID = "1474135100521451813"
DISCORD_API_BASE = "https://discord.com/api/v10"
OPENCLAW_STATE_DIR = pathlib.Path(os.environ.get("OPENCLAW_STATE_DIR", "/home/openclaw/.openclaw"))
OPENCLAW_CONFIG = OPENCLAW_STATE_DIR / "openclaw.json"
OPENCLAW_ENV_FILE = pathlib.Path("/etc/openclaw/openclaw.env")

SEEN_FILE = DATA_DIR / "seen_signal_ids.json"
ZONE_FILE = DATA_DIR / "last_zone_shift.json"
CB_FILE = DATA_DIR / "recent_circuit_breakers.json"
LOG_FILE = DATA_DIR / "committee_log.jsonl"
DAILY_COUNT_FILE = DATA_DIR / "committee_daily_count.json"
PENDING_SIGNALS_FILE = DATA_DIR / "pending_signals.json"

ZONE_RE = re.compile(r"from\s+([A-Z_]+)\s+to\s+([A-Z_]+)", re.IGNORECASE)

MIN_SCORE_CTA = 60
MIN_SCORE_COUNTER_BIAS = 80  # legacy fallback
# Graduated thresholds — stronger bias = higher bar for counter-bias signals
GATEKEEPER_THRESHOLDS = {"MAJOR": 85, "MINOR": 70, "NEUTRAL": 60}
MAX_DAILY_RUNS = 20
SIGNAL_MAX_AGE_MIN = 30
CB_RETENTION_HOURS = 2
LOG_MAX_LINES = 500

# TradingView strategy keywords for routing
TV_COMMITTEE_STRATEGIES = {"sniper", "scout", "exhaustion", "holy_grail"}
TV_WHALE_STRATEGIES = {"whale", "whale_hunter", "whalehunter"}
TV_CIRCUIT_BREAKER_STRATEGIES = {"circuit_breaker", "circuitbreaker", "circuit"}

# Committee model — all agents use Sonnet
COMMITTEE_MODEL = "claude-sonnet-4-5-20250929"


# ── utility functions ────────────────────────────────────────


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


def load_discord_token(cfg: dict[str, Any], env_file: dict[str, str]) -> str:
    env_token = os.environ.get("DISCORD_BOT_TOKEN", "").strip() or env_file.get("DISCORD_BOT_TOKEN", "").strip()
    if env_token:
        return env_token

    token = (((cfg.get("channels") or {}).get("discord") or {}).get("token") or "").strip()
    if token:
        return token

    raise RuntimeError("Discord token not found. Set DISCORD_BOT_TOKEN or channels.discord.token in openclaw.json")


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


def save_zone_shift(signal: dict[str, Any]) -> None:
    notes = str(signal.get("notes") or "")
    m = ZONE_RE.search(notes)
    from_zone = m.group(1).upper() if m else None
    to_zone = m.group(2).upper() if m else None

    ts = str(signal.get("timestamp") or now_utc().isoformat())
    payload = {
        "timestamp": ts,
        "signal_type": str(signal.get("signal_type") or ""),
        "direction": str(signal.get("direction") or ""),
        "from_zone": from_zone,
        "to_zone": to_zone,
    }
    ensure_data_dir()
    ZONE_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def is_zone_signal(signal: dict[str, Any]) -> bool:
    signal_type = str(signal.get("signal_type") or "").upper()
    strategy = str(signal.get("strategy") or "").upper()
    return "ZONE" in signal_type or "ZONE" in strategy


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def fetch_signals(api_url: str, api_key: str) -> list[dict[str, Any]]:
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


# ── Pending signals (for Run Committee button) ───────────────

def load_pending_signals() -> dict:
    """Load pending signals awaiting committee run."""
    try:
        if PENDING_SIGNALS_FILE.exists():
            return json.loads(PENDING_SIGNALS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def save_pending_signal(signal_id: str, signal: dict, context: dict) -> None:
    """Store signal + context for on-demand committee run."""
    ensure_data_dir()
    pending = load_pending_signals()
    pending[signal_id] = {
        "signal": signal,
        "context": context,
        "stored_at": now_utc().isoformat(),
    }
    # Trim old entries (keep last 50)
    if len(pending) > 50:
        sorted_keys = sorted(pending.keys(), key=lambda k: pending[k].get("stored_at", ""))
        for k in sorted_keys[:-50]:
            del pending[k]
    PENDING_SIGNALS_FILE.write_text(json.dumps(pending, default=str, indent=2), encoding="utf-8")


def pop_pending_signal(signal_id: str) -> dict | None:
    """Remove and return a pending signal."""
    pending = load_pending_signals()
    entry = pending.pop(signal_id, None)
    ensure_data_dir()
    PENDING_SIGNALS_FILE.write_text(json.dumps(pending, default=str, indent=2), encoding="utf-8")
    return entry


# ── Gatekeeper ───────────────────────────────────────────────

def classify_signal_source(signal: dict) -> str:
    """Determine routing: 'committee', 'whale', 'circuit_breaker', 'zone', 'skip'"""
    strategy = str(signal.get("strategy") or "").lower()
    signal_type = str(signal.get("signal_type") or "").upper()

    if "ZONE" in signal_type or "ZONE" in strategy.upper():
        return "zone"
    if any(kw in strategy for kw in TV_CIRCUIT_BREAKER_STRATEGIES):
        return "circuit_breaker"
    if any(kw in strategy for kw in TV_WHALE_STRATEGIES):
        return "whale"
    return "committee"


def is_tv_prequalified(signal: dict) -> bool:
    """TradingView Sniper/Scout/Exhaustion skip score threshold."""
    strategy = str(signal.get("strategy") or "").lower()
    return any(kw in strategy for kw in TV_COMMITTEE_STRATEGIES)


def get_dedup_key(signal: dict) -> str:
    """One committee run per ticker+direction per day."""
    ticker = str(signal.get("ticker") or "UNKNOWN").upper()
    direction = str(signal.get("direction") or "UNKNOWN").upper()
    date = now_utc().strftime("%Y-%m-%d")
    return f"{ticker}_{direction}_{date}"


def load_daily_count() -> dict:
    try:
        if DAILY_COUNT_FILE.exists():
            data = json.loads(DAILY_COUNT_FILE.read_text())
            if data.get("date") == now_utc().strftime("%Y-%m-%d"):
                return data
    except Exception:
        pass
    return {"date": now_utc().strftime("%Y-%m-%d"), "count": 0, "dedup_keys": []}


def save_daily_count(data: dict) -> None:
    ensure_data_dir()
    DAILY_COUNT_FILE.write_text(json.dumps(data, indent=2))


def gatekeeper(signal: dict, bias_level: str, defcon: str, daily: dict) -> tuple[bool, str | None]:
    """
    Returns (pass: bool, reject_reason: str|None).
    If pass=True, signal proceeds to committee.
    """
    score = safe_float(signal.get("score"))
    direction = str(signal.get("direction") or "").upper()
    tv_prequalified = is_tv_prequalified(signal)

    if not tv_prequalified and score < MIN_SCORE_CTA:
        return False, "score_below_threshold"

    ts_raw = signal.get("timestamp")
    if ts_raw:
        sig_ts = parse_iso_ts(str(ts_raw))
        if sig_ts and (now_utc() - sig_ts).total_seconds() > SIGNAL_MAX_AGE_MIN * 60:
            return False, "signal_too_old"

    dedup_key = get_dedup_key(signal)
    if dedup_key in daily.get("dedup_keys", []):
        return False, "duplicate_ticker_direction_today"

    if daily.get("count", 0) >= MAX_DAILY_RUNS:
        return False, "daily_cap_reached"

    defcon_upper = defcon.upper() if defcon else "GREEN"
    if defcon_upper == "RED" and direction not in ("SHORT", "BEARISH", "SELL"):
        return False, "defcon_red_bearish_only"
    if defcon_upper == "ORANGE":
        is_bullish_direction = direction in ("LONG", "BULLISH", "BUY")
        is_bearish_direction = direction in ("SHORT", "BEARISH", "SELL")
        bias_upper = bias_level.upper() if bias_level else "NEUTRAL"
        if "TORO" in bias_upper and is_bearish_direction:
            return False, "defcon_orange_counter_bias"
        if "URSA" in bias_upper and is_bullish_direction:
            return False, "defcon_orange_counter_bias"

    if not tv_prequalified:
        bias_upper = bias_level.upper() if bias_level else "NEUTRAL"
        is_bullish = direction in ("LONG", "BULLISH", "BUY")
        is_bearish = direction in ("SHORT", "BEARISH", "SELL")

        # Graduated thresholds: MAJOR bias = 85, MINOR = 70
        counter_bias = False
        if "TORO" in bias_upper and is_bearish:
            counter_bias = True
        elif "URSA" in bias_upper and is_bullish:
            counter_bias = True

        if counter_bias:
            if "MAJOR" in bias_upper:
                threshold = GATEKEEPER_THRESHOLDS["MAJOR"]
            elif "MINOR" in bias_upper:
                threshold = GATEKEEPER_THRESHOLDS["MINOR"]
            else:
                threshold = GATEKEEPER_THRESHOLDS["NEUTRAL"]
            if score < threshold:
                return False, f"counter_bias_score_too_low ({score} < {threshold} for {bias_upper})"

    return True, None


def build_gatekeeper_report(
    signal: dict,
    bias_level: str,
    defcon: str,
    daily: dict,
    context: dict,
) -> str:
    """
    Build a human-readable breakdown of what the gatekeeper evaluated.
    """
    lines = []
    score = safe_float(signal.get("score"))
    direction = str(signal.get("direction") or "").upper()
    tv_prequalified = is_tv_prequalified(signal)
    bias_upper = bias_level.upper() if bias_level else "NEUTRAL"

    if tv_prequalified:
        strategy = str(signal.get("strategy") or "").lower()
        lines.append(f"\u2705 TradingView pre-qualified ({strategy}) \u2014 score threshold skipped")
    else:
        threshold = MIN_SCORE_CTA
        is_bullish = direction in ("LONG", "BULLISH", "BUY")
        is_bearish = direction in ("SHORT", "BEARISH", "SELL")
        counter_bias = False
        if "TORO" in bias_upper and is_bearish:
            counter_bias = True
        elif "URSA" in bias_upper and is_bullish:
            counter_bias = True

        if counter_bias:
            if "MAJOR" in bias_upper:
                threshold = GATEKEEPER_THRESHOLDS["MAJOR"]
            elif "MINOR" in bias_upper:
                threshold = GATEKEEPER_THRESHOLDS["MINOR"]
            else:
                threshold = GATEKEEPER_THRESHOLDS["NEUTRAL"]
            lines.append(f"\u26a0\ufe0f Score: {int(score)} (counter-bias threshold: {threshold} for {bias_upper})")
        else:
            lines.append(f"\u2705 Score: {int(score)} (threshold: {threshold})")

    if "TORO" in bias_upper:
        bias_display = "TORO"
    elif "URSA" in bias_upper:
        bias_display = "URSA"
    else:
        bias_display = "NEUTRAL"

    direction_display = (
        "BULLISH" if direction in ("LONG", "BULLISH", "BUY")
        else "BEARISH" if direction in ("SHORT", "BEARISH", "SELL")
        else direction
    )

    is_aligned = (
        ("TORO" in bias_upper and direction_display == "BULLISH") or
        ("URSA" in bias_upper and direction_display == "BEARISH") or
        bias_display == "NEUTRAL"
    )

    if is_aligned:
        lines.append(f"\u2705 Bias-aligned: {direction_display} signal + {bias_level} bias")
    else:
        lines.append(f"\u26a0\ufe0f Counter-bias: {direction_display} signal vs {bias_level} bias")

    defcon_upper = defcon.upper() if defcon else "GREEN"
    if defcon_upper == "GREEN":
        lines.append(f"\u2705 DEFCON: {defcon_upper}")
    else:
        lines.append(f"\u26a0\ufe0f DEFCON: {defcon_upper} (filtering active)")

    earnings = context.get("earnings") or {}
    if earnings.get("has_earnings"):
        days = earnings["days_until"]
        if days <= 3:
            lines.append(f"\U0001f534 Earnings: {signal.get('ticker')} reports in {days} day(s)!")
        else:
            lines.append(f"\u26a0\ufe0f Earnings: {signal.get('ticker')} reports in {days} days")
    else:
        lines.append(f"\u2705 No earnings within 14 days")

    ts_raw = signal.get("timestamp")
    if ts_raw:
        sig_ts = parse_iso_ts(str(ts_raw))
        if sig_ts:
            age_secs = (now_utc() - sig_ts).total_seconds()
            if age_secs < 60:
                lines.append(f"\u2705 Age: {int(age_secs)}s old (max: {SIGNAL_MAX_AGE_MIN}min)")
            else:
                lines.append(f"\u2705 Age: {int(age_secs / 60)}min old (max: {SIGNAL_MAX_AGE_MIN}min)")

    count = daily.get("count", 0)
    remaining = MAX_DAILY_RUNS - count
    if remaining <= 5:
        lines.append(f"\u26a0\ufe0f Daily budget: {count}/{MAX_DAILY_RUNS} runs used ({remaining} remaining)")
    else:
        lines.append(f"\u2705 Daily budget: {count}/{MAX_DAILY_RUNS} runs used")

    return "\n".join(lines)


# ── Market Context Builder ───────────────────────────────────

def parse_defcon_from_session_state() -> str:
    """Extract DEFCON level from SESSION-STATE.md."""
    if not SESSION_STATE_FILE.exists():
        return "GREEN"
    content = SESSION_STATE_FILE.read_text(encoding="utf-8")
    for line in content.split("\n"):
        if "DEFCON" in line.upper() and ":" in line:
            parts = line.split(":")
            if len(parts) >= 2:
                level = parts[-1].strip().upper()
                for valid in ("GREEN", "YELLOW", "ORANGE", "RED"):
                    if valid in level:
                        return valid
    return "GREEN"


def load_recent_circuit_breakers() -> list[dict]:
    """Load CB events from last 2 hours."""
    try:
        if CB_FILE.exists():
            events = json.loads(CB_FILE.read_text(encoding="utf-8"))
            now = now_utc()
            recent = []
            for ev in events:
                ts = parse_iso_ts(str(ev.get("timestamp") or ""))
                if ts and (now - ts).total_seconds() <= CB_RETENTION_HOURS * 3600:
                    recent.append(ev)
            return recent
    except Exception:
        pass
    return []


def save_circuit_breaker(signal: dict) -> None:
    """Append CB event, prune old entries."""
    ensure_data_dir()
    events = load_recent_circuit_breakers()
    events.append({
        "ticker": str(signal.get("ticker") or "SPY"),
        "direction": str(signal.get("direction") or "BEARISH"),
        "timestamp": str(signal.get("timestamp") or now_utc().isoformat()),
        "entry_price": safe_float(signal.get("entry_price")),
        "notes": str(signal.get("notes") or signal.get("signal_type") or ""),
    })
    CB_FILE.write_text(json.dumps(events, indent=2), encoding="utf-8")


# ETFs don't have earnings — skip yfinance quoteSummary call (returns 404 for ETFs)
_ETF_TICKERS = {
    "SPY", "QQQ", "IWM", "DIA", "SMH", "XLF", "XLE", "XLU",
    "XLK", "XLV", "XLI", "XLP", "XLY", "XLB", "XLRE",
    "EFA", "EEM", "GLD", "SLV", "TLT", "HYG", "LQD",
    "VTI", "VOO", "ARKK", "SOXX", "KRE", "XBI", "IBB",
    "FXI", "KWEB", "GDX", "GDXJ", "USO", "UNG",
}


def check_earnings_proximity(ticker: str, dte_days: int = 30) -> dict:
    """Check if ticker has earnings within the DTE window (default 30 days for swing trades)."""
    _no_earnings = {"has_earnings": False, "days_until": None, "date": None, "within_dte_window": False}

    if not ticker or ticker.upper() in _ETF_TICKERS:
        return _no_earnings

    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        cal = t.calendar
        if cal is not None and not cal.empty and "Earnings Date" in cal.index:
            from datetime import date
            earn_date = cal.loc["Earnings Date"][0]
            if hasattr(earn_date, "date"):
                earn_date = earn_date.date()
            days = (earn_date - date.today()).days
            window = max(14, dte_days)  # always check at least 14 days
            if 0 <= days <= window:
                return {
                    "has_earnings": True,
                    "days_until": days,
                    "date": str(earn_date),
                    "within_dte_window": days <= dte_days,
                }
    except Exception as e:
        log.warning("Earnings check failed for %s: %s", ticker, e)
    return _no_earnings


def _compute_timeframe_fit(direction: str, context: dict) -> str:
    """Compute which timeframes align with the signal direction."""
    bias = context.get("bias_composite") or {}
    timeframes = bias.get("timeframes") or {}
    if not timeframes:
        return ""

    is_bullish = direction in ("LONG", "BULLISH", "BUY")
    is_bearish = direction in ("SHORT", "BEARISH", "SELL")
    if not is_bullish and not is_bearish:
        return ""

    aligned = []
    for tf_name in ("intraday", "swing", "macro"):
        tf = timeframes.get(tf_name, {})
        tf_bias = tf.get("bias_level", "NEUTRAL")
        if is_bullish and "TORO" in tf_bias:
            aligned.append(f"{tf_name}-aligned")
        elif is_bearish and "URSA" in tf_bias:
            aligned.append(f"{tf_name}-aligned")

    return ", ".join(aligned) if aligned else "no alignment"


def build_market_context(signal: dict, api_url: str, api_key: str) -> dict:
    """Build full context dict for committee agents."""
    headers = {"Authorization": f"Bearer {api_key}"}
    base = api_url.rstrip("/")

    # 1. Bias composite
    composite = {}
    try:
        composite = http_json(url=f"{base}/api/bias/composite", headers=headers, timeout=30)
    except Exception:
        pass

    # 2. DEFCON
    defcon = parse_defcon_from_session_state()

    # 3. Recent Circuit Breakers
    cb_events = load_recent_circuit_breakers()

    # 4. Earnings proximity
    ticker = str(signal.get("ticker") or "").upper()
    earnings = check_earnings_proximity(ticker, dte_days=30)

    # 5. Zone context
    zone = {}
    try:
        if ZONE_FILE.exists():
            zone = json.loads(ZONE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass

    # 6. Portfolio context (graceful fallback to empty)
    portfolio = {}
    try:
        from committee_context import fetch_portfolio_context
        portfolio = fetch_portfolio_context(api_url)
    except Exception:
        pass

    # 7. Timeframe sub-scores
    timeframes = {}
    try:
        tf_data = http_json(url=f"{base}/api/bias/composite/timeframes", headers=headers, timeout=30)
        if isinstance(tf_data, dict):
            timeframes = tf_data.get("timeframes", {})
    except Exception:
        pass

    # 8. Circuit breaker live status from Railway
    cb_status = {}
    try:
        cb_status = http_json(url=f"{base}/webhook/circuit_breaker/status", headers=headers, timeout=10)
    except Exception:
        pass

    # Extract key factors from composite response for agent context
    factors_raw = composite.get("factors", {}) if isinstance(composite, dict) else {}

    return {
        "bias_composite": {
            "bias_level": composite.get("bias_level", "UNKNOWN") if isinstance(composite, dict) else "UNKNOWN",
            "composite_score": composite.get("composite_score") if isinstance(composite, dict) else None,
            "confidence": composite.get("confidence", "UNKNOWN") if isinstance(composite, dict) else "UNKNOWN",
            "timeframes": timeframes,
            "factors": factors_raw,
        },
        "defcon": defcon,
        "circuit_breakers": cb_events,
        "circuit_breaker_status": cb_status.get("circuit_breaker", {}) if isinstance(cb_status, dict) else {},
        "earnings": earnings,
        "zone": zone,
        "portfolio": portfolio,
        "api_url": api_url,
        "api_key": api_key,
    }


# ── Committee (4 agents: TORO, URSA, TECHNICALS, PIVOT) ─────

def run_committee(signal: dict, context: dict, api_key: str, technical_data: dict | None = None) -> dict:
    """
    Run all four committee agents via Anthropic API.
    Returns recommendation dict with agent analyses and raw responses.
    """
    base_context = format_signal_context(signal, context)

    # Inject live technical data if available
    tech_block = format_technical_data(technical_data or {})
    if tech_block:
        base_context = base_context + "\n\n" + tech_block

    # Inject economic calendar events within DTE window
    try:
        from committee_context import fetch_economic_calendar, format_economic_calendar
        econ_events = fetch_economic_calendar(dte_days=30)
        econ_block = format_economic_calendar(econ_events)
        if econ_block:
            base_context = base_context + "\n\n" + econ_block
    except Exception as e:
        log.warning("Failed to inject economic calendar: %s", e)

    # Inject UW flow data for the signal ticker + market flow
    try:
        from committee_context import build_uw_flow_context, build_market_flow_context
        api_url = context.get("api_url") or os.environ.get("PANDORA_API_URL") or ""
        api_key_val = context.get("api_key") or os.environ.get("PIVOT_API_KEY") or ""
        ticker = signal.get("ticker", "")
        if ticker and api_url:
            uw_ticker_block = build_uw_flow_context(ticker, api_url, api_key_val)
            if uw_ticker_block:
                base_context = base_context + "\n\n" + uw_ticker_block
        if api_url:
            uw_market_block = build_market_flow_context(api_url, api_key_val)
            if uw_market_block:
                base_context = base_context + "\n\n" + uw_market_block
    except Exception as e:
        log.warning("Failed to inject UW flow context: %s", e)

    # Inject portfolio context (balances + open positions)
    try:
        from committee_context import format_portfolio_context
        portfolio_block = format_portfolio_context(context.get("portfolio") or {})
        if portfolio_block:
            base_context = base_context + "\n\n" + portfolio_block
    except Exception as e:
        log.warning("Failed to inject portfolio context: %s", e)

    # Inject recent P&L / loss streak context
    try:
        from committee_context import fetch_recent_pnl_context
        pnl_block = fetch_recent_pnl_context()
        if pnl_block:
            base_context = base_context + "\n\n" + pnl_block
    except Exception as e:
        log.warning("Failed to inject P&L context: %s", e)

    # Build per-agent context with agent-specific feedback
    def _agent_context(agent_name: str) -> str:
        ctx = base_context
        feedback = _get_agent_feedback_context(agent_name)
        if feedback:
            ctx = ctx + feedback
        return ctx

    # ── TORO ANALYST ──
    log.info("Calling TORO agent...")
    toro_raw = call_agent(
        system_prompt=TORO_SYSTEM_PROMPT,
        user_message=_agent_context("TORO"),
        api_key=api_key,
        max_tokens=500,
        temperature=0.3,
        agent_name="TORO",
        model=COMMITTEE_MODEL,
    )
    if toro_raw:
        toro_response = parse_analyst_response(toro_raw, "TORO")
    else:
        toro_response = {
            "agent": "TORO",
            "analysis": "[ANALYSIS UNAVAILABLE — TORO agent timed out]",
            "conviction": "MEDIUM",
        }

    # ── URSA ANALYST ──
    log.info("Calling URSA agent...")
    ursa_raw = call_agent(
        system_prompt=URSA_SYSTEM_PROMPT,
        user_message=_agent_context("URSA"),
        api_key=api_key,
        max_tokens=500,
        temperature=0.3,
        agent_name="URSA",
        model=COMMITTEE_MODEL,
    )
    if ursa_raw:
        ursa_response = parse_analyst_response(ursa_raw, "URSA")
    else:
        ursa_response = {
            "agent": "URSA",
            "analysis": "[ANALYSIS UNAVAILABLE — URSA agent timed out]",
            "conviction": "MEDIUM",
        }

    # ── TECHNICALS ANALYST ──
    log.info("Calling TECHNICALS agent...")
    technicals_raw = call_agent(
        system_prompt=TECHNICALS_SYSTEM_PROMPT,
        user_message=_agent_context("TECHNICALS"),
        api_key=api_key,
        max_tokens=750,
        temperature=0.3,
        agent_name="TECHNICALS",
        model=COMMITTEE_MODEL,
    )
    if technicals_raw:
        technicals_response = parse_analyst_response(technicals_raw, "TECHNICALS")
    else:
        technicals_response = {
            "agent": "TECHNICALS",
            "analysis": "[ANALYSIS UNAVAILABLE — TECHNICALS agent timed out]",
            "conviction": "MEDIUM",
        }

    # ── PIVOT / MARK BAUM ──
    log.info("Calling PIVOT agent...")
    bias_challenge = get_bias_challenge_context(signal, context)

    pivot_feedback = _get_agent_feedback_context("PIVOT")
    pivot_context = (
        f"{base_context}\n\n"
        f"## TORO ANALYST REPORT\n"
        f"Analysis: {toro_response['analysis']}\n"
        f"Conviction: {toro_response['conviction']}\n\n"
        f"## URSA ANALYST REPORT\n"
        f"Analysis: {ursa_response['analysis']}\n"
        f"Conviction: {ursa_response['conviction']}\n\n"
        f"## TECHNICALS ANALYST REPORT\n"
        f"Analysis: {technicals_response['analysis']}\n"
        f"Conviction: {technicals_response['conviction']}"
        f"{bias_challenge}"
        f"{pivot_feedback}"
    )

    pivot_raw = call_agent(
        system_prompt=PIVOT_SYSTEM_PROMPT,
        user_message=pivot_context,
        api_key=api_key,
        max_tokens=1500,
        temperature=0.6,
        agent_name="PIVOT",
        model=COMMITTEE_MODEL,
    )
    if pivot_raw:
        pivot_response = parse_pivot_response(pivot_raw)
    else:
        pivot_response = {
            "agent": "PIVOT",
            "synthesis": (
                f"[PIVOT UNAVAILABLE — plain summary]\n"
                f"Bull: {toro_response['analysis']}\n"
                f"Bear: {ursa_response['analysis']}\n"
                f"Technicals: {technicals_response['analysis']}"
            ),
            "conviction": "LOW",
            "action": "WATCHING",
            "invalidation": "Manual review required — Pivot synthesis unavailable",
        }

    # ── ASSEMBLE RECOMMENDATION ──
    return {
        "signal": signal,
        "agents": {
            "toro": toro_response,
            "ursa": ursa_response,
            "technicals": technicals_response,
            "pivot": pivot_response,
        },
        "timestamp": now_utc().isoformat(),
        "model": COMMITTEE_MODEL,
        "raw_responses": {
            "toro": toro_raw,
            "ursa": ursa_raw,
            "technicals": technicals_raw,
            "pivot": pivot_raw,
        },
    }


# ── Discord Posting ──────────────────────────────────────────

def truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def build_committee_embed(recommendation: dict, context: dict, gatekeeper_report: str = None) -> dict:
    """Build Discord embed payload from committee recommendation."""
    agents = recommendation["agents"]
    signal = recommendation["signal"]
    pivot = agents["pivot"]
    toro = agents["toro"]
    ursa = agents["ursa"]
    technicals = agents["technicals"]

    # Color by action
    color_map = {"TAKE": 0x00FF88, "PASS": 0xFF4444, "WATCHING": 0xFFAA00}
    color = color_map.get(pivot.get("action", "WATCHING"), 0x888888)

    # Action emoji
    emoji_map = {"TAKE": "\U0001f7e2", "PASS": "\U0001f534", "WATCHING": "\U0001f7e1"}
    emoji = emoji_map.get(pivot.get("action", "WATCHING"), "\u26aa")

    ticker = str(signal.get("ticker") or "???")
    direction = str(signal.get("direction") or "???").upper()

    # Conviction display
    conviction_display = {
        "HIGH": "\U0001f7e9\U0001f7e9\U0001f7e9 HIGH",
        "MEDIUM": "\U0001f7e8\U0001f7e8\u2b1c MEDIUM",
        "LOW": "\U0001f7e5\u2b1c\u2b1c LOW",
    }

    fields = [
        {
            "name": "Conviction",
            "value": conviction_display.get(pivot.get("conviction", "MEDIUM"), pivot.get("conviction", "MEDIUM")),
            "inline": True,
        },
        {
            "name": "Direction",
            "value": direction,
            "inline": True,
        },
        {
            "name": "Signal",
            "value": truncate(
                f"{signal.get('alert_type', signal.get('signal_type', signal.get('strategy', '?')))} "
                f"(score: {signal.get('score', 'N/A')})",
                256,
            ),
            "inline": True,
        },
    ]

    # Gatekeeper report
    if gatekeeper_report:
        fields.append({
            "name": "\U0001f50d Gatekeeper Report",
            "value": truncate(gatekeeper_report, 1024),
            "inline": False,
        })

    # Analyst reports
    fields += [
        {
            "name": f"\U0001f402 TORO ({toro.get('conviction', '?')})",
            "value": truncate(toro.get("analysis", "N/A"), 512),
            "inline": True,
        },
        {
            "name": f"\U0001f43b URSA ({ursa.get('conviction', '?')})",
            "value": truncate(ursa.get("analysis", "N/A"), 512),
            "inline": True,
        },
        {
            "name": f"\U0001f4c8 TECHNICALS ({technicals.get('conviction', '?')})",
            "value": truncate(technicals.get("analysis", "N/A"), 1024),
            "inline": False,
        },
    ]

    # Timeframe alignment
    tf_fit = _compute_timeframe_fit(direction, context)
    if tf_fit:
        fields.append({
            "name": "Timeframe Fit",
            "value": tf_fit,
            "inline": True,
        })

    # Earnings warning
    earnings = context.get("earnings") or {}
    if earnings.get("has_earnings"):
        fields.append({
            "name": "\U0001f4c5 Earnings Warning",
            "value": f"\u26a0\ufe0f {ticker} earnings in {earnings['days_until']} days ({earnings['date']})",
            "inline": False,
        })

    # Invalidation
    fields.append({
        "name": "\u274c Invalidation",
        "value": truncate(pivot.get("invalidation", "See analysis above"), 256),
        "inline": False,
    })

    # Options structure recommendation (if present)
    structure = pivot.get("structure")
    if structure and structure.upper() != "N/A":
        fields.append({
            "name": "\U0001f3af Options Structure",
            "value": truncate(structure, 512),
            "inline": False,
        })

    # Entry/Stop/Target levels (if present)
    levels = pivot.get("levels")
    if levels and levels.upper() != "N/A":
        fields.append({
            "name": "\U0001f4cd Levels (Entry / Stop / Target)",
            "value": truncate(levels, 512),
            "inline": False,
        })

    # Position sizing recommendation (if present)
    size = pivot.get("size")
    if size and size.upper() != "N/A":
        fields.append({
            "name": "\U0001f4b0 Position Size",
            "value": truncate(size, 256),
            "inline": False,
        })

    embed = {
        "title": truncate(f"{emoji} {ticker} {direction} \u2014 {pivot.get('action', 'WATCHING')}", 256),
        "description": truncate(pivot.get("synthesis", "No synthesis available"), 4000),
        "color": color,
        "timestamp": recommendation.get("timestamp", now_utc().isoformat()),
        "fields": fields,
        "footer": {
            "text": f"Signal: {signal.get('signal_id', 'N/A')} | Model: {recommendation.get('model', 'N/A')}",
        },
    }

    return embed


def post_discord_message(token: str, channel_id: str, content: str) -> dict:
    """Post a plain text message to Discord."""
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": "Pivot-II/2.0",
        "Content-Type": "application/json",
    }
    if len(content) > 1950:
        content = content[:1950] + "\n[truncated]"
    return http_json(url=url, method="POST", headers=headers, payload={"content": content}, timeout=30)


def post_discord_embed(
    token: str,
    channel_id: str,
    embed: dict,
    content: str = "",
    components: list | None = None,
) -> dict:
    """Post an embed message to Discord via REST API, optionally with button components."""
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": "Pivot-II/2.0",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {"embeds": [embed]}
    if content:
        payload["content"] = content
    if components:
        payload["components"] = components
    return http_json(url=url, method="POST", headers=headers, payload=payload, timeout=30)


def edit_discord_message(
    token: str,
    channel_id: str,
    message_id: str,
    embed: dict | None = None,
    content: str | None = None,
    components: list | None = None,
) -> dict:
    """Edit an existing Discord message."""
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages/{message_id}"
    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": "Pivot-II/2.0",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {}
    if embed is not None:
        payload["embeds"] = [embed]
    if content is not None:
        payload["content"] = content
    if components is not None:
        payload["components"] = components
    return http_json(url=url, method="PATCH", headers=headers, payload=payload, timeout=30)


def format_whale_message(signal: dict) -> str:
    ticker = str(signal.get("ticker") or "???")
    direction = str(signal.get("direction") or "???").upper()
    return (
        f"\U0001f40b **Whale Hunter detected: {ticker} {direction}**\n\n"
        f"Absorption pattern on the tape. Need options flow confirmation before "
        f"this goes to the committee.\n\n"
        f"**Nick \u2014 post a UW screenshot for {ticker}.** I'm looking for:\n"
        f"\u2022 Large block/sweep activity matching {direction} direction\n"
        f"\u2022 Elevated OI at nearby strikes\n"
        f"\u2022 Dark pool prints supporting the thesis\n\n"
        f"\u23f0 Signal expires in 30 minutes if no confirmation."
    )


def format_circuit_breaker_message(signal: dict) -> str:
    ticker = str(signal.get("ticker") or "???")
    direction = str(signal.get("direction") or "???").upper()
    return (
        f"\u26a1 **Circuit Breaker fired: {ticker} {direction}**\n"
        f"This is a market stress warning, not a trade idea. "
        f"The committee will factor this into its next analysis."
    )


# ── Logging ──────────────────────────────────────────────────

def log_committee_event(entry: dict) -> None:
    """Append to committee_log.jsonl, trim to LOG_MAX_LINES."""
    ensure_data_dir()
    line = json.dumps(entry, default=str) + "\n"

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)

    try:
        lines = LOG_FILE.read_text(encoding="utf-8").strip().split("\n")
        if len(lines) > LOG_MAX_LINES:
            LOG_FILE.write_text("\n".join(lines[-LOG_MAX_LINES:]) + "\n", encoding="utf-8")
    except Exception:
        pass


# ── Main Pipeline ────────────────────────────────────────────

def run(channel_id: str, dry_run: bool) -> dict:
    """
    Main pipeline: fetch signals, apply gatekeeper, post lightweight alerts
    with "Run Committee" button (committee runs on-demand, not here).
    """
    cfg = load_openclaw_config()
    env_file = load_env_file(OPENCLAW_ENV_FILE)

    api_url = pick_env("PANDORA_API_URL", cfg, env_file) or DEFAULT_PANDORA_API_URL
    api_key = pick_env("PIVOT_API_KEY", cfg, env_file)
    if not api_key:
        raise RuntimeError("PIVOT_API_KEY is required")

    discord_token = load_discord_token(cfg, env_file)

    # Rotate logs and expire stale recommendations
    rotate_log_if_needed(DECISION_LOG)
    rotate_log_if_needed(COMMITTEE_LOG)
    expire_stale_recommendations()

    # Fetch signals
    signals = fetch_signals(api_url=api_url, api_key=api_key)

    # Load state
    seen_ids = load_seen_ids()
    seen_set = set(seen_ids)
    daily = load_daily_count()

    # Get bias for Gatekeeper
    bias_level = "NEUTRAL"
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        composite = http_json(url=f"{api_url.rstrip('/')}/bias/composite", headers=headers, timeout=30)
        bias_level = composite.get("bias_level", "NEUTRAL") if isinstance(composite, dict) else "NEUTRAL"
    except Exception:
        pass

    defcon = parse_defcon_from_session_state()

    summary = {
        "ok": True,
        "signals_fetched": len(signals),
        "new_signals": 0,
        "signals_posted": 0,
        "filtered": 0,
        "whale_requests": 0,
        "circuit_breakers": 0,
        "zone_shifts": 0,
    }

    for signal in signals:
        signal_id = str(signal.get("signal_id") or "").strip()
        if not signal_id:
            continue
        if signal_id in seen_set:
            continue

        summary["new_signals"] += 1
        seen_ids.append(signal_id)
        seen_set.add(signal_id)

        # Route signal
        route = classify_signal_source(signal)

        if route == "zone":
            save_zone_shift(signal)
            summary["zone_shifts"] += 1
            continue

        if route == "circuit_breaker":
            save_circuit_breaker(signal)
            msg = format_circuit_breaker_message(signal)
            if not dry_run:
                post_discord_message(discord_token, channel_id, msg)
            else:
                print(f"[DRY RUN] CB: {msg[:100]}...")
            log_committee_event({
                "timestamp": now_utc().isoformat(),
                "signal_id": signal_id,
                "ticker": signal.get("ticker"),
                "route": "circuit_breaker",
                "committee_ran": False,
            })
            summary["circuit_breakers"] += 1
            continue

        if route == "whale":
            msg = format_whale_message(signal)
            if not dry_run:
                post_discord_message(discord_token, channel_id, msg)
            else:
                print(f"[DRY RUN] Whale: {msg[:100]}...")
            log_committee_event({
                "timestamp": now_utc().isoformat(),
                "signal_id": signal_id,
                "ticker": signal.get("ticker"),
                "route": "whale_hunter",
                "status": "AWAITING_UW_CONFIRM",
                "committee_ran": False,
            })
            summary["whale_requests"] += 1
            continue

        # route == "committee" — run Gatekeeper
        passed, reason = gatekeeper(signal, bias_level, defcon, daily)

        if not passed:
            log_committee_event({
                "timestamp": now_utc().isoformat(),
                "signal_id": signal_id,
                "ticker": signal.get("ticker"),
                "direction": signal.get("direction"),
                "strategy": signal.get("strategy"),
                "score": safe_float(signal.get("score")),
                "gatekeeper_result": "FILTERED",
                "gatekeeper_reason": reason,
                "committee_ran": False,
            })
            summary["filtered"] += 1
            continue

        # ── Signal passed Gatekeeper — post lightweight alert with Run Committee button ──
        context = build_market_context(signal, api_url, api_key)
        gatekeeper_report = build_gatekeeper_report(signal, bias_level, defcon, daily, context)

        # Save signal for on-demand committee run
        save_pending_signal(signal_id, signal, context)

        # Build lightweight signal alert embed
        ticker = str(signal.get("ticker") or "???")
        direction_display = str(signal.get("direction") or "???").upper()
        score = signal.get("score", "N/A")
        strategy = signal.get("strategy", signal.get("signal_type", "N/A"))

        alert_embed = {
            "title": f"\U0001f4e1 Signal: {ticker} {direction_display}",
            "description": f"**Strategy:** {strategy}\n**Score:** {score}\n**Bias:** {bias_level}",
            "color": 0x5865F2,  # Discord blurple
            "timestamp": now_utc().isoformat(),
            "fields": [],
            "footer": {"text": f"Signal ID: {signal_id}"},
        }

        if gatekeeper_report:
            alert_embed["fields"].append({
                "name": "\U0001f50d Gatekeeper",
                "value": truncate(gatekeeper_report, 1024),
                "inline": False,
            })

        # Timeframe alignment badge
        tf_fit = _compute_timeframe_fit(direction_display, context)
        if tf_fit:
            alert_embed["fields"].append({
                "name": "Timeframe Fit",
                "value": tf_fit,
                "inline": True,
            })

        # Run Committee button
        run_committee_button = [
            {
                "type": 1,  # Action Row
                "components": [
                    {
                        "type": 2,  # Button
                        "style": 1,  # Blurple
                        "label": "Run Committee",
                        "custom_id": f"committee_run_{signal_id}",
                        "emoji": {"name": "\U0001f52c"},
                    },
                ],
            }
        ]

        if not dry_run:
            post_discord_embed(discord_token, channel_id, alert_embed, components=run_committee_button)
        else:
            print(f"[DRY RUN] Signal alert: {ticker} {direction_display} (score: {score})")

        # Update daily count + dedup
        daily["count"] = daily.get("count", 0) + 1
        dedup_key = get_dedup_key(signal)
        daily.setdefault("dedup_keys", []).append(dedup_key)

        log_committee_event({
            "timestamp": now_utc().isoformat(),
            "signal_id": signal_id,
            "ticker": signal.get("ticker"),
            "direction": signal.get("direction"),
            "strategy": signal.get("strategy"),
            "score": safe_float(signal.get("score")),
            "gatekeeper_result": "PASS",
            "bias_level": bias_level,
            "defcon": defcon,
            "earnings_proximity": context["earnings"],
            "committee_ran": False,
            "status": "AWAITING_COMMITTEE_RUN",
        })

        summary["signals_posted"] += 1

    # Save state
    save_seen_ids(seen_ids)
    save_daily_count(daily)

    return summary


# ── CLI ──────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="Pivot II Trading Team Pipeline")
    parser.add_argument("--channel-id", default=DEFAULT_CHANNEL_ID)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    args = parse_args()
    try:
        result = run(channel_id=args.channel_id, dry_run=args.dry_run)
        print(json.dumps(result, indent=2))
        return 0
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            pass
        err = {"ok": False, "error": f"HTTP {e.code}: {e.reason}", "body": err_body[:1200]}
        print(json.dumps(err, ensure_ascii=False))
        return 1
    except Exception as e:
        log.exception("Pipeline failed")
        err = {"ok": False, "error": str(e)}
        print(json.dumps(err, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
