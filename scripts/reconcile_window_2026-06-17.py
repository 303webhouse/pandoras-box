"""
One-off reconciliation of un-logged Robinhood activity, 2026-06-11 .. 2026-06-16
(plus a few un-logged 2026-06-08..10 round trips), against the live hub.

Targets:
  - unified_positions : live open-position view (close 3, adjust 2, add 8)
  - trades            : P&L ledger (insert un-logged closed round-trips + expirations)

READ-ONLY by default. Pass --commit to write. Idempotent: skips inserts whose
(ticker, opened_at::date, strike, short_strike, structure) already exist.

Connection string is read from .mcp.json (never printed).
"""
import json, sys, re
import psycopg2
import psycopg2.extras
from datetime import date

COMMIT = "--commit" in sys.argv
TODAY = date(2026, 6, 17)

def conn_url():
    d = json.load(open(".mcp.json"))
    pg = d["mcpServers"]["postgres"]
    for a in pg.get("args", []):
        if isinstance(a, str) and a.startswith(("postgres://", "postgresql://")):
            return a
    raise SystemExit("no pg url in .mcp.json")

def dte(expiry):
    if not expiry:
        return None
    y, m, dd = map(int, expiry.split("-"))
    return (date(y, m, dd) - TODAY).days

# ---- STAGE 1a: close existing hub opens that closed in the window ----
CLOSES = [
    # position_id, exit_price(net), exit_date, realized_pnl, outcome
    ("POS_IBIT_20260610_155020", 0.25, "2026-06-11", -17.0, "LOSS"),  # IBIT 34/31 put sprd
    ("POS_IBIT_20260610_155153", 0.05, "2026-06-11",  -6.0, "LOSS"),  # IBIT 29 long put
    ("POS_NEE_20260610_173915",  0.26, "2026-06-15",  -9.0, "LOSS"),  # NEE 105/115 call sprd
]
# ---- STAGE 1b: quantity adjustments on existing opens ----
QTY_ADJ = [
    # position_id, new_qty, note
    ("POS_XLF_20260429_062700", 2, "Partial close 10/12 @ 0.04 net on 6/16 (LOSS -$172.50); 2 left"),
    ("POS_XLE_20260610_154117", 6, "Added +1 (6/15); now 6 contracts"),
]
# ---- STAGE 1c: new open positions (still open as of today) ----
# ticker, asset_type, structure, direction, long, short, expiry, qty, entry(net debit), entry_date
NEW_OPENS = [
    ("META","OPTION","put_debit_spread","SHORT",500,490,"2026-07-02",2,0.52,"2026-06-12"),
    ("VIXW","OPTION","call_debit_spread","LONG",30,40,"2026-06-24",2,0.12,"2026-06-12"),
    ("KNX","OPTION","long_put","SHORT",62.5,None,"2026-07-17",2,0.25,"2026-06-15"),
    ("USO","OPTION","call_debit_spread","LONG",150,165,"2026-10-16",1,1.45,"2026-06-15"),
    ("IBIT","OPTION","long_call","LONG",40,None,"2026-06-18",5,0.06,"2026-06-15"),
    ("IBIT","OPTION","call_debit_spread","LONG",43,48,"2026-07-17",2,0.20,"2026-06-15"),
    ("NVDA","OPTION","put_debit_spread","SHORT",175,165,"2026-07-17",1,0.36,"2026-06-16"),
    ("XLF","OPTION","put_debit_spread","SHORT",48,45,"2026-07-17",3,0.09,"2026-06-15"),  # 6/12+6/15 adds
]
# ---- STAGE 2: un-logged closed trades for the P&L ledger ----
# ticker, direction, structure, long, short, expiry, qty, entry(net), exit(net), opened, closed, pnl, reason
TRADES = [
    # un-logged round-trips
    ("WFC","SHORT","put_debit_spread",72.5,67.5,"2026-07-17",1,0.45,0.46,"2026-06-08","2026-06-09",0.80,"manual"),
    ("VIX","LONG","call_debit_spread",25,30,"2026-06-17",3,0.178,0.20,"2026-06-08","2026-06-11",2.48,"manual"),
    ("QQQ","SHORT","long_put",680,None,"2026-06-11",1,0.21,0.40,"2026-06-11","2026-06-11",18.90,"manual"),
    ("IWM","SHORT","put_debit_spread",280,275,"2026-06-18",1,0.37,0.369,"2026-06-12","2026-06-12",-0.20,"manual"),
    ("IWM","SHORT","call_debit_spread",310,315,"2026-06-18",1,0.221,0.109,"2026-06-12","2026-06-12",-11.20,"manual"),
    ("IREN","SHORT","put_debit_spread",50,45,"2026-06-18",1,0.41,0.269,"2026-06-12","2026-06-12",-14.20,"manual"),
    ("IBIT","LONG","long_call",38,None,"2026-06-18",1,0.21,0.16,"2026-06-12","2026-06-12",-5.10,"manual"),
    ("NOK","LONG","long_call",17,None,"2026-06-18",2,0.10,0.0995,"2026-06-12","2026-06-12",-0.18,"manual"),
    ("NVDA","SHORT","put_debit_spread",200,195,"2026-06-22",1,0.30,0.319,"2026-06-15","2026-06-16",1.80,"manual"),
    ("IWM","SHORT","put_debit_spread",285,280,"2026-06-22",1,0.46,0.409,"2026-06-15","2026-06-16",-5.20,"manual"),
    # expired worthless (full loss of debit)
    ("SPY","SHORT","put_debit_spread",705,700,"2026-06-12",4,0.124,0.0,"2026-06-09","2026-06-12",-49.40,"expired"),
    ("QQQ","LONG","call_debit_spread",745,750,"2026-06-12",5,0.071,0.0,"2026-06-11","2026-06-12",-35.43,"expired"),
    ("QQQ","SHORT","put_debit_spread",700,695,"2026-06-12",2,0.171,0.0,"2026-06-12","2026-06-12",-34.18,"expired"),
    ("IBIT","SHORT","long_put",35,None,"2026-06-12",2,0.10,0.0,"2026-06-11","2026-06-12",-20.08,"expired"),
    ("IBIT","SHORT","long_put",33,None,"2026-06-12",4,0.045,0.0,"2026-06-10","2026-06-12",-18.16,"expired"),
    ("NVDA","SHORT","long_put",190,None,"2026-06-12",2,0.20,0.0,"2026-06-11","2026-06-12",-40.08,"expired"),
    ("TSLA","LONG","long_call",425,None,"2026-06-12",1,0.09,0.0,"2026-06-12","2026-06-12",-9.04,"expired"),
    # also log the 3 hub-open closes to the ledger
    ("IBIT","SHORT","put_debit_spread",34,31,"2026-06-18",1,0.42,0.25,"2026-06-10","2026-06-11",-17.0,"manual"),
    ("IBIT","SHORT","long_put",29,None,"2026-06-18",1,0.11,0.05,"2026-06-10","2026-06-11",-6.0,"manual"),
    ("NEE","LONG","call_debit_spread",105,115,"2026-09-18",1,0.35,0.26,"2026-06-10","2026-06-15",-9.0,"manual"),
    ("XLF","SHORT","put_debit_spread",48,45,"2026-07-17",10,0.2125,0.04,"2026-04-29","2026-06-16",-172.50,"manual"),
]

def main():
    cur_conn = psycopg2.connect(conn_url())
    cur_conn.autocommit = False
    cur = cur_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    log = []

    # STAGE 1a closes
    for pid, exitp, exitd, pnl, outcome in CLOSES:
        cur.execute("SELECT status FROM unified_positions WHERE position_id=%s", (pid,))
        r = cur.fetchone()
        if not r:
            log.append(f"  SKIP close {pid}: not found"); continue
        if r["status"] == "CLOSED":
            log.append(f"  SKIP close {pid}: already CLOSED"); continue
        cur.execute("""UPDATE unified_positions SET status='CLOSED', exit_price=%s,
            exit_date=%s::timestamptz, realized_pnl=%s, trade_outcome=%s, updated_at=now()
            WHERE position_id=%s""", (exitp, exitd, pnl, outcome, pid))
        log.append(f"  CLOSE {pid} -> exit {exitp} {exitd} pnl {pnl}")

    # STAGE 1b qty adjust
    for pid, nq, note in QTY_ADJ:
        cur.execute("SELECT quantity, notes FROM unified_positions WHERE position_id=%s", (pid,))
        r = cur.fetchone()
        if not r:
            log.append(f"  SKIP adj {pid}: not found"); continue
        newnote = (r["notes"] + " | " if r["notes"] else "") + note
        cur.execute("UPDATE unified_positions SET quantity=%s, notes=%s, updated_at=now() WHERE position_id=%s",
                    (nq, newnote, pid))
        log.append(f"  ADJUST {pid} qty {r['quantity']}->{nq}")

    # STAGE 1c new opens
    seq = 1
    for tk, at, st, dr, lng, sht, exp, qty, entry, ed in NEW_OPENS:
        # dedup guard
        cur.execute("""SELECT 1 FROM unified_positions WHERE ticker=%s AND structure=%s
            AND expiry=%s::date AND status='OPEN' AND coalesce(long_strike,-1)=%s
            AND coalesce(short_strike,-1)=%s AND entry_date::date=%s::date""",
            (tk, st, exp, lng if lng is not None else -1, sht if sht is not None else -1, ed))
        if cur.fetchone():
            log.append(f"  SKIP open {tk} {st} {lng}/{sht} {exp}: exists"); continue
        pid = f"POS_{tk}_{ed.replace('-','')}_csv{seq:02d}"; seq += 1
        cb = round(entry * qty * 100, 2)
        cur.execute("""INSERT INTO unified_positions
            (position_id,ticker,asset_type,structure,direction,long_strike,short_strike,expiry,dte,
             quantity,entry_price,entry_date,cost_basis,max_loss,source,account,status,created_at,updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s::date,%s,%s,%s,%s::timestamptz,%s,%s,'CSV_SYNC','ROBINHOOD','OPEN',now(),now())""",
            (pid, tk, at, st, dr, lng, sht, exp, dte(exp), qty, entry, ed, cb, cb))
        log.append(f"  OPEN {pid}  {tk} {st} {lng}/{sht} x{qty} @{entry} exp {exp}")

    # STAGE 2 trades ledger
    ins = skip = 0
    for tk, dr, st, lng, sht, exp, qty, entry, exitp, od, cd, pnl, reason in TRADES:
        cur.execute("""SELECT 1 FROM trades WHERE ticker=%s AND opened_at::date=%s::date
            AND coalesce(long_strike,-1)=%s AND coalesce(short_strike,-1)=%s AND structure=%s
            AND closed_at::date=%s::date""",
            (tk, od, lng if lng is not None else -1, sht if sht is not None else -1, st, cd))
        if cur.fetchone():
            skip += 1; continue
        pnl_pct = round(pnl / (entry * qty * 100) * 100, 2) if entry else None
        cur.execute("""INSERT INTO trades
            (ticker,direction,status,account,structure,entry_price,quantity,opened_at,closed_at,
             exit_price,pnl_dollars,pnl_percent,strike,expiry,short_strike,long_strike,exit_reason,origin,notes)
            VALUES (%s,%s,'closed','ROBINHOOD',%s,%s,%s,%s::timestamptz,%s::timestamptz,%s,%s,%s,%s,%s::date,%s,%s,%s,'csv_reconcile','RH window 6/8-6/16 backfill')""",
            (tk, dr, st, entry, qty, od, cd, exitp, pnl, pnl_pct,
             lng, exp, sht, lng, reason))
        ins += 1
        log.append(f"  TRADE {tk:5s} {st:18s} {lng}/{sht} x{qty} {od}->{cd} pnl {pnl:+.2f} [{reason}]")

    print(f"=== {'COMMIT' if COMMIT else 'DRY-RUN'} ===")
    print("\n".join(log))
    print(f"\nStage2 trades: inserted {ins}, skipped(existing) {skip}")
    print(f"Total un-logged P&L being added: {sum(t[11] for t in TRADES):.2f}")

    if COMMIT:
        cur_conn.commit(); print("\nCOMMITTED.")
    else:
        cur_conn.rollback(); print("\nrolled back (dry-run). Re-run with --commit to write.")
    cur.close(); cur_conn.close()

if __name__ == "__main__":
    main()
