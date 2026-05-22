"""
Sector Constituent Cache — Phase A canonical envelope schema.

Stores per-ticker per-field values written by `jobs/sector_constituent_refresh`
and consumed by `/sectors/{etf}/leaders` and the ticker profile endpoint.

Envelope shape:
    {"value": <number | null>, "ts": <ISO 8601 string>, "source": "UW"}

The envelope is intentional. Phase C (Olympus enrichment expansion) will adopt
the same shape for committee enrichment caching, so the popup-side fix Phase A
ships becomes the architectural template for the next build. Keep the shape
stable.

Redis keys:
    sector:constituent:{TICKER}:{field}

Supported fields: wk_change_pct, mo_change_pct, rsi_14. New fields can be added
without schema changes — writers and readers agree on a string identifier and
the envelope.

The cache does not enforce a TTL on writes. The refresh job overwrites entries
on its own cadence; readers consume the envelope and surface freshness via the
`ts` field rather than relying on TTL expiry. This is the canonical pattern
the brief mandates.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database.redis_client import get_redis_client

logger = logging.getLogger("sector_cache")

KEY_PREFIX = "sector:constituent"
SUPPORTED_FIELDS = ("wk_change_pct", "mo_change_pct", "rsi_14")


def _key(ticker: str, field: str) -> str:
    return f"{KEY_PREFIX}:{ticker.upper()}:{field}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def write_field(
    ticker: str,
    field: str,
    value: Optional[float],
    source: str = "UW",
) -> bool:
    """Write a single field envelope. Returns True on write, False on no-op or failure.

    `value=None` is a valid write — it records that the refresh job ran but UW
    returned no usable data. Readers should treat null `value` as "absent" but
    can still trust the `ts` to know the field was attempted recently.
    """
    redis = await get_redis_client()
    if not redis:
        return False
    envelope: Dict[str, Any] = {
        "value": value if value is None else float(value),
        "ts": _now_iso(),
        "source": source,
    }
    try:
        await redis.set(_key(ticker, field), json.dumps(envelope))
        return True
    except Exception as e:
        logger.debug("sector_cache write_field failed for %s/%s: %s", ticker, field, e)
        return False


async def read_field(ticker: str, field: str) -> Optional[Dict[str, Any]]:
    """Read a single field envelope. Returns None if the key is missing.

    Returned dict has shape {"value": float|None, "ts": str, "source": str}.
    The caller is responsible for null-checking `value`.
    """
    redis = await get_redis_client()
    if not redis:
        return None
    try:
        raw = await redis.get(_key(ticker, field))
        if not raw:
            return None
        envelope = json.loads(raw)
        if not isinstance(envelope, dict):
            return None
        envelope.setdefault("value", None)
        envelope.setdefault("ts", None)
        envelope.setdefault("source", "UW")
        return envelope
    except Exception as e:
        logger.debug("sector_cache read_field failed for %s/%s: %s", ticker, field, e)
        return None


async def read_many(
    tickers: List[str],
    fields: List[str],
) -> Dict[str, Dict[str, Optional[Dict[str, Any]]]]:
    """Batch read: returns {ticker: {field: envelope|None}}.

    Uses a single Redis MGET roundtrip across all (ticker, field) pairs to keep
    the popup's batch read cheap. Missing keys come back as None entries.
    """
    redis = await get_redis_client()
    out: Dict[str, Dict[str, Optional[Dict[str, Any]]]] = {
        t.upper(): {f: None for f in fields} for t in tickers
    }
    if not redis or not tickers or not fields:
        return out

    keys: List[str] = []
    coords: List[tuple] = []
    for t in tickers:
        for f in fields:
            keys.append(_key(t, f))
            coords.append((t.upper(), f))

    try:
        raws = await redis.mget(*keys)
    except Exception as e:
        logger.debug("sector_cache read_many MGET failed: %s", e)
        return out

    for (t, f), raw in zip(coords, raws):
        if not raw:
            continue
        try:
            envelope = json.loads(raw)
            if isinstance(envelope, dict):
                envelope.setdefault("value", None)
                envelope.setdefault("ts", None)
                envelope.setdefault("source", "UW")
                out[t][f] = envelope
        except Exception:
            continue
    return out
