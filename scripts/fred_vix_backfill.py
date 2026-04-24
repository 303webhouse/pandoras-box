"""
FRED VIX Backfill — one-shot admin script.

Seeds factor_readings with 252 trading days of historical VIXCLS data so the
percentile gate (iv_regime v2) has real history from day 1.

REQUIREMENTS:
    pip install httpx asyncpg

RUN (from repo root — no `railway run` needed):
    python scripts/fred_vix_backfill.py

  Requires two env vars set in your shell or as persistent Windows env vars:
    FRED_API_KEY  — from Railway dashboard or `railway variables`
    DATABASE_URL  — full public proxy DSN, e.g.:
                    postgresql://postgres:<pw>@trolley.proxy.rlwy.net:25012/railway
                    (get values from Railway dashboard → Postgres → Connect)

  Alternatively set individual vars: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD.
  If DATABASE_URL is set it takes precedence.

EXIT CODES:
    0 — success, ≥252 trading days seeded
    1 — missing env vars or FRED/DB connection failure
    2 — success but fewer than 252 trading days inserted (extend start date)

IDEMPOTENT: safe to re-run; existing fred_backfill rows are skipped.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta

import asyncpg
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)   # suppress full URL logs (contain api_key)
logging.getLogger("hpack").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
SERIES_ID = "VIXCLS"
LOOKBACK_TARGET = 252
# 365 calendar days covers 252 trading days with holiday/weekend buffer.
# Calculated at runtime so the script works correctly on any future date.
CALENDAR_LOOKBACK_DAYS = 365


async def fetch_fred_observations(api_key: str, start_date: str) -> list[dict]:
    params = {
        "series_id": SERIES_ID,
        "file_type": "json",
        "api_key": api_key,
        "observation_start": start_date,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(FRED_URL, params=params)
        resp.raise_for_status()
    return resp.json()["observations"]


async def get_backfilled_dates(conn: asyncpg.Connection) -> set[str]:
    rows = await conn.fetch(
        """
        SELECT DATE(timestamp)::TEXT AS day
        FROM factor_readings
        WHERE factor_id = 'iv_regime'
          AND source = 'fred_backfill'
        """
    )
    return {r["day"] for r in rows}


async def main() -> None:
    fred_key = os.environ.get("FRED_API_KEY")
    if not fred_key:
        logger.error(
            "FRED_API_KEY not set. "
            "Run via: DB_HOST=trolley.proxy.rlwy.net DB_PORT=25012 railway run python scripts/fred_vix_backfill.py"
        )
        sys.exit(1)

    database_url = os.environ.get("DATABASE_URL")  # full DSN takes precedence
    db_host = os.environ.get("DB_HOST") or "localhost"
    db_port = int(os.environ.get("DB_PORT") or 5432)
    db_name = os.environ.get("DB_NAME") or "railway"
    db_user = os.environ.get("DB_USER") or "postgres"
    db_password = os.environ.get("DB_PASSWORD") or ""

    start_date = (datetime.now() - timedelta(days=CALENDAR_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    logger.info("Fetching VIXCLS from FRED since %s ...", start_date)

    try:
        observations = await fetch_fred_observations(fred_key, start_date)
    except Exception as exc:
        logger.error("FRED fetch failed: %s", exc)
        sys.exit(1)

    total_fetched = len(observations)
    logger.info("  FRED returned %d observations", total_fetched)

    try:
        if database_url:
            conn = await asyncpg.connect(database_url, ssl="require")
        else:
            conn = await asyncpg.connect(
                host=db_host,
                port=db_port,
                database=db_name,
                user=db_user,
                password=db_password,
                ssl="require",
            )
    except Exception as exc:
        logger.error("DB connection failed: %s", exc)
        sys.exit(1)

    try:
        existing_dates = await get_backfilled_dates(conn)
        logger.info("  Already-present fred_backfill dates: %d", len(existing_dates))

        skipped_missing = 0
        skipped_existing = 0
        inserted = 0
        now = datetime.now()

        for obs in observations:
            obs_date_str: str = obs["date"]
            value_str: str = obs["value"]

            if value_str == ".":
                # FRED missing-data sentinel (holidays, non-trading days)
                skipped_missing += 1
                continue

            if obs_date_str in existing_dates:
                skipped_existing += 1
                continue

            vix = float(value_str)
            obs_dt = datetime.strptime(obs_date_str, "%Y-%m-%d")
            ts = obs_dt.replace(hour=16, minute=0, second=0, microsecond=0)  # 16:00 UTC ≈ market close

            metadata = {
                "raw_data": {
                    "vix": vix,
                    "iv_rank": None,
                    "rank_source": "fred_backfill",
                    "source_note": "VIXCLS daily close from FRED — historical backfill for percentile gate",
                }
            }

            await conn.execute(
                """
                INSERT INTO factor_readings
                    (factor_id, score, signal, source, metadata, timestamp, created_at)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
                """,
                "iv_regime",
                0.0,          # NOT NULL constraint; 0.0 is a sentinel — gate reads raw vix from metadata
                None,
                "fred_backfill",
                json.dumps(metadata),
                ts,
                now,
            )
            inserted += 1

        # Verification counts
        total_row = await conn.fetchrow(
            "SELECT COUNT(*) AS n FROM factor_readings WHERE factor_id = 'iv_regime' AND source = 'fred_backfill'"
        )
        total_fred_rows = int(total_row["n"])

        range_row = await conn.fetchrow(
            """
            SELECT
                MIN(DATE(timestamp))::TEXT AS min_d,
                MAX(DATE(timestamp))::TEXT AS max_d
            FROM factor_readings
            WHERE factor_id = 'iv_regime' AND source = 'fred_backfill'
            """
        )

        print()
        print("FRED backfill complete.")
        print(f"  FRED observations fetched:    {total_fetched}")
        print(f"  Missing-data (.) skipped:     {skipped_missing}")
        print(f"  Already-present skipped:      {skipped_existing}")
        print(f"  New rows inserted:            {inserted}")
        print(f"  Total fred_backfill rows now: {total_fred_rows}")
        print(f"  Date range: {range_row['min_d']} to {range_row['max_d']}")
        print(f"  Trading days covered:         {total_fred_rows} (target: >={LOOKBACK_TARGET})")

        if total_fred_rows < LOOKBACK_TARGET:
            logger.error(
                "Only %d trading days seeded — below target of %d. "
                "Increase CALENDAR_LOOKBACK_DAYS and re-run.",
                total_fred_rows,
                LOOKBACK_TARGET,
            )
            sys.exit(2)

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
