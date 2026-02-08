"""
APScheduler runner for Pivot.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, time
from pathlib import Path
from typing import Dict, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo

from collectors.config import TIMEZONE
from collectors import (
    factor_credit_spreads,
    factor_market_breadth,
    factor_vix_term,
    factor_tick_breadth,
    factor_sector_rotation,
    factor_dollar_smile,
    factor_excess_cape,
    factor_savita,
    sector_strength,
    health_check,
)
from collectors.base_collector import post_pivot_alert
from monitors.bias_shift import check_bias_shift
from monitors.cta_zones import check_cta_zones
from monitors.factor_velocity import check_factor_velocity
from monitors.volume_anomaly import check_volume_anomalies
from monitors.earnings_calendar import check_earnings
from monitors.economic_calendar import check_economic_calendar
from notifications.discord import send_discord
from llm.pivot_agent import call_llm
from llm.prompts import build_morning_brief_prompt, build_eod_prompt, build_anomaly_prompt
from collectors.base_collector import get_json

logger = logging.getLogger(__name__)

TZ = ZoneInfo(TIMEZONE)

COOLDOWN_PATH = Path(__file__).resolve().parents[1] / "state" / "cooldowns.json"
COOLDOWNS = {
    "bias_shift": 1800,
    "cta_zone": 900,
    "factor_velocity": 3600,
    "volume_spike": 1800,
    "earnings": 7200,
    "economic": 7200,
}


def _configure_logging() -> None:
    from logging.handlers import TimedRotatingFileHandler

    fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    root.addHandler(stream_handler)

    log_path = Path(__file__).resolve().parents[1] / "logs" / "pivot.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = TimedRotatingFileHandler(log_path, when="midnight", backupCount=7)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)


def _load_cooldowns() -> Dict[str, Any]:
    try:
        if COOLDOWN_PATH.exists():
            return json.loads(COOLDOWN_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_cooldowns(data: Dict[str, Any]) -> None:
    try:
        COOLDOWN_PATH.parent.mkdir(parents=True, exist_ok=True)
        COOLDOWN_PATH.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def _should_send(key: str, cooldown_seconds: int) -> bool:
    state = _load_cooldowns()
    last = state.get(key)
    now_ts = datetime.utcnow().timestamp()
    if last and now_ts - last < cooldown_seconds:
        return False
    state[key] = now_ts
    _save_cooldowns(state)
    return True


def _is_market_hours(now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    start = time(9, 30)
    end = time(16, 0)
    return start <= now.time() <= end


async def run_all_factors() -> int:
    tasks = [
        factor_credit_spreads.collect_and_post(),
        factor_market_breadth.collect_and_post(),
        factor_vix_term.collect_and_post(),
        factor_tick_breadth.collect_and_post(),
        factor_sector_rotation.collect_and_post(),
        factor_dollar_smile.collect_and_post(),
        factor_excess_cape.collect_and_post(),
        factor_savita.collect_and_post(),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    count = 0
    for result in results:
        if isinstance(result, Exception):
            logger.warning(f"Factor job failed: {result}")
            continue
        if result is not None:
            count += 1
    return count


async def run_pre_market():
    logger.info("Pre-market factor pull")
    count = await run_all_factors()
    await health_check.collect_and_post(factors_collected=count)


async def run_post_open():
    logger.info("Post-open factor pull")
    count = await run_all_factors()
    await health_check.collect_and_post(factors_collected=count)


async def run_intraday_factors():
    logger.info("Intraday factor refresh")
    count = await run_all_factors()
    await health_check.collect_and_post(factors_collected=count)


async def run_post_close():
    logger.info("Post-close factor pull")
    count = await run_all_factors()
    await health_check.collect_and_post(factors_collected=count)


async def run_sector_strength():
    logger.info("Sector strength refresh")
    await sector_strength.collect_and_post()


async def run_vix_only():
    logger.info("Extended-hours VIX check")
    await factor_vix_term.collect_and_post()


async def run_cape_only():
    logger.info("CAPE refresh")
    await factor_excess_cape.collect_and_post()


async def heartbeat_job():
    now = datetime.now(TZ)
    if not _is_market_hours(now):
        return

    logger.info("Heartbeat cycle")

    bias_shift = await check_bias_shift()
    if bias_shift and _should_send("bias_shift", COOLDOWNS["bias_shift"]):
        message = f"{bias_shift['previous']} → {bias_shift['current']} (score {bias_shift['score']})"
        await send_discord("critical", "Bias Shift", message, priority="CRITICAL")
        await post_pivot_alert({
            "type": "bias_shift",
            "message": message,
            "timestamp": bias_shift.get("timestamp"),
        })

    cta_changes = await check_cta_zones()
    if cta_changes and _should_send("cta_zone", COOLDOWNS["cta_zone"]):
        summary = ", ".join(f"{c['ticker']}: {c['previous']} → {c['current']}" for c in cta_changes[:5])
        await send_discord("signals", "CTA Zone Change", summary, priority="HIGH")
        await post_pivot_alert({
            "type": "cta_zone",
            "message": summary,
            "timestamp": datetime.utcnow().isoformat(),
        })

    velocity = await check_factor_velocity()
    if velocity and _should_send("factor_velocity", COOLDOWNS["factor_velocity"]):
        summary = ", ".join(f"{v['factor']} {v['delta']:+.2f}" for v in velocity)
        await send_discord("critical", "Rapid Factor Move", summary, priority="CRITICAL")
        await post_pivot_alert({
            "type": "factor_velocity",
            "message": summary,
            "timestamp": datetime.utcnow().isoformat(),
        })

    volume_anomalies = await check_volume_anomalies()
    if volume_anomalies and _should_send("volume_spike", COOLDOWNS["volume_spike"]):
        summary = ", ".join(
            f"{a['ticker']} {a['multiplier']}x"
            for a in volume_anomalies[:6]
        )
        await send_discord("signals", "Volume Spike", summary, priority="MEDIUM")
        await post_pivot_alert({
            "type": "volume_spike",
            "message": summary,
            "timestamp": datetime.utcnow().isoformat(),
        })

    earnings = await check_earnings()
    if earnings and _should_send("earnings", COOLDOWNS["earnings"]):
        summary = ", ".join(f"{e['ticker']} ({e['days_until']}d)" for e in earnings[:6])
        await send_discord("calendar", "Earnings Soon", summary, priority="MEDIUM")

    economic = await check_economic_calendar()
    if economic and _should_send("economic", COOLDOWNS["economic"]):
        summary = ", ".join(item.get("event", "event") for item in economic[:6])
        await send_discord("calendar", "Economic Events", summary, priority="MEDIUM")

    await health_check.collect_and_post()


async def morning_brief():
    try:
        composite = await get_json("/bias/composite")
        prompt = build_morning_brief_prompt(json.dumps(composite, indent=2))
        text = await call_llm(prompt, max_tokens=700)
        await send_discord("briefs", "Morning Brief", text, priority="MEDIUM")
    except Exception as exc:
        logger.warning(f"Morning brief failed: {exc}")


async def eod_brief():
    try:
        composite = await get_json("/bias/composite")
        prompt = build_eod_prompt(json.dumps(composite, indent=2))
        text = await call_llm(prompt, max_tokens=700)
        await send_discord("briefs", "EOD Summary", text, priority="MEDIUM")
    except Exception as exc:
        logger.warning(f"EOD summary failed: {exc}")


async def anomaly_brief(message: str):
    prompt = build_anomaly_prompt(message)
    text = await call_llm(prompt, max_tokens=400)
    await send_discord("critical", "Anomaly Detail", text, priority="CRITICAL")


def start_scheduler() -> None:
    scheduler = AsyncIOScheduler(timezone=TZ)

    scheduler.add_job(run_pre_market, CronTrigger(day_of_week="mon-fri", hour=6, minute=30, timezone=TZ))
    scheduler.add_job(run_post_open, CronTrigger(day_of_week="mon-fri", hour=9, minute=35, timezone=TZ))
    scheduler.add_job(run_intraday_factors, CronTrigger(day_of_week="mon-fri", hour=10, minute=30, timezone=TZ))
    scheduler.add_job(run_post_close, CronTrigger(day_of_week="mon-fri", hour=16, minute=5, timezone=TZ))
    scheduler.add_job(run_sector_strength, CronTrigger(day_of_week="mon-fri", hour=16, minute=15, timezone=TZ))

    scheduler.add_job(run_vix_only, CronTrigger(day_of_week="mon-fri", hour=17, minute=0, timezone=TZ))
    scheduler.add_job(run_cape_only, CronTrigger(day_of_week="mon-fri", hour="*/4", minute=0, timezone=TZ))

    scheduler.add_job(heartbeat_job, CronTrigger(day_of_week="mon-fri", minute="*/15", timezone=TZ))

    scheduler.add_job(morning_brief, CronTrigger(day_of_week="mon-fri", hour=6, minute=45, timezone=TZ))
    scheduler.add_job(eod_brief, CronTrigger(day_of_week="mon-fri", hour=16, minute=30, timezone=TZ))

    scheduler.start()
    logger.info("Pivot scheduler started")


async def _run_forever() -> None:
    start_scheduler()
    await asyncio.Event().wait()


if __name__ == "__main__":
    _configure_logging()
    asyncio.run(_run_forever())
