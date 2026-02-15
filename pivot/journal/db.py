"""
SQLite database setup for the Pivot trade journal.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Optional

from collectors.config import JOURNAL_DB_PATH

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1  # Bump when schema changes

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),

    account         TEXT NOT NULL,
    ticker          TEXT NOT NULL,
    strategy        TEXT,
    direction       TEXT NOT NULL,

    entry_price     REAL,
    entry_date      TEXT NOT NULL DEFAULT (date('now')),
    size            TEXT,
    max_loss        REAL,
    stop_price      REAL,
    target_price    REAL,

    bias_at_entry   TEXT,
    defcon_at_entry TEXT,
    iv_rank         REAL,
    thesis          TEXT,
    catalyst        TEXT,
    invalidation    TEXT,
    confidence      INTEGER,

    exit_price      REAL,
    exit_date       TEXT,
    pnl_dollars     REAL,
    pnl_percent     REAL,
    followed_plan   INTEGER,
    exit_reason     TEXT,
    lesson          TEXT,

    status          TEXT NOT NULL DEFAULT 'open'
);

CREATE TABLE IF NOT EXISTS daily_pnl (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,
    account         TEXT NOT NULL,
    starting_balance REAL,
    ending_balance  REAL,
    realized_pnl    REAL DEFAULT 0,
    trades_taken    INTEGER DEFAULT 0,
    wins            INTEGER DEFAULT 0,
    losses          INTEGER DEFAULT 0,
    notes           TEXT,
    UNIQUE(date, account)
);

CREATE TABLE IF NOT EXISTS breakout_tracking (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL DEFAULT (datetime('now')),
    balance         REAL NOT NULL,
    high_water_mark REAL NOT NULL,
    drawdown_floor_real    REAL NOT NULL,
    drawdown_floor_personal REAL NOT NULL,
    daily_loss_used REAL DEFAULT 0,
    daily_loss_limit REAL,
    step            INTEGER DEFAULT 1,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS defcon_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL DEFAULT (datetime('now')),
    level           TEXT NOT NULL,
    previous_level  TEXT,
    triggers        TEXT,
    duration_minutes INTEGER,
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_trades_account ON trades(account);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_ticker ON trades(ticker);
CREATE INDEX IF NOT EXISTS idx_trades_entry_date ON trades(entry_date);
CREATE INDEX IF NOT EXISTS idx_daily_pnl_date ON daily_pnl(date);
CREATE INDEX IF NOT EXISTS idx_breakout_timestamp ON breakout_tracking(timestamp);
CREATE INDEX IF NOT EXISTS idx_defcon_timestamp ON defcon_events(timestamp);
"""


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Get a SQLite connection with WAL mode and foreign keys enabled."""
    path = db_path or JOURNAL_DB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row  # Dict-like access
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """Initialize the database schema. Safe to call multiple times."""
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER)"
        )
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (_SCHEMA_VERSION,),
            )
        conn.commit()
        logger.info(f"Journal DB initialized at {db_path or JOURNAL_DB_PATH}")
    finally:
        conn.close()
