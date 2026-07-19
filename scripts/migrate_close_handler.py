"""
Migration: close-handler refactor tables
Creates close_attempts and background_task_failures for the TOCTOU-safe close handler.
"""
import asyncio
import asyncpg
import os

# Use public proxy when running outside Railway network
DB_HOST = "trolley.proxy.rlwy.net"
DB_PORT = 25012
DB_NAME = os.getenv("DB_NAME") or "railway"
DB_USER = os.getenv("DB_USER") or "postgres"
DB_PASSWORD = os.getenv("DB_PASSWORD") or ""

DDL = """
CREATE TABLE IF NOT EXISTS close_attempts (
    id              BIGSERIAL    PRIMARY KEY,
    position_id     TEXT         NOT NULL,
    attempted_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    exit_price      NUMERIC(12,4),
    status          TEXT         NOT NULL DEFAULT 'started',
    trade_id        BIGINT,
    error_message   TEXT,
    CONSTRAINT close_attempts_status_chk
        CHECK (status IN ('started', 'completed', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_close_attempts_position_id
    ON close_attempts(position_id);

CREATE INDEX IF NOT EXISTS idx_close_attempts_attempted_at
    ON close_attempts(attempted_at DESC);

CREATE TABLE IF NOT EXISTS background_task_failures (
    id              BIGSERIAL    PRIMARY KEY,
    task_name       TEXT         NOT NULL,
    related_id      TEXT,
    error_class     TEXT,
    error_message   TEXT,
    stack_trace     TEXT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bg_failures_task_name
    ON background_task_failures(task_name);

CREATE INDEX IF NOT EXISTS idx_bg_failures_created_at
    ON background_task_failures(created_at DESC);
"""


async def main():
    conn = await asyncpg.connect(
        host=DB_HOST, port=DB_PORT,
        database=DB_NAME, user=DB_USER, password=DB_PASSWORD,
    )
    try:
        await conn.execute(DDL)
        print("Migration applied: close_attempts + background_task_failures created (or already existed).")

        # Verify
        tables = await conn.fetch("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
              AND tablename IN ('close_attempts', 'background_task_failures')
            ORDER BY tablename
        """)
        for t in tables:
            print(f"  confirmed: {t['tablename']}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
