-- 027_strike_ib_shadow.sql
-- STRIKE-SPEC-01: IB-break -> shadow signal converter, per-ticker feed watermarks.
--
-- PYTHIA Pine v2.4 already emits ib_break_up / ib_break_down into pythia_events;
-- nothing downstream consumed them. The converter turns the first qualifying break
-- per ticker/direction/session into a status='SHADOW' row in the existing signals
-- pipeline, graded by the canonical 15-min resolver and invisible to every
-- actionable surface, to collect the n>=50 both-direction sample gating STRIKE
-- promotion (target ~09-18, verdict 10-01).
--
-- These two tables are the converter's OWN instrumentation, not signal data:
-- strike_feed_watermarks answers "is this ticker's alert flow alive at all", and
-- strike_ib_session_counts accumulates the per-ticker observed daily distributions.
--
-- DELETION LAW (SPEC-01 addendum section 2, binding): no retention or cleanup
-- policy may touch strike_ib_session_counts, or the pythia_events history it
-- summarizes, while the decay-instrument derivation claim is unexercised. The
-- Triton retention case is the worked example -- 46 pre-08-01 ungraded rows were
-- the only physical evidence of an entire ungradeable instrument class, and a
-- 30-day sweep would have erased the evidence while keeping the defect.
--
-- NOTE ON APPLICATION: this repo has no migration runner; tables are created at
-- boot via backend/database/postgres_client.py::init_database() (CREATE TABLE IF
-- NOT EXISTS). This file is the human record; the authoritative DDL is mirrored
-- verbatim in init_database(). Keep the two in sync.
--

CREATE TABLE IF NOT EXISTS strike_feed_watermarks (
    ticker              TEXT PRIMARY KEY,
    baseline_sessions   INTEGER NOT NULL DEFAULT 0,   -- distinct sessions with >=1 pythia_events row (any alert_type)
    last_event_ts       TIMESTAMPTZ,                  -- any alert_type
    last_event_session  DATE,
    last_ib_event_ts    TIMESTAMPTZ,                  -- ib_break_* only
    last_signal_ts      TIMESTAMPTZ,                  -- last converted emission
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS strike_ib_session_counts (
    ticker          TEXT NOT NULL,
    session_date    DATE NOT NULL,
    pythia_events   INTEGER NOT NULL DEFAULT 0,
    ib_events       INTEGER NOT NULL DEFAULT 0,
    signals_emitted INTEGER NOT NULL DEFAULT 0,
    rejects         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (ticker, session_date)
);

-- DOWN
-- DROP TABLE IF EXISTS strike_ib_session_counts;
-- DROP TABLE IF EXISTS strike_feed_watermarks;
