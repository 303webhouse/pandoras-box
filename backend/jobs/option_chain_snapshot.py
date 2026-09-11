"""S8 — daily option-chain snapshot for PS-02 (R-IV.361 addition).

THE COLLECTOR LAW APPLIES: THIS CANNOT BE RETROFITTED. There is no vendor call
that returns yesterday's bid/ask/IV as they stood at capture. A session not
captured is permanently absent from the eventual dataset, so this job's failure
mode matters more than its throughput.

WHAT IT CAPTURES
    SPY and QQQ, contracts expiring 30-45 calendar days out: strike, expiry,
    bid, ask, IV, open interest, volume -- as published AT CAPTURE.

TWO CALLS A DAY, and the cap that comes with them
    One `/option-contracts` call per ticker, unfiltered by expiry, then filtered
    to the DTE window here. UW caps that endpoint at 500 rows.

    A TRUNCATED CHAIN IS INDISTINGUISHABLE FROM A THIN ONE, so truncation is
    RECORDED rather than guarded against: `raw_contract_count` and `truncated`
    go into every row. If the cap binds, the data says so and a later reader can
    discount that session instead of averaging a censored sample.

    Stated plainly for the record: at 500 the capture IS incomplete, and the fix
    is per-expiry calls, which costs more budget than this job was given. The
    measurement decides that, not a guess -- which is why the count is stored
    from day one rather than added after someone notices.

CAPTURE TIME — 15:45 ET, a choice, not a default
    Late enough that the session's IV is meaningful, early enough that quotes are
    still live. A post-close capture would record stale, wide, untradeable
    spreads and would look like data.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

logger = logging.getLogger(__name__)

S8_TICKERS = ("SPY", "QQQ")
DTE_MIN = 30
DTE_MAX = 45
UW_CONTRACT_CAP = 500          # the documented per-call ceiling (uw_api.py:783-789)
JOB_NAME = "option_chain_snapshot"


def _dte(expiry: date, today: date) -> int:
    return (expiry - today).days


def _rows_from_chain(ticker: str, chain: list, today: date) -> tuple[list, int]:
    """(rows, raw_count). Filters to the DTE window; never raises on a bad contract."""
    raw = len(chain or [])
    out = []
    for c in chain or []:
        try:
            d = c.get("details") or {}
            exp_s = d.get("expiration_date")
            if not exp_s:
                continue
            exp = datetime.strptime(str(exp_s)[:10], "%Y-%m-%d").date()
            dte = _dte(exp, today)
            if not (DTE_MIN <= dte <= DTE_MAX):
                continue
            q = c.get("last_quote") or {}
            day = c.get("day") or {}
            out.append({
                "ticker": ticker,
                "expiry": exp,
                "dte": dte,
                "contract_type": d.get("contract_type"),
                "strike": d.get("strike_price"),
                "bid": q.get("bid"),
                "ask": q.get("ask"),
                "iv": c.get("implied_volatility"),
                "open_interest": day.get("open_interest"),
                "volume": day.get("volume"),
            })
        except Exception:
            # One malformed contract must not cost the session's capture.
            continue
    return out, raw


async def run_option_chain_snapshot(session_date: date | None = None) -> dict:
    """One capture pass. Never raises. Returns a small summary."""
    from database.postgres_client import get_postgres_client
    from integrations.uw_api import get_options_snapshot

    today = session_date or datetime.now(timezone.utc).date()
    summary = {"tickers": {}, "rows": 0, "truncated": []}

    pool = await get_postgres_client()
    if not pool:
        logger.warning("[s8] no db pool — capture lost for %s", today)
        return {"error": "no_db_pool", "rows": 0}

    for ticker in S8_TICKERS:
        try:
            chain = await get_options_snapshot(ticker)
        except Exception as exc:
            logger.warning("[s8] %s chain fetch failed: %s", ticker, type(exc).__name__)
            summary["tickers"][ticker] = {"error": type(exc).__name__}
            continue
        if not chain:
            logger.warning("[s8] %s chain empty — nothing captured", ticker)
            summary["tickers"][ticker] = {"rows": 0, "raw": 0}
            continue

        rows, raw = _rows_from_chain(ticker, chain, today)
        truncated = raw >= UW_CONTRACT_CAP
        if truncated:
            # Loud, because the row-level flag is for later readers and this is
            # for whoever can still widen the call today.
            logger.error("[s8] %s returned %d contracts >= cap %d — CAPTURE IS CENSORED",
                         ticker, raw, UW_CONTRACT_CAP)
            summary["truncated"].append(ticker)

        written = 0
        async with pool.acquire() as conn:
            for r in rows:
                try:
                    await conn.execute(
                        """
                        INSERT INTO option_chain_snapshots
                            (session_date, ticker, expiry, dte, contract_type, strike,
                             bid, ask, iv, open_interest, volume,
                             raw_contract_count, truncated, source)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,'uw')
                        ON CONFLICT (session_date, ticker, expiry, contract_type, strike)
                        DO UPDATE SET
                            captured_at = NOW(), bid = EXCLUDED.bid, ask = EXCLUDED.ask,
                            iv = EXCLUDED.iv, open_interest = EXCLUDED.open_interest,
                            volume = EXCLUDED.volume,
                            raw_contract_count = EXCLUDED.raw_contract_count,
                            truncated = EXCLUDED.truncated
                        """,
                        today, r["ticker"], r["expiry"], r["dte"], r["contract_type"],
                        r["strike"], r["bid"], r["ask"], r["iv"],
                        r["open_interest"], r["volume"], raw, truncated,
                    )
                    written += 1
                except Exception as exc:
                    logger.warning("[s8] row insert failed %s %s: %s",
                                   ticker, r.get("strike"), type(exc).__name__)
        summary["tickers"][ticker] = {"rows": written, "raw": raw, "truncated": truncated}
        summary["rows"] += written
        logger.info("[s8] %s captured %d contracts in %d-%d DTE (raw %d%s)",
                    ticker, written, DTE_MIN, DTE_MAX, raw,
                    ", TRUNCATED" if truncated else "")

    return summary


async def snapshot_status() -> dict:
    """For /health. A forward collection needs a surface that shows a missed day
    WHILE IT CAN STILL BE NOTICED -- the data itself can never show it later."""
    from database.postgres_client import get_postgres_client
    try:
        pool = await get_postgres_client()
        if not pool:
            return {"state": "UNKNOWN", "reason": "no pool"}
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT max(session_date) AS last_session, count(*) AS rows_total "
                "FROM option_chain_snapshots")
            last = row["last_session"] if row else None
            today = datetime.now(timezone.utc).date()
            age_days = (today - last).days if last else None
            return {
                "last_session": str(last) if last else None,
                "age_days": age_days,
                "rows_total": int(row["rows_total"] or 0) if row else 0,
                "tickers": list(S8_TICKERS),
                "dte_window": [DTE_MIN, DTE_MAX],
                "note": ("no capture yet — every session before the first is "
                         "permanently absent" if last is None else None),
            }
    except Exception as exc:
        return {"state": "ERROR", "reason": type(exc).__name__}
