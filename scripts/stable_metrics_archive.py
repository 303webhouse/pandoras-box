"""R-IV.1033(c): ARCHIVE stable_metrics history to F: BEFORE anything is deleted.

DELETING 2021-2026 HISTORY IS IRREVERSIBLE, so the order is export, verify, and only then --
in Saturday's window -- delete. This script does the first two and DELETES NOTHING. It has no
DELETE statement in it at all, which is the only form of that assurance worth having.

THE VERIFY IS A COUNT MATCH ON THE SAME PREDICATE. The export and the eventual delete must
select the same rows, so both use `date < current_date - 180` and the script asserts that the
Parquet row count equals the count the predicate returns. A mismatch stops it: an archive one
row short of the deletion is a row destroyed.

PARTITIONED BY YEAR, because a 800k-row single file is awkward to read back and a reader
wanting 2023 should not load 2021-2026. Each file is read back, hashed, and reported so
`f_export.write_manifest()` picks it up (it walks all of F: since R-IV.1017(c)).
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
import tempfile

import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = r"F:\pandora-data"
OUT_DIR = os.path.join(ROOT, "stable_metrics_archive")

#: R-IV.1033(c): the retention boundary. The export and the delete MUST share this predicate.
RETAIN_DAYS = 180
PREDICATE = "date < current_date - %d" % RETAIN_DAYS


def _dsn() -> str:
    raw = open(os.path.join(REPO, ".mcp.json"), encoding="utf-8").read()
    for m in re.finditer(r"postgres(?:ql)?://[^\"\s]+", raw):
        if "railway.internal" not in m.group(0):
            return m.group(0)
    raise RuntimeError("no usable postgres URL in .mcp.json")


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_parquet(df: pd.DataFrame, path: str) -> dict:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".parquet", dir=os.path.dirname(path))
    os.close(fd)
    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    back = pd.read_parquet(path)
    return {"path": path, "rows": len(df), "rows_read_back": len(back),
            "bytes": os.path.getsize(path), "sha256": sha256_of(path),
            "ok": len(back) == len(df)}


def main() -> int:
    if not os.path.isdir("F:\\"):
        print("F: is not mounted; nothing archived")
        return 3
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(_dsn())
    # READ-ONLY SESSION. This script must not be able to delete even by accident.
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("SELECT count(*) AS n FROM stable_metrics WHERE " + PREDICATE)
    to_delete = cur.fetchone()["n"]
    cur.execute("SELECT count(*) AS n FROM stable_metrics")
    total = cur.fetchone()["n"]
    cur.execute("SELECT min(date) AS lo, max(date) AS hi FROM stable_metrics WHERE " + PREDICATE)
    span = cur.fetchone()
    print("stable_metrics archive — R-IV.1033(c)")
    print("  predicate            : %s   (retention %d days)" % (PREDICATE, RETAIN_DAYS))
    print("  rows in table        : %d" % total)
    print("  rows TO BE DELETED   : %d   span %s .. %s" % (to_delete, span["lo"], span["hi"]))
    print("  rows retained        : %d" % (total - to_delete))
    if not to_delete:
        print("  nothing older than the boundary; nothing archived")
        return 0

    cur.execute("SELECT DISTINCT extract(year FROM date)::int AS y FROM stable_metrics "
                "WHERE " + PREDICATE + " ORDER BY 1")
    years = [r["y"] for r in cur.fetchall()]
    print("  years to archive     : %s" % years)
    print()

    rows_written, manifest = 0, []
    for y in years:
        cur.execute("SELECT * FROM stable_metrics WHERE " + PREDICATE
                    + " AND extract(year FROM date)::int = %s ORDER BY date, ticker", (y,))
        recs = cur.fetchall()
        df = pd.DataFrame([dict(r) for r in recs])
        path = os.path.join(OUT_DIR, "stable_metrics_%d.parquet" % y)
        row = write_parquet(df, path)
        rows_written += row["rows"]
        manifest.append(row)
        print("  %d  %7d rows  %10d bytes  %s%s"
              % (y, row["rows"], row["bytes"], row["sha256"][:16],
                 "" if row["ok"] else "   READ-BACK MISMATCH"))

    print()
    print("  rows exported        : %d" % rows_written)
    print("  rows to be deleted   : %d" % to_delete)
    bad = [r for r in manifest if not r["ok"]]
    if bad or rows_written != to_delete:
        print()
        print("  >>> VERIFY FAILED. The DELETE must NOT run.")
        if rows_written != to_delete:
            print("      exported %d != %d selected by the delete predicate"
                  % (rows_written, to_delete))
        for r in bad:
            print("      read-back mismatch: %s" % r["path"])
        return 4

    print("  >>> VERIFIED: every row the delete predicate selects is on F:, read back and")
    print("      hashed. The DELETE and the rewrite are Saturday's, not this script's --")
    print("      there is no DELETE statement in this file and the session is read-only.")
    print()
    print("  Run scripts/f_export.py to fold these into MANIFEST.tsv (it walks all of F:).")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
