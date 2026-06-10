"""
Shared webhook authentication helpers (AEGIS hardening, centralized).

Every inbound webhook handler should enforce the same shared-secret contract
instead of copy-pasting blocks. This module is the single source of truth for:

  - fail-closed shared-secret validation (constant-time compare)
  - an OBSERVE mode for staged cutovers (validate-but-allow, log the verdict)
  - payload size caps (Content-Length + serialized-body)
  - secret-strip before logging / persistence

Mirrors the inline blocks already living in `webhooks/pythia_events.py` and
`webhooks/mp_levels.py`; those can migrate to these helpers in a later chunk.

Cutover usage (per the Phase 1 brief):
    1. Re-arm the alert(s) to send `secret`.
    2. Call with observe=True — logs whether each POST carries a valid secret,
       but never rejects, so a missed re-arm can't drop a real signal.
    3. Once N consecutive valid secret-bearing POSTs are seen across ALL alerts
       in the chunk, set the env var and flip observe=False (fail-closed).
"""

from __future__ import annotations

import hmac
import json
import logging
from typing import Any, Optional

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

DEFAULT_MAX_PAYLOAD_BYTES = 8192


def enforce_content_length_cap(
    request: Optional[Request], max_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES
) -> None:
    """Reject oversized bodies via the Content-Length header BEFORE reading them
    into memory. No-op when request is None or the header is absent/non-numeric."""
    if request is None:
        return
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > max_bytes:
        raise HTTPException(status_code=413, detail="payload too large")


def enforce_payload_size_cap(
    payload: Any, max_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES
) -> None:
    """Reject oversized payloads after parse (covers chunked bodies that arrive
    without a Content-Length header). Silently skips if payload isn't serializable."""
    try:
        size = len(json.dumps(payload).encode("utf-8"))
    except (TypeError, ValueError):
        return
    if size > max_bytes:
        logger.warning("Rejected webhook — payload over size cap (%d > %d)", size, max_bytes)
        raise HTTPException(status_code=413, detail="payload too large")


def validate_webhook_secret(
    supplied: Optional[str],
    *,
    secret: str,
    observe: bool = False,
    label: str = "webhook",
) -> bool:
    """
    Fail-closed, constant-time shared-secret check.

    ENFORCE mode (observe=False):
      - secret == "" (env unset)        -> 503 (webhook auth not configured)
      - supplied mismatch / missing     -> 401 (invalid webhook secret)
      - valid                           -> returns True

    OBSERVE mode (observe=True):
      - never raises; logs whether the payload carried a secret and whether it
        matched, then returns the verdict (True=valid, False=would-reject).
        Use during cutover so a missed re-arm doesn't drop a real signal.

    Returns True iff the supplied secret is valid against `secret`.
    """
    supplied_str = str(supplied or "")
    supplied_present = bool(supplied_str)

    if observe:
        if not secret:
            logger.warning(
                "[%s] OBSERVE: env secret UNSET; payload secret %s — would 503, allowing",
                label, "PRESENT" if supplied_present else "ABSENT",
            )
            return False
        valid = hmac.compare_digest(supplied_str, secret)
        logger.warning(
            "[%s] OBSERVE: payload secret %s, match=%s — allowing",
            label, "PRESENT" if supplied_present else "ABSENT", valid,
        )
        return valid

    # ── ENFORCE ──
    if not secret:
        logger.error("[%s] secret not configured — rejecting (fail-closed)", label)
        raise HTTPException(status_code=503, detail="webhook auth not configured")
    if not hmac.compare_digest(supplied_str, secret):
        logger.warning("[%s] rejected — invalid webhook secret", label)
        raise HTTPException(status_code=401, detail="invalid webhook secret")
    return True


def strip_secret(payload: dict) -> dict:
    """Return a shallow copy of `payload` with the 'secret' key removed, for
    safe logging / persistence. Handlers that map fields explicitly (and never
    serialize the whole payload) don't strictly need this, but use it whenever
    a raw dict is logged or stored."""
    return {k: v for k, v in payload.items() if k != "secret"}
