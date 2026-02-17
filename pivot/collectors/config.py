"""
Pivot collector configuration.
"""

from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()


def _normalize_api_url(url: str) -> str:
    if not url:
        return ""
    url = url.strip().rstrip("/")
    if not url.endswith("/api"):
        url = f"{url}/api"
    return url


PANDORA_API_URL = _normalize_api_url(os.getenv("PANDORA_API_URL", ""))
PIVOT_API_KEY = os.getenv("PIVOT_API_KEY", "")

FRED_API_KEY = os.getenv("FRED_API_KEY", "")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openrouter")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "anthropic/claude-haiku-4-5")

DISCORD_WEBHOOK_CRITICAL = os.getenv("DISCORD_WEBHOOK_CRITICAL", "")
DISCORD_WEBHOOK_SIGNALS = os.getenv("DISCORD_WEBHOOK_SIGNALS", "")
DISCORD_WEBHOOK_BRIEFS = os.getenv("DISCORD_WEBHOOK_BRIEFS", "")
DISCORD_WEBHOOK_CALENDAR = os.getenv("DISCORD_WEBHOOK_CALENDAR", "")
DISCORD_WEBHOOK_SYSTEM = os.getenv("DISCORD_WEBHOOK_SYSTEM", "")

WHALE_ALERTS_CHANNEL_ID = os.getenv("WHALE_ALERTS_CHANNEL_ID", "")

DISCORD_MIN_PRIORITY = os.getenv("DISCORD_MIN_PRIORITY", "MEDIUM")
HEALTH_OFFLINE_THRESHOLD_MINUTES = int(os.getenv("HEALTH_OFFLINE_THRESHOLD_MINUTES", "30"))
TIMEZONE = os.getenv("TIMEZONE", "America/New_York")

HTTP_TIMEOUT = float(os.getenv("PIVOT_HTTP_TIMEOUT", "20"))
RETRY_ATTEMPTS = int(os.getenv("PIVOT_RETRY_ATTEMPTS", "3"))
RETRY_BACKOFF_SECONDS = float(os.getenv("PIVOT_RETRY_BACKOFF", "2"))
