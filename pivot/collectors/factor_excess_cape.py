"""
Excess CAPE Yield factor.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from fredapi import Fred

from .base_collector import get_latest_price, post_factor, _clamp
from .config import FRED_API_KEY

logger = logging.getLogger(__name__)

CACHE_PATH = Path(__file__).resolve().parents[1] / "cache" / "cape.json"
CACHE_TTL = timedelta(hours=24)


def _load_cache() -> float | None:
    try:
        if not CACHE_PATH.exists():
            return None
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        ts = datetime.fromisoformat(payload.get("timestamp"))
        if datetime.utcnow() - ts > CACHE_TTL:
            return None
        return float(payload.get("cape"))
    except Exception:
        return None


def _save_cache(value: float) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {"cape": value, "timestamp": datetime.utcnow().isoformat()}
        CACHE_PATH.write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        pass


def _fetch_cape_from_fred() -> float | None:
    if not FRED_API_KEY:
        return None
    try:
        fred = Fred(api_key=FRED_API_KEY)
        for series in ("CAPE", "SP500_PE_RATIO_MONTH"):
            try:
                data = fred.get_series(series)
                data = data.dropna()
                if not data.empty:
                    return float(data.iloc[-1])
            except Exception:
                continue
    except Exception as exc:
        logger.warning(f"FRED fetch failed: {exc}")
    return None


def _fetch_cape_from_multpl() -> float | None:
    try:
        url = "https://www.multpl.com/shiller-pe/table/by-month"
        resp = httpx.get(url, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table")
        if not table:
            return None
        rows = table.find_all("tr")
        if len(rows) < 2:
            return None
        cells = rows[1].find_all("td")
        if len(cells) < 2:
            return None
        value = float(cells[1].get_text(strip=True))
        return value
    except Exception as exc:
        logger.warning(f"multpl scrape failed: {exc}")
        return None


async def _get_cape_ratio() -> float | None:
    cached = _load_cache()
    if cached:
        return cached

    cape = _fetch_cape_from_fred()
    if cape is None:
        cape = _fetch_cape_from_multpl()

    if cape is not None:
        _save_cache(cape)
    return cape


async def compute_score():
    cape = await _get_cape_ratio()
    ten_year = await get_latest_price("^TNX")

    if cape is None or ten_year is None:
        return None

    ten_year = ten_year / 100
    cape_ey = 1.0 / cape if cape > 0 else 0
    ecy = (cape_ey - ten_year) * 100

    if ecy >= 3.0:
        score = 0.6
    elif ecy >= 2.0:
        score = 0.3
    elif ecy >= 1.0:
        score = 0.0
    elif ecy >= 0.0:
        score = -0.4
    else:
        score = -0.8

    score = _clamp(score)

    detail = (
        f"CAPE {cape:.1f}, EY {cape_ey * 100:.1f}%, 10Y {ten_year * 100:.1f}%, ECY {ecy:.1f}%"
    )

    data = {
        "cape": float(cape),
        "earnings_yield": cape_ey,
        "ten_year": ten_year,
        "ecy": ecy,
    }

    return score, detail, data


async def collect_and_post():
    result = await compute_score()
    if not result:
        logger.warning("Excess CAPE data unavailable")
        return None

    score, detail, data = result
    return await post_factor(
        "excess_cape",
        score=score,
        detail=detail,
        data=data,
        collected_at=datetime.utcnow(),
        stale_after_hours=168,
        source="fred",
    )
