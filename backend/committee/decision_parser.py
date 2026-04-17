"""
Extract structured decision block from PIVOT synthesis output.
Handles markdown fences, leading whitespace, and minor PIVOT drift.

Brief C v1.1 — replaces the fragile line-prefix parser with a fenced JSON block.
One regex, one failure mode, trivial to validate.
"""
import json
import re
import logging
from datetime import datetime
from typing import Optional, Dict

logger = logging.getLogger(__name__)

_DECISION_BLOCK = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)

VALID_DECISIONS = {"ENTER", "PASS", "WATCH", "HEDGE"}
VALID_CONVICTIONS = {"HIGH", "MEDIUM", "LOW"}


def extract_committee_decision(pivot_response: str) -> Optional[Dict]:
    """
    Parse the structured JSON decision block from PIVOT's synthesis output.
    Returns None if no valid block found (caller decides how to handle).

    Searches from the end — PIVOT is instructed to put the block last.
    The last fenced JSON block in the response is the decision block.
    """
    if not pivot_response:
        return None

    matches = _DECISION_BLOCK.findall(pivot_response)
    if not matches:
        logger.warning("No JSON decision block found in PIVOT response")
        return None

    # Last match is the one we want (PIVOT may reference JSON earlier in reasoning)
    raw_json = matches[-1]
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as e:
        logger.warning("PIVOT JSON block malformed: %s", e)
        return None

    decision = (parsed.get("decision") or "").upper().strip()
    conviction = (parsed.get("conviction") or "").upper().strip()
    key_risk = (parsed.get("key_risk") or "").strip()

    if decision not in VALID_DECISIONS:
        logger.warning("Invalid decision value: %r", decision)
        return None
    if conviction not in VALID_CONVICTIONS:
        logger.warning("Invalid conviction value: %r", conviction)
        return None

    return {
        "recommendation": decision,
        "conviction": conviction,
        "key_risk": key_risk,
        "decided_at": datetime.utcnow().isoformat(),
        "committee_version": "2.0",
    }
