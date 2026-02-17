"""
OpenRouter client for Pivot.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import httpx

from collectors.config import LLM_API_KEY, LLM_MODEL
from .prompts import PIVOT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _extract_text_from_response(data: Dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return ""

    message = first_choice.get("message")
    if not isinstance(message, dict):
        return ""

    content = message.get("content")
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts: List[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") != "text":
                continue
            text_value = part.get("text")
            if isinstance(text_value, str) and text_value.strip():
                text_parts.append(text_value)
        return "\n".join(text_parts).strip()

    return str(content or "")


def _build_openrouter_payload(messages: List[Dict[str, Any]], max_tokens: int) -> Dict[str, Any]:
    return {
        "model": LLM_MODEL,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": PIVOT_SYSTEM_PROMPT},
            *messages,
        ],
    }


async def call_llm_messages(messages: List[Dict[str, Any]], max_tokens: int = 1000) -> str:
    if not LLM_API_KEY:
        return "[LLM disabled: LLM_API_KEY not configured]"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://pandoras-box.up.railway.app",
                    "X-Title": "Pivot Trading Agent",
                },
                json=_build_openrouter_payload(messages, max_tokens),
            )

            if response.status_code == 429:
                logger.warning("OpenRouter rate limited - skipping LLM")
                return "[Rate limited - skipping interpretation]"
            if response.status_code == 402:
                logger.error("OpenRouter billing limit - check dashboard")
                return "[Billing limit reached]"

            data = response.json()

            if response.status_code != 200:
                err = data.get("error", {}) if isinstance(data, dict) else {}
                logger.error(
                    "OpenRouter error %s: %s",
                    response.status_code,
                    err.get("message", data),
                )
                return f"[LLM error: HTTP {response.status_code} - {err.get('message', 'unknown error')}]"

            if not isinstance(data, dict) or "choices" not in data:
                logger.error("OpenRouter unexpected response: %s", data)
                return "[LLM error: unexpected response format from OpenRouter]"

            response_text = _extract_text_from_response(data)
            if not response_text:
                logger.error("OpenRouter response missing content text: %s", data)
                return "[LLM error: empty response content from OpenRouter]"

            return response_text
    except Exception as exc:
        logger.exception("LLM call failed: %s", exc)
        return f"[LLM error: {exc}]"


async def call_llm(user_prompt: str, max_tokens: int = 1000) -> str:
    return await call_llm_messages(
        [{"role": "user", "content": user_prompt}],
        max_tokens=max_tokens,
    )
