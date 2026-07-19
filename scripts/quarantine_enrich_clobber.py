#!/usr/bin/env python3
"""quarantine_enrich_clobber.py — DEF-ENRICH-CLOBBER quarantine remediation.

Wraps (never nulls) the equity-clobbered enrichment_data on CRYPTO signals
that predate the Phase 1 fix, preserving the pre-image in-row while removing
top-level poison (~$28-on-BTC-class values) from every reader, including
api/committee_bridge.py:58.

Predicate (never a frozen ID list — rows accrued until the fix deployed):
  asset_class='CRYPTO' AND enrichment_data ? 'avg_volume_20d'

Dry-run is the DEFAULT (no flags, or --dry-run explicitly): prints the count
+ writes an A1 pre-image JSONL (signal_id, ticker, created_at, full
enrichment_data). ZERO writes to `signals`.

Hard-stop band: --apply refuses if the live count falls outside 150 +/- 25
(125-175) -- report to Nick instead of proceeding.

--apply requires --i-have-go (A5). Parameterized single UPDATE, no
f-string SQL (A7) -- the predicate/transform below is a fixed literal, no
interpolated values. A6 invariance: total `signals` row count unchanged;
post-apply predicate count == 0 (the fingerprint key is no longer top-level
— the predicate self-verifies the transform).

Modeled on scripts/backfill_suppression.py's runbook conventions.

Usage:
  python scripts/quarantine_enrich_clobber.py                  # dry-run
  python scripts/quarantine_enrich_clobber.py --apply --i-have-go   # apply
"""
import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def _load_db_env():
    """Local convenience: hydrate DB_* from .mcp.json when not already set.
    No-op on Railway/VPS (DB_* present, .mcp.json absent)."""
    if os.getenv("DB_HOST"):
        return
    mcp = Path(__file__).resolve().parent.parent / ".mcp.json"
    if mcp.exists():
        from urllib.parse import urlparse
        m = re.search(r'postgres(?:ql)?://[^"\\ ]+', mcp.read_text(encoding="utf-8"))
        if m:
            u = urlparse(m.group(0))
            os.environ.update(
                DB_HOST=u.hostname or "localhost",
                DB_PORT=str(u.port or 5432),
                DB_NAME=(u.path or "/").lstrip("/") or "railway",
                DB_USER=u.username or "postgres",
                DB_PASSWORD=u.password or "",
            )


_load_db_env()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from database.postgres_client import get_postgres_client  # noqa: E402

PREDICATE = "asset_class = 'CRYPTO' AND enrichment_data ? 'avg_volume_20d'"

COUNT_SQL = f"SELECT COUNT(*) FROM signals WHERE {PREDICATE}"
TOTAL_SIGNALS_SQL = "SELECT COUNT(*) FROM signals"

AFFECTED_SQL = (
    f"SELECT signal_id, ticker, created_at, enrichment_data "
    f"FROM signals WHERE {PREDICATE} ORDER BY created_at"
)

APPLY_SQL = f"""
UPDATE signals
SET enrichment_data = jsonb_build_object(
    'quarantined_equity_clobber', enrichment_data,
    'quarantine_meta', jsonb_build_object(
        'defect', 'DEF-ENRICH-CLOBBER',
        'quarantined_at', to_char(now() at time zone 'utc', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')))
WHERE {PREDICATE}"""

HARD_STOP_CENTER = 150
HARD_STOP_TOLERANCE = 25


def _write_preimage(affected) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pre_path = Path(r"C:\temp") / f"quarantine_preimage_DEF_ENRICH_{ts}.jsonl"
    pre_path.parent.mkdir(parents=True, exist_ok=True)
    with pre_path.open("w", encoding="utf-8") as f:
        for r in affected:
            ed = r["enrichment_data"]
            if isinstance(ed, str):
                try:
                    ed = json.loads(ed)
                except (ValueError, TypeError):
                    pass
            f.write(json.dumps({
                "signal_id": r["signal_id"],
                "ticker": r["ticker"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "enrichment_data": ed,
            }) + "\n")
    return pre_path


async def main():
    ap = argparse.ArgumentParser(description="DEF-ENRICH-CLOBBER quarantine remediation")
    ap.add_argument("--dry-run", action="store_true", help="explicit no-op flag; dry-run is the default regardless")
    ap.add_argument("--apply", action="store_true", help="apply the quarantine wrap (default is dry-run)")
    ap.add_argument("--i-have-go", action="store_true",
                    help="A5 phase-gate acknowledgement; required alongside --apply")
    args = ap.parse_args()

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        count = await conn.fetchval(COUNT_SQL)
        total_before = await conn.fetchval(TOTAL_SIGNALS_SQL)

        print("=== quarantine_enrich_clobber " + ("APPLY" if args.apply else "DRY-RUN") + " ===")
        print(f"predicate           : {PREDICATE}")
        print(f"matching rows       : {count}")
        print(f"total signals rows  : {total_before}")
        print(f"hard-stop band      : {HARD_STOP_CENTER - HARD_STOP_TOLERANCE}-{HARD_STOP_CENTER + HARD_STOP_TOLERANCE}")

        affected = await conn.fetch(AFFECTED_SQL)
        pre_path = _write_preimage(affected)
        print(f"\nA1 pre-image: {len(affected)} rows -> {pre_path}")

        print("\n--- samples (first 5) ---")
        for r in affected[:5]:
            ed = r["enrichment_data"]
            if isinstance(ed, str):
                try:
                    ed = json.loads(ed)
                except (ValueError, TypeError):
                    ed = {}
            print(f"  {r['signal_id']}  ticker={r['ticker']}  created_at={r['created_at']}")
            print(f"    current_price={ed.get('current_price')}  avg_volume_20d={ed.get('avg_volume_20d')}")

        if not args.apply:
            print("\nDRY-RUN only — nothing written. Re-run with "
                  "--apply --i-have-go after the count is GO'd (A5).")
            return

        if not (HARD_STOP_CENTER - HARD_STOP_TOLERANCE) <= count <= (HARD_STOP_CENTER + HARD_STOP_TOLERANCE):
            print(f"\nHARD-STOP: live count {count} is outside the {HARD_STOP_CENTER}+/-{HARD_STOP_TOLERANCE} band "
                  f"({HARD_STOP_CENTER - HARD_STOP_TOLERANCE}-{HARD_STOP_CENTER + HARD_STOP_TOLERANCE}). "
                  f"Refusing to apply -- report to Nick instead of proceeding.")
            return

        if not args.i_have_go:
            print("\nA5 REFUSED: --apply requires --i-have-go (phase-gate "
                  "acknowledgement). Post the dry-run count, get GO, then re-run.")
            return

        n = await conn.execute(APPLY_SQL)
        print(f"\napply: {n}")

        total_after = await conn.fetchval(TOTAL_SIGNALS_SQL)
        remaining = await conn.fetchval(COUNT_SQL)
        print(f"A6 row-count invariance: before={total_before} after={total_after} -> "
              f"{'OK' if total_before == total_after else 'FAIL — INVESTIGATE'}")
        print(f"post-apply predicate count (must be 0): {remaining} -> "
              f"{'OK' if remaining == 0 else 'FAIL — INVESTIGATE'}")


if __name__ == "__main__":
    asyncio.run(main())
