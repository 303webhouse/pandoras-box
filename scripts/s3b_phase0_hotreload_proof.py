r"""S-3b Phase 0.0 item (b): hot-reload proof for crypto_gate_config and
crypto_cycle_config, post-cdec3e8-restart. INSERT-only (append-only config
convention -- never UPDATE), one benign trivial field bump per table, mirrors
the S-2 DD-8 pattern (S2_HOTRELOAD_PROOF, adx_trend_min 20->21).

Never prints the DB URL (reads .mcp.json, same pattern as
crypto_dual_write_diff_report.py / reconcile_soxs_xlf_dry_run.py).

Run from C:\trading-hub:
    python scripts\s3b_phase0_hotreload_proof.py
"""

from __future__ import annotations

import asyncio
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))


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
                gate_row = await conn.fetchrow(
                    "SELECT id, config FROM crypto_gate_config ORDER BY id DESC LIMIT 1"
                )
                gate_config = json.loads(gate_row["config"]) if isinstance(gate_row["config"], str) else dict(gate_row["config"])
                old_val = gate_config["regime"]["stale_bars_max_hours"]
                gate_config["regime"]["stale_bars_max_hours"] = old_val + 1
                new_gate_id = await conn.fetchval(
                    "INSERT INTO crypto_gate_config (created_at, created_by, note, config) "
                    "VALUES (now(), $1, $2, $3::jsonb) RETURNING id",
                    "S3B_PHASE0_HOTRELOAD_PROOF",
                    f"Post-restart hot-reload proof (S-3b brief, Phase 0.0 item b): "
                    f"regime.stale_bars_max_hours {old_val} -> {old_val + 1}, no redeploy",
                    json.dumps(gate_config),
                )
                print(f"crypto_gate_config: inserted id={new_gate_id} "
                      f"(stale_bars_max_hours {old_val} -> {old_val + 1})")

                cycle_row = await conn.fetchrow(
                    "SELECT id, config FROM crypto_cycle_config ORDER BY id DESC LIMIT 1"
                )
                cycle_config = json.loads(cycle_row["config"]) if isinstance(cycle_row["config"], str) else dict(cycle_row["config"])
                old_stale = cycle_config["tape_health"]["staleness_seconds"]
                cycle_config["tape_health"]["staleness_seconds"] = old_stale + 1
                new_cycle_id = await conn.fetchval(
                    "INSERT INTO crypto_cycle_config (created_at, created_by, note, config) "
                    "VALUES (now(), $1, $2, $3::jsonb) RETURNING id",
                    "S3B_PHASE0_HOTRELOAD_PROOF",
                    f"Post-restart hot-reload proof (S-3b brief, Phase 0.0 item b): "
                    f"tape_health.staleness_seconds {old_stale} -> {old_stale + 1}, no redeploy",
                    json.dumps(cycle_config),
                )
                print(f"crypto_cycle_config: inserted id={new_cycle_id} "
                      f"(staleness_seconds {old_stale} -> {old_stale + 1})")
    finally:
        await pool.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
