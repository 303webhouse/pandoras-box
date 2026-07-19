"""
Correction: IBIT 7/17 43/48 call spread x2 was a SAME-DAY round trip on 6/15
(only appears 6/15 in the full CSV), not a new open. Earlier reconcile wrongly
added it as an open unified_position. Fix: delete the bogus open, log the
closed round-trip to the trades ledger.

Dry-run by default; --commit to write.
"""
import json, sys
import psycopg2, psycopg2.extras

COMMIT = "--commit" in sys.argv

def conn_url():
    d = json.load(open(".mcp.json"))
    for a in d["mcpServers"]["postgres"].get("args", []):
        if isinstance(a, str) and a.startswith(("postgres://", "postgresql://")):
            return a
    raise SystemExit("no pg url")

c = psycopg2.connect(conn_url()); c.autocommit = False
cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
log = []

# 1) remove the bogus open
cur.execute("SELECT position_id,status FROM unified_positions WHERE position_id=%s",
            ("POS_IBIT_20260615_csv06",))
r = cur.fetchone()
if r:
    cur.execute("DELETE FROM unified_positions WHERE position_id=%s", ("POS_IBIT_20260615_csv06",))
    log.append(f"DELETE unified_positions POS_IBIT_20260615_csv06 (was {r['status']})")
else:
    log.append("SKIP delete: POS_IBIT_20260615_csv06 not found")

# 2) log the round-trip to trades (idempotent)
cur.execute("""SELECT 1 FROM trades WHERE ticker='IBIT' AND structure='call_debit_spread'
    AND long_strike=43 AND short_strike=48 AND opened_at::date='2026-06-15'""")
if cur.fetchone():
    log.append("SKIP trade insert: already exists")
else:
    cur.execute("""INSERT INTO trades
        (ticker,direction,status,account,structure,entry_price,quantity,opened_at,closed_at,
         exit_price,pnl_dollars,pnl_percent,strike,expiry,short_strike,long_strike,exit_reason,origin,notes)
        VALUES ('IBIT','LONG','closed','ROBINHOOD','call_debit_spread',0.205,2,
         '2026-06-15'::timestamptz,'2026-06-15'::timestamptz,0.18,-5.38,-13.12,
         43,'2026-07-17'::date,48,43,'manual','csv_reconcile','same-day round trip 6/15')""")
    log.append("INSERT trade IBIT call_debit_spread 43/48 x2 6/15->6/15 pnl -5.38")

print("=== " + ("COMMIT" if COMMIT else "DRY-RUN") + " ===")
print("\n".join(log))
if COMMIT:
    c.commit(); print("COMMITTED.")
else:
    c.rollback(); print("rolled back (dry-run).")
cur.close(); c.close()
