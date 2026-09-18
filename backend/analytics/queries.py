"""
Reusable SQL query builders and data access helpers for analytics endpoints.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from database.postgres_client import get_postgres_client
from utils.json_sanitize import dumps_jsonb


def _utc_now_naive() -> datetime:
    return datetime.utcnow().replace(tzinfo=None)


def _parse_date(value: Optional[str], end_of_day: bool = False) -> Optional[datetime]:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    if end_of_day and len(text) <= 10:
        dt = dt + timedelta(days=1) - timedelta(microseconds=1)
    return dt


def window_bounds(days: int = 30, start: Optional[str] = None, end: Optional[str] = None) -> Tuple[datetime, datetime]:
    now = _utc_now_naive()
    end_dt = _parse_date(end, end_of_day=True) or now
    start_dt = _parse_date(start) or (end_dt - timedelta(days=max(1, int(days))))
    return start_dt, end_dt


async def fetch_rows(query: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(row) for row in rows]


async def fetch_row(query: str, params: Sequence[Any] = ()) -> Optional[Dict[str, Any]]:
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *params)
    return dict(row) if row else None


async def fetch_val(query: str, params: Sequence[Any] = ()) -> Any:
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        return await conn.fetchval(query, *params)


def _signal_conditions(
    source: Optional[str] = None,
    ticker: Optional[str] = None,
    direction: Optional[str] = None,
    bias_regime: Optional[str] = None,
    alias: str = "s",
) -> Tuple[List[str], List[Any]]:
    conditions: List[str] = []
    params: List[Any] = []

    if source:
        params.append(f"%{source}%")
        conditions.append(
            f"(LOWER({alias}.strategy) LIKE LOWER(${len(params)}) OR LOWER({alias}.signal_type) LIKE LOWER(${len(params)}))"
        )

    if ticker:
        params.append(ticker.upper())
        conditions.append(f"UPPER({alias}.ticker) = ${len(params)}")

    if direction:
        value = direction.upper()
        if value in {"BULLISH", "LONG", "BUY"}:
            conditions.append(f"UPPER({alias}.direction) IN ('LONG', 'BUY', 'BULLISH')")
        elif value in {"BEARISH", "SHORT", "SELL"}:
            conditions.append(f"UPPER({alias}.direction) IN ('SHORT', 'SELL', 'BEARISH')")
        else:
            params.append(value)
            conditions.append(f"UPPER({alias}.direction) = ${len(params)}")

    if bias_regime:
        params.append(bias_regime.upper())
        conditions.append(f"UPPER(COALESCE({alias}.bias_level, '')) = ${len(params)}")

    return conditions, params


async def get_signal_stats_rows(
    source: Optional[str] = None,
    ticker: Optional[str] = None,
    direction: Optional[str] = None,
    days: int = 30,
    bias_regime: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> List[Dict[str, Any]]:
    start_dt, end_dt = window_bounds(days=days, start=start, end=end)
    conditions = ["s.timestamp >= $1", "s.timestamp <= $2"]
    params: List[Any] = [start_dt, end_dt]

    dynamic_conditions, dynamic_params = _signal_conditions(
        source=source,
        ticker=ticker,
        direction=direction,
        bias_regime=bias_regime,
        alias="s",
    )
    for cond in dynamic_conditions:
        # Shift positional indexes by existing param count.
        offset = len(params)
        rewritten = cond
        for idx in range(len(dynamic_params), 0, -1):
            rewritten = rewritten.replace(f"${idx}", f"${idx + offset}")
        conditions.append(rewritten)
    params.extend(dynamic_params)

    query = f"""
        SELECT
            s.id,
            s.signal_id,
            s.timestamp,
            s.strategy,
            s.signal_type,
            s.ticker,
            s.direction,
            s.asset_class,
            s.timeframe,
            s.bias_level,
            s.bias_alignment,
            s.day_of_week,
            s.hour_of_day,
            s.is_opex_week,
            s.days_to_earnings,
            s.market_event,
            s.score,
            s.entry_price,
            s.stop_loss,
            s.target_1,
            s.target_2,
            s.risk_reward,
            s.user_action,
            s.dismissed_at,
            s.selected_at,
            s.notes,
            s.triggering_factors,
            s.bias_at_signal,
            EXISTS(
                SELECT 1
                FROM trades t
                WHERE t.signal_id = s.signal_id
            ) AS traded,
            so.outcome,
            so.outcome_at,
            so.max_favorable,
            so.max_adverse,
            so.entry,
            so.days_to_outcome,
            so.outcome_price
        FROM signals s
        LEFT JOIN signal_outcomes so
            ON so.signal_id = s.signal_id
        WHERE {" AND ".join(conditions)}
        ORDER BY s.timestamp DESC
    """
    return await fetch_rows(query, params)


# ── WHICH ROLLUP READS WHAT (R-IV.451(d)) ─────────────────────────────────────────────────
#
# Written down because a fix was credited to the wrong mechanism once already: the partition
# change in /trade-stats was correct and did not remove the BITX double count, because that
# rollup never read the table the double count lived in.
#
#   /api/analytics/trade-stats    get_trade_rows -> trades          (realized, win rate, curve)
#   /api/analytics/trades         get_trade_rows -> trades          (the list)
#   /api/analytics/export/trades  get_trade_rows -> trades          (the CSV)
#   /api/v2/positions*            unified_positions                 (the book)
#   /api/portfolio/positions/closed  closed_positions               (legacy closed list)
#
# `trades` is filled by ONE write path (the close endpoint). R-IV.451(a) rules that analytics
# reads the book instead; until that ships, every figure above carries `book_coverage` so a
# reader can see what the figure is missing. The ruling's order: (1) analytics reads the book,
# (2) realized metrics go live on Abacus, (3) trades retires or becomes a labelled import log.


async def book_coverage_gap() -> Dict[str, Any]:
    """What the book holds that `trades` does not, computed live. Never raises.

    Live rather than quoted: the ruling measured 77 closes and -1,373.64, and those figures move
    every time a position closes by a path that is not the close endpoint. A chip carrying a
    number from the day it was written is the stale-figure defect in a new place.

    Populations, each named by its method (conventions #18):
      unlinked        CLOSED/EXPIRED with no trade_id — no record the close endpoint wrote
      absent          unlinked AND no same-ticker same-day trades row — nothing plausible either
      unknown_result  CLOSED/EXPIRED with neither realized nor outcome — ended, result unrecorded
      trades_orphans  closed trades rows with no book row that day — IN this figure, NOT in the
                      book (added after the acceptance test: the gap runs BOTH ways)

    CORRECTED 2026-09-18. The first version measured one direction only -- what the book holds
    that `trades` lacks. The acceptance test for the read-from-book build found the other: 70
    closed trades in this figure with no book row at all (+356.10, historical imports). A chip
    naming only what a figure is missing reads as "the rest is right", and it was not.
    """
    try:
        rows = await fetch_rows(
            """
            WITH ended AS (
                SELECT p.*,
                       EXISTS (SELECT 1 FROM trades t
                                WHERE t.ticker = p.ticker
                                  AND t.closed_at::date = p.exit_date::date) AS plausible
                  FROM unified_positions p
                 WHERE p.status IN ('CLOSED', 'EXPIRED')
            )
            SELECT
                COUNT(*) FILTER (WHERE trade_id IS NULL)                      AS unlinked,
                COUNT(*) FILTER (WHERE trade_id IS NULL AND exit_date IS NOT NULL
                                   AND NOT plausible)                         AS absent,
                COALESCE(SUM(realized_pnl) FILTER (WHERE trade_id IS NULL
                                   AND exit_date IS NOT NULL AND NOT plausible), 0)
                                                                              AS absent_realized,
                COUNT(*) FILTER (WHERE realized_pnl IS NULL
                                   AND trade_outcome IS NULL)                 AS unknown_result
              FROM ended
            """, [])
        # CORRECTED AGAIN, same day: "no book row that day" stopped seeing trades whose day DOES
        # hold a book row that could not be paired with them -- a second trade, or a duplicate
        # record. After the import those were the only ones left, and the chip went quiet about
        # them. The count that matters is every closed trade not LINKED to the book; the strict
        # no-book-row-at-all figure is kept beside it as its own partition.
        orphans = await fetch_rows(
            """
            SELECT COUNT(*) AS n, COALESCE(SUM(t.pnl_dollars), 0) AS pnl,
                   COUNT(*) FILTER (WHERE NOT EXISTS (
                       SELECT 1 FROM unified_positions p
                        WHERE p.ticker = t.ticker
                          AND p.exit_date::date = t.closed_at::date
                          AND UPPER(p.status) <> 'OPEN')) AS no_book_row
              FROM trades t
             WHERE LOWER(t.status) IN ('closed', 'expired')
               AND NOT EXISTS (SELECT 1 FROM unified_positions p WHERE p.trade_id = t.id)
            """, [])
        r = rows[0] if rows else {}
        o = orphans[0] if orphans else {}
        absent = int(r.get("absent") or 0)
        absent_realized = round(float(r.get("absent_realized") or 0), 2)
        orphan_n = int(o.get("n") or 0)
        orphan_pnl = round(float(o.get("pnl") or 0), 2)
        orphan_strict = int(o.get("no_book_row") or 0)
        parts = []
        if absent:
            parts.append(f"{absent} closes ({absent_realized:+,.2f} realized) are in the book "
                         f"but not in this figure")
        if orphan_n:
            parts.append(f"{orphan_n} trades ({orphan_pnl:+,.2f}) in this figure are not linked "
                         f"to the book ({orphan_strict} with no book row at all)")
        return {
            "source": "trades",
            "book_source": "unified_positions",
            "unlinked_closes": int(r.get("unlinked") or 0),
            "absent_closes": absent,
            "absent_realized": absent_realized,
            "unknown_result_closes": int(r.get("unknown_result") or 0),
            "trades_orphans": orphan_n,
            "trades_orphans_pnl": orphan_pnl,
            "trades_orphans_no_book_row": orphan_strict,
            "complete": absent == 0 and orphan_n == 0,
            "chip": "; ".join(parts) if parts else None,
            "ruling": "R-IV.451(a): analytics reads the book; until then this figure is partial",
        }
    except Exception as exc:
        # An unmeasurable gap is reported as unmeasured — never as complete.
        return {"source": "trades", "complete": None,
                "chip": "coverage of the book could not be measured for this figure",
                "error": type(exc).__name__}


# ── THE BOOK READER (R-IV.451(a), R-IV.454(f)) ─────────────────────────────────────────────
#
# Analytics reads the book. `trades` is filled by one write path, so every position ended any
# other way was missing from every analytics figure (77 closes, -1,373.64 realized, when ruled).
# This reads `unified_positions` and projects each row into the shape the analytics routes
# already consume, so their contracts do not move -- only their source does.
#
# THE SIX RULINGS, each implemented where it is enforced:
#   (1) exit_date windows a terminal row's realized; entry_date windows an open row.
#   (2) a terminal row with NO RESULT is counted and never summed: pnl_dollars stays None, and
#       `result_known` says so, so no rollup can mistake it for a flat trade.
#   (3) retired duplicates are excluded by the vocabulary (position_status), and counted.
#   (4) the account filter reads every alias (models.accounts.scope_for).
#   (5) realized is the row's own figure now; lot closures take over when that table has rows.
#   (6) percent return is realized / |cost_basis|, and NULL when the basis is NULL or zero --
#       the source of the impossible percentages on the principal's screen.
#
# AND THE NULL-PREDICATE RULE (R-IV.454(b)): a terminal row with no exit_date cannot be placed
# in a window, so it is returned FLAGGED `undated`, never silently dropped. The rollup keeps it
# out of windowed sums and surfaces it as its own line.

BOOK_FIELDS_NOT_IN_BOOK = ("rr_achieved", "risk_pct", "bias_at_entry",
                           "account_balance_at_open", "exit_reason")


def _aware(dt):
    from datetime import timezone as _tz
    return dt.replace(tzinfo=_tz.utc) if dt is not None and dt.tzinfo is None else dt


def book_row_to_trade_shape(r: Dict[str, Any]) -> Dict[str, Any]:
    """One book row in the trades shape. Pure, so the projection is testable without a database."""
    from models import position_status as PS

    status = PS.normalize(r.get("status"))
    terminal = PS.counts_as_realized(status)
    realized = r.get("realized_pnl")
    basis = r.get("cost_basis")
    pnl = (float(realized) if realized is not None else None) if terminal else (
        float(r["unrealized_pnl"]) if r.get("unrealized_pnl") is not None else None)
    pct = None
    if pnl is not None and basis is not None and float(basis) != 0:
        pct = round(pnl / abs(float(basis)) * 100.0, 4)
    return {
        "id": r.get("id"),
        "position_id": r.get("position_id"),
        "trade_id": r.get("trade_id"),
        "ticker": r.get("ticker"),
        "direction": r.get("direction"),
        "structure": r.get("structure"),
        "account": r.get("account"),
        "status": status.lower(),
        "opened_at": r.get("entry_date"),
        "closed_at": r.get("exit_date"),
        "pnl_dollars": pnl,
        "pnl_percent": pct,
        "origin": (r.get("source") or "manual").lower(),
        "signal_id": r.get("signal_id"),
        "signal_source": r.get("linked_signal_strategy"),
        "linked_signal_strategy": r.get("linked_signal_strategy"),
        "linked_signal_type": r.get("linked_signal_type"),
        "linked_signal_bias": r.get("linked_signal_bias"),
        "trade_outcome": r.get("trade_outcome"),
        "notes": r.get("notes"),
        "cost_basis": float(basis) if basis is not None else None,
        "result_known": (not terminal) or realized is not None,
        "undated": terminal and r.get("exit_date") is None,
        "backfill_exempt": PS.is_backfill_exempt(r),
        "source_table": "unified_positions",
        # Present in the trades shape, absent from the book: named rather than invented.
        **{f: None for f in BOOK_FIELDS_NOT_IN_BOOK},
    }


async def get_book_rows(
    account: Optional[str] = None,
    ticker: Optional[str] = None,
    direction: Optional[str] = None,
    structure: Optional[str] = None,
    origin: Optional[str] = None,
    days: int = 90,
    signal_source: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Dict[str, Any]:
    """The book, windowed and projected. Returns {"rows": [...], "retired_excluded": n}.

    Terminal rows are windowed on exit_date, open rows on entry_date, and a terminal row with
    no exit_date is included FLAGGED rather than dropped (the NULL-predicate rule).
    """
    from models import position_status as PS
    from models.accounts import scope_for

    start_dt, end_dt = window_bounds(days=days, start=start, end=end)
    params: List[Any] = [_aware(start_dt), _aware(end_dt)]
    conditions = ["""(
        (UPPER(p.status) = 'OPEN' AND (p.entry_date IS NULL OR p.entry_date BETWEEN $1 AND $2))
        OR (UPPER(p.status) <> 'OPEN' AND (p.exit_date IS NULL OR p.exit_date BETWEEN $1 AND $2))
    )"""]
    if account:
        params.append([s.upper() for s in scope_for(account)])
        conditions.append(f"UPPER(COALESCE(p.account, '')) = ANY(${len(params)}::text[])")
    if ticker:
        params.append(ticker.upper())
        conditions.append(f"UPPER(p.ticker) = ${len(params)}")
    if direction:
        params.append(direction.upper())
        conditions.append(f"UPPER(COALESCE(p.direction, '')) = ${len(params)}")
    if structure:
        params.append(structure.lower())
        conditions.append(f"LOWER(COALESCE(p.structure, '')) = ${len(params)}")
    if origin:
        params.append(origin.lower())
        conditions.append(f"LOWER(COALESCE(p.source, 'manual')) = ${len(params)}")
    if signal_source:
        params.append(f"%{signal_source}%")
        conditions.append(f"LOWER(COALESCE(s.strategy, '')) LIKE LOWER(${len(params)})")

    raw = await fetch_rows(f"""
        SELECT p.*,
               s.strategy   AS linked_signal_strategy,
               s.signal_type AS linked_signal_type,
               s.bias_level AS linked_signal_bias
          FROM unified_positions p
          LEFT JOIN signals s ON s.signal_id = p.signal_id
         WHERE {" AND ".join(conditions)}
         ORDER BY COALESCE(p.exit_date, p.entry_date) ASC NULLS LAST, p.id ASC
    """, params)
    retired = [r for r in raw if PS.is_retired(r.get("status"))]
    rows = [book_row_to_trade_shape(r) for r in raw if not PS.is_retired(r.get("status"))]
    return {"rows": rows, "retired_excluded": len(retired)}


async def get_trade_rows(
    account: Optional[str] = None,
    ticker: Optional[str] = None,
    direction: Optional[str] = None,
    structure: Optional[str] = None,
    origin: Optional[str] = None,
    days: int = 90,
    signal_source: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> List[Dict[str, Any]]:
    start_dt, end_dt = window_bounds(days=days, start=start, end=end)
    conditions = ["COALESCE(t.opened_at, NOW()) >= $1", "COALESCE(t.opened_at, NOW()) <= $2"]
    params: List[Any] = [start_dt, end_dt]

    if account:
        params.append(account.upper())
        conditions.append(f"UPPER(COALESCE(t.account, '')) = ${len(params)}")
    if ticker:
        params.append(ticker.upper())
        conditions.append(f"UPPER(t.ticker) = ${len(params)}")
    if direction:
        params.append(direction.upper())
        conditions.append(f"UPPER(COALESCE(t.direction, '')) = ${len(params)}")
    if structure:
        params.append(structure.lower())
        conditions.append(f"LOWER(COALESCE(t.structure, '')) = ${len(params)}")
    if origin:
        params.append(origin.lower())
        conditions.append(f"LOWER(COALESCE(t.origin, 'manual')) = ${len(params)}")
    if signal_source:
        params.append(f"%{signal_source}%")
        conditions.append(
            f"(LOWER(COALESCE(t.signal_source, '')) LIKE LOWER(${len(params)}) "
            f"OR LOWER(COALESCE(s.strategy, '')) LIKE LOWER(${len(params)}))"
        )

    query = f"""
        SELECT
            t.*,
            s.strategy AS linked_signal_strategy,
            s.signal_type AS linked_signal_type,
            s.bias_level AS linked_signal_bias
        FROM trades t
        LEFT JOIN signals s ON s.signal_id = t.signal_id
        WHERE {" AND ".join(conditions)}
        ORDER BY COALESCE(t.opened_at, NOW()) ASC
    """
    return await fetch_rows(query, params)


async def get_factor_rows(
    factor: Optional[str] = None,
    days: int = 60,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> List[Dict[str, Any]]:
    start_dt, end_dt = window_bounds(days=days, start=start, end=end)
    conditions = ["f.collected_at >= $1", "f.collected_at <= $2"]
    params: List[Any] = [start_dt, end_dt]
    if factor:
        params.append(factor)
        conditions.append(f"f.factor_name = ${len(params)}")

    query = f"""
        SELECT
            f.factor_name,
            f.score,
            f.bias,
            f.data,
            f.collected_at
        FROM factor_history f
        WHERE {" AND ".join(conditions)}
        ORDER BY f.collected_at ASC
    """
    return await fetch_rows(query, params)


async def get_spy_daily_closes(
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    conditions = ["ticker = 'SPY'", "timeframe = 'D'", "close IS NOT NULL"]
    params: List[Any] = []
    if start is not None:
        params.append(start.replace(tzinfo=timezone.utc))
        conditions.append(f"timestamp >= ${len(params)}")
    if end is not None:
        params.append(end.replace(tzinfo=timezone.utc))
        conditions.append(f"timestamp <= ${len(params)}")

    query = f"""
        SELECT
            DATE(timestamp) AS day,
            timestamp,
            close
        FROM price_history
        WHERE {" AND ".join(conditions)}
        ORDER BY timestamp ASC
    """
    rows = await fetch_rows(query, params)
    dedup: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        day = str(row.get("day"))
        dedup[day] = row
    ordered = [dedup[key] for key in sorted(dedup.keys())]
    return ordered


async def get_price_bars(
    ticker: str,
    timeframe: str,
    start_ts: datetime,
    end_ts: datetime,
) -> List[Dict[str, Any]]:
    query = """
        SELECT timestamp, open, high, low, close, volume
        FROM price_history
        WHERE UPPER(ticker) = UPPER($1)
          AND timeframe = $2
          AND timestamp >= $3
          AND timestamp <= $4
        ORDER BY timestamp ASC
    """
    params = [ticker.upper(), timeframe, start_ts.replace(tzinfo=timezone.utc), end_ts.replace(tzinfo=timezone.utc)]
    return await fetch_rows(query, params)


async def get_strategy_sources(days: int = 30, ticker: Optional[str] = None) -> List[str]:
    start_dt, end_dt = window_bounds(days=days)
    conditions = ["timestamp >= $1", "timestamp <= $2"]
    params: List[Any] = [start_dt, end_dt]
    if ticker:
        params.append(ticker.upper())
        conditions.append(f"UPPER(ticker) = ${len(params)}")
    query = f"""
        SELECT DISTINCT strategy
        FROM signals
        WHERE {" AND ".join(conditions)}
          AND strategy IS NOT NULL
        ORDER BY strategy
    """
    rows = await fetch_rows(query, params)
    return [str(row["strategy"]) for row in rows if row.get("strategy")]


async def get_convergence_candidate_rows(
    days: int = 30,
    ticker: Optional[str] = None,
) -> List[Dict[str, Any]]:
    start_dt, end_dt = window_bounds(days=days)
    conditions = ["s.timestamp >= $1", "s.timestamp <= $2"]
    params: List[Any] = [start_dt, end_dt]
    if ticker:
        params.append(ticker.upper())
        conditions.append(f"UPPER(s.ticker) = ${len(params)}")

    query = f"""
        SELECT
            s.signal_id,
            s.timestamp,
            s.ticker,
            s.direction,
            s.strategy,
            so.outcome,
            so.entry,
            so.max_favorable,
            so.max_adverse
        FROM signals s
        LEFT JOIN signal_outcomes so ON so.signal_id = s.signal_id
        WHERE {" AND ".join(conditions)}
        ORDER BY s.timestamp ASC
    """
    return await fetch_rows(query, params)


async def get_latest_portfolio_snapshots(account: Optional[str] = None) -> List[Dict[str, Any]]:
    conditions = ["1=1"]
    params: List[Any] = []
    if account:
        params.append(account.upper())
        conditions.append(f"UPPER(account) = ${len(params)}")
    query = f"""
        WITH ranked AS (
            SELECT
                *,
                ROW_NUMBER() OVER (PARTITION BY account ORDER BY timestamp DESC) AS rn
            FROM portfolio_snapshots
            WHERE {" AND ".join(conditions)}
        )
        SELECT *
        FROM ranked
        WHERE rn = 1
        ORDER BY account
    """
    return await fetch_rows(query, params)


async def get_latest_benchmarks() -> Dict[str, float]:
    query = """
        WITH ranked AS (
            SELECT
                benchmark,
                cumulative_return,
                ROW_NUMBER() OVER (PARTITION BY benchmark ORDER BY timestamp DESC) AS rn
            FROM benchmarks
        )
        SELECT benchmark, cumulative_return
        FROM ranked
        WHERE rn = 1
    """
    rows = await fetch_rows(query)
    return {
        str(row.get("benchmark")): float(row.get("cumulative_return") or 0.0)
        for row in rows
        if row.get("benchmark")
    }


async def get_signals_for_backtest(
    source: Optional[str],
    ticker: Optional[str],
    direction: Optional[str],
    start_date: str,
    end_date: str,
) -> List[Dict[str, Any]]:
    start_dt, end_dt = window_bounds(days=30, start=start_date, end=end_date)
    conditions = ["s.timestamp >= $1", "s.timestamp <= $2", "s.entry_price IS NOT NULL"]
    params: List[Any] = [start_dt, end_dt]
    extra_conditions, extra_params = _signal_conditions(
        source=source,
        ticker=ticker,
        direction=direction,
        alias="s",
    )
    for cond in extra_conditions:
        offset = len(params)
        rewritten = cond
        for idx in range(len(extra_params), 0, -1):
            rewritten = rewritten.replace(f"${idx}", f"${idx + offset}")
        conditions.append(rewritten)
    params.extend(extra_params)

    query = f"""
        SELECT
            s.signal_id,
            s.timestamp,
            s.ticker,
            s.direction,
            s.strategy,
            s.signal_type,
            s.entry_price,
            s.stop_loss,
            s.target_1,
            s.target_2,
            s.score,
            s.bias_alignment
        FROM signals s
        WHERE {" AND ".join(conditions)}
        ORDER BY s.timestamp ASC
    """
    return await fetch_rows(query, params)


async def get_schema_table_summary() -> Dict[str, Dict[str, Any]]:
    tables = [
        "signals",
        "trades",
        "signal_outcomes",
        "factor_history",
        "price_history",
        "trade_legs",
        "benchmarks",
        "portfolio_snapshots",
        "strategy_health",
        "health_alerts",
        "uw_snapshots",
    ]
    summary: Dict[str, Dict[str, Any]] = {}
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        for table in tables:
            exists = await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", f"public.{table}")
            if not exists:
                summary[table] = {"rows": 0, "exists": False}
                continue

            rows = int(await conn.fetchval(f"SELECT COUNT(*) FROM {table}") or 0)
            stats: Dict[str, Any] = {"rows": rows, "exists": True}

            if table == "signals":
                oldest = await conn.fetchval("SELECT MIN(timestamp) FROM signals")
                newest = await conn.fetchval("SELECT MAX(timestamp) FROM signals")
                stats["oldest"] = oldest.isoformat() if oldest else None
                stats["newest"] = newest.isoformat() if newest else None
            elif table == "trades":
                open_count = int(await conn.fetchval("SELECT COUNT(*) FROM trades WHERE LOWER(COALESCE(status,'open')) = 'open'") or 0)
                closed_count = int(await conn.fetchval("SELECT COUNT(*) FROM trades WHERE LOWER(COALESCE(status,'')) IN ('closed','win','loss')") or 0)
                stats["open"] = open_count
                stats["closed"] = closed_count
            elif table == "signal_outcomes":
                pending = int(await conn.fetchval("SELECT COUNT(*) FROM signal_outcomes WHERE outcome = 'PENDING'") or 0)
                stats["pending"] = pending
            elif table == "price_history":
                oldest = await conn.fetchval("SELECT MIN(timestamp) FROM price_history")
                newest = await conn.fetchval("SELECT MAX(timestamp) FROM price_history")
                tickers = int(await conn.fetchval("SELECT COUNT(DISTINCT ticker) FROM price_history") or 0)
                stats["oldest"] = oldest.isoformat() if oldest else None
                stats["newest"] = newest.isoformat() if newest else None
                stats["tickers"] = tickers
            elif table == "health_alerts":
                try:
                    unresolved = int(
                        await conn.fetchval("SELECT COUNT(*) FROM health_alerts WHERE resolved_at IS NULL") or 0
                    )
                    stats["unresolved"] = unresolved
                except Exception:
                    stats["unresolved"] = 0
            elif table == "uw_snapshots":
                oldest = await conn.fetchval("SELECT MIN(timestamp) FROM uw_snapshots")
                newest = await conn.fetchval("SELECT MAX(timestamp) FROM uw_snapshots")
                stats["oldest"] = oldest.isoformat() if oldest else None
                stats["newest"] = newest.isoformat() if newest else None

            summary[table] = stats

    return summary


async def insert_trade(trade: Dict[str, Any]) -> Dict[str, Any]:
    query = """
        INSERT INTO trades (
            signal_id, ticker, direction, status, account, structure,
            signal_source, entry_price, stop_loss, target_1, quantity,
            opened_at, notes, pivot_recommendation, pivot_conviction,
            full_context, bias_at_entry, risk_amount,
            origin, strike, expiry, short_strike, long_strike,
            closed_at, exit_price, pnl_dollars, pnl_percent, rr_achieved, exit_reason
        ) VALUES (
            $1, $2, $3, $4, $5, $6,
            $7, $8, $9, $10, $11,
            $12, $13, $14, $15,
            $16::jsonb, $17, $18,
            $19, $20, $21, $22, $23,
            $24, $25, $26, $27, $28, $29
        )
        RETURNING *
    """
    params = [
        trade.get("signal_id"),
        trade.get("ticker"),
        trade.get("direction"),
        trade.get("status", "open"),
        trade.get("account"),
        trade.get("structure"),
        trade.get("signal_source"),
        trade.get("entry_price"),
        trade.get("stop_loss"),
        trade.get("target_1"),
        trade.get("quantity"),
        trade.get("opened_at") or _utc_now_naive().replace(tzinfo=timezone.utc),
        trade.get("notes"),
        trade.get("pivot_recommendation"),
        trade.get("pivot_conviction"),
        dumps_jsonb(trade.get("full_context") or {}),
        trade.get("bias_at_entry"),
        trade.get("risk_amount"),
        trade.get("origin") or "manual",
        trade.get("strike"),
        trade.get("expiry"),
        trade.get("short_strike"),
        trade.get("long_strike"),
        trade.get("closed_at"),
        trade.get("exit_price"),
        trade.get("pnl_dollars"),
        trade.get("pnl_percent"),
        trade.get("rr_achieved"),
        trade.get("exit_reason"),
    ]
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *params)
    return dict(row) if row else {}


async def find_matching_signals(
    ticker: str,
    direction: str,
    entry_timestamp: datetime,
    window_hours: int = 4,
) -> List[str]:
    """
    Find likely matching signals around a trade entry window.
    """
    if not ticker or not direction or not entry_timestamp:
        return []

    dir_upper = str(direction).upper()
    if dir_upper in {"LONG", "BUY"}:
        candidates = ["LONG", "BUY", "BULLISH"]
    elif dir_upper in {"SHORT", "SELL"}:
        candidates = ["SHORT", "SELL", "BEARISH"]
    else:
        candidates = [dir_upper]

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT signal_id
            FROM signals
            WHERE LOWER(ticker) = LOWER($1)
              AND UPPER(direction) = ANY($2::text[])
              AND timestamp BETWEEN ($3::timestamp - ($4::int * INTERVAL '1 hour'))
                              AND ($3::timestamp + ($4::int * INTERVAL '1 hour'))
            ORDER BY ABS(EXTRACT(EPOCH FROM (timestamp - $3::timestamp)))
            LIMIT 5
            """,
            ticker,
            candidates,
            entry_timestamp,
            max(1, int(window_hours)),
        )
    return [str(row["signal_id"]) for row in rows if row.get("signal_id")]


async def trade_exists_duplicate(
    ticker: str,
    direction: Optional[str],
    entry_date: Optional[datetime],
    strike: Optional[float],
    short_strike: Optional[float],
) -> bool:
    if not ticker or not entry_date:
        return False

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id
            FROM trades
            WHERE UPPER(ticker) = UPPER($1)
              AND ($2::text IS NULL OR UPPER(COALESCE(direction,'')) = UPPER($2))
              AND DATE(COALESCE(opened_at, NOW())) BETWEEN (DATE($3::timestamp) - 1) AND (DATE($3::timestamp) + 1)
              AND (
                    ($4::numeric IS NULL AND strike IS NULL)
                    OR ABS(COALESCE(strike, 0) - COALESCE($4, 0)) < 0.01
                  )
              AND (
                    ($5::numeric IS NULL AND short_strike IS NULL)
                    OR ABS(COALESCE(short_strike, 0) - COALESCE($5, 0)) < 0.01
                  )
            LIMIT 1
            """,
            ticker,
            direction,
            entry_date,
            strike,
            short_strike,
        )
    return row is not None


async def close_trade(trade_id: int, update: Dict[str, Any]) -> Dict[str, Any]:
    query = """
        UPDATE trades
        SET
            status = COALESCE($2, status),
            closed_at = COALESCE($3, closed_at),
            exit_price = COALESCE($4, exit_price),
            pnl_dollars = COALESCE($5, pnl_dollars),
            pnl_percent = COALESCE($6, pnl_percent),
            rr_achieved = COALESCE($7, rr_achieved),
            exit_reason = COALESCE($8, exit_reason),
            notes = COALESCE($9, notes)
        WHERE id = $1
        RETURNING *
    """
    params = [
        trade_id,
        update.get("status"),
        update.get("closed_at") or _utc_now_naive().replace(tzinfo=timezone.utc),
        update.get("exit_price"),
        update.get("pnl_dollars"),
        update.get("pnl_percent"),
        update.get("rr_achieved"),
        update.get("exit_reason"),
        update.get("notes"),
    ]
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *params)
    return dict(row) if row else {}


async def insert_trade_leg(payload: Dict[str, Any]) -> Dict[str, Any]:
    query = """
        INSERT INTO trade_legs (
            trade_id, timestamp, action, direction, quantity, price,
            strike, expiry, leg_type, commission, notes
        ) VALUES (
            $1, $2, $3, $4, $5, $6,
            $7, $8, $9, $10, $11
        )
        RETURNING *
    """
    params = [
        payload.get("trade_id"),
        payload.get("timestamp") or _utc_now_naive().replace(tzinfo=timezone.utc),
        payload.get("action"),
        payload.get("direction"),
        payload.get("quantity"),
        payload.get("price"),
        payload.get("strike"),
        payload.get("expiry"),
        payload.get("leg_type"),
        payload.get("commission", 0.0),
        payload.get("notes"),
    ]
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *params)
    return dict(row) if row else {}


async def insert_uw_snapshot(payload: Dict[str, Any]) -> Dict[str, Any]:
    query = """
        INSERT INTO uw_snapshots (
            timestamp, dashboard_type, time_slot, extracted_data, raw_summary, signal_alignment
        ) VALUES (
            COALESCE($1, NOW()), $2, $3, $4::jsonb, $5, $6
        )
        RETURNING *
    """
    params = [
        payload.get("timestamp"),
        payload.get("dashboard_type"),
        payload.get("time_slot"),
        dumps_jsonb(payload.get("extracted_data") or {}),
        payload.get("raw_summary"),
        payload.get("signal_alignment"),
    ]
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *params)
    return dict(row) if row else {}


async def get_uw_snapshot_rows(
    days: int = 1,
    dashboard_type: Optional[str] = None,
    time_slot: Optional[str] = None,
) -> List[Dict[str, Any]]:
    start_dt, end_dt = window_bounds(days=max(1, days))
    conditions = ["timestamp >= $1", "timestamp <= $2"]
    params: List[Any] = [start_dt, end_dt]
    if dashboard_type:
        params.append(dashboard_type)
        conditions.append(f"LOWER(dashboard_type) = LOWER(${len(params)})")
    if time_slot:
        params.append(time_slot)
        conditions.append(f"LOWER(COALESCE(time_slot,'')) = LOWER(${len(params)})")
    query = f"""
        SELECT *
        FROM uw_snapshots
        WHERE {" AND ".join(conditions)}
        ORDER BY timestamp DESC
    """
    return await fetch_rows(query, params)
