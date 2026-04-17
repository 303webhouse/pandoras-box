#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import urllib.error
import urllib.request
from typing import Any

DEFAULT_PANDORA_API_URL = "https://pandoras-box-production.up.railway.app/api"
DEFAULT_CHANNEL_ID = "1474135100521451813"
DATA_DIR = pathlib.Path("/opt/openclaw/workspace/data")
SEEN_FILE = DATA_DIR / "seen_signal_ids.json"
ZONE_FILE = DATA_DIR / "last_zone_shift.json"
OPENCLAW_STATE_DIR = pathlib.Path(os.environ.get("OPENCLAW_STATE_DIR", "/home/openclaw/.openclaw"))
OPENCLAW_CONFIG = OPENCLAW_STATE_DIR / "openclaw.json"
OPENCLAW_ENV_FILE = pathlib.Path("/etc/openclaw/openclaw.env")
DISCORD_API_BASE = "https://discord.com/api/v10"
ZONE_RE = re.compile(r"from\s+([A-Z_]+)\s+to\s+([A-Z_]+)", re.IGNORECASE)


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


def build_zone_context(signal: dict[str, Any]) -> str:
    cta_zone = str(signal.get("cta_zone") or "UNKNOWN")
    try:
        if ZONE_FILE.exists():
            data = json.loads(ZONE_FILE.read_text(encoding="utf-8"))
            ts = parse_iso_ts(str(data.get("timestamp") or ""))
            if ts is not None:
                age_hours = (now_utc() - ts).total_seconds() / 3600.0
                if age_hours <= 6:
                    to_zone = str(data.get("to_zone") or "UNKNOWN")
                    direction = str(data.get("direction") or "UNKNOWN")
                    return f"Confirmation: Zone shifted to {to_zone} {age_hours:.1f}h ago ({direction})."
    except Exception:
        pass
    return f"Zone context: Current CTA zone is {cta_zone} (no zone shift in last 6h)."


def is_zone_signal(signal: dict[str, Any]) -> bool:
    signal_type = str(signal.get("signal_type") or "").upper()
    strategy = str(signal.get("strategy") or "").upper()
    return "ZONE" in signal_type or "ZONE" in strategy


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def compute_rr(entry: float, stop: float, target: float) -> float:
    if entry == 0 or stop == 0 or target == 0:
        return 0.0
    risk = abs(entry - stop)
    reward = abs(target - entry)
    if risk <= 0:
        return 0.0
    return reward / risk


TIER_LABELS = {
    "top_feed":  "[TOP FEED]",
    "watchlist": "[WATCHLIST]",
    "ta_feed":   "[TA FEED]",
}

TIER_COLORS = {
    "top_feed":  0xF59E0B,   # amber
    "watchlist": 0x2DD4BF,   # teal
    "ta_feed":   0x818CF8,   # indigo
}


def build_embed(signal: dict[str, Any]) -> dict[str, Any]:
    ticker = str(signal.get("ticker") or "???")
    direction = str(signal.get("direction") or "???").upper()
    score = safe_float(signal.get("score"))
    strategy = str(signal.get("strategy") or "Unknown")
    entry = safe_float(signal.get("entry_price"))
    stop = safe_float(signal.get("stop_loss"))
    target = safe_float(signal.get("target_1"))
    rr = compute_rr(entry, stop, target)
    bias_alignment = str(signal.get("bias_alignment") or "Unknown")
    signal_id = str(signal.get("signal_id") or "N/A")
    feed_tier = str(signal.get("feed_tier") or "").strip()
    zone_context_text = build_zone_context(signal)

    tier_label = TIER_LABELS.get(feed_tier, "")
    title = f"{tier_label} Trade Idea: {ticker} {direction}".strip()

    default_color = 0x00FF00 if direction == "LONG" else 0xFF0000
    color = TIER_COLORS.get(feed_tier, default_color)

    return {
        "title": title,
        "color": color,
        "fields": [
            {"name": "Score",        "value": f"{score:.0f}/100",  "inline": True},
            {"name": "Strategy",     "value": strategy,             "inline": True},
            {"name": "Direction",    "value": direction,            "inline": True},
            {"name": "Entry",        "value": f"${entry:.2f}",      "inline": True},
            {"name": "Stop",         "value": f"${stop:.2f}",       "inline": True},
            {"name": "Target",       "value": f"${target:.2f}",     "inline": True},
            {"name": "R:R",          "value": f"{rr:.1f}:1",        "inline": True},
            {"name": "Bias",         "value": bias_alignment,       "inline": True},
            {"name": "Bias Context", "value": zone_context_text,    "inline": False},
        ],
        "footer": {"text": f"Signal ID: {signal_id[:8]} | tier: {feed_tier or 'legacy'}"},
        "timestamp": now_utc().isoformat(),
    }


def post_discord_embed(token: str, channel_id: str, embed: dict[str, Any]) -> None:
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": "Pivot-II/1.0",
        "Content-Type": "application/json",
    }
    http_json(url=url, method="POST", headers=headers, payload={"embeds": [embed]}, timeout=30)


def post_discord_webhook(webhook_url: str, embed: dict[str, Any]) -> None:
    """Post an embed via a Discord incoming webhook URL (no bot token needed)."""
    payload = json.dumps({"embeds": [embed]}).encode("utf-8")
    req = urllib.request.Request(
        url=webhook_url,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "Pivot-II/1.0"},
        data=payload,
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()  # 204 No Content on success


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


def run(channel_id: str, min_score: float, dry_run: bool) -> dict[str, Any]:
    cfg = load_openclaw_config()
    env_file = load_env_file(OPENCLAW_ENV_FILE)

    api_url = pick_env("PANDORA_API_URL", cfg, env_file) or DEFAULT_PANDORA_API_URL
    api_key = pick_env("PIVOT_API_KEY", cfg, env_file)
    if not api_key:
        raise RuntimeError("PIVOT_API_KEY is required")

    discord_token = load_discord_token(cfg, env_file)

    # ZEUS Phase 3: tiered Discord routing
    zeus_flag = pick_env("ZEUS_TIERED_ROUTING", cfg, env_file)
    zeus_enabled = zeus_flag.lower() not in ("false", "0", "no") if zeus_flag else True

    tier_webhooks: dict[str, str] = {}
    if zeus_enabled:
        for tier, env_name in (
            ("top_feed",  "DISCORD_WEBHOOK_TOP_FEED"),
            ("watchlist", "DISCORD_WEBHOOK_WATCHLIST"),
            ("ta_feed",   "DISCORD_WEBHOOK_TA_FEED"),
        ):
            wh = pick_env(env_name, cfg, env_file)
            if wh:
                tier_webhooks[tier] = wh

    signals = fetch_signals(api_url=api_url, api_key=api_key)

    seen_ids = load_seen_ids()
    seen_set = set(seen_ids)

    summary: dict[str, Any] = {
        "ok": True,
        "zeus_enabled": zeus_enabled,
        "signals_fetched": len(signals),
        "new_signals": 0,
        "posted": 0,
        "skipped_zone": 0,
        "skipped_low_score": 0,
        "skipped_research_log": 0,
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

        if is_zone_signal(signal):
            summary["skipped_zone"] += 1
            save_zone_shift(signal)
            continue

        score = safe_float(signal.get("score"))
        if score < min_score:
            summary["skipped_low_score"] += 1
            continue

        feed_tier = str(signal.get("feed_tier") or "").strip()

        # ZEUS: skip research_log — noise tier, not actionable enough for Discord
        if zeus_enabled and feed_tier == "research_log":
            summary["skipped_research_log"] += 1
            continue

        embed = build_embed(signal)

        if dry_run:
            print(json.dumps({"dry_run_embed": embed, "feed_tier": feed_tier}, ensure_ascii=False))
        else:
            webhook_url = tier_webhooks.get(feed_tier, "") if zeus_enabled else ""
            if webhook_url:
                post_discord_webhook(webhook_url=webhook_url, embed=embed)
            else:
                # Fallback: legacy channel via Bot token
                post_discord_embed(token=discord_token, channel_id=channel_id, embed=embed)

        summary["posted"] += 1

    save_seen_ids(seen_ids)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pivot II trade idea poller — ZEUS Phase 3")
    parser.add_argument("--channel-id", default=DEFAULT_CHANNEL_ID)
    parser.add_argument("--min-score", type=float, default=80)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        summary = run(channel_id=args.channel_id, min_score=args.min_score, dry_run=args.dry_run)
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    except urllib.error.HTTPError as e:
        err = {"ok": False, "error": f"HTTP {e.code}", "detail": e.reason}
        print(json.dumps(err, ensure_ascii=False))
        return 1
    except Exception as e:
        err = {"ok": False, "error": str(e)}
        print(json.dumps(err, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
