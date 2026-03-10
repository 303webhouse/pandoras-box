#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DISCORD_API_BASE = "https://discord.com/api/v10"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
DEFAULT_PANDORA_API_URL = "https://pandoras-box-production.up.railway.app/api"
DEFAULT_CHANNEL_ID = "1474135100521451813"
MAX_IMAGE_COUNT = 6

FACTOR_META = {
    # Intraday (fast-moving, 4-8h staleness)
    "vix_term":            {"staleness_hours": 4,    "weight": 0.07, "timeframe": "intraday", "label": "VIX Term Structure"},
    "tick_breadth":        {"staleness_hours": 4,    "weight": 0.06, "timeframe": "intraday", "label": "TICK Breadth"},
    "vix_regime":          {"staleness_hours": 4,    "weight": 0.05, "timeframe": "intraday", "label": "VIX Regime"},
    "spy_trend_intraday":  {"staleness_hours": 4,    "weight": 0.05, "timeframe": "intraday", "label": "SPY Intraday Trend"},
    "breadth_momentum":    {"staleness_hours": 24,   "weight": 0.04, "timeframe": "intraday", "label": "Breadth Momentum"},
    "options_sentiment":   {"staleness_hours": 8,    "weight": 0.03, "timeframe": "intraday", "label": "Options Sentiment (UW)"},
    # Swing (multi-day, 24-72h staleness)
    "credit_spreads":      {"staleness_hours": 48,   "weight": 0.09, "timeframe": "swing",    "label": "Credit Spreads"},
    "market_breadth":      {"staleness_hours": 48,   "weight": 0.09, "timeframe": "swing",    "label": "Market Breadth"},
    "sector_rotation":     {"staleness_hours": 48,   "weight": 0.07, "timeframe": "swing",    "label": "Sector Rotation"},
    "spy_200sma_distance": {"staleness_hours": 24,   "weight": 0.07, "timeframe": "swing",    "label": "SPY 200 SMA Distance"},
    "high_yield_oas":      {"staleness_hours": 48,   "weight": 0.05, "timeframe": "swing",    "label": "High Yield OAS"},
    "dollar_smile":        {"staleness_hours": 48,   "weight": 0.04, "timeframe": "swing",    "label": "Dollar Smile"},
    "put_call_ratio":      {"staleness_hours": 72,   "weight": 0.04, "timeframe": "swing",    "label": "Put/Call Ratio"},
    # Macro (slow-moving, 48-1080h staleness)
    "yield_curve":         {"staleness_hours": 72,   "weight": 0.05, "timeframe": "macro",    "label": "Yield Curve"},
    "initial_claims":      {"staleness_hours": 168,  "weight": 0.05, "timeframe": "macro",    "label": "Initial Claims"},
    "sahm_rule":           {"staleness_hours": 168,  "weight": 0.04, "timeframe": "macro",    "label": "Sahm Rule"},
    "copper_gold_ratio":   {"staleness_hours": 48,   "weight": 0.03, "timeframe": "macro",    "label": "Copper/Gold Ratio"},
    "dxy_trend":           {"staleness_hours": 48,   "weight": 0.05, "timeframe": "macro",    "label": "DXY Trend"},
    "excess_cape":         {"staleness_hours": 168,  "weight": 0.03, "timeframe": "macro",    "label": "Excess CAPE Yield"},
    "ism_manufacturing":   {"staleness_hours": 720,  "weight": 0.03, "timeframe": "macro",    "label": "ISM Manufacturing"},
    "savita":              {"staleness_hours": 1080, "weight": 0.02, "timeframe": "macro",    "label": "BofA Sell Side (Savita)"},
}


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_iso_ts(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.timezone.utc)


def http_json(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | list[Any] | None = None,
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


def chunk_text(text: str, max_len: int = 1900) -> list[str]:
    text = (text or "").strip()
    if not text:
        return ["(empty brief)"]
    if len(text) <= max_len:
        return [text]

    out: list[str] = []
    remaining = text
    while len(remaining) > max_len:
        split_at = remaining.rfind("\n\n", 0, max_len)
        if split_at < max_len // 2:
            split_at = remaining.rfind("\n", 0, max_len)
        if split_at < max_len // 2:
            split_at = remaining.rfind(" ", 0, max_len)
        if split_at < max_len // 2:
            split_at = max_len
        out.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        out.append(remaining)
    return out


def load_discord_token() -> str:
    env_token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if env_token:
        return env_token

    state_dir = pathlib.Path(os.environ.get("OPENCLAW_STATE_DIR", "/home/openclaw/.openclaw"))
    cfg_path = state_dir / "openclaw.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        token = (((cfg.get("channels") or {}).get("discord") or {}).get("token") or "").strip()
        if token:
            return token
    except Exception:
        pass

    raise RuntimeError("Discord token not found. Set DISCORD_BOT_TOKEN or channels.discord.token in openclaw.json")


def load_persona_context(workspace: pathlib.Path) -> str:
    sections: list[str] = []
    for name in ["AGENTS.md", "SOUL.md", "IDENTITY.md", "USER.md"]:
        p = workspace / name
        if not p.exists():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            continue
        if text:
            sections.append(f"[{name}]\n{text}")

    if not sections:
        return "You are Pivot II, a trading analyst bot."

    return (
        "You are Pivot II. Follow the persona and operating rules below exactly. "
        "Be concise, specific, and actionable.\n\n" + "\n\n".join(sections)
    )


def discord_get_recent_images(token: str, channel_id: str, window_minutes: int) -> tuple[str, list[dict[str, Any]]]:
    since = now_utc() - dt.timedelta(minutes=window_minutes)
    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": "Pivot-II/1.0",
    }

    all_messages: list[dict[str, Any]] = []
    before_id: str | None = None

    for _ in range(5):
        url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages?limit=100"
        if before_id:
            url += "&before=" + urllib.parse.quote(before_id)

        batch = http_json(url=url, headers=headers, timeout=25)
        if not isinstance(batch, list) or not batch:
            break

        all_messages.extend(batch)
        before_id = str(batch[-1].get("id"))

        oldest_raw = batch[-1].get("timestamp")
        if isinstance(oldest_raw, str):
            try:
                if parse_iso_ts(oldest_raw) <= since:
                    break
            except Exception:
                pass

    images: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for msg in all_messages:
        raw_ts = msg.get("timestamp")
        if not isinstance(raw_ts, str):
            continue

        try:
            msg_ts = parse_iso_ts(raw_ts)
        except Exception:
            continue

        if msg_ts < since:
            continue

        author = msg.get("author") or {}
        if bool(author.get("bot")):
            continue

        for att in msg.get("attachments") or []:
            content_type = str(att.get("content_type") or "").lower()
            filename = str(att.get("filename") or "").lower()
            url = str(att.get("url") or att.get("proxy_url") or "").strip()
            if not url:
                continue

            is_image = content_type.startswith("image/") or filename.endswith(
                (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff")
            )
            if not is_image or url in seen_urls:
                continue

            seen_urls.add(url)
            images.append(
                {
                    "message_id": msg.get("id"),
                    "author_id": author.get("id"),
                    "author_name": author.get("username"),
                    "timestamp": raw_ts,
                    "url": url,
                    "filename": att.get("filename"),
                }
            )

    images.sort(key=lambda item: str(item.get("timestamp") or ""))
    return since.isoformat(), images


def discord_post_chunks(token: str, channel_id: str, text: str) -> list[str]:
    ids: list[str] = []
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
        "User-Agent": "Pivot-II/1.0",
    }

    for chunk in chunk_text(text):
        sent = http_json(url=url, method="POST", headers=headers, payload={"content": chunk}, timeout=25)
        if isinstance(sent, dict) and sent.get("id"):
            ids.append(str(sent["id"]))
    return ids


def fetch_pandora_data(mode: str, api_url: str, api_key: str) -> dict[str, Any]:
    base = api_url.rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}"}

    composite = http_json(url=f"{base}/bias/composite", headers=headers, timeout=30)
    payload: dict[str, Any] = {"composite": composite}

    if mode == "eod":
        payload["convergence"] = http_json(
            url=f"{base}/analytics/convergence-stats?days=1&min_sources=2", headers=headers, timeout=30
        )
        payload["uw_snapshots_api"] = http_json(
            url=f"{base}/analytics/uw-snapshots?days=1", headers=headers, timeout=30
        )

        factors = (composite or {}).get("factors") if isinstance(composite, dict) else {}
        if not isinstance(factors, dict):
            factors = {}

        stale_list = (composite or {}).get("stale_factors") if isinstance(composite, dict) else []
        if not isinstance(stale_list, list):
            stale_list = []
        stale_set = set(str(s) for s in stale_list if isinstance(s, str))

        unverifiable_list = (composite or {}).get("unverifiable_factors") if isinstance(composite, dict) else []
        if not isinstance(unverifiable_list, list):
            unverifiable_list = []
        unverifiable_set = set(str(s) for s in unverifiable_list if isinstance(s, str))

        now = now_utc()
        factor_details = []
        for fid, meta in FACTOR_META.items():
            entry = {
                "factor_id": fid,
                "label": meta["label"],
                "timeframe": meta["timeframe"],
                "weight": meta["weight"],
                "staleness_hours": meta["staleness_hours"],
            }

            factor_data = factors.get(fid)
            if factor_data is None or fid in stale_set:
                entry["status"] = "STALE"
                entry["age_hours"] = None
                entry["source"] = None
            elif fid in unverifiable_set:
                entry["status"] = "FALLBACK"
                entry["age_hours"] = 0
                entry["source"] = "fallback"
            else:
                ts_raw = factor_data.get("timestamp") if isinstance(factor_data, dict) else None
                age_hours = None
                if ts_raw and isinstance(ts_raw, str):
                    try:
                        factor_ts = parse_iso_ts(ts_raw)
                        age_hours = round((now - factor_ts).total_seconds() / 3600, 1)
                    except Exception:
                        pass

                source = factor_data.get("source", "unknown") if isinstance(factor_data, dict) else "unknown"
                entry["status"] = "FRESH"
                entry["age_hours"] = age_hours
                entry["source"] = source

            factor_details.append(entry)

        timeframe_health = {}
        for tf in ("intraday", "swing", "macro"):
            tf_factors = [f for f in factor_details if f["timeframe"] == tf]
            timeframe_health[tf] = {
                "fresh": sum(1 for f in tf_factors if f["status"] == "FRESH"),
                "fallback": sum(1 for f in tf_factors if f["status"] == "FALLBACK"),
                "stale": sum(1 for f in tf_factors if f["status"] == "STALE"),
                "total": len(tf_factors),
                "total_weight": round(sum(f["weight"] for f in tf_factors), 2),
                "active_weight": round(sum(f["weight"] for f in tf_factors if f["status"] in ("FRESH", "FALLBACK")), 2),
            }

        payload["factor_health"] = {
            "summary": {
                "fresh": sum(1 for f in factor_details if f["status"] == "FRESH"),
                "fallback": sum(1 for f in factor_details if f["status"] == "FALLBACK"),
                "stale": sum(1 for f in factor_details if f["status"] == "STALE"),
                "total": len(FACTOR_META),
                "confidence": (composite or {}).get("confidence", "UNKNOWN"),
            },
            "by_timeframe": timeframe_health,
            "factors": factor_details,
        }

    return payload


def build_prompt(mode: str, data_payload: dict[str, Any], image_rows: list[dict[str, Any]], window_start_iso: str) -> str:
    image_meta = [
        {
            "author_name": row.get("author_name"),
            "timestamp": row.get("timestamp"),
            "filename": row.get("filename"),
            "url": row.get("url"),
        }
        for row in image_rows
    ]

    if mode == "morning":
        instructions = (
            "Generate the morning brief. Follow the format from your identity/personality context.\n\n"
            "ONE-LINE bias summary first. Then:\n"
            "- Overnight developments (2-3 bullets, concise)\n"
            "- Factor snapshot (all factors with scores and one-line reads)\n"
            "- DEFCON status (Green/Yellow/Orange/Red + any active triggers)\n"
            "- Open positions across all 3 accounts if data available\n"
            "- Breakout account status (balance, HWM, room to floors)\n"
            "- Key catalysts today (from economic/earnings calendars)\n"
            "- Trading implications (1-2 sentences, account-specific)\n\n"
            "If UW screenshots were provided, include:\n"
            "- Market Tide read (bullish/bearish/neutral flow)\n"
            "- Dark Pool positioning\n"
            "- Notable unusual activity\n\n"
            "If any factor data is stale or missing, flag it.\n"
            "If any factor conflicts exist, highlight them.\n"
            "If no UW data was provided, include exactly: \"WARNING: No UW visual data provided - flow analysis unavailable.\"\n"
        )
    else:
        instructions = (
            "Generate the EOD summary. Follow the format from your identity/personality context.\n\n"
            "Lead with the day verdict: did the bias call play out?\n\n"
            "FACTOR HEALTH section (use data.factor_health):\n"
            "- Summary line: X/Y factors fresh, Z on fallback, W stale | Confidence: {confidence}\n"
            "- If summary.stale > 5: 'WARNING: Low data confidence - too many stale factors.'\n"
            "- Group by timeframe (intraday, swing, macro). For each group show:\n"
            "  - How many fresh vs stale vs fallback\n"
            "  - Call out any factor with status STALE and weight >= 0.05 as a blind spot\n"
            "  - Call out FALLBACK factors as 'scoring neutral but unverified'\n"
            "- If any FRESH factor has age_hours > staleness_hours * 0.75, flag it as 'aging'\n"
            "- End with a one-line data quality verdict: 'Data quality: GOOD/DEGRADED/POOR'\n"
            "  - GOOD: <=3 stale, no high-weight blind spots\n"
            "  - DEGRADED: 4-7 stale or 1+ high-weight blind spot\n"
            "  - POOR: 8+ stale or confidence LOW\n\n"
            "Signal Convergence section (last 24h):\n"
            "  - 'CONVERGENCE: {ticker} {direction} - confirmed by {source1}, {source2}'\n"
            "  - 2 sources = MODERATE, 3+ = HIGH\n"
            "  - If none: 'No signal convergence detected today.'\n\n"
            "UW Flow Intelligence from screenshots if provided:\n"
            "  - Market Tide read, Dark Pool positioning, GEX analysis\n"
            "  - If no screenshots: 'UW visual data not provided - flow analysis based on API data only.'\n\n"
            "Remaining sections:\n"
            "- Factor changes during session (what moved, what did not)\n"
            "- DEFCON events today\n"
            "- Notable flow activity\n"
            "- P&L across accounts if data available\n"
            "- Breakout account end-of-day status\n"
            "- Lessons or patterns worth noting\n"
            "- Setup for tomorrow (overnight bias lean)\n"
        )

    combined = {
        "window_start_utc": window_start_iso,
        "discord_images": image_meta,
        "data": data_payload,
    }

    return f"{instructions}\nDATA:\n{json.dumps(combined, indent=2)}"


def call_anthropic(
    api_key: str, model: str, system_prompt: str,
    user_prompt: str, image_rows: list[dict[str, Any]],
) -> str:
    content = [{"type": "text", "text": user_prompt}]
    for row in image_rows[:MAX_IMAGE_COUNT]:
        url = str(row.get("url") or "").strip()
        if url:
            content.append({"type": "image", "source": {"type": "url", "url": url}})
    payload = {
        "model": model, "temperature": 0.2, "max_tokens": 1800,
        "system": system_prompt,
        "messages": [{"role": "user", "content": content}],
    }
    headers = {
        "x-api-key": api_key, "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    resp = http_json(url=ANTHROPIC_URL, method="POST", headers=headers, payload=payload, timeout=90)
    parts = []
    for b in (resp or {}).get("content", []):
        if isinstance(b, dict) and b.get("type") == "text":
            parts.append(b["text"])
    text = "\n".join(parts).strip()
    if not text:
        raise RuntimeError("Anthropic API returned empty content")
    return text


def build_fallback(mode: str, data_payload: dict[str, Any], had_images: bool) -> str:
    comp = data_payload.get("composite") if isinstance(data_payload, dict) else {}
    score = (comp or {}).get("composite_score") if isinstance(comp, dict) else None
    bias = (comp or {}).get("bias_level") if isinstance(comp, dict) else None

    lines = [
        f"Pivot II {mode.upper()} BRIEF (fallback mode)",
        f"Bias: {bias} | Composite score: {score}",
    ]
    if not had_images:
        lines.append("WARNING: No UW visual data provided - flow analysis unavailable.")
    lines.append("Primary generation failed, so this is a minimal fallback summary.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and post Pivot II morning/EOD brief")
    parser.add_argument("--mode", choices=["morning", "eod"], required=True)
    parser.add_argument("--channel-id", default=DEFAULT_CHANNEL_ID)
    parser.add_argument("--window-minutes", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    window_minutes = args.window_minutes
    if window_minutes <= 0:
        window_minutes = 30 if args.mode == "morning" else 15

    pandora_api_url = os.environ.get("PANDORA_API_URL", DEFAULT_PANDORA_API_URL).strip()
    pivot_api_key = os.environ.get("PIVOT_API_KEY", "").strip()
    anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL

    if not pivot_api_key:
        raise RuntimeError("PIVOT_API_KEY is missing")
    if not anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is missing")

    workspace = pathlib.Path("/opt/openclaw/workspace")
    discord_token = load_discord_token()

    window_start_iso, images = discord_get_recent_images(discord_token, args.channel_id, window_minutes)
    data_payload = fetch_pandora_data(args.mode, pandora_api_url, pivot_api_key)
    prompt = build_prompt(args.mode, data_payload, images, window_start_iso)
    system_prompt = load_persona_context(workspace)

    try:
        brief_text = call_anthropic(anthropic_api_key, model, system_prompt, prompt, images)
    except Exception:
        brief_text = build_fallback(args.mode, data_payload, had_images=bool(images))

    if args.dry_run:
        print(
            json.dumps(
                {
                    "ok": True,
                    "mode": args.mode,
                    "channel_id": args.channel_id,
                    "image_count": len(images),
                    "window_minutes": window_minutes,
                    "preview": brief_text[:800],
                }
            )
        )
        return 0

    message_ids = discord_post_chunks(discord_token, args.channel_id, brief_text)
    print(
        json.dumps(
            {
                "ok": True,
                "mode": args.mode,
                "channel_id": args.channel_id,
                "window_minutes": window_minutes,
                "image_count": len(images),
                "message_ids": message_ids,
            }
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        err_body = ""
        try:
            err_body = exc.read().decode("utf-8", errors="ignore")
        except Exception:
            pass
        print(json.dumps({"ok": False, "error": f"HTTP {exc.code}: {exc.reason}", "body": err_body[:1200]}))
        raise
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        raise
