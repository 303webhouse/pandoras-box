"""
Aggregation queries for performance reviews and analytics.

All functions are synchronous; wrap in asyncio.to_thread() when calling
from async contexts (cron_runner, Discord bot).
"""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Optional

from journal.db import get_connection
from journal.trades import get_streak

logger = logging.getLogger(__name__)

ACCOUNT_BALANCE_401K = float(os.getenv("ACCOUNT_BALANCE_401K", "8100"))
ACCOUNT_BALANCE_RH = float(os.getenv("ACCOUNT_BALANCE_RH", "4698"))


def _row_to_dict(row) -> dict:
    return dict(row) if row is not None else {}


def _week_bounds(weeks_ago: int = 0) -> tuple[str, str]:
    """Return ISO date strings for the Monday–Friday of the target week."""
    today = date.today()
    # Monday of current week
    monday = today - timedelta(days=today.weekday())
    # Shift back by the requested number of weeks
    monday -= timedelta(weeks=weeks_ago)
    friday = monday + timedelta(days=4)
    return monday.isoformat(), friday.isoformat()


def _account_stats(trades: list[dict]) -> dict:
    """Compute per-account stats from a list of closed trade dicts."""
    closed = [t for t in trades if t.get("status") == "closed"]
    wins = [t for t in closed if (t.get("pnl_dollars") or 0) >= 0]
    losses = [t for t in closed if (t.get("pnl_dollars") or 0) < 0]

    total_pnl = sum(t.get("pnl_dollars") or 0 for t in closed)
    avg_winner = (
        sum(t.get("pnl_dollars") or 0 for t in wins) / len(wins) if wins else 0.0
    )
    avg_loser = (
        sum(t.get("pnl_dollars") or 0 for t in losses) / len(losses) if losses else 0.0
    )
    largest_win = max((t.get("pnl_dollars") or 0 for t in wins), default=0.0)
    largest_loss = min((t.get("pnl_dollars") or 0 for t in losses), default=0.0)

    followed = [
        t for t in closed if t.get("followed_plan") is not None
    ]
    followed_plan_pct = (
        sum(1 for t in followed if t.get("followed_plan") == 1) / len(followed)
        if followed
        else None
    )

    return {
        "trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(closed) if closed else 0.0,
        "total_pnl": round(total_pnl, 2),
        "avg_winner": round(avg_winner, 2),
        "avg_loser": round(avg_loser, 2),
        "largest_win": round(largest_win, 2),
        "largest_loss": round(largest_loss, 2),
        "followed_plan_pct": round(followed_plan_pct, 3) if followed_plan_pct is not None else None,
    }


def weekly_summary(
    weeks_ago: int = 0,
    account: Optional[str] = None,
) -> dict:
    """
    Generate weekly performance summary.

    Returns a dict with period, by_account stats, totals, streaks,
    rule_violations, and bias_alignment.
    """
    start, end = _week_bounds(weeks_ago)

    conn = get_connection()
    try:
        if account:
            rows = conn.execute(
                "SELECT * FROM trades WHERE entry_date >= ? AND entry_date <= ? "
                "AND account = ? ORDER BY entry_date ASC",
                (start, end, account),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM trades WHERE entry_date >= ? AND entry_date <= ? "
                "ORDER BY entry_date ASC",
                (start, end),
            ).fetchall()
    finally:
        conn.close()

    trades = [_row_to_dict(r) for r in rows]

    # Group by account
    by_account: dict[str, list[dict]] = {}
    for t in trades:
        acc = t.get("account", "unknown")
        by_account.setdefault(acc, []).append(t)

    account_stats = {acc: _account_stats(acct_trades) for acc, acct_trades in by_account.items()}

    # Totals across all accounts
    all_closed = [t for t in trades if t.get("status") == "closed"]
    total_pnl = sum(t.get("pnl_dollars") or 0 for t in all_closed)
    total_wins = sum(1 for t in all_closed if (t.get("pnl_dollars") or 0) >= 0)

    totals = {
        "trades": len(all_closed),
        "net_pnl": round(total_pnl, 2),
        "win_rate": round(total_wins / len(all_closed), 3) if all_closed else 0.0,
    }

    # Streaks (uses all-time closed trades for accuracy)
    current_streak = get_streak(account)

    # Rule violations
    rule_violations: list[str] = []
    rh_same_day: dict[str, int] = {}
    for t in trades:
        if t.get("status") == "cancelled":
            continue
        trade_account = t.get("account")
        max_loss = t.get("max_loss")

        # 401k: max_loss > 1% of balance (~$81)
        if trade_account == "401k" and max_loss is not None:
            limit = ACCOUNT_BALANCE_401K * 0.01
            if max_loss > limit:
                rule_violations.append(
                    f"Trade {t['id']} ({t.get('ticker')}): 401k max_loss "
                    f"${max_loss} exceeds 1% limit (${limit:.0f})"
                )

        # Robinhood: max_loss > 5% of balance (~$235)
        if trade_account == "robinhood" and max_loss is not None:
            limit = ACCOUNT_BALANCE_RH * 0.05
            if max_loss > limit:
                rule_violations.append(
                    f"Trade {t['id']} ({t.get('ticker')}): Robinhood max_loss "
                    f"${max_loss} exceeds 5% limit (${limit:.0f})"
                )

        # Robinhood same-day overtrading (> 1 trade same day)
        if trade_account == "robinhood":
            edate = t.get("entry_date", "")
            rh_same_day[edate] = rh_same_day.get(edate, 0) + 1

        # Counter-bias trade without thesis
        bias = t.get("bias_at_entry")
        direction = t.get("direction")
        thesis = t.get("thesis")
        if bias and direction:
            bearish_bias = bias in ("ursa_major", "ursa_minor")
            bullish_bias = bias in ("toro_major", "toro_minor")
            counter = (bearish_bias and direction == "long") or (
                bullish_bias and direction == "short"
            )
            if counter and not thesis:
                rule_violations.append(
                    f"Trade {t['id']} ({t.get('ticker')}): counter-bias trade "
                    f"({direction} with {bias}) has no thesis"
                )

    for edate, count in rh_same_day.items():
        if count > 1:
            rule_violations.append(
                f"Overtrading: {count} Robinhood trades on {edate}"
            )

    # Bias alignment
    with_bias = 0
    against_bias = 0
    against_bias_won = 0
    for t in all_closed:
        bias = t.get("bias_at_entry")
        direction = t.get("direction")
        pnl = t.get("pnl_dollars") or 0
        if not bias or not direction:
            continue
        bearish_bias = bias in ("ursa_major", "ursa_minor")
        bullish_bias = bias in ("toro_major", "toro_minor")
        aligned = (bearish_bias and direction == "short") or (
            bullish_bias and direction == "long"
        ) or bias == "neutral"
        if aligned:
            with_bias += 1
        else:
            against_bias += 1
            if pnl >= 0:
                against_bias_won += 1

    return {
        "period": {"start": start, "end": end},
        "by_account": account_stats,
        "totals": totals,
        "streaks": {
            "current": {
                "type": current_streak["type"],
                "count": current_streak["count"],
            }
        },
        "rule_violations": rule_violations,
        "bias_alignment": {
            "with_bias": with_bias,
            "against_bias": against_bias,
            "against_bias_won": against_bias_won,
        },
    }


def daily_summary(date: Optional[str] = None, account: Optional[str] = None) -> dict:
    """
    Generate daily P&L summary for a given date (defaults to today).
    Used by EOD brief.
    """
    from datetime import date as date_type
    target_date = date or date_type.today().isoformat()

    conn = get_connection()
    try:
        if account:
            rows = conn.execute(
                "SELECT * FROM trades WHERE exit_date = ? AND status = 'closed' "
                "AND account = ?",
                (target_date, account),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM trades WHERE exit_date = ? AND status = 'closed'",
                (target_date,),
            ).fetchall()
    finally:
        conn.close()

    trades = [_row_to_dict(r) for r in rows]

    by_account: dict[str, dict] = {}
    for t in trades:
        acc = t.get("account", "unknown")
        if acc not in by_account:
            by_account[acc] = {"pnl": 0.0, "trades": 0, "wins": 0, "losses": 0}
        pnl = t.get("pnl_dollars") or 0
        by_account[acc]["pnl"] = round(by_account[acc]["pnl"] + pnl, 2)
        by_account[acc]["trades"] += 1
        if pnl >= 0:
            by_account[acc]["wins"] += 1
        else:
            by_account[acc]["losses"] += 1

    total_pnl = sum(v["pnl"] for v in by_account.values())

    return {
        "date": target_date,
        "by_account": by_account,
        "total_pnl": round(total_pnl, 2),
    }


def rule_compliance_check(trade_id: int) -> list[str]:
    """
    Check a specific trade against Playbook risk rules.
    Returns a list of violations (empty list = compliant).
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM trades WHERE id = ?", (trade_id,)
        ).fetchone()
        if row is None:
            return [f"Trade {trade_id} not found"]
        trade = _row_to_dict(row)

        # Count same-day same-account trades for overtrading check
        same_day_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM trades WHERE account = ? AND entry_date = ? "
            "AND status != 'cancelled'",
            (trade.get("account"), trade.get("entry_date")),
        ).fetchone()["cnt"]
    finally:
        conn.close()

    violations: list[str] = []
    account = trade.get("account")
    max_loss = trade.get("max_loss")
    direction = trade.get("direction")
    bias = trade.get("bias_at_entry")
    thesis = trade.get("thesis")

    if account == "401k" and max_loss is not None:
        limit = ACCOUNT_BALANCE_401K * 0.01
        if max_loss > limit:
            violations.append(
                f"Max loss ${max_loss} exceeds 401k 1% rule (limit: ${limit:.0f})"
            )

    if account == "robinhood" and max_loss is not None:
        limit = ACCOUNT_BALANCE_RH * 0.05
        if max_loss > limit:
            violations.append(
                f"Max loss ${max_loss} exceeds Robinhood 5% rule (limit: ${limit:.0f})"
            )

    if account == "robinhood" and same_day_count > 1:
        violations.append(
            f"Overtrading: {same_day_count} Robinhood trades on {trade.get('entry_date')}"
        )

    if bias and direction:
        bearish_bias = bias in ("ursa_major", "ursa_minor")
        bullish_bias = bias in ("toro_major", "toro_minor")
        counter = (bearish_bias and direction == "long") or (
            bullish_bias and direction == "short"
        )
        if counter and not thesis:
            violations.append(
                f"Counter-bias trade ({direction} with {bias}) has no thesis documented"
            )

    return violations


def ticker_history(ticker: str) -> dict:
    """
    Performance history for a specific ticker across all accounts.
    Returns trades, win_rate, total_pnl, avg_hold_time, common_strategies.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM trades WHERE ticker = ? AND status = 'closed' "
            "ORDER BY entry_date DESC",
            (ticker,),
        ).fetchall()
    finally:
        conn.close()

    trades = [_row_to_dict(r) for r in rows]
    wins = [t for t in trades if (t.get("pnl_dollars") or 0) >= 0]
    total_pnl = sum(t.get("pnl_dollars") or 0 for t in trades)

    # Average hold time in days
    hold_times = []
    for t in trades:
        if t.get("entry_date") and t.get("exit_date"):
            try:
                from datetime import date as date_type
                entry = date_type.fromisoformat(t["entry_date"])
                exit_ = date_type.fromisoformat(t["exit_date"])
                hold_times.append((exit_ - entry).days)
            except ValueError:
                pass
    avg_hold_time = round(sum(hold_times) / len(hold_times), 1) if hold_times else None

    # Most common strategies
    strategy_counts: dict[str, int] = {}
    for t in trades:
        s = t.get("strategy")
        if s:
            strategy_counts[s] = strategy_counts.get(s, 0) + 1
    common_strategies = sorted(strategy_counts, key=strategy_counts.get, reverse=True)[:3]  # type: ignore[arg-type]

    return {
        "ticker": ticker,
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(trades) - len(wins),
        "win_rate": round(len(wins) / len(trades), 3) if trades else 0.0,
        "total_pnl": round(total_pnl, 2),
        "avg_hold_time_days": avg_hold_time,
        "common_strategies": common_strategies,
    }


def monthly_summary(year: int, month: int) -> dict:
    """
    Monthly rollup. Similar structure to weekly_summary but for the full month.
    """
    import calendar
    start = f"{year:04d}-{month:02d}-01"
    last_day = calendar.monthrange(year, month)[1]
    end = f"{year:04d}-{month:02d}-{last_day:02d}"

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM trades WHERE entry_date >= ? AND entry_date <= ? "
            "ORDER BY entry_date ASC",
            (start, end),
        ).fetchall()
    finally:
        conn.close()

    trades = [_row_to_dict(r) for r in rows]

    by_account: dict[str, list[dict]] = {}
    for t in trades:
        acc = t.get("account", "unknown")
        by_account.setdefault(acc, []).append(t)

    account_stats = {
        acc: _account_stats(acct_trades) for acc, acct_trades in by_account.items()
    }

    all_closed = [t for t in trades if t.get("status") == "closed"]
    total_pnl = sum(t.get("pnl_dollars") or 0 for t in all_closed)
    total_wins = sum(1 for t in all_closed if (t.get("pnl_dollars") or 0) >= 0)

    return {
        "period": {"start": start, "end": end, "year": year, "month": month},
        "by_account": account_stats,
        "totals": {
            "trades": len(all_closed),
            "net_pnl": round(total_pnl, 2),
            "win_rate": round(total_wins / len(all_closed), 3) if all_closed else 0.0,
        },
    }
