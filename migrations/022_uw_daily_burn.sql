-- 022_uw_daily_burn.sql
-- UW budget watchdog (Fable 2026-07-09): durable per-day UW-burn snapshot.
--
-- The per-caller + global daily request counters live in Redis under a 48h TTL
-- (uw:daily_requests_by_caller:{date} / uw:daily_requests:{date}). That TTL blinded
-- us to 7/6-7/8 daily totals TWICE this month. This table is the durable record:
-- at each UTC rollover the snapshot job (jobs/uw_budget_watchdog.run_daily_burn_snapshot)
-- reads the prior day's still-alive counter keys and upserts them here.
--
-- caller = '_TOTAL' holds the grand total for the day.
--
-- APPLICATION: this repo has no migration runner; tables boot at startup via
-- backend/database/postgres_client.py::init_database() (CREATE TABLE IF NOT EXISTS).
-- This file is the human record; the authoritative DDL is mirrored there and in the
-- snapshot job (which also creates it defensively). Keep the three in sync.

CREATE TABLE IF NOT EXISTS uw_daily_burn (
    day             DATE NOT NULL,
    caller          TEXT NOT NULL,           -- governor caller tag, or '_TOTAL' for the grand total
    count           INT  NOT NULL,
    snapshotted_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (day, caller)
);
