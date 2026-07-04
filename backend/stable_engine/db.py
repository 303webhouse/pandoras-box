"""Postgres connection + schema for the Stable Engine.

Adapted from Stable Market Board by Ryan Scott (shared within The Stable, 2026).
Math unchanged; data layer swapped Polygon->yfinance and DuckDB->Postgres.

The engine is synchronous (pandas-heavy compute run from scheduler jobs / backfill),
so it uses psycopg2 rather than the hub's async asyncpg pool. API endpoints read the
resulting `stable_*` tables via the async pool. All tables are additive and prefixed
`stable_` — nothing existing is touched.

Connection precedence: STABLE_DB_URL -> DATABASE_URL -> assembled from the hub's
DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD env vars (as used by postgres_client).
"""

from __future__ import annotations

import os
from contextlib import contextmanager

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values


def _dsn() -> str:
    url = os.getenv("STABLE_DB_URL") or os.getenv("DATABASE_URL")
    if url:
        return url
    # Assemble from the hub's discrete env vars (Railway internal networking).
    host = os.getenv("DB_HOST") or "localhost"
    port = os.getenv("DB_PORT") or "5432"
    name = os.getenv("DB_NAME") or "railway"
    user = os.getenv("DB_USER") or "postgres"
    pw = os.getenv("DB_PASSWORD") or ""
    return f"postgresql://{user}:{pw}@{host}:{port}/{name}"


@contextmanager
def connect():
    """Open a psycopg2 connection (context-managed, auto-commit on clean exit)."""
    conn = psycopg2.connect(_dsn())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def read_df(sql: str, params: list | tuple | None = None) -> pd.DataFrame:
    """Run a read query and return a DataFrame. Uses %s placeholders (psycopg2)."""
    with connect() as conn:
        return pd.read_sql(sql, conn, params=params)


# ── Schema (Postgres) ─────────────────────────────────────────────────────────
# Column names for stable_daily_bars follow the brief: (ticker, date, o, h, l, c, v).
# The metrics columns mirror the source `metrics` table 1:1 so the ported math is
# byte-identical.
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS stable_universe (
    ticker          TEXT PRIMARY KEY,
    name            TEXT,
    sector          TEXT,
    industry        TEXT,
    theme           TEXT,
    subtheme        TEXT,
    liquidity_tier  TEXT
);

CREATE TABLE IF NOT EXISTS stable_daily_bars (
    ticker  TEXT NOT NULL,
    date    DATE NOT NULL,
    o       DOUBLE PRECISION,
    h       DOUBLE PRECISION,
    l       DOUBLE PRECISION,
    c       DOUBLE PRECISION,
    v       BIGINT,
    PRIMARY KEY (ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_stable_bars_date ON stable_daily_bars(date);

CREATE TABLE IF NOT EXISTS stable_metrics (
    ticker          TEXT NOT NULL,
    date            DATE NOT NULL,
    ret_1d          DOUBLE PRECISION,
    ret_5d          DOUBLE PRECISION,
    ret_20d         DOUBLE PRECISION,
    ret_60d         DOUBLE PRECISION,
    ma_10           DOUBLE PRECISION,
    ma_20           DOUBLE PRECISION,
    ma_21           DOUBLE PRECISION,
    ma_50           DOUBLE PRECISION,
    ma_200          DOUBLE PRECISION,
    dist_ma10_pct   DOUBLE PRECISION,
    dist_ma20_pct   DOUBLE PRECISION,
    dist_ma21_pct   DOUBLE PRECISION,
    dist_ma50_pct   DOUBLE PRECISION,
    dist_ma200_pct  DOUBLE PRECISION,
    above_ma10      SMALLINT,
    above_ma20      SMALLINT,
    above_ma21      SMALLINT,
    above_ma50      SMALLINT,
    above_ma200     SMALLINT,
    atr_14          DOUBLE PRECISION,
    atr_ext_50ma    DOUBLE PRECISION,
    vol_ma_20       DOUBLE PRECISION,
    vol_ratio       DOUBLE PRECISION,
    high_20d        DOUBLE PRECISION,
    high_52w        DOUBLE PRECISION,
    new_high_20d    SMALLINT,
    new_high_52w    SMALLINT,
    rs_qqq_20d      DOUBLE PRECISION,
    rs_qqq_60d      DOUBLE PRECISION,
    rs_rsp_20d      DOUBLE PRECISION,
    rs_rsp_60d      DOUBLE PRECISION,
    PRIMARY KEY (ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_stable_metrics_date ON stable_metrics(date);

CREATE TABLE IF NOT EXISTS stable_theme_scores (
    theme            TEXT NOT NULL,
    date             DATE NOT NULL,
    anchor           TEXT NOT NULL,          -- 'close' | 'provisional'
    score            DOUBLE PRECISION,
    status           TEXT,
    rank             INTEGER,
    score_1d_delta   DOUBLE PRECISION,
    n_names          INTEGER,
    breadth          DOUBLE PRECISION,
    leadership       DOUBLE PRECISION,
    momentum         DOUBLE PRECISION,
    extension_raw    DOUBLE PRECISION,
    pct_above_20ma   DOUBLE PRECISION,
    pct_above_50ma   DOUBLE PRECISION,
    pct_above_200ma  DOUBLE PRECISION,
    pct_new_high_20d DOUBLE PRECISION,
    pct_new_high_52w DOUBLE PRECISION,
    avg_ret_5d       DOUBLE PRECISION,
    avg_ret_20d      DOUBLE PRECISION,
    avg_atr_ext_50ma DOUBLE PRECISION,
    avg_rs_qqq_20d   DOUBLE PRECISION,
    as_of            TIMESTAMPTZ,
    data_age_seconds DOUBLE PRECISION,
    degraded         BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (theme, date, anchor)
);
CREATE INDEX IF NOT EXISTS idx_stable_theme_scores_date ON stable_theme_scores(date);

CREATE TABLE IF NOT EXISTS stable_live_strip (
    symbol      TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,               -- 'index' | 'yield' | 'spread' | 'sector' | 'fx'
    value       DOUBLE PRECISION,            -- % change (index/sector/fx) or yield percent
    day_change  DOUBLE PRECISION,            -- indices: n/a; yields: basis points; spread: bp
    extra       DOUBLE PRECISION,            -- yields: raw level; free slot otherwise
    as_of       TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS stable_intraday_points (
    symbol  TEXT NOT NULL,
    ts      TIMESTAMPTZ NOT NULL,
    value   DOUBLE PRECISION,
    PRIMARY KEY (symbol, ts)
);
CREATE INDEX IF NOT EXISTS idx_stable_intraday_symbol_ts ON stable_intraday_points(symbol, ts);
"""


def init_schema() -> None:
    """Create the stable_* tables if missing. Idempotent, additive only."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)


def upsert_bars(rows: list[tuple]) -> int:
    """Upsert (ticker, date, o, h, l, c, v) rows into stable_daily_bars."""
    if not rows:
        return 0
    sql = """
        INSERT INTO stable_daily_bars (ticker, date, o, h, l, c, v)
        VALUES %s
        ON CONFLICT (ticker, date) DO UPDATE SET
            o = EXCLUDED.o, h = EXCLUDED.h, l = EXCLUDED.l,
            c = EXCLUDED.c, v = EXCLUDED.v
    """
    with connect() as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql, rows, page_size=5000)
    return len(rows)


def latest_bar_date_per_ticker() -> dict:
    """Return {ticker: latest_date} for incremental ingestion."""
    df = read_df("SELECT ticker, MAX(date) AS d FROM stable_daily_bars GROUP BY ticker")
    return {r["ticker"]: r["d"] for _, r in df.iterrows()}
