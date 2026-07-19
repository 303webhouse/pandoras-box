"""DuckDB connection and schema management."""

import duckdb
from contextlib import contextmanager
from . import config


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS universe (
    ticker          VARCHAR PRIMARY KEY,
    name            VARCHAR,
    sector          VARCHAR,
    industry        VARCHAR,
    theme           VARCHAR,
    subtheme        VARCHAR,
    liquidity_tier  VARCHAR
);

CREATE TABLE IF NOT EXISTS prices (
    ticker  VARCHAR NOT NULL,
    date    DATE    NOT NULL,
    open    DOUBLE,
    high    DOUBLE,
    low     DOUBLE,
    close   DOUBLE,
    volume  BIGINT,
    PRIMARY KEY (ticker, date)
);

CREATE INDEX IF NOT EXISTS idx_prices_date ON prices(date);
CREATE INDEX IF NOT EXISTS idx_prices_ticker ON prices(ticker);

CREATE TABLE IF NOT EXISTS metrics (
    ticker          VARCHAR NOT NULL,
    date            DATE    NOT NULL,
    ret_1d          DOUBLE,
    ret_5d          DOUBLE,
    ret_20d         DOUBLE,
    ret_60d         DOUBLE,
    ma_10           DOUBLE,
    ma_20           DOUBLE,
    ma_21           DOUBLE,
    ma_50           DOUBLE,
    ma_200          DOUBLE,
    dist_ma10_pct   DOUBLE,
    dist_ma20_pct   DOUBLE,
    dist_ma21_pct   DOUBLE,
    dist_ma50_pct   DOUBLE,
    dist_ma200_pct  DOUBLE,
    above_ma10      TINYINT,
    above_ma20      TINYINT,
    above_ma21      TINYINT,
    above_ma50      TINYINT,
    above_ma200     TINYINT,
    atr_14          DOUBLE,
    atr_ext_50ma    DOUBLE,
    vol_ma_20       DOUBLE,
    vol_ratio       DOUBLE,
    high_20d        DOUBLE,
    high_52w        DOUBLE,
    new_high_20d    TINYINT,
    new_high_52w    TINYINT,
    rs_qqq_20d      DOUBLE,
    rs_qqq_60d      DOUBLE,
    rs_rsp_20d      DOUBLE,
    rs_rsp_60d      DOUBLE,
    PRIMARY KEY (ticker, date)
);

CREATE INDEX IF NOT EXISTS idx_metrics_date ON metrics(date);
CREATE INDEX IF NOT EXISTS idx_metrics_ticker ON metrics(ticker);
"""


# Columns to ALTER TABLE add for databases created before v2 of the schema.
_METRICS_V2_COLUMNS = [
    ("ma_10",         "DOUBLE"),
    ("ma_21",         "DOUBLE"),
    ("dist_ma10_pct", "DOUBLE"),
    ("dist_ma21_pct", "DOUBLE"),
    ("above_ma10",    "TINYINT"),
    ("above_ma21",    "TINYINT"),
]


@contextmanager
def connect(read_only: bool = False):
    """Open a DuckDB connection. Use as a context manager."""
    conn = duckdb.connect(str(config.DB_PATH), read_only=read_only)
    try:
        yield conn
    finally:
        conn.close()


def _existing_metrics_columns(conn) -> set:
    rows = conn.execute("PRAGMA table_info('metrics')").fetchall()
    return {row[1] for row in rows}


def init_schema() -> None:
    """Create tables if missing, and migrate older metrics tables to add v2 columns."""
    with connect() as conn:
        conn.execute(SCHEMA_SQL)

        # Migrate: add v2 columns if absent
        try:
            existing = _existing_metrics_columns(conn)
            for col, dtype in _METRICS_V2_COLUMNS:
                if col not in existing:
                    conn.execute(f"ALTER TABLE metrics ADD COLUMN {col} {dtype}")
        except Exception:
            pass


def latest_date_per_ticker() -> dict:
    """Return {ticker: latest_date} for incremental ingestion."""
    with connect(read_only=True) as conn:
        rows = conn.execute(
            "SELECT ticker, MAX(date) FROM prices GROUP BY ticker"
        ).fetchall()
    return {ticker: date for ticker, date in rows}
