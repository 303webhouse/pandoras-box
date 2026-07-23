#!/usr/bin/env python3
"""def_position_integrity.py — DEF-POSITION-INTEGRITY (P0).

Data-only maintenance on `unified_positions` (fake-healthy class):
  - SOXS 1-for-10 reverse-split correction on the one STRADDLING row.
  - XLF third-leg strike backfill (long_strike NULL -> 30.0).

Modes (all DB access via get_postgres_client(); no ad-hoc connection strings):
  (default) / --inventory : Phase 0 read-only inventory (P0.1..P0.5). No writes.
  --dry-run               : apply-in-a-rolled-back-transaction; prints before->after
                            + invariants. Writes the pre-image. NO persisted writes.
  --apply --i-have-go     : pre-image -> reversal rehearsal -> real apply (single txn,
                            in-txn invariant SELECTs, ROLLBACK on any failure).
  --restore <preimage>    : restore the touched rows from a pre-image JSONL.

Transform (STRADDLING SOXS row POS_SOXS_20260610_154556), per §1 + Nick's
2026-07-23 rulings (breakeven INCLUDED):
  quantity /10 ; entry_price x10 ; stop_loss x10 (NULL-safe) ;
  target_1 x10, target_2 x10 (NULL-safe) ; breakeven[] x10 (NULL-safe).
  UNTOUCHED: current_price (pipeline-owned), max_loss (dollar/ split-invariant),
  cost_basis (stored, split-invariant), unrealized_pnl (engine recomputes).
XLF backfill (POS_XLF_20260609_233128): long_strike NULL -> 30.0 (idempotent
predicate AND long_strike IS NULL).

Split classification boundary (UTC) uses columns entry_date / exit_date:
  < 2026-07-14T20:00:00Z -> PRE units ; >= 2026-07-15T08:00:00Z -> POST units ;
  between -> ANOMALOUS (human ruling).
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
    Mirrors scripts/quarantine_enrich_clobber.py."""
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

TABLE = "unified_positions"
PRE_CUTOFF = datetime(2026, 7, 14, 20, 0, 0, tzinfo=timezone.utc)
POST_CUTOFF = datetime(2026, 7, 15, 8, 0, 0, tzinfo=timezone.utc)
SPLIT_DAY = datetime(2026, 7, 15, 0, 0, 0, tzinfo=timezone.utc)

SOXS_ID = "POS_SOXS_20260610_154556"
XLF_ID = "POS_XLF_20260609_233128"
XLF_NEW_STRIKE = Decimal("30.0")
TOUCHED_IDS = (SOXS_ID, XLF_ID)
POST_ENTRY_BAND = (Decimal("35"), Decimal("55"))

# Columns each touched row mutates (used by restore + rehearsal).
SOXS_MUT_COLS = ["quantity", "entry_price", "stop_loss", "target_1", "target_2", "breakeven"]
XLF_MUT_COLS = ["long_strike"]

# SOXS: keyed by explicit id; idempotency guard entry_price < 20 (pre-split entry
# 4.0395 < 20 < post-split 40.395) prevents a double x10.
SOXS_UPDATE = f"""
UPDATE {TABLE}
SET quantity   = quantity / 10,
    entry_price = entry_price * 10,
    stop_loss  = stop_loss * 10,
    target_1   = target_1 * 10,
    target_2   = target_2 * 10,
    breakeven  = (SELECT array_agg(v * 10 ORDER BY o)
                  FROM unnest(breakeven) WITH ORDINALITY AS u(v, o))
WHERE position_id = $1 AND entry_price < 20
"""
XLF_UPDATE = f"""
UPDATE {TABLE}
SET long_strike = $2
WHERE position_id = $1 AND long_strike IS NULL
"""

PRICE_CANDIDATES = {
    "entry_price", "stop_loss", "target_1", "target_2", "current_price",
    "exit_price", "long_strike", "short_strike", "long_leg_price", "short_leg_price", "breakeven",
}
NEG_SCAN = {
    "entry_price", "current_price", "exit_price", "stop_loss", "target_1", "target_2",
    "long_strike", "short_strike", "long_leg_price", "short_leg_price", "cost_basis",
}
NUMERIC_TYPES = {"numeric", "double precision", "real", "integer", "bigint", "smallint"}


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


def _cb(qty, entry):
    if qty is None or entry is None:
        return None
    return Decimal(qty) * Decimal(entry)


def side(ts):
    if ts is None:
        return None
    if ts < PRE_CUTOFF:
        return "PRE"
    if ts >= POST_CUTOFF:
        return "POST"
    return "ANOMALOUS_WINDOW"


def classify(entry_date, exit_date, status):
    o, c = side(entry_date), side(exit_date)
    st = (status or "").upper()
    if o == "ANOMALOUS_WINDOW" or c == "ANOMALOUS_WINDOW":
        return "ANOMALOUS"
    if o == "PRE" and (st == "OPEN" or c == "POST"):
        return "STRADDLING"
    if o == "PRE" and c == "PRE":
        return "FULLY-PRE"
    if o == "POST":
        return "FULLY-POST"
    if o == "PRE" and c is None and st != "OPEN":
        return "REVIEW(open-PRE, exit_date NULL, status!=OPEN)"
    return "REVIEW"


async def _schema(conn):
    cols = await conn.fetch(
        """SELECT column_name, data_type, numeric_precision, numeric_scale, is_nullable
           FROM information_schema.columns WHERE table_name = $1 ORDER BY ordinal_position""",
        TABLE)
    return cols


# ==================== PHASE 0 INVENTORY (read-only) ====================
async def inventory(conn):
    cols = await _schema(conn)
    colnames = [c["column_name"] for c in cols]
    ts_cols = [c["column_name"] for c in cols
               if "timestamp" in c["data_type"] or c["data_type"] == "date"]
    pershare_cols = [c for c in colnames if c in PRICE_CANDIDATES]
    strike_cols = [c for c in colnames if "strike" in c]
    neg_cols = [c["column_name"] for c in cols
                if c["column_name"] in NEG_SCAN and c["data_type"] in NUMERIC_TYPES]

    def has(n):
        return n if n in colnames else None

    ticker_col = has("ticker") or has("symbol")
    id_col = has("position_id") or has("id")
    status_col = has("status")
    opened_col = has("entry_date") or has("opened_at")
    closed_col = has("exit_date") or has("closed_at")
    type_col = has("asset_type") or has("instrument_type")

    print("========== P0.1 SCHEMA: unified_positions ==========")
    for c in cols:
        num = f"({c['numeric_precision']},{c['numeric_scale']})" if c["numeric_precision"] else ""
        print(f"  {c['column_name']:<28} {c['data_type']}{num:<10} null={c['is_nullable']}")
    print(f"\n  timestamp cols          : {ts_cols}")
    print(f"  per-share price cols     : {pershare_cols}")
    print(f"  strike cols              : {strike_cols}")
    print(f"  ticker/id/status         : {ticker_col} / {id_col} / {status_col}")
    print(f"  opened/closed/type       : {opened_col} / {closed_col} / {type_col}")

    def sel_all():
        parts = [f'"{c}"' for c in colnames]
        parts += [f'"{c}"::text AS "{c}__txt"' for c in ts_cols]
        return ", ".join(parts)

    def tx(r, c):
        return r[f"{c}__txt"] if c in ts_cols else r[c]

    def g(r, n):
        return r[n] if n in colnames else None

    print("\n========== P0.2 SOXS inventory (all statuses) ==========")
    soxs = await conn.fetch(
        f'SELECT {sel_all()} FROM {TABLE} WHERE {ticker_col} = $1 ORDER BY {opened_col}', "SOXS")
    straddlers = 0
    for r in soxs:
        cls = classify(r[opened_col], r[closed_col], r[status_col])
        if cls == "STRADDLING":
            straddlers += 1
        print(f"  [{cls}] {g(r, id_col)} acct={g(r,'account')} type={g(r, type_col)} "
              f"status={r[status_col]} qty={g(r,'quantity')} entry={g(r,'entry_price')} "
              f"cost_basis={g(r,'cost_basis')} be={g(r,'breakeven')} cur={g(r,'current_price')} "
              f"max_loss={g(r,'max_loss')} uPnL={g(r,'unrealized_pnl')} "
              f"opened={tx(r,opened_col)} closed={tx(r,closed_col)}")
    print(f"\n  STRADDLING count = {straddlers} (EXPECTED 1: {SOXS_ID})")

    print("\n========== P0.3 split-exposure sweep (OPEN, opened < 2026-07-15) ==========")
    sweep = await conn.fetch(
        f"""SELECT {ticker_col} AS tkr, {id_col} AS pid, entry_price, current_price
            FROM {TABLE} WHERE {status_col} = 'OPEN' AND {opened_col} < $1
              AND entry_price IS NOT NULL AND current_price IS NOT NULL AND entry_price <> 0""",
        SPLIT_DAY)
    flagged = 0
    for r in sweep:
        ratio = float(r["current_price"]) / float(r["entry_price"])
        if (7 <= ratio <= 13) or (0.04 <= ratio <= 0.06):
            flagged += 1
            print(f"  ** FLAG {r['tkr']} {r['pid']} ratio={ratio:.3f} "
                  f"entry={r['entry_price']} cur={r['current_price']} **")
    print(f"  swept={len(sweep)} flagged={flagged} (EXPECTED: SOXS only)")

    print("\n========== P0.4 XLF inventory + neg-price scan ==========")
    xlf = await conn.fetch(
        f'SELECT {sel_all()} FROM {TABLE} WHERE {ticker_col} = $1 ORDER BY {opened_col}', "XLF")
    for r in xlf:
        print(f"  {g(r, id_col)} struct={g(r,'structure')} status={r[status_col]} qty={g(r,'quantity')} "
              f"entry={g(r,'entry_price')} long_strike={g(r,'long_strike')} "
              f"short_strike={g(r,'short_strike')} exp={tx(r,'expiry') if 'expiry' in colnames else None}")
    known = await conn.fetchrow(f'SELECT long_strike FROM {TABLE} WHERE {id_col} = $1', XLF_ID)
    print(f"  {XLF_ID} long_strike = {known['long_strike'] if known else 'NOT FOUND'} (EXPECTED NULL)")
    if neg_cols:
        nw = " OR ".join([f'"{c}" < 0' for c in neg_cols])
        neg = await conn.fetch(
            f'SELECT {id_col} AS pid, {ticker_col} AS tkr, {status_col} AS st, '
            + ", ".join([f'"{c}"' for c in neg_cols]) + f' FROM {TABLE} WHERE {nw}')
        print(f"  neg-price rows: {len(neg)} (report-only; brief hunts XLF specifically)")
        for r in neg:
            bad = ", ".join([f"{c}={r[c]}" for c in neg_cols if r[c] is not None and float(r[c]) < 0])
            print(f"    NEG {r['tkr']} {r['pid']} status={r['st']}: {bad}")

    print("\n========== P0.5 null-strike options sweep (excl. known XLF leg) ==========")
    if strike_cols and type_col:
        nw = " OR ".join([f'"{c}" IS NULL' for c in strike_cols])
        rows = await conn.fetch(
            f"""SELECT {id_col} AS pid, {ticker_col} AS tkr, {status_col} AS st, structure
                FROM {TABLE}
                WHERE lower({type_col}::text) NOT IN ('stock','equity','shares','etf')
                  AND ({nw}) AND {id_col} <> $1""", XLF_ID)
        print(f"  null-strike option rows: {len(rows)} (report-only)")
    print("\n========== INVENTORY COMPLETE (read-only, zero writes) ==========")


# ==================== pre-image / restore ====================
async def _fetch_all(conn, ticker):
    return await conn.fetch(f'SELECT * FROM {TABLE} WHERE ticker = $1 ORDER BY entry_date', ticker)


async def _fetch_one(conn, pid):
    return await conn.fetchrow(f'SELECT * FROM {TABLE} WHERE position_id = $1', pid)


def _preimage_records(soxs_rows, xlf_rows):
    recs = []
    for kind, rows in (("soxs", soxs_rows), ("xlf", xlf_rows)):
        for r in rows:
            d = {k: _ser(v) for k, v in dict(r).items()}
            d["_kind"] = kind
            d["_touched"] = (r["position_id"] in TOUCHED_IDS)
            recs.append(d)
    return recs


def _write_preimage(recs, ts):
    archive = Path(__file__).resolve().parent.parent / "backend" / "database" / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    name = "2026-07-23-def-position-integrity-preimage.jsonl"
    p1 = archive / name
    p2 = Path(r"C:\temp") / name
    body = "".join(json.dumps(r) + "\n" for r in recs)
    p1.write_text(body, encoding="utf-8")
    p2.parent.mkdir(parents=True, exist_ok=True)
    p2.write_text(body, encoding="utf-8")
    touched = sum(1 for r in recs if r["_touched"])
    print(f"  pre-image: {len(recs)} rows ({touched} touched) -> {p1}\n"
          f"            copy -> {p2}")
    return p1, p2


async def _restore_row(conn, rec):
    pid = rec["position_id"]
    cols = SOXS_MUT_COLS if pid == SOXS_ID else (XLF_MUT_COLS if pid == XLF_ID else None)
    if not cols:
        return 0
    set_sql = ", ".join([f'"{c}" = ${i + 2}' for i, c in enumerate(cols)])
    vals = [_deser(rec[c]) for c in cols]
    status = await conn.execute(
        f'UPDATE {TABLE} SET {set_sql} WHERE position_id = $1', pid, *vals)
    return _rowcount(status)


# ==================== dry-run / apply invariants ====================
async def _apply_updates(conn):
    n_soxs = _rowcount(await conn.execute(SOXS_UPDATE, SOXS_ID))
    n_xlf = _rowcount(await conn.execute(XLF_UPDATE, XLF_ID, XLF_NEW_STRIKE))
    return n_soxs, n_xlf


def _print_delta(tag, before, after, fields):
    print(f"  {tag}:")
    for f in fields:
        b, a = before[f], after[f]
        mark = "" if b == a else "   <-- CHANGED"
        note = "   (untouched)" if b == a and f in ("current_price", "max_loss", "cost_basis") else ""
        print(f"      {f:<14} {b}  ->  {a}{mark}{note}")


def _check_invariants(sb, sa, xb, xa, total_before, total_after):
    fails = []
    cb_b, cb_a = _cb(sb["quantity"], sb["entry_price"]), _cb(sa["quantity"], sa["entry_price"])
    if cb_b is None or cb_a is None or abs(cb_b - cb_a) >= Decimal("0.01"):
        fails.append(f"cost-basis qty*entry {cb_b} -> {cb_a} (Δ must be < 0.01)")
    if sb["max_loss"] != sa["max_loss"]:
        fails.append(f"max_loss changed {sb['max_loss']} -> {sa['max_loss']}")
    if sb["cost_basis"] != sa["cost_basis"]:
        fails.append(f"stored cost_basis changed {sb['cost_basis']} -> {sa['cost_basis']}")
    if sb["current_price"] != sa["current_price"]:
        fails.append(f"current_price changed {sb['current_price']} -> {sa['current_price']}")
    lo, hi = POST_ENTRY_BAND
    if sa["entry_price"] is None or not (lo <= sa["entry_price"] <= hi):
        fails.append(f"post entry {sa['entry_price']} outside plausible band {lo}-{hi}")
    if sa["quantity"] != sb["quantity"] // 10:
        fails.append(f"quantity {sb['quantity']} -> {sa['quantity']} (expected /10)")
    if xa["long_strike"] != XLF_NEW_STRIKE:
        fails.append(f"XLF long_strike {xa['long_strike']} (expected {XLF_NEW_STRIKE})")
    if total_before != total_after:
        fails.append(f"row-count invariance {total_before} -> {total_after}")
    return fails, cb_b, cb_a


async def dry_run(conn, ts):
    print("========== DRY-RUN (apply-in-rolled-back-transaction) ==========")
    sb = await _fetch_one(conn, SOXS_ID)
    xb = await _fetch_one(conn, XLF_ID)
    if not sb or not xb:
        print("  ABORT: a touched row was not found.")
        return
    if sb["quantity"] % 10 != 0:
        print(f"  ABORT: SOXS quantity {sb['quantity']} not divisible by 10.")
        return
    _write_preimage(_preimage_records(await _fetch_all(conn, "SOXS"), await _fetch_all(conn, "XLF")), ts)

    total_before = await conn.fetchval(f"SELECT count(*) FROM {TABLE}")
    tr = conn.transaction()
    await tr.start()
    try:
        n_soxs, n_xlf = await _apply_updates(conn)
        sa = await _fetch_one(conn, SOXS_ID)
        xa = await _fetch_one(conn, XLF_ID)
        total_after = await conn.fetchval(f"SELECT count(*) FROM {TABLE}")
        print(f"\n  rows affected: SOXS={n_soxs} (expect 1)  XLF={n_xlf} (expect 1)")
        _print_delta(f"SOXS {SOXS_ID}", sb, sa,
                     ["quantity", "entry_price", "breakeven", "stop_loss", "target_1", "target_2",
                      "current_price", "max_loss", "cost_basis"])
        _print_delta(f"XLF  {XLF_ID}", xb, xa, ["long_strike"])
        fails, cb_b, cb_a = _check_invariants(sb, sa, xb, xa, total_before, total_after)
        print(f"\n  invariant cost-basis qty*entry: {cb_b} -> {cb_a} (Δ={abs(cb_b - cb_a)})")
        print(f"  SET-list guard: max_loss / cost_basis / current_price NOT in any SET clause ✓")
        print("  INVARIANTS: " + ("ALL OK ✓" if not fails else "FAIL -> " + "; ".join(fails)))
        eng = None
        if sa["current_price"] is not None:
            eng = Decimal(sa["quantity"]) * (Decimal(sa["current_price"]) - Decimal(sa["entry_price"]))
        print(f"  (engine will recompute unrealized_pnl ~= qty*(cur-entry) = {eng})")
    finally:
        await tr.rollback()
    print("\n  DRY-RUN rolled back — nothing persisted. Pre-image written.")
    print("  Re-run with --apply --i-have-go after the G1 gate is GO'd.")


async def apply(conn, ts, i_have_go):
    print("========== APPLY ==========")
    sb = await _fetch_one(conn, SOXS_ID)
    xb = await _fetch_one(conn, XLF_ID)
    if not sb or not xb:
        print("  ABORT: a touched row was not found.")
        return
    if sb["entry_price"] is None or sb["entry_price"] >= 20:
        print(f"  ABORT: SOXS entry_price {sb['entry_price'] if sb else None} not in pre-split band "
              f"(<20). Already applied? Refusing.")
        return
    if sb["quantity"] % 10 != 0:
        print(f"  ABORT: SOXS quantity {sb['quantity']} not divisible by 10.")
        return
    if xb["long_strike"] is not None:
        print(f"  NOTE: XLF long_strike already {xb['long_strike']} (idempotent predicate will skip it).")

    recs = _preimage_records(await _fetch_all(conn, "SOXS"), await _fetch_all(conn, "XLF"))
    _write_preimage(recs, ts)

    if not i_have_go:
        print("\n  REFUSED: --apply requires --i-have-go (phase-gate acknowledgement).")
        return

    # ---- reversal rehearsal: BEGIN -> apply -> restore-from-preimage -> verify -> ROLLBACK ----
    print("\n  --- reversal rehearsal (apply -> restore -> verify -> rollback) ---")
    touched_recs = [r for r in recs if r["_touched"]]
    tr = conn.transaction()
    await tr.start()
    try:
        await _apply_updates(conn)
        for rec in touched_recs:
            await _restore_row(conn, rec)
        ok = True
        for rec in touched_recs:
            cur = await _fetch_one(conn, rec["position_id"])
            cols = SOXS_MUT_COLS if rec["position_id"] == SOXS_ID else XLF_MUT_COLS
            for c in cols:
                if cur[c] != _deser(rec[c]):
                    ok = False
                    print(f"    REHEARSAL MISMATCH {rec['position_id']}.{c}: {cur[c]} != {_deser(rec[c])}")
        print(f"    rehearsal restore fidelity: {'OK ✓ (restore path verified)' if ok else 'FAIL'}")
    finally:
        await tr.rollback()
    if not ok:
        print("  ABORT: reversal rehearsal failed — not applying.")
        return

    # ---- real apply: single txn, invariant SELECTs, commit-or-rollback ----
    print("\n  --- real apply (single transaction) ---")
    total_before = await conn.fetchval(f"SELECT count(*) FROM {TABLE}")
    tr = conn.transaction()
    await tr.start()
    committed = False
    try:
        n_soxs, n_xlf = await _apply_updates(conn)
        if n_soxs != 1 or n_xlf != 1:
            raise RuntimeError(f"rowcount guard: SOXS={n_soxs} XLF={n_xlf} (both must be 1)")
        sa = await _fetch_one(conn, SOXS_ID)
        xa = await _fetch_one(conn, XLF_ID)
        total_after = await conn.fetchval(f"SELECT count(*) FROM {TABLE}")
        fails, cb_b, cb_a = _check_invariants(sb, sa, xb, xa, total_before, total_after)
        if fails:
            raise RuntimeError("invariant failure -> " + "; ".join(fails))
        await tr.commit()
        committed = True
        print(f"    applied: SOXS={n_soxs} XLF={n_xlf}; cost-basis {cb_b}->{cb_a} (Δ={abs(cb_b-cb_a)}); "
              f"row-count {total_before}=={total_after}; invariants OK ✓  COMMITTED")
    except Exception as exc:
        if not committed:
            await tr.rollback()
        print(f"    ROLLED BACK — {exc}")
        return
    # post-commit read-back
    sa = await _fetch_one(conn, SOXS_ID)
    xa = await _fetch_one(conn, XLF_ID)
    print(f"\n  POST-APPLY SOXS: qty={sa['quantity']} entry={sa['entry_price']} breakeven={sa['breakeven']} "
          f"cost_basis={sa['cost_basis']} max_loss={sa['max_loss']} cur={sa['current_price']} "
          f"uPnL={sa['unrealized_pnl']}")
    print(f"  POST-APPLY XLF : long_strike={xa['long_strike']}")


async def restore(conn, path):
    print(f"========== RESTORE from {path} ==========")
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    recs = [json.loads(ln) for ln in lines if ln.strip()]
    touched = [r for r in recs if r.get("_touched")]
    tr = conn.transaction()
    await tr.start()
    try:
        for rec in touched:
            n = await _restore_row(conn, rec)
            print(f"  restored {rec['position_id']}: {n} row(s)")
        await tr.commit()
    except Exception as exc:
        await tr.rollback()
        print(f"  ROLLED BACK — {exc}")
        return
    print("  RESTORE committed.")


async def main():
    ap = argparse.ArgumentParser(description="DEF-POSITION-INTEGRITY maintenance")
    ap.add_argument("--inventory", action="store_true", help="Phase 0 read-only inventory (default)")
    ap.add_argument("--dry-run", action="store_true", help="apply-in-rolled-back-txn preview")
    ap.add_argument("--apply", action="store_true", help="apply the mutation (needs --i-have-go)")
    ap.add_argument("--i-have-go", action="store_true", help="phase-gate acknowledgement for --apply")
    ap.add_argument("--restore", metavar="PREIMAGE", help="restore touched rows from a pre-image JSONL")
    args = ap.parse_args()

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        if args.restore:
            await restore(conn, args.restore)
        elif args.apply:
            await apply(conn, ts, args.i_have_go)
        elif args.dry_run:
            await dry_run(conn, ts)
        else:
            await inventory(conn)


if __name__ == "__main__":
    asyncio.run(main())
