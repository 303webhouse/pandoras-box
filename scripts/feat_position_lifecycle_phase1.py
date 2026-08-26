#!/usr/bin/env python3
"""FEAT-POSITION-LIFECYCLE — Phase 1 schema migration.

Authority: principal brief 2026-08-26, decisions D1-D4.
Runbook conventions modelled on scripts/def_position_integrity.py.

DRY RUN BY DEFAULT. Pass --apply to write. Single transaction; any failure rolls
the whole migration back.

ORDER IS LOAD-BEARING:
  step 1 (D4 occurrence) must precede step 2 (D3 casing normalisation), because
  normalising 'robinhood' -> 'ROBINHOOD' makes two existing cash_flows rows
  identical on the current unique key. Adding `occurrence` to the key first is
  what lets the normalisation land without a constraint violation.

HARD SCOPE GUARD: the account_balances row labelled BROKERAGE_LINK_401K is NEVER
touched (DEF-ACCOUNT-LABEL-DUP is a frozen dispute; migrating it would adjudicate
it by side effect). Asserted before and after.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import psycopg2
import psycopg2.extras

CANONICAL = {
    "robinhood": "ROBINHOOD",
    "Robinhood": "ROBINHOOD",
    "ROBINHOOD": "ROBINHOOD",
    "Fidelity Roth": "FIDELITY_ROTH",
    "FIDELITY_ROTH": "FIDELITY_ROTH",
    "Fidelity 401A": "FIDELITY_401A",
    "FIDELITY_401A": "FIDELITY_401A",
}
FROZEN_LABELS = {"BROKERAGE_LINK_401K"}   # never migrated — frozen dispute


def dsn() -> str:
    cfg = json.loads(pathlib.Path(r"C:\trading-hub\.mcp.json").read_text(encoding="utf-8"))
    return cfg["mcpServers"]["postgres"]["args"][2]


def show(cur, label, sql, args=()):
    cur.execute(sql, args)
    rows = cur.fetchall()
    print(f"  {label}")
    for r in rows:
        print(f"     {tuple(r)}")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    args = ap.parse_args()

    conn = psycopg2.connect(dsn())
    conn.autocommit = False
    cur = conn.cursor()

    print("=" * 78)
    print(f"FEAT-POSITION-LIFECYCLE Phase 1 — {'APPLY' if args.apply else 'DRY RUN'}")
    print("=" * 78)

    # ---------- PREIMAGE ----------
    print("\n-- PREIMAGE ------------------------------------------------------")
    show(cur, "cash_flows.account_name:",
         "SELECT account_name, COUNT(*) FROM cash_flows GROUP BY 1 ORDER BY 1")
    show(cur, "account_balances.account_name:",
         "SELECT account_name, COUNT(*) FROM account_balances GROUP BY 1 ORDER BY 1")
    show(cur, "unified_positions.account:",
         "SELECT account, COUNT(*) FROM unified_positions GROUP BY 1 ORDER BY 1")
    frozen_pre = show(cur, "FROZEN row (must be identical post-migration):",
                      "SELECT account_name, balance, updated_at FROM account_balances "
                      "WHERE account_name = ANY(%s)", (list(FROZEN_LABELS),))

    # unmapped values would be silently dropped by the CASE — refuse instead
    cur.execute("SELECT DISTINCT account_name FROM cash_flows "
                "UNION SELECT DISTINCT account_name FROM account_balances")
    seen = {r[0] for r in cur.fetchall()}
    unmapped = seen - set(CANONICAL) - FROZEN_LABELS
    if unmapped:
        print(f"\n  !! UNMAPPED account labels, refusing to guess: {sorted(unmapped)}")
        conn.rollback()
        return 2

    # ---------- STEP 1 (D4): occurrence, before any casing change ----------
    print("\n-- STEP 1 (D4) cash_flows.occurrence + widened dedup key ----------")
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_name='cash_flows' AND column_name='occurrence'""")
    if cur.fetchone():
        print("  occurrence already present — idempotent skip")
    else:
        cur.execute("ALTER TABLE cash_flows ADD COLUMN occurrence integer NOT NULL DEFAULT 1")
        print("  + occurrence integer NOT NULL DEFAULT 1")

    # de-collide BEFORE normalising casing: rows that only differ by account casing
    cur.execute("""
        WITH norm AS (
            SELECT id,
                   CASE account_name
                        WHEN 'robinhood' THEN 'ROBINHOOD' WHEN 'Robinhood' THEN 'ROBINHOOD'
                        WHEN 'Fidelity Roth' THEN 'FIDELITY_ROTH'
                        WHEN 'Fidelity 401A' THEN 'FIDELITY_401A'
                        ELSE account_name END AS acct,
                   flow_type, amount, description, activity_date, imported_from
            FROM cash_flows),
        ranked AS (
            SELECT id, ROW_NUMBER() OVER (
                     PARTITION BY acct, flow_type, amount, description, activity_date, imported_from
                     ORDER BY id) AS rn
            FROM norm)
        SELECT id, rn FROM ranked WHERE rn > 1 ORDER BY id""")
    collisions = cur.fetchall()
    if collisions:
        print(f"  !! {len(collisions)} row(s) collide once casing is normalised:")
        for cid, rn in collisions:
            cur.execute("SELECT account_name, amount, description, activity_date::text, imported_from "
                        "FROM cash_flows WHERE id=%s", (cid,))
            print(f"       id={cid} rn={rn} {tuple(cur.fetchone())}")
            cur.execute("UPDATE cash_flows SET occurrence=%s WHERE id=%s", (rn, cid))
        print("  -> assigned occurrence>1 (NOT deleted — suspected duplicate, principal rules)")
    else:
        print("  no collisions")

    cur.execute("""SELECT conname FROM pg_constraint
                   WHERE conrelid='public.cash_flows'::regclass AND conname='cash_flows_dedup_key'""")
    if cur.fetchone():
        cur.execute("ALTER TABLE cash_flows DROP CONSTRAINT cash_flows_dedup_key")
    cur.execute("""ALTER TABLE cash_flows ADD CONSTRAINT cash_flows_dedup_key
                   UNIQUE NULLS NOT DISTINCT
                   (account_name, flow_type, amount, description, activity_date,
                    imported_from, occurrence)""")
    print("  dedup key rebuilt with occurrence")

    # ---------- STEP 2 (D3): canonical account vocabulary ----------
    print("\n-- STEP 2 (D3) canonical account vocabulary -----------------------")
    for tbl in ("cash_flows", "account_balances"):
        cur.execute(f"""
            UPDATE {tbl} SET account_name = CASE account_name
                WHEN 'robinhood' THEN 'ROBINHOOD' WHEN 'Robinhood' THEN 'ROBINHOOD'
                WHEN 'Fidelity Roth' THEN 'FIDELITY_ROTH'
                WHEN 'Fidelity 401A' THEN 'FIDELITY_401A'
                ELSE account_name END
            WHERE account_name <> ALL(%s)
              AND account_name IN ('robinhood','Robinhood','Fidelity Roth','Fidelity 401A')
        """, (list(FROZEN_LABELS),))
        print(f"  {tbl}: {cur.rowcount} row(s) normalised")

    # ---------- STEP 3: position_lots ----------
    print("\n-- STEP 3 position_lots + LEGACY-SINGLE-LOT backfill ---------------")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS position_lots (
            id            serial PRIMARY KEY,
            position_id   text NOT NULL REFERENCES unified_positions(position_id)
                              ON DELETE CASCADE,
            fill_date     timestamptz NOT NULL,
            quantity      numeric NOT NULL,
            price         numeric,
            fees          numeric NOT NULL DEFAULT 0,
            source        text NOT NULL DEFAULT 'MANUAL'
                              CHECK (source IN ('MANUAL','IMPORT','LEGACY-SINGLE-LOT')),
            created_at    timestamptz NOT NULL DEFAULT now()
        )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_position_lots_position ON position_lots(position_id)")
    print("  position_lots ensured")
    cur.execute("""
        INSERT INTO position_lots (position_id, fill_date, quantity, price, fees, source)
        SELECT p.position_id, p.entry_date, p.quantity, p.entry_price, 0, 'LEGACY-SINGLE-LOT'
        FROM unified_positions p
        WHERE NOT EXISTS (SELECT 1 FROM position_lots l WHERE l.position_id = p.position_id)
    """)
    print(f"  backfilled {cur.rowcount} LEGACY-SINGLE-LOT row(s)")

    # ---------- STEP 4 (D2): widen position_sync_audit ----------
    print("\n-- STEP 4 (D2) widen position_sync_audit ---------------------------")
    for col, ddl in (("field", "text"), ("reason", "text"), ("actor", "text")):
        cur.execute("""SELECT 1 FROM information_schema.columns
                       WHERE table_name='position_sync_audit' AND column_name=%s""", (col,))
        if cur.fetchone():
            print(f"  {col} already present")
        else:
            cur.execute(f"ALTER TABLE position_sync_audit ADD COLUMN {col} {ddl}")
            print(f"  + {col} {ddl} (nullable — sync rows leave it null)")
    # D2 says manual edits "leave sync columns null" — which REQUIRES dropping their
    # NOT NULL. Without this the trigger's INSERT violates them and every
    # UPDATE unified_positions fails in production (all 19 sites, the mark job, the
    # expiry sweep, Friday's TGT stamp).
    for col in ("sync_run_id", "csv_paths", "csv_sha256"):
        cur.execute("""SELECT is_nullable FROM information_schema.columns
                       WHERE table_name='position_sync_audit' AND column_name=%s""", (col,))
        row = cur.fetchone()
        if row and row[0] == "NO":
            cur.execute(f"ALTER TABLE position_sync_audit ALTER COLUMN {col} DROP NOT NULL")
            print(f"  {col}: NOT NULL dropped (sync-only column; manual/trigger rows leave it null)")
        else:
            print(f"  {col}: already nullable")

    cur.execute("""COMMENT ON TABLE position_sync_audit IS
        'Position mutation timeline. Originally CSV-sync only (sync_run_id/csv_*); '
        'widened 2026-08-26 per FEAT-POSITION-LIFECYCLE D2 to carry manual edits and '
        'trigger-captured mutations. Manual/trigger rows leave the sync columns NULL. '
        'One timeline per position — do not add a second audit table.'""")

    # ---------- STEP 5 (D1): the trigger ----------
    print("\n-- STEP 5 (D1) AFTER UPDATE/DELETE audit trigger -------------------")
    cur.execute("""
        CREATE OR REPLACE FUNCTION unified_positions_audit() RETURNS trigger AS $$
        BEGIN
            IF (TG_OP = 'UPDATE') THEN
                IF to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW) THEN
                    INSERT INTO position_sync_audit
                        (operation, position_id, ticker, structure,
                         before_state, after_state, actor, notes, executed_at)
                    VALUES ('UPDATE', NEW.position_id, NEW.ticker, NEW.structure,
                            to_jsonb(OLD), to_jsonb(NEW),
                            current_setting('app.actor', true), NULL, now());
                END IF;
                RETURN NEW;
            ELSIF (TG_OP = 'DELETE') THEN
                INSERT INTO position_sync_audit
                    (operation, position_id, ticker, structure,
                     before_state, after_state, actor, notes, executed_at)
                VALUES ('DELETE', OLD.position_id, OLD.ticker, OLD.structure,
                        to_jsonb(OLD), NULL,
                        current_setting('app.actor', true), NULL, now());
                RETURN OLD;
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql""")
    cur.execute("DROP TRIGGER IF EXISTS trg_unified_positions_audit ON unified_positions")
    cur.execute("""CREATE TRIGGER trg_unified_positions_audit
                   AFTER UPDATE OR DELETE ON unified_positions
                   FOR EACH ROW EXECUTE FUNCTION unified_positions_audit()""")
    print("  trigger installed (fires for all 19 write sites and any future writer)")

    # FIREABILITY: a trigger that is created but never exercised is an unproven
    # trigger. Force it to fire inside this transaction against a real row and
    # assert an audit row appeared with both states captured. This is what would
    # have caught the NOT NULL defect above had it been present from the start.
    # SAVEPOINT so the probe NEVER commits, even under --apply. Without it the
    # probe edit and its revert both fire the trigger and both commit, leaving two
    # self-cancelling rows in the audit timeline (that happened on the 2026-08-26
    # apply run; rows 27/28 were annotated rather than deleted).
    cur.execute("SAVEPOINT trigger_probe")
    cur.execute("SELECT position_id, notes FROM unified_positions ORDER BY id LIMIT 1")
    probe_id, probe_notes = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM position_sync_audit")
    audit_before = cur.fetchone()[0]
    cur.execute("UPDATE unified_positions SET notes = COALESCE(notes,'') || %s "
                "WHERE position_id = %s", ("__trigger_probe__", probe_id))
    cur.execute("SELECT COUNT(*) FROM position_sync_audit")
    audit_after = cur.fetchone()[0]
    cur.execute("""SELECT operation, position_id,
                          before_state->>'notes' IS DISTINCT FROM after_state->>'notes',
                          sync_run_id IS NULL
                   FROM position_sync_audit ORDER BY id DESC LIMIT 1""")
    op, apid, captured, sync_null = cur.fetchone()
    print(f"  FIREABILITY: audit rows {audit_before} -> {audit_after} "
          f"(op={op}, pid={apid}, before/after differ={captured}, sync cols null={sync_null})")
    if audit_after != audit_before + 1 or op != "UPDATE" or apid != probe_id or not captured:
        print("  !! TRIGGER DID NOT FIRE CORRECTLY — rolling back")
        conn.rollback()
        return 5
    # revert the probe mutation; the audit rows it produced roll back with the txn
    cur.execute("ROLLBACK TO SAVEPOINT trigger_probe")
    print("  probe rolled back to savepoint — no probe rows reach the audit timeline")

    # NEGATIVE CONTROL: a no-op UPDATE must NOT write an audit row, or the timeline
    # fills with noise from every mark-job pass that changes nothing.
    cur.execute("SELECT COUNT(*) FROM position_sync_audit")
    noop_before = cur.fetchone()[0]
    cur.execute("UPDATE unified_positions SET notes = notes WHERE position_id = %s", (probe_id,))
    cur.execute("SELECT COUNT(*) FROM position_sync_audit")
    noop_after = cur.fetchone()[0]
    print(f"  NEGATIVE CONTROL: no-op UPDATE wrote {noop_after - noop_before} audit row(s) "
          f"(must be 0 — IS DISTINCT FROM guard)")
    if noop_after != noop_before:
        print("  !! no-op writes audit noise — rolling back")
        conn.rollback()
        return 6

    # ---------- POSTIMAGE ----------
    print("\n-- POSTIMAGE -----------------------------------------------------")
    show(cur, "cash_flows.account_name:",
         "SELECT account_name, COUNT(*) FROM cash_flows GROUP BY 1 ORDER BY 1")
    show(cur, "account_balances.account_name:",
         "SELECT account_name, COUNT(*) FROM account_balances GROUP BY 1 ORDER BY 1")
    show(cur, "position_lots by source:",
         "SELECT source, COUNT(*) FROM position_lots GROUP BY 1 ORDER BY 1")
    frozen_post = show(cur, "FROZEN row:",
                       "SELECT account_name, balance, updated_at FROM account_balances "
                       "WHERE account_name = ANY(%s)", (list(FROZEN_LABELS),))

    if frozen_pre != frozen_post:
        print("\n  !! FROZEN ROW CHANGED — rolling back")
        conn.rollback()
        return 3
    print("\n  frozen row identical pre/post: GUARD HELD")

    cur.execute("SELECT COUNT(*) FROM position_lots l JOIN unified_positions p "
                "USING (position_id) WHERE l.source='LEGACY-SINGLE-LOT' "
                "AND (l.quantity <> p.quantity OR l.price IS DISTINCT FROM p.entry_price)")
    drift = cur.fetchone()[0]
    print(f"  backfill fidelity: {drift} lot(s) disagree with their position (must be 0)")
    if drift:
        conn.rollback()
        return 4

    if args.apply:
        conn.commit()
        print("\nCOMMITTED")
    else:
        conn.rollback()
        print("\nROLLED BACK (dry run — pass --apply to write)")
    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
