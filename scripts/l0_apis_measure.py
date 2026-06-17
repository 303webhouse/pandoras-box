r"""L0.3 APIS gating — retrospective measure (read-only).

Reports, over all APIS_CALL (and KODIAK_CALL for context) fires, the
liquid/non-liquid split with count + avg/median outcome_pnl_pct. Classifies via
the LIVE `is_liquid` allowlist (config.liquid_universe) so it can never drift
from the gate's actual decision. Confirms the liquid APIS population stays
negative-edge — the justification for the L0_APIS_ENFORCE flip.

Never prints the DB URL. Run from C:\trading-hub (or the l0-apis worktree):
    python scripts\l0_apis_measure.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", "backend"))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from config.liquid_universe import is_liquid  # noqa: E402


def _find_mcp_config() -> str:
    candidates = [
        os.path.join(HERE, "..", ".mcp.json"),
        os.path.join("C:\\", "trading-hub", ".mcp.json"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    raise RuntimeError(".mcp.json not found (worktree root or C:\\trading-hub).")


async def _get_pool():
    import asyncpg as _asyncpg
    cfg = json.load(open(_find_mcp_config()))
    args = cfg["mcpServers"]["postgres"]["args"]
    url = next((a for a in reversed(args) if a.startswith("postgres")), None)
    if not url:
        raise RuntimeError("postgres URL not found in .mcp.json")
    return await _asyncpg.create_pool(url, min_size=1, max_size=3)


def _summarize(rows):
    """rows: list of (pnl_or_None). Return (n_total, n_resolved, avg, median)."""
    pnls = sorted(float(r) for r in rows if r is not None)
    n_total = len(rows)
    n_res = len(pnls)
    avg = round(sum(pnls) / n_res, 3) if n_res else None
    med = round(pnls[n_res // 2], 3) if n_res else None
    return n_total, n_res, avg, med


async def main() -> int:
    pool = await _get_pool()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT signal_type, ticker, outcome_pnl_pct
                FROM signals
                WHERE signal_type IN ('APIS_CALL', 'KODIAK_CALL')
                """
            )
    finally:
        await pool.close()

    # bucket by signal_type x liquid
    buckets: dict = {}
    for r in rows:
        st = r["signal_type"]
        bucket = "liquid" if is_liquid(r["ticker"]) else "non_liquid"
        buckets.setdefault((st, bucket), []).append(r["outcome_pnl_pct"])

    print("=" * 64)
    print("L0.3 APIS/KODIAK GATING MEASURE")
    print("=" * 64)
    print(f"{'signal_type':<14} {'bucket':<11} {'n':>5} {'resolved':>9} {'avg_pnl':>9} {'median':>8}")
    print("-" * 64)
    for st in ("APIS_CALL", "KODIAK_CALL"):
        for bucket in ("liquid", "non_liquid"):
            data = buckets.get((st, bucket))
            if not data:
                continue
            n_total, n_res, avg, med = _summarize(data)
            print(f"{st:<14} {bucket:<11} {n_total:>5} {n_res:>9} "
                  f"{('' if avg is None else f'{avg:+.3f}'):>9} "
                  f"{('' if med is None else f'{med:+.3f}'):>8}")

    apis_liq = _summarize(buckets.get(("APIS_CALL", "liquid"), []))
    apis_non = _summarize(buckets.get(("APIS_CALL", "non_liquid"), []))
    print()
    print("Read:")
    print(f"  APIS liquid avg = {apis_liq[2]} (would be WITHHELD under enforce)")
    print(f"  APIS non-liquid avg = {apis_non[2]} (kept)")
    kodiak_liq = buckets.get(("KODIAK_CALL", "liquid"), [])
    print(f"  KODIAK liquid fires = {len(kodiak_liq)} "
          f"({'no-op gate — leave ungated' if not kodiak_liq else 'REVIEW: liquid KODIAK present'})")
    if apis_liq[2] is not None and apis_liq[2] < 0:
        print("\nPASS: liquid APIS edge is negative — gating to non-liquid withholds the bleed.")
        return 0
    print("\nNOTE: liquid APIS edge is NOT negative at this snapshot — re-evaluate before enforce.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
