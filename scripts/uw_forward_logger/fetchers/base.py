"""
Shared base: auth header, retry logic, 429 backoff, response envelope unwrap.
All fetchers import from here — no direct requests calls elsewhere.
"""

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

UW_BASE = "https://api.unusualwhales.com"

# Retry config
MAX_RETRIES_429 = 5
MAX_RETRIES_5XX = 3
BACKOFF_429_BASE_S = 2.0
BACKOFF_5XX_S = 5.0
BACKOFF_NET_S = 2.0
MAX_RETRIES_NET = 3


def build_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def _extract_rows(response_json: Any) -> list:
    """
    Unwrap UW response envelopes defensively.
    Per Phase 0 findings §5.4 — most endpoints: {"data": [...]}.
    """
    if isinstance(response_json, list):
        return response_json
    for key in ("data", "chains"):
        if key in response_json:
            return response_json[key]
    logger.warning(
        "Unexpected response envelope — keys: %s. Returning empty.",
        list(response_json.keys()) if isinstance(response_json, dict) else type(response_json),
    )
    return []


def uw_get(
    path: str,
    api_key: str,
    params: dict | None = None,
    timeout: int = 30,
) -> list:
    """
    GET a UW endpoint with retry + backoff. Returns list of row dicts.
    Raises on unrecoverable errors so caller can decide how to handle.

    Error handling per brief §B.8:
    - 429: respect Retry-After if present, else exponential backoff
    - 5xx: retry 3× with 5s backoff
    - 403 + historic_data_access_missing: WARNING, return []
    - 403 other: raises (caller should alert)
    - Network error: retry 3× with 2s backoff
    """
    url = UW_BASE + path
    headers = build_headers(api_key)

    attempt_429 = 0
    attempt_5xx = 0
    attempt_net = 0

    while True:
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as e:
            attempt_net += 1
            if attempt_net > MAX_RETRIES_NET:
                raise RuntimeError(f"Network error on {path} after {MAX_RETRIES_NET} retries: {e}") from e
            logger.debug("Network error on %s (attempt %d/%d): %s", path, attempt_net, MAX_RETRIES_NET, e)
            time.sleep(BACKOFF_NET_S * attempt_net)
            continue

        if resp.status_code == 200:
            try:
                return _extract_rows(resp.json())
            except Exception as e:
                raise RuntimeError(f"Failed to parse JSON from {path}: {e}") from e

        elif resp.status_code == 429:
            attempt_429 += 1
            if attempt_429 > MAX_RETRIES_429:
                raise RuntimeError(f"Rate-limited on {path} after {MAX_RETRIES_429} retries — giving up")
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else BACKOFF_429_BASE_S * (2 ** (attempt_429 - 1))
            logger.warning("429 on %s (attempt %d/%d) — waiting %.1fs", path, attempt_429, MAX_RETRIES_429, wait)
            time.sleep(wait)

        elif resp.status_code in (500, 502, 503, 504):
            attempt_5xx += 1
            if attempt_5xx > MAX_RETRIES_5XX:
                raise RuntimeError(f"{resp.status_code} on {path} after {MAX_RETRIES_5XX} retries")
            logger.debug("%d on %s (attempt %d/%d) — retrying in %ds",
                         resp.status_code, path, attempt_5xx, MAX_RETRIES_5XX, BACKOFF_5XX_S)
            time.sleep(BACKOFF_5XX_S)

        elif resp.status_code == 403:
            try:
                body = resp.json()
            except Exception:
                body = {}
            code_field = body.get("code", "") or body.get("error", "")
            if "historic_data_access_missing" in str(code_field):
                # Expected — out of rolling window. Log and return empty.
                logger.warning("403 historic_data_access_missing on %s — skipping (out of 30d window)", path)
                return []
            # Any other 403 is unexpected — raise so caller can alert
            raise RuntimeError(f"403 Forbidden on {path}: {body}")

        elif resp.status_code == 401:
            raise RuntimeError(f"401 Unauthorized on {path} — check UW_API_KEY")

        else:
            raise RuntimeError(f"Unexpected {resp.status_code} on {path}: {resp.text[:200]}")
