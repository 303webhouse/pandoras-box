"""Where grades live. Migration 035; the same DDL runs at boot (keep the two in sync).

shadow_grades is INSERT-ONLY (R-IV.428(a)(3)). A grade, once written, is never rewritten:
  * the same (signal, population, method, horizon) again -> skipped, counted `already_graded`;
  * one already stored on a DIFFERENT basis -> left alone, counted `basis_differs_not_regraded`.
Only graded rows are written. A pending or ungraded row is recomputed on the next pass and
counted by reason in the run record -- writing it would make a transient gap permanent.

Every run is recorded with what the calibration clause asks for (R-IV.425(d)): the code
commit, the bar vintage, the population window, and the row counts.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Tuple

from utils.json_sanitize import dumps_jsonb

DDL = """
CREATE TABLE IF NOT EXISTS shadow_grades (
    id              BIGSERIAL PRIMARY KEY,
    signal_id       TEXT        NOT NULL,
    population      TEXT        NOT NULL,
    method          TEXT        NOT NULL,
    horizon         INTEGER     NOT NULL,
    anchor_session  DATE        NOT NULL,
    exit_session    DATE        NOT NULL,
    entry_raw       NUMERIC,
    entry_factor    NUMERIC     NOT NULL,
    entry_basis     NUMERIC     NOT NULL,
    anchor_close    NUMERIC,
    exit_price      NUMERIC     NOT NULL,
    ret_pct         NUMERIC     NOT NULL,
    ret_raw_pct     NUMERIC     NOT NULL,
    ret_v2_pct      NUMERIC,
    r_multiple      NUMERIC,
    outcome         TEXT,
    direction_sign  SMALLINT    NOT NULL,
    basis_id        TEXT        NOT NULL,
    basis           JSONB       NOT NULL,
    flags           TEXT[]      NOT NULL DEFAULT '{}',
    tags            JSONB,
    grader_version  TEXT        NOT NULL,
    run_id          BIGINT,
    graded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (signal_id, population, method, horizon)
);
CREATE INDEX IF NOT EXISTS idx_shadow_grades_population
    ON shadow_grades (population, method, horizon, anchor_session);

CREATE TABLE IF NOT EXISTS backtest_runs (
    id              BIGSERIAL PRIMARY KEY,
    kind            TEXT        NOT NULL,
    population      TEXT        NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    status          TEXT        NOT NULL DEFAULT 'running',
    grader_version  TEXT        NOT NULL,
    code_commit     TEXT,
    params          JSONB,
    counts          JSONB,
    error           TEXT
);

CREATE TABLE IF NOT EXISTS backtest_results (
    id              BIGSERIAL PRIMARY KEY,
    run_id          BIGINT      NOT NULL,
    population      TEXT        NOT NULL,
    cell            TEXT        NOT NULL,
    method          TEXT        NOT NULL,
    horizon         INTEGER     NOT NULL,
    stratum         TEXT        NOT NULL DEFAULT 'ALL',
    symbol          TEXT        NOT NULL DEFAULT 'ALL',
    first_anchor    DATE,
    last_anchor     DATE,
    trades          INTEGER     NOT NULL,
    win_rate        NUMERIC,
    mean_ret_pct    NUMERIC,
    profit_factor   NUMERIC,
    avg_winner_r    NUMERIC,
    avg_loser_r     NUMERIC,
    expectancy_r    NUMERIC,
    max_dd_r        NUMERIC,
    sharpe          NUMERIC,
    summary         JSONB       NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_backtest_results_run ON backtest_results (run_id);
"""

# Migration 036 (R-IV.432(e)): a row the second vendor disagrees with is HELD, not graded.
# The hold is recorded so the check is not re-paid every pass; it is keyed on the basis, so a
# new basis looks again.
DDL_HOLDS = """
CREATE TABLE IF NOT EXISTS shadow_grade_holds (
    id              BIGSERIAL PRIMARY KEY,
    signal_id       TEXT        NOT NULL,
    population      TEXT        NOT NULL,
    method          TEXT        NOT NULL,
    horizon         INTEGER     NOT NULL,
    basis_id        TEXT        NOT NULL,
    reason          TEXT        NOT NULL,
    detail          JSONB       NOT NULL,
    tags            JSONB,
    grader_version  TEXT        NOT NULL,
    run_id          BIGINT,
    held_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (signal_id, population, method, horizon, basis_id)
);
CREATE INDEX IF NOT EXISTS idx_shadow_grade_holds_population
    ON shadow_grade_holds (population, method, horizon);
"""

WRITE_COLUMNS = ("signal_id", "population", "method", "horizon", "anchor_session",
                 "exit_session", "entry_raw", "entry_factor", "entry_basis", "anchor_close",
                 "exit_price", "ret_pct", "ret_raw_pct", "ret_v2_pct", "r_multiple", "outcome",
                 "direction_sign", "basis_id", "basis", "flags", "tags", "grader_version",
                 "run_id")


async def ensure_tables(conn) -> None:
    for stmt in [s for s in (DDL + DDL_HOLDS).split(";") if s.strip()]:
        await conn.execute(stmt)


async def existing(conn, population: str, signal_ids: List[str]) -> Dict[Tuple[str, str, int], str]:
    rows = await conn.fetch(
        "SELECT signal_id, method, horizon, basis_id FROM shadow_grades "
        "WHERE population = $1 AND signal_id = ANY($2::text[])",
        population, signal_ids)
    return {(r["signal_id"], r["method"], r["horizon"]): r["basis_id"] for r in rows}


async def held(conn, population: str, signal_ids: List[str], basis_id: str) -> set:
    rows = await conn.fetch(
        "SELECT signal_id, method, horizon FROM shadow_grade_holds "
        "WHERE population = $1 AND basis_id = $2 AND signal_id = ANY($3::text[])",
        population, basis_id, signal_ids)
    return {(r["signal_id"], r["method"], r["horizon"]) for r in rows}


def hold_record(g, population: str, reason: str, detail: Dict[str, Any], tags: Dict[str, Any],
                grader_version: str, run_id: Optional[int]) -> Tuple:
    safe_tags = {k: v for k, v in tags.items() if not k.startswith("_")}
    return (g.signal_id, population, g.method, g.horizon, g.basis["basis_id"], reason,
            dumps_jsonb(detail, default=str), dumps_jsonb(safe_tags, default=str),
            grader_version, run_id)


async def insert_holds(conn, records: List[Tuple]) -> int:
    written = 0
    for rec in records:
        res = await conn.execute(
            "INSERT INTO shadow_grade_holds (signal_id, population, method, horizon, basis_id, "
            "reason, detail, tags, grader_version, run_id) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8::jsonb,$9,$10) "
            "ON CONFLICT (signal_id, population, method, horizon, basis_id) DO NOTHING", *rec)
        written += int(str(res).strip().endswith("1"))
    return written


async def load_holds(conn, population: str) -> List[Dict[str, Any]]:
    rows = await conn.fetch(
        "SELECT signal_id, method, horizon, reason, tags FROM shadow_grade_holds "
        "WHERE population = $1", population)
    out = []
    for r in rows:
        d = dict(r)
        t = d.get("tags")
        d["tags"] = json.loads(t) if isinstance(t, str) else (t or {})
        out.append(d)
    return out


def grade_record(g, population: str, sign: int, tags: Dict[str, Any], grader_version: str,
                 run_id: Optional[int]) -> Tuple:
    """The positional insert tuple for one GRADED grade (column order = WRITE_COLUMNS)."""
    safe_tags = {k: v for k, v in tags.items() if not k.startswith("_")}
    return (g.signal_id, population, g.method, g.horizon, g.anchor_session, g.target_session,
            g.entry_raw, g.entry_factor, g.entry_basis, g.anchor_close, g.exit_price,
            g.ret_pct, g.ret_raw_pct, g.ret_v2_pct, g.r_multiple, g.outcome, sign,
            g.basis["basis_id"], dumps_jsonb(g.basis, default=str), list(g.flags),
            dumps_jsonb(safe_tags, default=str), grader_version, run_id)


async def insert_grades(conn, records: List[Tuple]) -> int:
    if not records:
        return 0
    cols = ", ".join(WRITE_COLUMNS)
    ph = ", ".join(f"${i}" + ("::jsonb" if c in ("basis", "tags") else "")
                   for i, c in enumerate(WRITE_COLUMNS, start=1))
    sql = (f"INSERT INTO shadow_grades ({cols}) VALUES ({ph}) "
           "ON CONFLICT (signal_id, population, method, horizon) DO NOTHING")
    written = 0
    for rec in records:
        res = await conn.execute(sql, *rec)
        written += int(str(res).strip().endswith("1"))
    return written


async def start_run(conn, kind: str, population: str, grader_version: str,
                    params: Dict[str, Any]) -> int:
    try:
        from build_identity import build_identity
        commit = (build_identity() or {}).get("commit")
    except Exception:
        commit = None
    return await conn.fetchval(
        "INSERT INTO backtest_runs (kind, population, grader_version, code_commit, params) "
        "VALUES ($1, $2, $3, $4, $5::jsonb) RETURNING id",
        kind, population, grader_version, commit, dumps_jsonb(params, default=str))


async def finish_run(conn, run_id: int, status: str, counts: Dict[str, Any],
                     error: Optional[str] = None) -> None:
    await conn.execute(
        "UPDATE backtest_runs SET finished_at = NOW(), status = $2, counts = $3::jsonb, "
        "error = $4 WHERE id = $1",
        run_id, status, dumps_jsonb(counts, default=str), (error or "")[:500] or None)


async def load_graded(conn, population: str) -> List[Dict[str, Any]]:
    rows = await conn.fetch(
        "SELECT signal_id, method, horizon, anchor_session, exit_session AS target_session, "
        "ret_pct, ret_raw_pct, ret_v2_pct, r_multiple, outcome, direction_sign, flags, tags, "
        "basis_id FROM shadow_grades WHERE population = $1", population)
    out = []
    for r in rows:
        d = dict(r)
        for k in ("ret_pct", "ret_raw_pct", "ret_v2_pct", "r_multiple"):
            d[k] = float(d[k]) if d[k] is not None else None
        t = d.get("tags")
        d["tags"] = json.loads(t) if isinstance(t, str) else (t or {})
        d["flags"] = list(d.get("flags") or [])
        out.append(d)
    return out


async def write_results(conn, run_id: int, population: str, results: Iterable[Dict[str, Any]]) -> int:
    n = 0
    for r in results:
        s = r["summary"]
        await conn.execute(
            "INSERT INTO backtest_results (run_id, population, cell, method, horizon, stratum, "
            "first_anchor, last_anchor, trades, win_rate, mean_ret_pct, profit_factor, "
            "avg_winner_r, avg_loser_r, expectancy_r, max_dd_r, sharpe, summary) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18::jsonb)",
            run_id, population, r["cell"], r["method"], r["horizon"], r.get("stratum", "ALL"),
            r.get("first_anchor"), r.get("last_anchor"), s.get("n", 0),
            s.get("hit", s.get("win_rate")), s.get("mean"), s.get("pf", s.get("pf_r")),
            s.get("avg_win_r"), s.get("avg_loss_r"), s.get("expectancy_r"), s.get("max_dd_r"),
            s.get("sharpe"), dumps_jsonb(s, default=str))
        n += 1
    return n
