#!/usr/bin/env python3
"""
pivot2_twitter.py — Twitter/X sentiment aggregator for Pivot II
Polls followed accounts, scores sentiment, pushes to Pandora API as bias factor.
Run via cron every 15-30 minutes during market hours.
"""
from __future__ import annotations

import json
import os
import subprocess
import datetime as dt
import urllib.request


def _load_openclaw_env() -> dict:
    config_path = "/home/openclaw/.openclaw/openclaw.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        env = data.get("env")
        return env if isinstance(env, dict) else {}
    except Exception:
        return {}


_CONFIG_ENV = _load_openclaw_env()

# ── Config ───────────────────────────────────────────────────────────────────

BIRD_BIN = os.path.expanduser("~/.local/bin/bird")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
PANDORA_API_URL = (
    os.environ.get("PANDORA_API_URL")
    or _CONFIG_ENV.get("PANDORA_API_URL")
    or "https://pandoras-box-production.up.railway.app/api"
).rstrip("/")
PIVOT_API_KEY = os.environ.get("PIVOT_API_KEY") or _CONFIG_ENV.get("PIVOT_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY") or _CONFIG_ENV.get("ANTHROPIC_API_KEY", "")
AUTH_TOKEN = os.environ.get("AUTH_TOKEN") or _CONFIG_ENV.get("AUTH_TOKEN", "")
CT0 = os.environ.get("CT0") or _CONFIG_ENV.get("CT0", "")

LOOKBACK_MINUTES = 30

# Account list with categories and signal weights
ACCOUNTS = {
    # Flow / options — highest signal weight
    "unusual_whales":  {"category": "flow",   "weight": 1.0},
    "CheddarFlow":     {"category": "flow",   "weight": 0.9},
    "Mr_Derivatives":  {"category": "flow",   "weight": 0.8},

    # Macro / breaking news
    "DeItaone":        {"category": "macro",  "weight": 1.0},
    "KobeissiLetter":  {"category": "macro",  "weight": 0.9},
    "financialjuice":  {"category": "macro",  "weight": 0.9},
    "StockMKTNewz":    {"category": "macro",  "weight": 0.7},
    "Investingcom":    {"category": "macro",  "weight": 0.6},
    "StockSavvyShay":  {"category": "macro",  "weight": 0.6},
    "IncomeSharks":    {"category": "macro",  "weight": 0.5},
    "financedystop":   {"category": "macro",  "weight": 0.4},

    # Political / policy risk (can move markets fast)
    "elonmusk":        {"category": "policy", "weight": 0.8},
    "DonaldJTrumpJr":  {"category": "policy", "weight": 0.6},

    # Tech / AI sentiment
    "ycombinator":     {"category": "tech",   "weight": 0.6},
    "TrendSpider":     {"category": "tech",   "weight": 0.4},

    # General news (lower weight, higher noise)
    "BBCWorld":        {"category": "news",   "weight": 0.3},
    "CNN":             {"category": "news",   "weight": 0.3},
    "ABC":             {"category": "news",   "weight": 0.3},
    "FoxNews":         {"category": "news",   "weight": 0.2},

    # Strategy mentors — highest priority (Nick's primary influences)
    "TheFlowHorse":    {"category": "strategy", "weight": 1.0},  # Ryan Scott / The Stable founder
    "LindaRaschke":    {"category": "strategy", "weight": 1.0},  # Legendary technical trader

    # Thematic equity / macro research
    "Citrini7":        {"category": "macro",    "weight": 0.9},  # Citrini Research — megatrend baskets, global macro

    # Macro / sentiment data
    "sentimentrader":  {"category": "macro",  "weight": 0.9},  # Data-driven sentiment analytics
    "LizAnnSonders":   {"category": "macro",  "weight": 0.8},  # Schwab chief investment strategist
    "RayDalio":        {"category": "macro",  "weight": 0.7},  # Bridgewater macro framework
    "TheCompoundNews": {"category": "macro",  "weight": 0.6},  # Finance/markets commentary
    "syouth1":         {"category": "macro",  "weight": 0.4},  # Morningstar / CFA analysis

    # Lower priority / context only
    "realEstateTrent": {"category": "other",  "weight": 0.2},
    "money_cruncher":  {"category": "other",  "weight": 0.1},
    "instablog9ja":    {"category": "other",  "weight": 0.0},  # Nigeria news, not market-relevant
}

# Keywords that trigger an immediate Pandora alert regardless of score
ALERT_KEYWORDS = [
    "fed ", "fomc", "rate cut", "rate hike", "emergency", "circuit breaker",
    "halt", "black swan", "crash", "collapse", "recession", "default",
    "tariff", "sanction", "war", "attack", "explosion", "breaking",
    "powell", "yellen", "treasury", "cpi", "ppi", "nfp", "jobs report",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def run_bird(args: list[str]) -> list[dict]:
    env = os.environ.copy()
    env["AUTH_TOKEN"] = AUTH_TOKEN
    env["CT0"] = CT0
    try:
        result = subprocess.run(
            [BIRD_BIN, "--plain"] + args + ["--json"],
            capture_output=True, text=True, timeout=30, env=env
        )
        if result.returncode != 0:
            return []
        # [info]/[warn] lines go to stderr; stdout should be clean JSON
        return json.loads(result.stdout)
    except Exception:
        return []


def http_post(url: str, headers: dict, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url=url, method="POST", headers=headers, data=body)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_tweet_ts(raw_ts: str) -> "dt.datetime | None":
    for fmt in ("%a %b %d %H:%M:%S %z %Y", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return dt.datetime.strptime(raw_ts, fmt)
        except Exception:
            pass
    try:
        return dt.datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
    except Exception:
        return None


def filter_recent(tweets: list[dict], lookback_minutes: int) -> list[str]:
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=lookback_minutes)
    recent = []
    for t in tweets:
        raw_ts = t.get("timestamp") or t.get("createdAt") or ""
        ts = parse_tweet_ts(raw_ts)
        if ts and ts >= cutoff:
            text = t.get("text") or t.get("fullText") or ""
            if text:
                recent.append(text[:280])
    return recent


def fetch_recent_tweets(username: str, lookback_minutes: int) -> list[str]:
    tweets = run_bird(["user-tweets", username, "-n", "20"])
    if not tweets:
        return []
    return filter_recent(tweets, lookback_minutes)


def fetch_home_timeline(lookback_minutes: int) -> dict[str, list[str]]:
    """Fetch home timeline and bucket tweets by tracked username."""
    tweets = run_bird(["home", "-n", "200"])
    if not tweets:
        return {}
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=lookback_minutes)
    by_user: dict[str, list[str]] = {}
    tracked_lower = {k.lower(): k for k in ACCOUNTS}
    for t in tweets:
        raw_ts = t.get("timestamp") or t.get("createdAt") or ""
        ts = parse_tweet_ts(raw_ts)
        if not ts or ts < cutoff:
            continue
        author = (t.get("author") or {}).get("username", "")
        canonical = tracked_lower.get(author.lower())
        if not canonical:
            continue
        text = t.get("text") or t.get("fullText") or ""
        if text:
            by_user.setdefault(canonical, []).append(text[:280])
    return by_user


def score_tweets_with_llm(tweets: list[str], username: str, category: str) -> dict:
    if not tweets or not ANTHROPIC_API_KEY:
        return {"score": 0.0, "signal": "NEUTRAL", "summary": "no data", "tickers": [], "alert": False}

    combined = "\n---\n".join(tweets[:10])
    prompt = f"""You are a trading sentiment scorer. Analyze these recent tweets from @{username} (category: {category}).

Tweets:
{combined}

Return JSON only, no markdown:
{{
  "score": <float -1.0 to 1.0, where -1=very bearish, 0=neutral, 1=very bullish>,
  "signal": <"URSA_MAJOR"|"URSA_MINOR"|"NEUTRAL"|"TORO_MINOR"|"TORO_MAJOR">,
  "summary": <one sentence max 100 chars>,
  "tickers": <list of mentioned stock tickers e.g. ["SPY","AAPL"], empty if none>,
  "alert": <true if contains breaking market-moving news, else false>
}}"""

    headers = {
        "x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 200,
        "temperature": 0.1,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        resp = http_post(ANTHROPIC_URL, headers, payload)
        content = "".join(b.get("text","") for b in resp.get("content",[]) if b.get("type")=="text").strip()
        # Strip markdown code fences
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        # Extract just the JSON object (ignore trailing text)
        brace_start = content.find("{")
        brace_end = content.rfind("}") + 1
        if brace_start != -1 and brace_end > brace_start:
            content = content[brace_start:brace_end]
        return json.loads(content.strip())
    except Exception:
        return {"score": 0.0, "signal": "NEUTRAL", "summary": "parse error", "tickers": [], "alert": False}


def score_to_signal(score: float) -> str:
    if score <= -0.6:  return "URSA_MAJOR"
    if score <= -0.2:  return "URSA_MINOR"
    if score >= 0.6:   return "TORO_MAJOR"
    if score >= 0.2:   return "TORO_MINOR"
    return "NEUTRAL"


def has_alert_keyword(tweets: list[str]) -> bool:
    combined = " ".join(tweets).lower()
    return any(kw in combined for kw in ALERT_KEYWORDS)


def push_factor(score: float, signal: str, detail: str, raw: dict) -> bool:
    headers = {"Authorization": f"Bearer {PIVOT_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "factor_id": "twitter_sentiment",
        "score": round(score, 4),
        "signal": signal,
        "detail": detail,
        "source": "twitter/bird",
        "raw_data": raw,
    }
    try:
        http_post(f"{PANDORA_API_URL}/bias/factor-update", headers, payload)
        return True
    except Exception:
        return False


def push_flow(ticker: str, sentiment: str, notes: str) -> bool:
    headers = {"Authorization": f"Bearer {PIVOT_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "ticker": ticker,
        "sentiment": sentiment,
        "flow_type": "TWITTER_MENTION",
        "premium": 0,
        "notes": notes[:200],
    }
    try:
        http_post(f"{PANDORA_API_URL}/flow/manual", headers, payload)
        return True
    except Exception:
        return False


def push_alert(message: str, data: dict) -> bool:
    headers = {"Authorization": f"Bearer {PIVOT_API_KEY}", "Content-Type": "application/json"}
    payload = {"type": "twitter_breaking", "message": message, "data": data}
    try:
        http_post(f"{PANDORA_API_URL}/alerts/pivot", headers, payload)
        return True
    except Exception:
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def check_tweet_for_theme(tweet_text: str, author: str, tweet_url: str = None):
    """
    Check if a scored tweet summary matches the active regime's theme keywords.
    If it does, store it in Redis via the Railway API for frontend display.
    """
    try:
        req = urllib.request.Request(
            f"{PANDORA_API_URL}/regime/current",
            headers={"X-API-Key": PIVOT_API_KEY},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            regime = json.loads(resp.read().decode())

        keywords = regime.get("theme_keywords", [])
        if not keywords:
            return False

        text_lower = tweet_text.lower()
        matched_keywords = [kw for kw in keywords if kw.lower() in text_lower]
        if not matched_keywords:
            return False

        hit = json.dumps({
            "text": tweet_text[:500],
            "author": author,
            "url": tweet_url,
            "matched_keywords": matched_keywords,
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        }).encode()

        req2 = urllib.request.Request(
            f"{PANDORA_API_URL}/regime/theme-hit",
            data=hit,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": PIVOT_API_KEY,
            },
            method="POST",
        )
        with urllib.request.urlopen(req2, timeout=10) as resp2:
            if resp2.status == 200:
                print(f"  Theme hit stored: @{author} matched {matched_keywords}")
                return True
    except Exception as e:
        # Non-critical — don't break the main scoring flow
        pass
    return False


def main():
    results = []
    alerts = []
    ticker_mentions: dict[str, list] = {}

    active_accounts = {k: v for k, v in ACCOUNTS.items() if v["weight"] > 0}

    # Pull home timeline once — catches accounts whose per-user fetch fails (e.g. Linda)
    home_tweets = fetch_home_timeline(LOOKBACK_MINUTES)

    for username, meta in active_accounts.items():
        # Merge per-account fetch + home timeline (deduplicate by content)
        direct = fetch_recent_tweets(username, LOOKBACK_MINUTES)
        from_home = home_tweets.get(username, [])
        seen = set(direct)
        merged = direct + [t for t in from_home if t not in seen]
        tweets = merged
        if not tweets:
            continue

        scored = score_tweets_with_llm(tweets, username, meta["category"])
        weighted_score = scored.get("score", 0.0) * meta["weight"]

        results.append({
            "username": username,
            "category": meta["category"],
            "weight": meta["weight"],
            "raw_score": scored.get("score", 0.0),
            "weighted_score": weighted_score,
            "signal": scored.get("signal", "NEUTRAL"),
            "summary": scored.get("summary", ""),
            "tickers": scored.get("tickers", []),
            "alert": scored.get("alert", False),
            "tweet_count": len(tweets),
        })

        for ticker in scored.get("tickers", []):
            if len(ticker) <= 5 and ticker.isalpha():
                ticker_mentions.setdefault(ticker, []).append({
                    "username": username,
                    "score": scored.get("score", 0.0),
                    "summary": scored.get("summary", ""),
                })

        if scored.get("alert") or has_alert_keyword(tweets):
            alerts.append(f"@{username}: {scored.get('summary', tweets[0][:100])}")

        # Check for regime theme keyword matches (5D)
        summary_text = scored.get("summary", "")
        combined_text = summary_text + " " + " ".join(tweets[:3])
        check_tweet_for_theme(combined_text, username)

    # After scoring loop, log signals for post-mortem correlation.
    signal_log_path = "/opt/openclaw/workspace/data/twitter_signals.jsonl"
    os.makedirs(os.path.dirname(signal_log_path), exist_ok=True)
    for r in results:
        if abs(r.get("raw_score", 0.0)) >= 0.3 and r.get("tickers"):
            entry = {
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
                "username": r.get("username"),
                "category": r.get("category"),
                "score": r.get("raw_score"),
                "signal": r.get("signal"),
                "summary": r.get("summary"),
                "tickers": r.get("tickers"),
            }
            try:
                from safe_jsonl import safe_append
                from pathlib import Path
                safe_append(Path(signal_log_path), entry)
            except Exception:
                pass

    if not results:
        print(json.dumps({"ok": True, "message": "no recent tweets in window", "factor_pushed": False}))
        return

    # Weighted composite score
    total_weight = sum(r["weight"] for r in results)
    composite = sum(r["weighted_score"] for r in results) / total_weight if total_weight > 0 else 0.0
    composite = max(-1.0, min(1.0, composite))
    signal = score_to_signal(composite)

    top = sorted(results, key=lambda x: abs(x["raw_score"]), reverse=True)[:3]
    top_str = " | ".join(f"@{r['username']}: {r['summary']}" for r in top)
    detail = f"Twitter ({len(results)} accts, {LOOKBACK_MINUTES}m). {top_str}"[:500]

    raw_data = {
        "accounts_scored": len(results),
        "lookback_minutes": LOOKBACK_MINUTES,
        "composite_raw": composite,
        "breakdown": [
            {"username": r["username"], "category": r["category"],
             "score": r["raw_score"], "signal": r["signal"], "summary": r["summary"]}
            for r in results
        ],
    }

    push_factor(composite, signal, detail, raw_data)

    for ticker, mentions in ticker_mentions.items():
        avg = sum(m["score"] for m in mentions) / len(mentions)
        sentiment = "BULLISH" if avg > 0.1 else "BEARISH" if avg < -0.1 else "NEUTRAL"
        sources = ", ".join(f"@{m['username']}" for m in mentions[:3])
        push_flow(ticker, sentiment, f"Twitter ({sources}): avg {avg:.2f}")

    for msg in alerts[:3]:
        push_alert(f"TWITTER ALERT: {msg}", {"source": "pivot2_twitter"})

    print(json.dumps({
        "ok": True,
        "composite_score": round(composite, 4),
        "signal": signal,
        "accounts_scored": len(results),
        "alerts_fired": len(alerts),
        "ticker_mentions": list(ticker_mentions.keys()),
        "top_signals": [{"username": r["username"], "score": r["raw_score"], "summary": r["summary"]} for r in top],
    }, indent=2))


if __name__ == "__main__":
    main()
