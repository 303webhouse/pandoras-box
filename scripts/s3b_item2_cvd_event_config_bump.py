r"""S-3b Item 2: append the CVD event-detection thresholds to crypto_cycle_
config's existing cvd_events section (level_proximity_pct,
absorption_cvd_threshold_usd, local_extreme_lookback_bars, stop_buffer_pct,
target_rr). Append-only -- INSERT a new version, never UPDATE. Everything
else in the config carries forward unchanged.

Run from C:\trading-hub:
    python scripts\s3b_item2_cvd_event_config_bump.py
"""

from __future__ import annotations

import asyncio
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))

NEW_CVD_EVENT_KEYS = {
    "level_proximity_pct": 0.3,
    "absorption_cvd_threshold_usd": 50000.0,
    "local_extreme_lookback_bars": 12,
    "stop_buffer_pct": 0.5,
    "target_rr": 1.5,
}


def _find_mcp_config() -> str:
    candidates = [os.path.join(ROOT, ".mcp.json"), os.path.join("C:\\", "trading-hub", ".mcp.json")]
    for path in candidates:
        if os.path.exists(path):
            return path
    raise RuntimeError(".mcp.json not found -- run from a clone that has it.")


async def _get_pool():
    import asyncpg
    cfg = json.load(open(_find_mcp_config()))
    args = cfg["mcpServers"]["postgres"]["args"]
    url = next((a for a in reversed(args) if a.startswith("postgres")), None)
    if not url:
        raise RuntimeError("postgres URL not found in .mcp.json")
    return await asyncpg.create_pool(url, min_size=1, max_size=2)


async def main() -> int:
    pool = await _get_pool()
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT id, config FROM crypto_cycle_config ORDER BY id DESC LIMIT 1"
                )
                config = json.loads(row["config"]) if isinstance(row["config"], str) else dict(row["config"])
                before = dict(config.get("cvd_events", {}))
                config.setdefault("cvd_events", {}).update(NEW_CVD_EVENT_KEYS)

                new_id = await conn.fetchval(
                    "INSERT INTO crypto_cycle_config (created_at, created_by, note, config) "
                    "VALUES (now(), $1, $2, $3::jsonb) RETURNING id",
                    "S3B_ITEM2_CVD_EVENT_THRESHOLDS",
                    "S-3b Item 2: add CVD event-detection thresholds "
                    "(level_proximity_pct, absorption_cvd_threshold_usd, "
                    "local_extreme_lookback_bars, stop_buffer_pct, target_rr) "
                    "to cvd_events. Cooldown/expiry keys unchanged.",
                    json.dumps(config),
                )
                print(f"crypto_cycle_config: inserted id={new_id}")
                print(f"  cvd_events before: {before}")
                print(f"  cvd_events after:  {config['cvd_events']}")
    finally:
        await pool.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
