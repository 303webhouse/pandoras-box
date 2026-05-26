"""One-shot backup of unified_positions to a JSON snapshot.

Used as a rollback safety net before `scripts/sync_rh_csv.py --apply`.
"""
import json
import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal

import psycopg2


def _ser(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def main() -> int:
    url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
    if not url:
        print("FATAL: DATABASE_PUBLIC_URL / DATABASE_URL not set", file=sys.stderr)
        return 2

    conn = psycopg2.connect(url, connect_timeout=15)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM unified_positions ORDER BY id")
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        payload = [{c: _ser(v) for c, v in zip(cols, r)} for r in rows]
    finally:
        conn.close()

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join("backups", f"unified_positions_pre_sync_{ts}.json")
    os.makedirs("backups", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"Backed up {len(payload)} unified_positions rows -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
