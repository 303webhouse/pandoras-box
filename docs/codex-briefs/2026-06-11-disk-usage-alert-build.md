# Build Brief — Global Postgres Volume Disk-Usage Alert (Item 1)

**Status:** DRAFT for review. Small, low-risk, monitoring-only (read-only query + Discord alert).
No schema/data writes, no market-hours gate. Ships behind a go-ahead.
**Goal:** warn *before* the volume fills again (the 2026-06-11 crash) — a global, volume-%-based
daily check, alerting at **>70%**, routed through the existing Discord alert path.
**Source:** disk-maintenance brief item 1 + Phase 0 findings.

---

## Why this, not the existing guard

`analytics/price_collector.py` already has a DB-size guard (`VOLUME_WARN_MB=250` / `VOLUME_ABORT_MB=300`,
`send_alert`, cooldown) — but it's **too narrow**: DB-MB-based, only runs during the price-collection
cycle, and its ABORT only stops *price_history* writes. The volume still filled from `signals`/
`factor_readings`. **This brief adds a GLOBAL, volume-%-based daily check** and **reuses** the existing
helpers (`send_alert`, the `pg_database_size` pattern). Keep the price_collector guard as-is — it
protects the price-write path; this is the system-wide early-warning. (A future cleanup could unify them.)

## Key constraint (read it)

The app container **cannot** read the Postgres volume's real free space (separate container), so usage
is approximated as **`pg_database_size / DB_VOLUME_CAPACITY_MB`**. This **undercounts WAL (~80 MB) +
temp + overhead**, so:
- Keep the threshold **conservative** (70% on DB-size leaves margin for WAL/overhead).
- **`DB_VOLUME_CAPACITY_MB` must be kept in sync with the real Railway volume size** whenever Nick
  resizes it (it's 5 GB now → default 5120). Document this next to the env var.

---

## Code — drop-in

### New file: `backend/jobs/disk_usage_monitor.py`
```python
"""
Global Postgres volume disk-usage early-warning (read-only).

Root-cause prevention for the 2026-06-11 disk-full crash: warn BEFORE the volume fills.
Complements analytics/price_collector.py's price-collection-scoped 250/300 MB guard — this
is a GLOBAL, volume-%-based daily check.

NOTE: the app container can't read the Postgres volume's real free space (separate container),
so usage ≈ pg_database_size / DB_VOLUME_CAPACITY_MB. This undercounts WAL (~80 MB) + temp/overhead,
so the threshold stays conservative. KEEP DB_VOLUME_CAPACITY_MB in sync with the Railway volume size.
"""
from __future__ import annotations

import logging
import os

from database.postgres_client import get_postgres_client

logger = logging.getLogger(__name__)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name) or default)
    except (TypeError, ValueError):
        return default


DB_VOLUME_CAPACITY_MB = _int_env("DB_VOLUME_CAPACITY_MB", 5120)  # 5 GB Railway volume — UPDATE ON RESIZE
DB_VOLUME_WARN_PCT = _int_env("DB_VOLUME_WARN_PCT", 70)
DB_VOLUME_CRIT_PCT = _int_env("DB_VOLUME_CRIT_PCT", 85)


async def check_disk_usage() -> dict:
    """Read-only: DB size vs configured volume capacity; Discord alert if over threshold."""
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            size_bytes = await conn.fetchval("SELECT pg_database_size(current_database())")
    except Exception as exc:
        logger.warning("Disk usage check: could not read pg_database_size: %s", exc)
        return {"error": str(exc)}

    db_mb = (size_bytes or 0) / (1024 * 1024)
    pct = (db_mb / DB_VOLUME_CAPACITY_MB * 100) if DB_VOLUME_CAPACITY_MB else 0.0
    level = "critical" if pct >= DB_VOLUME_CRIT_PCT else "warning" if pct >= DB_VOLUME_WARN_PCT else None

    logger.info(
        "Disk usage: %.0f MB / %d MB (%.1f%%) level=%s",
        db_mb, DB_VOLUME_CAPACITY_MB, pct, level or "ok",
    )

    if level:
        try:
            from bias_engine.anomaly_alerts import send_alert
            await send_alert(
                title=f"Postgres volume {level.upper()} — {pct:.0f}% of {DB_VOLUME_CAPACITY_MB} MB",
                description=(
                    f"Database is {db_mb:.0f} MB of a configured {DB_VOLUME_CAPACITY_MB} MB volume "
                    f"({pct:.0f}%). Thresholds: warn={DB_VOLUME_WARN_PCT}% crit={DB_VOLUME_CRIT_PCT}%.\n"
                    "Excludes WAL/temp/overhead — real volume usage is higher. "
                    "Grow the Railway volume or run the disk-retention brief (REINDEX + archival)."
                ),
                severity=level,
            )
        except Exception as exc:
            logger.warning("Disk usage alert send failed: %s", exc)

    return {"db_mb": round(db_mb, 1), "capacity_mb": DB_VOLUME_CAPACITY_MB,
            "pct": round(pct, 1), "level": level}
```

### Register in `backend/main.py` (inside `lifespan`, with the other scan loops)
```python
    async def disk_usage_monitor_loop():
        """Daily global volume disk-usage early-warning."""
        await asyncio.sleep(300)  # 5 min after startup
        while True:
            try:
                from jobs.disk_usage_monitor import check_disk_usage
                await check_disk_usage()
            except Exception as e:
                logger.warning("Disk usage monitor error: %s", e)
            await asyncio.sleep(86400)  # daily
```
And register alongside the existing tasks (next to `holy_grail_task = asyncio.create_task(...)`):
```python
    disk_task = asyncio.create_task(disk_usage_monitor_loop())
```

---

## Config (env, all optional with safe defaults)
| Env | Default | Meaning |
|-----|---------|---------|
| `DB_VOLUME_CAPACITY_MB` | `5120` | Railway volume size in MB — **update when the volume is resized** |
| `DB_VOLUME_WARN_PCT` | `70` | warning threshold (brief's number) |
| `DB_VOLUME_CRIT_PCT` | `85` | critical threshold |

Discord routing reuses `DISCORD_WEBHOOK_ALERTS` (already used by `send_alert`). No new secret.

## Cadence
Daily (`86400`s) — one cheap query/day; gives years of lead time at current growth. The brief
suggested weekly; daily is negligible cost and earlier warning. (Alternative host: the 11:30 UTC
pre-market briefing — but a Railway-side loop is self-contained and queries the DB it protects, so
it doesn't depend on the VPS briefing system.)

## Verify (post-ship)
1. Logs show `Disk usage: <N> MB / 5120 MB (<pct>%) level=ok` ~5 min after deploy, then daily.
2. Temporarily set `DB_VOLUME_WARN_PCT=5` (env) → confirm a Discord alert fires to the alerts channel
   → revert to 70. (Or call `check_disk_usage()` once from a shell with the low threshold.)
3. Confirm no alert at the real ~6% (320 MB / 5120 MB).

## Out of scope
Items 2 (price_history REINDEX + drop the redundant `idx_price_ticker_tf`), 3 (archival — held), and
4 (orphan drops — blocked: live refs). This brief is the alert only.
