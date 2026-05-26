"""Post-apply verification for scripts/sync_rh_csv.py.

Prints current OPEN ROBINHOOD positions + audit rows for a given sync_run_id.
"""
import os
import sys

import psycopg2


def main() -> int:
    run_id = sys.argv[1] if len(sys.argv) > 1 else None
    url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
    if not url:
        print("FATAL: DATABASE_PUBLIC_URL / DATABASE_URL not set", file=sys.stderr)
        return 2
    conn = psycopg2.connect(url, connect_timeout=15)
    cur = conn.cursor()

    cur.execute(
        "SELECT ticker, structure, quantity, entry_price, long_strike, short_strike, expiry, position_id "
        "FROM unified_positions WHERE account='ROBINHOOD' AND status='OPEN' ORDER BY expiry, ticker"
    )
    rows = cur.fetchall()
    print(f"== {len(rows)} OPEN ROBINHOOD positions ==")
    for r in rows:
        long_s = f"{float(r[4]):g}" if r[4] is not None else "-"
        short_s = f"{float(r[5]):g}" if r[5] is not None else "-"
        print(f"  {r[0]:6} exp={r[6]} {str(r[1]):22} qty={r[2]:>2} entry=${float(r[3]):.4f}  L={long_s:>6}/S={short_s:<6}  ({r[7]})")

    if run_id:
        cur.execute(
            "SELECT operation, ticker, position_id, notes FROM position_sync_audit "
            "WHERE sync_run_id = %s ORDER BY id",
            (run_id,),
        )
        audit = cur.fetchall()
        print()
        print(f"== {len(audit)} position_sync_audit rows for run {run_id} ==")
        for r in audit:
            print(f"  {r[0]:7} {r[1]:6} {r[2] or '-':40} {r[3] or ''}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
