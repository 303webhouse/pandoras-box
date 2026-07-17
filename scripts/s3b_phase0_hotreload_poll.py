r"""Poll crypto_regime_log / crypto_cycle_log for the hot-reload proof's new
config_version to land naturally (hourly APScheduler interval jobs, zero
redeploys). Prints one line per poll; prints DONE and exits 0 once both are
observed, or exits 1 after max_minutes. Never prints the DB URL.

Run from C:\trading-hub:
    python scripts\s3b_phase0_hotreload_poll.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))

GATE_TARGET_VERSION = 3
CYCLE_TARGET_VERSION = 2
POLL_SECONDS = 60
MAX_MINUTES = 44


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
    gate_done = False
    cycle_done = False
    elapsed = 0
    try:
        async with pool.acquire() as conn:
            while elapsed < MAX_MINUTES * 60:
                if not gate_done:
                    row = await conn.fetchrow(
                        "SELECT symbol, computed_at FROM crypto_regime_log "
                        "WHERE config_version = $1 ORDER BY computed_at DESC LIMIT 1",
                        GATE_TARGET_VERSION,
                    )
                    if row:
                        print(f"GATE_CONFIRMED symbol={row['symbol']} computed_at={row['computed_at']} config_version={GATE_TARGET_VERSION}", flush=True)
                        gate_done = True
                if not cycle_done:
                    row = await conn.fetchrow(
                        "SELECT symbol, computed_at FROM crypto_cycle_log "
                        "WHERE config_version = $1 ORDER BY computed_at DESC LIMIT 1",
                        CYCLE_TARGET_VERSION,
                    )
                    if row:
                        print(f"CYCLE_CONFIRMED symbol={row['symbol']} computed_at={row['computed_at']} config_version={CYCLE_TARGET_VERSION}", flush=True)
                        cycle_done = True
                if gate_done and cycle_done:
                    print("DONE both confirmed", flush=True)
                    return 0
                await asyncio.sleep(POLL_SECONDS)
                elapsed += POLL_SECONDS
    finally:
        await pool.close()
    print(f"TIMEOUT after {MAX_MINUTES}min gate_done={gate_done} cycle_done={cycle_done}", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
