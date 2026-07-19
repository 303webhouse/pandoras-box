"""
Committee Response Parsers + LLM Call Wrapper — Brief 03B (refactored)

Synchronous Anthropic Messages API wrapper using urllib.
Parsers for TORO/URSA/TECHNICALS (analyst format) and Pivot (synthesizer format).
RISK parser removed — replaced by TECHNICALS which uses analyst format.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Optional

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-4-6"

log = logging.getLogger("committee_parsers")


class CreditExhaustedError(Exception):
    """Raised when Anthropic returns a credit/auth error that won't resolve with retries."""
    pass


# ── LLM Call Wrapper ──────────────────────────────────────────

def call_agent(
    system_prompt: str,
    user_message: str,
    api_key: str,
    max_tokens: int = 500,
    temperature: float = 0.3,
    agent_name: str = "unknown",
    timeout: int = 30,
    retries: int = 1,
    model: str = DEFAULT_MODEL,
) -> Optional[str]:
    """
    Call Anthropic Messages API with system prompt and user message (synchronous).

    Returns the assistant's text response, or None on failure.
    Raises CreditExhaustedError on credit/auth errors (do NOT retry these).
    """
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": user_message},
        ],
    }

    body = json.dumps(payload).encode("utf-8")

    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                url=ANTHROPIC_URL,
                method="POST",
                headers=headers,
                data=body,
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text = "".join(b["text"] for b in data.get("content", []) if b.get("type") == "text")
                log.info("[%s] Response received (%d chars)", agent_name, len(text))
                return text

        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="ignore")[:500]
            except Exception:
                pass

            # Circuit breaker: don't retry credit/auth errors
            err_lower = err_body.lower()
            if e.code in (400, 401, 403) and (
                "credit balance" in err_lower or "authentication" in err_lower
                or "billing" in err_lower or "api key" in err_lower
            ):
                log.error("[%s] CREDIT/AUTH ERROR (HTTP %d) — aborting: %s",
                          agent_name, e.code, err_body[:200])
                raise CreditExhaustedError(
                    f"Anthropic {e.code}: {err_body[:200]}"
                ) from e

            log.warning(
                "[%s] API error %d: %s (attempt %d/%d)",
                agent_name, e.code, err_body, attempt + 1, retries + 1,
            )
        except Exception as e:
            log.warning(
                "[%s] Error: %s (attempt %d/%d)",
                agent_name, e, attempt + 1, retries + 1,
            )

    log.error("[%s] All attempts failed, returning None", agent_name)
    return None


# ── Response Parsers ──────────────────────────────────────────

def parse_analyst_response(raw: str, agent_name: str) -> dict:
    """
    Parse TORO, URSA, or TECHNICALS analyst response into contract dict.

    Expected raw format from LLM:
    ANALYSIS: <1-3 sentence analysis>
    CONVICTION: HIGH|MEDIUM|LOW

    Handles multi-line ANALYSIS (text continues on lines after ANALYSIS:
    until CONVICTION: is found).

    Fallback: entire response as analysis with MEDIUM conviction.
    """
    result: dict[str, Any] = {
        "agent": agent_name,
        "analysis": raw.strip(),
        "conviction": "MEDIUM",
    }

    lines = raw.strip().split("\n")
    analysis_parts: list[str] = []
    in_analysis = False

    for line in lines:
        line_clean = line.strip()
        upper = line_clean.upper()

        if upper.startswith("CONVICTION:"):
            conv = line_clean[11:].strip().upper()
            if conv in ("HIGH", "MEDIUM", "LOW"):
                result["conviction"] = conv
            in_analysis = False
        elif upper.startswith("ANALYSIS:"):
            text_after = line_clean[9:].strip()
            if text_after:
                analysis_parts.append(text_after)
            in_analysis = True
        elif in_analysis and line_clean:
            analysis_parts.append(line_clean)

    if analysis_parts:
        result["analysis"] = " ".join(analysis_parts)

    return result


def parse_pivot_response(raw: str) -> dict:
    """
    Parse Pivot/Baum synthesizer response into contract dict.

    Expected raw format:
    SYNTHESIS: <Mark Baum-voiced synthesis paragraph>
    CONVICTION: HIGH|MEDIUM|LOW
    ACTION: TAKE|PASS|WATCHING
    INVALIDATION: <what kills this trade>

    Handles multi-line SYNTHESIS (text continues until next known prefix).

    Fallback: entire response as synthesis, MEDIUM conviction, WATCHING action.
    """
    result: dict[str, Any] = {
        "agent": "PIVOT",
        "synthesis": raw.strip(),
        "conviction": "MEDIUM",
        "action": "WATCHING",
        "invalidation": "See full analysis above",
    }

    known_prefixes = {"SYNTHESIS:", "CONVICTION:", "ACTION:", "INVALIDATION:", "STRUCTURE:", "LEVELS:", "SIZE:"}
    lines = raw.strip().split("\n")
    current_key: str | None = None
    parts: dict[str, list[str]] = {}

    for line in lines:
        line_clean = line.strip()
        upper = line_clean.upper()

        matched_prefix = None
        for prefix in known_prefixes:
            if upper.startswith(prefix):
                matched_prefix = prefix
                break

        if matched_prefix:
            current_key = matched_prefix.rstrip(":")
            text_after = line_clean[len(matched_prefix):].strip()
            parts[current_key] = [text_after] if text_after else []
        elif current_key and line_clean:
            parts.setdefault(current_key, []).append(line_clean)

    if "SYNTHESIS" in parts and parts["SYNTHESIS"]:
        result["synthesis"] = " ".join(parts["SYNTHESIS"])

    if "CONVICTION" in parts and parts["CONVICTION"]:
        conv = parts["CONVICTION"][0].upper()
        if conv in ("HIGH", "MEDIUM", "LOW"):
            result["conviction"] = conv

    if "ACTION" in parts and parts["ACTION"]:
        action = parts["ACTION"][0].upper()
        if action in ("TAKE", "PASS", "WATCHING"):
            result["action"] = action

    if "INVALIDATION" in parts and parts["INVALIDATION"]:
        result["invalidation"] = " ".join(parts["INVALIDATION"])

    if "STRUCTURE" in parts and parts["STRUCTURE"]:
        result["structure"] = " ".join(parts["STRUCTURE"])

    if "LEVELS" in parts and parts["LEVELS"]:
        result["levels"] = " ".join(parts["LEVELS"])

    if "SIZE" in parts and parts["SIZE"]:
        result["size"] = " ".join(parts["SIZE"])

    return result


def parse_combined_analyst_response(raw: str) -> dict:
    """
    Parse combined analyst response into three individual analyst dicts.

    Expected format:
    === TORO ===
    ANALYSIS: ...
    CONVICTION: ...
    === URSA ===
    ANALYSIS: ...
    CONVICTION: ...
    === TECHNICALS ===
    ANALYSIS: ...
    CONVICTION: ...
    """
    sections = {}
    current_agent = None
    current_lines = []

    for line in raw.strip().split("\n"):
        stripped = line.strip()
        upper = stripped.upper()

        if "TORO" in upper and upper.startswith("==="):
            if current_agent:
                sections[current_agent] = "\n".join(current_lines)
            current_agent = "TORO"
            current_lines = []
        elif "URSA" in upper and upper.startswith("==="):
            if current_agent:
                sections[current_agent] = "\n".join(current_lines)
            current_agent = "URSA"
            current_lines = []
        elif "TECHNICALS" in upper and upper.startswith("==="):
            if current_agent:
                sections[current_agent] = "\n".join(current_lines)
            current_agent = "TECHNICALS"
            current_lines = []
        else:
            current_lines.append(stripped)

    if current_agent:
        sections[current_agent] = "\n".join(current_lines)

    result = {}
    for agent in ("TORO", "URSA", "TECHNICALS"):
        if agent in sections:
            result[agent.lower()] = parse_analyst_response(sections[agent], agent)
        else:
            result[agent.lower()] = {
                "agent": agent,
                "analysis": f"[ANALYSIS UNAVAILABLE - {agent} section not found in combined response]",
                "conviction": "MEDIUM",
            }

    return result
