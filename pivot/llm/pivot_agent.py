"""
OpenRouter client for Pivot.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from collectors.config import LLM_API_KEY, LLM_MODEL
from .prompts import PIVOT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


async def call_llm(user_prompt: str, max_tokens: int = 1000) -> str:
    if not LLM_API_KEY:
        return "[LLM disabled: LLM_API_KEY not configured]"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://pandoras-box.up.railway.app",
                    "X-Title": "Pivot Trading Agent",
                },
                json={
                    "model": LLM_MODEL,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": PIVOT_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                },
            )

            if response.status_code == 429:
                logger.warning("OpenRouter rate limited — skipping LLM")
                return "[Rate limited — skipping interpretation]"
            if response.status_code == 402:
                logger.error("OpenRouter billing limit — check dashboard")
                return "[Billing limit reached]"

            data = response.json()

            if response.status_code != 200:
                err = data.get("error", {})
                logger.error(
                    f"OpenRouter error {response.status_code}: "
                    f"{err.get('message', data)}"
                )
                return f"[LLM error: HTTP {response.status_code} — {err.get('message', 'unknown error')}]"

            if "choices" not in data:
                logger.error(f"OpenRouter unexpected response: {data}")
                return "[LLM error: unexpected response format from OpenRouter]"

            return data["choices"][0]["message"]["content"]
    except Exception as exc:
        logger.exception(f"LLM call failed: {exc}")
        return f"[LLM error: {exc}]"
