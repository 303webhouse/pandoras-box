"""Backfill 1-minute SPY from 2026-09-15 on — R-IV.680(b).

ORDER OF PREFERENCE, as the ruling sets it:
  1. take every session the VENDOR still serves, and check it against the capture;
  2. a session the vendor no longer serves comes FROM THE CAPTURE, hash-verified, with its
     provenance on each row.

MEASURED 2026-10-07: yfinance serves 1m SPY back to **2026-09-09**, so every session from 09-15 is
still live and **step 2 is not needed for any session today**. That is the whole reason the ruling
says to act before about 10-15: W1 leaves the vendor then, and after that the capture becomes the
only source for it. Running this now means the record is built from the vendor, with the capture as
a cross-check rather than a dependency.

THE CROSS-CHECK IS BUILT BUT UNEXERCISED. CC-QUERY's ferry file (5,460 bars, sha256 2db41815…) is
not in this repo and not reachable from this lane, so `verify_against_capture` has no file to read
yet. It is written now, with the hash gate first, so the check is one command when the file
arrives — and so that nobody later mistakes "no capture was available" for "the capture agreed".

Run:
    python -m jobs.spy_minute_backfill --dsn <dsn> [--from 2026-09-15] [--to <today>]
    python -m jobs.spy_minute_backfill --dsn <dsn> --capture <path> --capture-sha256 <hex>
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import io
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# W1's first session, per R-IV.680(b): "every session from 2026-09-15 on".
DEFAULT_START = date(2026, 9, 15)
CHUNK_DAYS = 7          # yfinance caps a 1m request at 7 days


def chunks(start: date, end: date, size: int = CHUNK_DAYS) -> List[Tuple[date, date]]:
    """[start, end) in <= `size`-day windows. yfinance treats `end` as exclusive."""
    out, a = [], start
    while a < end:
        b = min(a + timedelta(days=size), end)
        out.append((a, b))
        a = b
    return out


def capture_sha256(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def load_capture(path: str, expected_sha256: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """({bar_at_iso: {close: ...}}, error). THE HASH IS CHECKED FIRST.

    A capture that does not hash to what the ruling names is not that capture, and reading it
    anyway would put rows into a system of record under a provenance string that is false. The
    hash gate comes before the parse so a mismatched file is never even interpreted.
    """
    if not os.path.exists(path):
        return None, "capture not found at %s" % path
    actual = capture_sha256(path)
    want = (expected_sha256 or "").strip().lower().rstrip(".… ")
    # A PREFIX MATCH, deliberately: R-IV.680(b) quotes the capture's hash truncated
    # ("2db41815…"), so requiring full equality would reject the very file the ruling names.
    # It must still be a genuine prefix of the real digest, and short prefixes are refused --
    # eight hex characters is 32 bits, which is the shortest thing worth calling a verification.
    if want:
        if len(want) < 8:
            return None, ("capture sha256 %r is too short to verify against (need >= 8 hex)"
                          % expected_sha256)
        if not actual.startswith(want):
            return None, ("capture sha256 mismatch: file is %s..., expected prefix %s -- "
                          "refusing to read it" % (actual[:16], want))
    else:
        return None, ("no expected sha256 given. The capture is only admissible hash-verified "
                      "(R-IV.680(b)), so an unverified file is refused rather than trusted.")
    raw = io.open(path, encoding="utf-8-sig").read()
    rows: List[Dict[str, Any]] = []
    try:
        obj = json.loads(raw)
        rows = obj if isinstance(obj, list) else (obj.get("bars") or obj.get("data") or [])
    except ValueError:
        rows = list(csv.DictReader(io.StringIO(raw)))
    out: Dict[str, Any] = {}
    for r in rows:
        ts = r.get("bar_at") or r.get("timestamp") or r.get("Datetime") or r.get("datetime")
        if not ts:
            continue
        out[str(ts)] = r
    return {"sha256": actual, "by_instant": out, "count": len(out)}, None


def compare_to_capture(bars: List[Dict[str, Any]], capture: Dict[str, Any]) -> Dict[str, Any]:
    """How the vendor's bars line up with the capture, on the instants both hold.

    Reports agreement rather than asserting it: a disagreement is a finding about one of the two
    sources, and which one is wrong is not this function's call to make.
    """
    by = capture.get("by_instant") or {}
    checked = agreed = 0
    disagreements: List[Dict[str, Any]] = []
    for b in bars:
        key = b["bar_at"].isoformat()
        row = by.get(key) or by.get(key.replace("+00:00", "Z"))
        if row is None:
            continue
        checked += 1
        raw = row.get("close") or row.get("Close")
        try:
            same = raw is not None and Decimal(str(raw)) == b["close"]
        except Exception:  # noqa: BLE001
            same = False
        if same:
            agreed += 1
        elif len(disagreements) < 10:
            disagreements.append({"bar_at": key, "capture": str(raw), "vendor": str(b["close"])})
    return {"checked": checked, "agreed": agreed, "disagreements": disagreements,
            "rate": round(agreed / checked, 4) if checked else None}


async def run(dsn: str, start: date, end: date, capture: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    import asyncpg

    from jobs.spy_minute_sink import PROV_YFINANCE, fetch_1m, persist_bars, session_report

    conn = await asyncpg.connect(dsn)
    try:
        total = 0
        served: List[str] = []
        missing: List[Tuple[str, str]] = []
        all_bars: List[Dict[str, Any]] = []
        for a, b in chunks(start, end):
            bars, skip = await fetch_1m("SPY", a, b, auto_adjust=False)
            if skip:
                missing.append(("%s..%s" % (a, b), skip))
                print("  %s .. %s  SKIP %s" % (a, b, skip), flush=True)
                continue
            res = await persist_bars(conn, bars, provenance=PROV_YFINANCE)
            if res.get("skipped"):
                missing.append(("%s..%s" % (a, b), res["skip_reason"]))
                print("  %s .. %s  SKIP %s" % (a, b, res["skip_reason"]), flush=True)
                continue
            total += res["written"]
            all_bars.extend(bars)
            live = res.get("liveness") or {}
            served.extend(live.get("sessions") or [])
            print("  %s .. %s  %4d bars  sessions %s  all known length=%s"
                  % (a, b, res["written"], len(live.get("sessions") or []),
                     live.get("known_length")), flush=True)

        out: Dict[str, Any] = {"written": total, "sessions": sorted(set(served)),
                               "missing": missing}
        if capture:
            out["capture"] = compare_to_capture(all_bars, capture)
        return out
    finally:
        await conn.close()


async def _main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dsn", required=True)
    p.add_argument("--from", dest="start", default=DEFAULT_START.isoformat())
    p.add_argument("--to", dest="end")
    p.add_argument("--capture")
    p.add_argument("--capture-sha256", default="")
    a = p.parse_args()

    start = date.fromisoformat(a.start)
    end = date.fromisoformat(a.end) if a.end else (
        datetime.now(timezone.utc).date() + timedelta(days=1))

    capture = None
    if a.capture:
        capture, err = load_capture(a.capture, a.capture_sha256)
        if err:
            print("CAPTURE: %s" % err)
            print("Refusing to continue with a capture that cannot be verified.")
            return 2
        print("CAPTURE: %d instants, sha256 %s" % (capture["count"], capture["sha256"][:16]))
    else:
        print("CAPTURE: none supplied -- the vendor is the only source this run, and any session "
              "it does not serve will be reported as MISSING rather than filled.")

    print("\nbackfilling 1m SPY %s .. %s (end exclusive), %d chunk(s)"
          % (start, end, len(chunks(start, end))))
    res = await run(a.dsn, start, end, capture)
    print("\n--- result ---")
    print("  bars written : %d" % res["written"])
    print("  sessions     : %d  %s" % (len(res["sessions"]), res["sessions"]))
    print("  MISSING      : %d  %s" % (len(res["missing"]), res["missing"][:6]))
    if res.get("capture"):
        c = res["capture"]
        print("  capture cross-check: %d instants compared, %d agreed, rate %s"
              % (c["checked"], c["agreed"], c["rate"]))
        if c["disagreements"]:
            print("  DISAGREEMENTS (first few): %s" % c["disagreements"][:3])
    return 0 if not res["missing"] else 1


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    logging.basicConfig(level=logging.WARNING)
    raise SystemExit(asyncio.run(_main()))
