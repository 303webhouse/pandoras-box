#!/usr/bin/env python3
"""reconcile_accounts_apply.py — RECONCILIATION APPLY (P1), addendum 2026-07-23.

Data-only maintenance on `account_balances` (shrunk-scope reconciliation):
  T1  DELETE the stale Interactive Brokers row ($0.00, 2026-02-25, updated_by='manual').
  T2  MERGE `Fidelity 401A` + `Fidelity 403B` -> ONE surviving row keyed
      account_name='BROKERAGE_LINK_401K' (the exact _DB_TO_NORMAL key that maps to
      brokerage_link_401k in backend/hub_mcp/tools/portfolio_balances.py), with
      balance/cash = the sum of both rows; delete the non-surviving row.

  (T3 — the portfolio_balances.py breakout_prop "untracked" payload entry — is CODE,
   handled in Phase 2 of the brief, NOT by this script.)

Modes (all DB access via get_postgres_client(); no ad-hoc connection strings):
  (default) / --inventory : Phase 0 read-only dump + G0 checks. No writes.
  --dry-run               : apply-in-a-rolled-back-transaction; before->after + invariants.
                            Writes the full-table pre-image. NO persisted writes.
  --apply --i-have-go     : pre-image -> reversal rehearsal -> real apply (single txn,
                            in-txn invariant SELECTs, ROLLBACK on any failure).
  --restore <preimage>    : restore the touched rows from a pre-image JSONL
                            (UPDATE-back the merged row + re-INSERT the deleted rows),
                            with an occupied-id guard + post-restore verification.

Concurrency safety (verified Phase 0: no trigger, no FK, UNIQUE(account_name),
id=serial): the merge SUM is computed IN-SQL from the two rows under FOR UPDATE row
locks taken inside the same transaction — never a stale literal captured before the
txn. This mirrors def_position_integrity.py's in-SQL transform pattern and closes the
lost-update window against the live writers (unified_positions cash-adjust,
portfolio cash-flow endpoints) that target the Fidelity rows by name.

Invariants (hard, in-txn, against a lock-consistent before-read):
  * Sigma(balance) across the table IDENTICAL before/after (IBKR contributes $0; the
    merge preserves the sum).
  * row count N -> N-2.
  * `Fidelity Roth` + `Robinhood` rows byte-identical (untouched).
  * no row other than the three targets touched (401A->merged UPDATE, 403B DELETE,
    IBKR DELETE); post-state account_name set == {BROKERAGE_LINK_401K, Fidelity Roth,
    Robinhood}.

updated_at policy: the surviving merged row KEEPS its original updated_at (no trigger
exists on the table). The consolidation is recorded in updated_by; updated_at honestly
reflects the underlying data age (June-9 screenshots), so the row stays honestly
`is_stale`. (Surfaced at G1 for Fable to override if desired.)

Modeled on scripts/def_position_integrity.py's runbook conventions.

Usage:
  python scripts/reconcile_accounts_apply.py                  # Phase 0 read-only
  python scripts/reconcile_accounts_apply.py --dry-run        # rolled-back preview
  python scripts/reconcile_accounts_apply.py --apply --i-have-go
  python scripts/reconcile_accounts_apply.py --restore <preimage.jsonl>
"""
import argparse
import asyncio
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

# Windows consoles default to cp1252; force UTF-8 so a print() can never raise
# (a print crash inside the apply transaction must never be able to abort it).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _load_db_env():
    """Hydrate DB_* from .mcp.json when not already set (local). No-op on Railway.
    Mirrors scripts/def_position_integrity.py."""
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

TABLE = "account_balances"
ALL_COLS = ["id", "account_name", "broker", "balance", "cash",
            "buying_power", "margin_total", "updated_at", "updated_by"]

IBKR_NAME = "Interactive Brokers"
F401A_NAME = "Fidelity 401A"
F403B_NAME = "Fidelity 403B"
SURVIVING_KEY = "BROKERAGE_LINK_401K"          # _DB_TO_NORMAL key -> brokerage_link_401k
MERGE_ANNOTATION = "pivot_screenshot; consolidated 401A+403B 2026-07-23"
UNTOUCHED_NAMES = ("Fidelity Roth", "Robinhood")   # byte-identical invariant
EXPECTED_POST_NAMES = {SURVIVING_KEY, *UNTOUCHED_NAMES}

PRE_NAME = "2026-07-23-reconciliation-preimage.jsonl"

# ---- explicit-key, parameterized SQL (no interpolated VALUES) ----
# Lock the three target rows FOR UPDATE inside the txn before reading/merging, so the
# merge sum is computed from a lock-consistent snapshot (no lost update vs live writers).
LOCK_SQL = f"SELECT id FROM {TABLE} WHERE account_name = ANY($1::text[]) FOR UPDATE"

# Merge computes balance/cash IN-SQL by self-joining 401A (t) to 403B (src); the rows
# are already locked by LOCK_SQL. updated_at is intentionally NOT in the SET (preserved).
MERGE_UPDATE_SQL = f"""
UPDATE {TABLE} t
SET account_name = $2,
    balance      = t.balance + src.balance,
    cash         = CASE WHEN t.cash IS NULL AND src.cash IS NULL THEN NULL
                        ELSE COALESCE(t.cash, 0) + COALESCE(src.cash, 0) END,
    updated_by   = $3
FROM {TABLE} src
WHERE t.account_name = $1 AND src.account_name = $4
"""
# Idempotency guards: IBKR delete requires balance=0 (a refunded row is NOT stale);
# 403B delete keys on its exact name. Both match at most one row (UNIQUE(account_name)).
DELETE_403B_SQL = f"DELETE FROM {TABLE} WHERE account_name = $1"
DELETE_IBKR_SQL = f"DELETE FROM {TABLE} WHERE account_name = $1 AND balance = 0"

# ---- DEF-SEED-RESURRECTION cleanup (2026-07-24) ----
# The buggy per-account startup seed resurrected the three rows this apply deleted, on
# the T3 deploy restart. Delete them keyed on the FULL re-seed signature (id + name +
# balance + the 00:21:10Z updated_at). Any mismatch on any target aborts the whole txn.
# Runs ONLY after the seed fix is deployed (else the next restart re-seeds again).
RESEED_PRE_NAME = "2026-07-24-reseed-cleanup-preimage.jsonl"
RESEED_TARGETS = [
    {"id": 6, "account_name": "Fidelity 401A",
     "balance": Decimal("10107.90"), "updated_at": "2026-07-24T00:21:10.210320+00:00"},
    {"id": 7, "account_name": "Fidelity 403B",
     "balance": Decimal("233.15"), "updated_at": "2026-07-24T00:21:10.215646+00:00"},
    {"id": 8, "account_name": "Interactive Brokers",
     "balance": Decimal("0.00"), "updated_at": "2026-07-24T00:21:10.221970+00:00"},
]
RESEED_DELETE_IDS = {t["id"] for t in RESEED_TARGETS}
# Post-cleanup the table must be EXACTLY these three survivors (the reconciled state):
EXPECTED_SURVIVORS = {
    "Robinhood": Decimal("835.69"),
    "BROKERAGE_LINK_401K": Decimal("11642.35"),
    "Fidelity Roth": Decimal("8842.09"),
}
EXPECTED_SURVIVOR_SUM = Decimal("21320.13")
DELETE_RESEED_SQL = (
    f"DELETE FROM {TABLE} "
    f"WHERE id = $1 AND account_name = $2 AND balance = $3 AND updated_at = $4"
)


class _Abort(Exception):
    """Precondition abort raised inside a txn so the finally-block rolls back cleanly."""


# ---------- serialization (round-trips Decimal / datetime / arrays / jsonb) ----------
def _ser(v):
    if v is None:
        return None
    if isinstance(v, Decimal):
        return {"_d": str(v)}
    if isinstance(v, datetime):
        return {"_t": v.isoformat()}
    if isinstance(v, date):
        return {"_D": v.isoformat()}
    if isinstance(v, list):
        return {"_a": [_ser(x) for x in v]}
    if isinstance(v, dict):
        return {"_j": v}
    return v


def _deser(v):
    if isinstance(v, dict):
        if "_d" in v:
            return Decimal(v["_d"])
        if "_t" in v:
            return datetime.fromisoformat(v["_t"])
        if "_D" in v:
            return date.fromisoformat(v["_D"])
        if "_a" in v:
            return [_deser(x) for x in v["_a"]]
        if "_j" in v:
            return v["_j"]
    return v


def _rowcount(status):
    try:
        return int(status.split()[-1])
    except (ValueError, AttributeError, IndexError):
        return -1


async def _fetch_table(conn):
    return await conn.fetch(f"SELECT {', '.join(ALL_COLS)} FROM {TABLE} ORDER BY id")


def _by_name(rows):
    return {r["account_name"]: r for r in rows}


def _by_id(rows):
    return {r["id"]: r for r in rows}


def _sum_balance(rows):
    return sum((r["balance"] for r in rows), Decimal(0))


def _merged_cash(a, b):
    ac, bc = a["cash"], b["cash"]
    if ac is None and bc is None:
        return None
    return (ac or Decimal(0)) + (bc or Decimal(0))


def _fmt_row(r):
    return (f"id={r['id']} name={r['account_name']!r} broker={r['broker']!r} "
            f"balance={r['balance']} cash={r['cash']} bp={r['buying_power']} "
            f"margin={r['margin_total']} updated_at={r['updated_at']} "
            f"updated_by={r['updated_by']!r}")


# ==================== pre-image / restore ====================
def _preimage_records(rows, a_id, b_id, ibkr_id):
    def op(rid):
        if rid == a_id:
            return "merge_survive"
        if rid in (b_id, ibkr_id):
            return "delete"
        return "untouched"
    recs = []
    for r in rows:
        d = {k: _ser(v) for k, v in dict(r).items()}
        d["_op"] = op(r["id"])
        d["_touched"] = d["_op"] != "untouched"
        recs.append(d)
    return recs


def _write_preimage(recs):
    archive = Path(__file__).resolve().parent.parent / "backend" / "database" / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    p1 = archive / PRE_NAME
    p2 = Path(r"C:\temp") / PRE_NAME
    body = "".join(json.dumps(r) + "\n" for r in recs)
    p1.write_text(body, encoding="utf-8")
    p2.parent.mkdir(parents=True, exist_ok=True)
    p2.write_text(body, encoding="utf-8")
    touched = sum(1 for r in recs if r["_touched"])
    print(f"  pre-image: {len(recs)} rows ({touched} touched) -> {p1}\n"
          f"            copy -> {p2}")
    return p1, p2


async def _restore_rec(conn, rec):
    """Restore one row to its pre-image state. Deleted rows are re-INSERTed with their
    explicit id, but ONLY if that id is free or already holds the same account (never
    overwrite an unrelated row that reused a freed id). The merged survivor is
    UPDATE-ed back by id."""
    vals = {c: _deser(rec[c]) for c in ALL_COLS}
    rid = vals["id"]
    if rec["_op"] == "delete":
        existing = await conn.fetchrow(f"SELECT account_name FROM {TABLE} WHERE id = $1", rid)
        if existing is not None:
            if existing["account_name"] != vals["account_name"]:
                raise RuntimeError(
                    f"restore refused: id={rid} now holds {existing['account_name']!r}, "
                    f"not the pre-image {vals['account_name']!r} — will not overwrite")
            return 0  # already present as expected — idempotent no-op
        cols = ", ".join(ALL_COLS)
        ph = ", ".join(f"${i + 1}" for i in range(len(ALL_COLS)))
        status = await conn.execute(
            f"INSERT INTO {TABLE} ({cols}) VALUES ({ph})", *[vals[c] for c in ALL_COLS])
        return _rowcount(status)
    # merge_survive -> UPDATE every non-id column back by id
    setcols = [c for c in ALL_COLS if c != "id"]
    set_sql = ", ".join(f"{c} = ${i + 2}" for i, c in enumerate(setcols))
    status = await conn.execute(
        f"UPDATE {TABLE} SET {set_sql} WHERE id = $1", rid, *[vals[c] for c in setcols])
    return _rowcount(status)


# ==================== preconditions + transform ====================
def _preconditions(by_name):
    """Return (ok, msg). Verifies the three target rows are in their pre-merge shape."""
    for nm in (IBKR_NAME, F401A_NAME, F403B_NAME, *UNTOUCHED_NAMES):
        if nm not in by_name:
            return False, f"missing expected row account_name={nm!r} (already applied? changed?)"
    if SURVIVING_KEY in by_name:
        return False, f"row {SURVIVING_KEY!r} already exists (already merged?)"
    ibkr = by_name[IBKR_NAME]
    if ibkr["balance"] != 0:
        return False, f"IBKR balance is {ibkr['balance']} (expected 0) — refunded? refusing to delete"
    for nm in (F401A_NAME, F403B_NAME):
        if by_name[nm]["balance"] is None or by_name[nm]["balance"] < 0:
            return False, f"{nm} balance {by_name[nm]['balance']} invalid (null/negative)"
    return True, "ok"


async def _apply_ops(conn):
    """Merge (in-SQL sum) + the two deletes. Caller must have taken FOR UPDATE locks."""
    n_merge = _rowcount(await conn.execute(
        MERGE_UPDATE_SQL, F401A_NAME, SURVIVING_KEY, MERGE_ANNOTATION, F403B_NAME))
    n_403b = _rowcount(await conn.execute(DELETE_403B_SQL, F403B_NAME))
    n_ibkr = _rowcount(await conn.execute(DELETE_IBKR_SQL, IBKR_NAME))
    return n_merge, n_403b, n_ibkr


async def _lock_and_read(conn):
    """Inside an open txn: lock the 3 targets FOR UPDATE, read the lock-consistent
    before-state, re-check preconditions, derive expected merge values + pre-image recs.
    Raises _Abort on any precondition failure."""
    await conn.execute(LOCK_SQL, [F401A_NAME, F403B_NAME, IBKR_NAME])
    before = await _fetch_table(conn)
    by_name = _by_name(before)
    ok, msg = _preconditions(by_name)
    if not ok:
        raise _Abort(msg)
    a, b, ibkr = by_name[F401A_NAME], by_name[F403B_NAME], by_name[IBKR_NAME]
    merged_balance = a["balance"] + b["balance"]
    merged_cash = _merged_cash(a, b)
    recs = _preimage_records(before, a["id"], b["id"], ibkr["id"])
    return before, a, b, ibkr, merged_balance, merged_cash, recs


def _check_invariants(before_rows, after_rows, a_id, b_id, ibkr_id,
                      merged_balance, merged_cash):
    fails = []
    b_before, b_after = _by_id(before_rows), _by_id(after_rows)

    # 1. Sigma(balance) identical
    sb, sa = _sum_balance(before_rows), _sum_balance(after_rows)
    if sb != sa:
        fails.append(f"Sigma(balance) {sb} -> {sa} (must be identical)")

    # 2. row count N -> N-2
    if len(after_rows) != len(before_rows) - 2:
        fails.append(f"row count {len(before_rows)} -> {len(after_rows)} (expected N-2)")

    # 3. deleted rows gone
    if b_id in b_after:
        fails.append(f"403B row id={b_id} still present")
    if ibkr_id in b_after:
        fails.append(f"IBKR row id={ibkr_id} still present")

    # 4. surviving merged row correct + non-merge cols preserved
    surv = b_after.get(a_id)
    a_pre = b_before[a_id]
    if surv is None:
        fails.append(f"surviving row id={a_id} missing after merge")
    else:
        if surv["account_name"] != SURVIVING_KEY:
            fails.append(f"survivor account_name {surv['account_name']} != {SURVIVING_KEY}")
        if surv["balance"] != merged_balance:
            fails.append(f"survivor balance {surv['balance']} != {merged_balance}")
        if surv["cash"] != merged_cash:
            fails.append(f"survivor cash {surv['cash']} != {merged_cash}")
        if surv["updated_by"] != MERGE_ANNOTATION:
            fails.append(f"survivor updated_by {surv['updated_by']!r} != {MERGE_ANNOTATION!r}")
        for c in ("broker", "buying_power", "margin_total", "updated_at"):
            if surv[c] != a_pre[c]:
                fails.append(f"survivor {c} changed {a_pre[c]} -> {surv[c]} (must be preserved)")

    # 5. untouched rows byte-identical
    before_by_name, after_by_name = _by_name(before_rows), _by_name(after_rows)
    for nm in UNTOUCHED_NAMES:
        rb, ra = before_by_name.get(nm), after_by_name.get(nm)
        if rb is None or ra is None or dict(rb) != dict(ra):
            fails.append(f"untouched row {nm!r} changed: {dict(rb) if rb else None} -> "
                         f"{dict(ra) if ra else None}")

    # 6. no stray rows — exact post-state name set
    post_names = set(after_by_name.keys())
    if post_names != EXPECTED_POST_NAMES:
        fails.append(f"post-state account_name set {post_names} != {EXPECTED_POST_NAMES}")

    return fails, sb, sa


# ==================== PHASE 0 inventory (read-only) ====================
async def inventory(conn):
    rows = await _fetch_table(conn)
    by_name = _by_name(rows)
    print("========== PHASE 0 · account_balances FULL DUMP (read-only) ==========")
    for r in rows:
        print("  " + _fmt_row(r))
    print(f"\n  row count: {len(rows)}")
    print(f"  Sigma(balance): {_sum_balance(rows)}")

    print("\n========== G0 EXPECTATIONS ==========")
    ibkr = [r for r in rows if r["account_name"] == IBKR_NAME]
    f401a = [r for r in rows if r["account_name"] == F401A_NAME]
    f403b = [r for r in rows if r["account_name"] == F403B_NAME]
    checks = [
        (f"exactly one {IBKR_NAME} row, $0.00",
         len(ibkr) == 1 and ibkr and ibkr[0]["balance"] == 0),
        (f"exactly one {F401A_NAME} row", len(f401a) == 1),
        (f"exactly one {F403B_NAME} row", len(f403b) == 1),
        ("Fidelity Roth present", "Fidelity Roth" in by_name),
        ("Robinhood present", "Robinhood" in by_name),
        (f"zero {SURVIVING_KEY} / breakout_prop rows",
         SURVIVING_KEY not in by_name
         and not any("BREAKOUT" in (r["account_name"] or "").upper() for r in rows)),
    ]
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    all_ok = all(ok for _, ok in checks)
    print(f"\n  G0: {'ALL EXPECTATIONS MET ✓' if all_ok else 'DEVIATION — STOP, hand back'}")
    if ibkr:
        print(f"\n  T1 target (delete): {_fmt_row(ibkr[0])}")
    if f401a and f403b:
        mb = f401a[0]["balance"] + f403b[0]["balance"]
        mc = _merged_cash(f401a[0], f403b[0])
        print(f"  T2 survivor key   : {SURVIVING_KEY}  (keep id={f401a[0]['id']})")
        print(f"  T2 merged balance : {f401a[0]['balance']} + {f403b[0]['balance']} = {mb}")
        print(f"  T2 merged cash    : {mc}")
        print(f"  T2 target (delete): {_fmt_row(f403b[0])}")
    print("\n========== INVENTORY COMPLETE (read-only, zero writes) ==========")


# ==================== dry-run ====================
async def dry_run(conn):
    print("========== DRY-RUN (apply-in-rolled-back-transaction) ==========")
    # fast outside-txn precondition check for a clean early message
    ok, msg = _preconditions(_by_name(await _fetch_table(conn)))
    if not ok:
        print(f"  ABORT precondition: {msg}")
        return

    tr = conn.transaction()
    await tr.start()
    try:
        before, a, b, ibkr, merged_balance, merged_cash, recs = await _lock_and_read(conn)
        a_id, b_id, ibkr_id = a["id"], b["id"], ibkr["id"]
        _write_preimage(recs)

        print("\n  --- T1 DELETE (Interactive Brokers) ---")
        print("      " + _fmt_row(ibkr))
        print("\n  --- T2 MERGE (Fidelity 401A + 403B -> BROKERAGE_LINK_401K) ---")
        print("      before 401A: " + _fmt_row(a))
        print("      before 403B: " + _fmt_row(b))
        print(f"      merged     : name={SURVIVING_KEY!r} balance={a['balance']}+{b['balance']}"
              f"={merged_balance} cash={merged_cash} updated_by={MERGE_ANNOTATION!r}")
        print(f"      updated_at : {a['updated_at']}  (PRESERVED — honest data-age; no trigger)")
        print("      delete 403B: " + _fmt_row(b))

        n_merge, n_403b, n_ibkr = await _apply_ops(conn)
        after = await _fetch_table(conn)
        print(f"\n  rows affected: merge={n_merge} (exp 1)  del-403B={n_403b} (exp 1)  "
              f"del-IBKR={n_ibkr} (exp 1)")
        print("\n  --- POST-STATE (in rolled-back txn) ---")
        for r in after:
            print("      " + _fmt_row(r))
        fails, sb, sa = _check_invariants(before, after, a_id, b_id, ibkr_id,
                                          merged_balance, merged_cash)
        print(f"\n  invariant Sigma(balance): {sb} -> {sa} "
              f"({'IDENTICAL ✓' if sb == sa else 'CHANGED ✗'})")
        print(f"  invariant row count     : {len(before)} -> {len(after)} "
              f"({'N-2 ✓' if len(after) == len(before) - 2 else 'WRONG ✗'})")
        print("  INVARIANTS: " + ("ALL OK ✓" if not fails else "FAIL -> " + "; ".join(fails)))
    except _Abort as exc:
        print(f"  ABORT precondition (in-txn): {exc}")
    finally:
        await tr.rollback()
    print("\n  DRY-RUN rolled back — nothing persisted. Pre-image written.")
    print("  Re-run with --apply --i-have-go after the G1 gate is GO'd.")


# ==================== apply ====================
async def apply(conn, i_have_go):
    print("========== APPLY ==========")
    before0 = await _fetch_table(conn)
    ok, msg = _preconditions(_by_name(before0))
    if not ok:
        print(f"  ABORT precondition: {msg}")
        return

    if not i_have_go:
        # still emit a pre-image artifact for inspection, then refuse.
        bn = _by_name(before0)
        _write_preimage(_preimage_records(before0, bn[F401A_NAME]["id"],
                                          bn[F403B_NAME]["id"], bn[IBKR_NAME]["id"]))
        print("\n  REFUSED: --apply requires --i-have-go (phase-gate acknowledgement).")
        return

    # ---- reversal rehearsal: BEGIN -> apply -> restore-from-preimage -> verify -> ROLLBACK ----
    print("\n  --- reversal rehearsal (apply -> restore -> verify -> rollback) ---")
    ok_reh = True
    tr = conn.transaction()
    await tr.start()
    try:
        before, a, b, ibkr, _mb, _mc, recs = await _lock_and_read(conn)
        touched = [r for r in recs if r["_touched"]]
        await _apply_ops(conn)
        for rec in touched:
            await _restore_rec(conn, rec)
        restored = _by_id(await _fetch_table(conn))
        for rec in touched:
            rid = _deser(rec["id"])
            cur = restored.get(rid)
            if cur is None:
                ok_reh = False
                print(f"    REHEARSAL MISMATCH id={rid}: row absent after restore")
                continue
            for c in ALL_COLS:
                if cur[c] != _deser(rec[c]):
                    ok_reh = False
                    print(f"    REHEARSAL MISMATCH id={rid}.{c}: {cur[c]} != {_deser(rec[c])}")
        print(f"    rehearsal restore fidelity: "
              f"{'OK ✓ (restore path verified)' if ok_reh else 'FAIL'}")
    except _Abort as exc:
        ok_reh = False
        print(f"    rehearsal ABORT precondition: {exc}")
    finally:
        await tr.rollback()
    if not ok_reh:
        print("  ABORT: reversal rehearsal failed — not applying.")
        return

    # ---- real apply: single txn, in-txn invariant SELECTs, commit-or-rollback ----
    print("\n  --- real apply (single transaction) ---")
    tr = conn.transaction()
    await tr.start()
    committed = False
    try:
        before, a, b, ibkr, merged_balance, merged_cash, recs = await _lock_and_read(conn)
        a_id, b_id, ibkr_id = a["id"], b["id"], ibkr["id"]
        _write_preimage(recs)  # authoritative: written from the lock-consistent read
        n_merge, n_403b, n_ibkr = await _apply_ops(conn)
        if (n_merge, n_403b, n_ibkr) != (1, 1, 1):
            raise RuntimeError(f"rowcount guard: merge={n_merge} del403B={n_403b} "
                               f"delIBKR={n_ibkr} (all must be 1)")
        after = await _fetch_table(conn)
        fails, sb, sa = _check_invariants(before, after, a_id, b_id, ibkr_id,
                                          merged_balance, merged_cash)
        if fails:
            raise RuntimeError("invariant failure -> " + "; ".join(fails))
        await tr.commit()
        committed = True
    except Exception as exc:
        if not committed:
            await tr.rollback()
        print(f"    ROLLED BACK — {exc}")
        return

    # committed is guaranteed True here — success reporting cannot misfire as rollback.
    print(f"    applied: merge={n_merge} del403B={n_403b} delIBKR={n_ibkr}; "
          f"Sigma(balance) {sb}=={sa}; row count {len(before)}->{len(after)}; "
          f"invariants OK ✓  COMMITTED")
    try:
        final = await _fetch_table(conn)
        print("\n  POST-APPLY table:")
        for r in final:
            print("      " + _fmt_row(r))
    except Exception as exc:
        print(f"  (committed OK; post-commit read-back failed to print: {exc})")


async def restore(conn, path):
    print(f"========== RESTORE from {path} ==========")
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    recs = [json.loads(ln) for ln in lines if ln.strip()]
    touched = [r for r in recs if r.get("_touched")]
    tr = conn.transaction()
    await tr.start()
    try:
        for rec in touched:
            n = await _restore_rec(conn, rec)
            print(f"  restored id={_deser(rec['id'])} ({rec['_op']}): {n} row(s)")
        # post-restore verification: every touched row must now match the pre-image
        cur = _by_id(await _fetch_table(conn))
        bad = []
        for rec in touched:
            rid = _deser(rec["id"])
            row = cur.get(rid)
            if row is None:
                bad.append(f"id={rid} absent after restore")
                continue
            for c in ALL_COLS:
                if row[c] != _deser(rec[c]):
                    bad.append(f"id={rid}.{c}: {row[c]} != {_deser(rec[c])}")
        if bad:
            raise RuntimeError("post-restore verify failed -> " + "; ".join(bad))
        await tr.commit()
    except Exception as exc:
        await tr.rollback()
        print(f"  ROLLED BACK — {exc}")
        return
    print("  RESTORE committed + verified.")


# ==================== DEF-SEED-RESURRECTION cleanup ====================
def _reseed_preimage_records(rows):
    recs = []
    for r in rows:
        d = {k: _ser(v) for k, v in dict(r).items()}
        d["_op"] = "delete" if r["id"] in RESEED_DELETE_IDS else "untouched"
        d["_touched"] = r["id"] in RESEED_DELETE_IDS
        recs.append(d)
    return recs


def _write_reseed_preimage(recs):
    archive = Path(__file__).resolve().parent.parent / "backend" / "database" / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    p1 = archive / RESEED_PRE_NAME
    p2 = Path(r"C:\temp") / RESEED_PRE_NAME
    body = "".join(json.dumps(r) + "\n" for r in recs)
    p1.write_text(body, encoding="utf-8")
    p2.parent.mkdir(parents=True, exist_ok=True)
    p2.write_text(body, encoding="utf-8")
    print(f"  reseed pre-image: {len(recs)} rows "
          f"({sum(1 for r in recs if r['_touched'])} touched) -> {p1}\n"
          f"                   copy -> {p2}")


def _verify_reseed_targets(by_id):
    """FULL-match each target (id + account_name + balance + updated_at). Any mismatch
    on any target => not ok => caller aborts the whole operation before any write."""
    msgs = []
    for t in RESEED_TARGETS:
        r = by_id.get(t["id"])
        if r is None:
            msgs.append(f"target id={t['id']} ({t['account_name']}) not present")
            continue
        exp_ts = datetime.fromisoformat(t["updated_at"])
        if r["account_name"] != t["account_name"]:
            msgs.append(f"id={t['id']} account_name {r['account_name']!r} != {t['account_name']!r}")
        if r["balance"] != t["balance"]:
            msgs.append(f"id={t['id']} balance {r['balance']} != {t['balance']}")
        if r["updated_at"] != exp_ts:
            msgs.append(f"id={t['id']} updated_at {r['updated_at']} != {exp_ts}")
    return (not msgs), msgs


async def cleanup_reseed(conn, i_have_go):
    print("========== DEF-SEED-RESURRECTION CLEANUP (delete 3 re-seeded rows) ==========")
    before = await _fetch_table(conn)
    by_id, by_name = _by_id(before), _by_name(before)

    print(f"  live rows: {len(before)}")
    for r in before:
        tag = "DELETE" if r["id"] in RESEED_DELETE_IDS else "keep  "
        print(f"    [{tag}] " + _fmt_row(r))

    ok, msgs = _verify_reseed_targets(by_id)
    if not ok:
        print("\n  ABORT full-match (id+name+balance+updated_at): " + "; ".join(msgs))
        return
    surv_bad = []
    for nm, bal in EXPECTED_SURVIVORS.items():
        r = by_name.get(nm)
        if r is None or r["balance"] != bal:
            surv_bad.append(f"{nm}: {None if r is None else r['balance']} != {bal}")
    if surv_bad:
        print("\n  ABORT survivor precheck: " + "; ".join(surv_bad))
        return

    _write_reseed_preimage(_reseed_preimage_records(before))
    surv_pre = {nm: by_name[nm] for nm in EXPECTED_SURVIVORS}

    if not i_have_go:
        print("\n  DRY-RUN only (full-match verified) — re-run with "
              "--cleanup-reseed --i-have-go to delete.")
        return

    tr = conn.transaction()
    await tr.start()
    committed = False
    try:
        for t in RESEED_TARGETS:
            n = _rowcount(await conn.execute(
                DELETE_RESEED_SQL, t["id"], t["account_name"], t["balance"],
                datetime.fromisoformat(t["updated_at"])))
            if n != 1:
                raise RuntimeError(f"delete id={t['id']} matched {n} rows (must be exactly 1)")
        after = await _fetch_table(conn)
        after_by_name = _by_name(after)
        fails = []
        if set(after_by_name) != set(EXPECTED_SURVIVORS):
            fails.append(f"post-state names {set(after_by_name)} != {set(EXPECTED_SURVIVORS)}")
        for nm, bal in EXPECTED_SURVIVORS.items():
            r = after_by_name.get(nm)
            if r is None or r["balance"] != bal:
                fails.append(f"survivor {nm} balance {None if r is None else r['balance']} != {bal}")
        s = _sum_balance(after)
        if s != EXPECTED_SURVIVOR_SUM:
            fails.append(f"Sigma(balance) {s} != {EXPECTED_SURVIVOR_SUM}")
        for nm in EXPECTED_SURVIVORS:
            if after_by_name[nm]["updated_at"] != surv_pre[nm]["updated_at"]:
                fails.append(f"survivor {nm} updated_at changed (must be preserved)")
        if len(after) != 3:
            fails.append(f"row count {len(after)} != 3")
        if fails:
            raise RuntimeError("invariant failure -> " + "; ".join(fails))
        await tr.commit()
        committed = True
    except Exception as exc:
        if not committed:
            await tr.rollback()
        print(f"    ROLLED BACK — {exc}")
        return
    print(f"    deleted 3 re-seeded rows; row count {len(before)}->3; "
          f"Sigma(balance)={EXPECTED_SURVIVOR_SUM}; survivors' updated_at preserved; "
          f"invariants OK ✓  COMMITTED")
    try:
        final = await _fetch_table(conn)
        print("\n  POST-CLEANUP table:")
        for r in final:
            print("      " + _fmt_row(r))
    except Exception as exc:
        print(f"  (committed OK; post-commit read-back failed to print: {exc})")


async def main():
    ap = argparse.ArgumentParser(description="RECONCILIATION APPLY (account_balances)")
    ap.add_argument("--inventory", action="store_true", help="Phase 0 read-only dump + G0 (default)")
    ap.add_argument("--dry-run", action="store_true", help="apply-in-rolled-back-txn preview")
    ap.add_argument("--apply", action="store_true", help="apply the mutation (needs --i-have-go)")
    ap.add_argument("--i-have-go", action="store_true", help="phase-gate acknowledgement for --apply")
    ap.add_argument("--restore", metavar="PREIMAGE", help="restore touched rows from a pre-image JSONL")
    ap.add_argument("--cleanup-reseed", action="store_true",
                    help="DEF-SEED-RESURRECTION: full-match delete of the 3 re-seeded rows "
                         "(dry-run unless --i-have-go)")
    args = ap.parse_args()

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        if args.restore:
            await restore(conn, args.restore)
        elif args.cleanup_reseed:
            await cleanup_reseed(conn, args.i_have_go)
        elif args.apply:
            await apply(conn, args.i_have_go)
        elif args.dry_run:
            await dry_run(conn)
        else:
            await inventory(conn)


if __name__ == "__main__":
    asyncio.run(main())
