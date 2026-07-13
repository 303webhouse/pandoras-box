"""UW budget watchdog — in-hub runtime circuit breaker + daily-burn snapshot.

Fable-approved design (2026-07-09), replacing the env-var shed:

  1. 24/7 ~5-min job reads the running daily UW total (get_daily_count).
     (2026-07-10 lesson: the first real 17K crossing happened AFTER the close —
     the counter accumulates on the UTC day, so the watchdog watches the UTC day.)
     >= SHED_THRESHOLD (17,000) -> set a same-day RUNTIME shed flag
     (Redis `quota_shed:triton`, TTL to the next UTC rollover so it matches the
     counter reset). The Triton shadow poller checks the flag at the top of each
     cycle and skips while set. Fire EXACTLY ONE Discord alert (first set of the
     day, via SET NX) + record in stable_job_status. Committee/radar priority is
     preserved; shadow research yields, never the reverse.

  2. Escalation ladder: >= ESCALATE_THRESHOLD (18,000) fire a SECOND alert naming
     next-tier shed candidates for a HUMAN call. NOTHING beyond Triton sheds
     automatically.

  3. Why runtime flag, not env var: `railway variables set TRITON_SHADOW_ENABLED
     =false` forces a mid-session redeploy (60-170s hub outage) and violates the
     RTH blackout. The env var remains a MANUAL fallback only. This guard needs no
     env change, no redeploy, and no external session/cron alive — if the backend
     is down, no UW calls are happening anyway, so it's fail-safe by construction.

  4. Daily-burn snapshot (run_daily_burn_snapshot): at rollover, persist the prior
     UTC day's per-caller + grand total to `uw_daily_burn` so the 48h Redis TTL on
     the counters can never blind us again (7/6-7/8 were lost twice this way).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone, date
from typing import Optional

logger = logging.getLogger("uw_budget_watchdog")

SHED_THRESHOLD = 17_000       # >= this -> auto-shed Triton
ESCALATE_THRESHOLD = 18_000   # >= this -> human-call alert (no further auto-shed)

SHED_KEY = "quota_shed:triton"          # Triton poller reads this each cycle
ESCALATE_KEY = "quota_shed:escalation_18k"

# Over-provisioned / non-live-trading callers a human could shed next, in order.
# (ohlc_bars is 2.6x its quota; sector/technical feeds go visibly stale, acceptable.)
NEXT_TIER_SHED_CANDIDATES = ["ohlc_bars", "technical_indicator", "ohlc_sector"]


def _seconds_to_utc_rollover() -> int:
    """TTL so the shed flag clears exactly at the UTC-date rollover — the same
    boundary at which the daily counter resets (keys are `...:{utc-date}`)."""
    now = datetime.now(timezone.utc)
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(60, int((nxt - now).total_seconds()))


def _sdecode(v):
    return v.decode() if isinstance(v, (bytes, bytearray)) else v


async def is_triton_shed() -> bool:
    """Called by the Triton poller at the top of each cycle. Fail-open: if Redis
    is unreadable, return False (do NOT block the poller on an infra blip — the
    watchdog will re-shed on its next tick if the budget is truly over)."""
    try:
        from database.redis_client import get_redis_client
        r = await get_redis_client()
        if not r:
            return False
        return bool(await r.get(SHED_KEY))
    except Exception:
        return False


async def _discord_alert(title: str, description: str, color: int = 0xFF4444) -> bool:
    """One Discord alert on the circuit-breaker channel. Mirrors strc_monitor.
    AEGIS: never logs the webhook URL. Returns True if posted."""
    url = os.getenv("DISCORD_WEBHOOK_CB") or ""
    if not url:
        logger.warning("DISCORD_WEBHOOK_CB not set — budget alert suppressed: %s", title)
        return False
    import httpx
    payload = {"embeds": [{
        "title": title,
        "description": description,
        "color": color,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "Pandora's Box — UW Budget Watchdog"},
    }]}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            return resp.status_code in (200, 204)
    except Exception as e:
        logger.error("budget alert Discord post failed: %s", type(e).__name__)
        return False


async def run_budget_watchdog(injected_total: Optional[int] = None) -> dict:
    """One watchdog tick. Never raises (fail-open).

    injected_total is a TEST SEAM (acceptance test only) — when provided, the live
    get_daily_count() read is bypassed. Production always passes None.
    """
    from stable_engine import job_status
    result = {"total": None, "shed": False, "escalated": False, "alert_fired": False}
    try:
        if injected_total is not None:
            total = injected_total
        else:
            from integrations.uw_api_cache import get_daily_count
            total = await get_daily_count()
        result["total"] = total

        from database.redis_client import get_redis_client
        r = await get_redis_client()

        if total >= SHED_THRESHOLD and r:
            ttl = _seconds_to_utc_rollover()
            was_set = await r.set(SHED_KEY, "1", nx=True, ex=ttl)  # first-of-day only
            result["shed"] = True
            if was_set:  # exactly-once alert per UTC day
                result["alert_fired"] = True
                await _discord_alert(
                    "UW Budget Circuit Breaker — Triton SHED",
                    f"Daily UW total hit **{total:,}** (>= {SHED_THRESHOLD:,}). "
                    f"Triton shadow poller **auto-shed** for the rest of the UTC day "
                    f"(flag `{SHED_KEY}`, clears at rollover). Committee / flow-radar "
                    f"priority preserved. Manual clear: `DEL {SHED_KEY}`.",
                )
                await job_status.mark_failure(
                    "uw_budget_shed", f"total={total} >= {SHED_THRESHOLD} -> Triton shed"
                )

        if total >= ESCALATE_THRESHOLD and r:
            esc_set = await r.set(ESCALATE_KEY, "1", nx=True, ex=_seconds_to_utc_rollover())
            if esc_set:
                result["escalated"] = True
                result["alert_fired"] = True
                await _discord_alert(
                    "UW Budget — 18K ESCALATION (human call required)",
                    f"Daily UW total hit **{total:,}** (>= {ESCALATE_THRESHOLD:,}), nearing the "
                    f"20K plan cap. Triton is already shed. Next-tier shed candidates for a "
                    f"**HUMAN** decision (NOT auto-shed): {', '.join(NEXT_TIER_SHED_CANDIDATES)}. "
                    f"Review /api/uw/health/by_caller.",
                    color=0xFF0000,
                )

        # Clean tick -> reset the shed ledger entry so it reads green once we're back under.
        if not result["shed"]:
            await job_status.mark_success("uw_budget_shed")
        await job_status.mark_success("uw_budget_watchdog")
    except Exception as e:
        logger.warning("budget watchdog error: %s", e)
    return result


async def run_daily_burn_snapshot(target_date: Optional[date] = None) -> dict:
    """Persist a completed UTC day's per-caller + grand-total UW burn to
    `uw_daily_burn` (idempotent upsert) so the 48h Redis TTL can never blind us.
    Reads the still-alive prior-date counter keys. target_date is a test seam;
    production snapshots yesterday. Never raises."""
    from database.postgres_client import get_postgres_client
    from database.redis_client import get_redis_client
    d = target_date or (datetime.now(timezone.utc).date() - timedelta(days=1))
    dstr = d.isoformat()
    result = {"date": dstr, "rows": 0, "grand_total": None}
    try:
        r = await get_redis_client()
        pool = await get_postgres_client()
        if not r or not pool:
            return result
        raw = await r.hgetall(f"uw:daily_requests_by_caller:{dstr}")
        per_caller = {}
        for k, v in (raw or {}).items():
            k = _sdecode(k); v = _sdecode(v)
            try:
                per_caller[k] = int(v)
            except (TypeError, ValueError):
                continue
        grand = _sdecode(await r.get(f"uw:daily_requests:{dstr}"))
        try:
            grand = int(grand) if grand is not None else sum(per_caller.values())
        except (TypeError, ValueError):
            grand = sum(per_caller.values())
        result["grand_total"] = grand
        if not per_caller and grand == 0:
            return result  # nothing to snapshot (no traffic that day)

        async with pool.acquire() as conn:
            await conn.execute(
                """CREATE TABLE IF NOT EXISTS uw_daily_burn (
                       day      DATE NOT NULL,
                       caller   TEXT NOT NULL,
                       count    INT  NOT NULL,
                       snapshotted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                       PRIMARY KEY (day, caller)
                   )"""
            )
            rows = list(per_caller.items()) + [("_TOTAL", grand)]
            for caller, cnt in rows:
                await conn.execute(
                    """INSERT INTO uw_daily_burn (day, caller, count, snapshotted_at)
                       VALUES ($1::text::date, $2, $3, now())
                       ON CONFLICT (day, caller)
                       DO UPDATE SET count = EXCLUDED.count, snapshotted_at = now()""",
                    dstr, caller, int(cnt),
                )
            result["rows"] = len(rows)
        logger.info("uw_daily_burn snapshot %s: %d callers, grand_total=%s", dstr, len(per_caller), grand)
    except Exception as e:
        logger.warning("uw_daily_burn snapshot error: %s", e)
    return result
