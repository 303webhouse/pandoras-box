"""
Local-first archive job for price_history.

Use this on your PC to move older rows out of Railway Postgres into cheap
local storage (compressed CSV files), then optionally purge those rows from DB.

Examples:
  # Export rows older than 2 days (no deletion)
  python -m backend.jobs.archive_price_history --older-than-days 2

  # Export + purge rows older than 2 days
  python -m backend.jobs.archive_price_history --older-than-days 2 --purge
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

try:
    from database.postgres_client import close_postgres_client, get_postgres_client
except ImportError:
    from backend.database.postgres_client import close_postgres_client, get_postgres_client

logger = logging.getLogger(__name__)
UTC = timezone.utc


def _parse_int_env(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Invalid integer env var %s=%r; using default=%d", name, raw, default)
        return default
    return max(value, minimum)


DEFAULT_ARCHIVE_DIR = os.getenv("PRICE_HISTORY_ARCHIVE_DIR", "data/archives/price_history")
DEFAULT_OLDER_THAN_DAYS = _parse_int_env("PRICE_HISTORY_ARCHIVE_OLDER_THAN_DAYS", 2)
DEFAULT_BATCH_SIZE = _parse_int_env("PRICE_HISTORY_ARCHIVE_BATCH_SIZE", 25000)


def _parse_cutoff(raw: Optional[str], older_than_days: int) -> datetime:
    if raw:
        text = raw.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        cutoff = datetime.fromisoformat(text)
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=UTC)
        return cutoff.astimezone(UTC)
    return datetime.now(UTC) - timedelta(days=older_than_days)


def _to_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        ts = value if value.tzinfo else value.replace(tzinfo=UTC)
        return ts.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return str(value)


def _write_batch_csv(
    rows: Sequence[Any],
    out_path: Path,
) -> None:
    headers = [
        "id",
        "ticker",
        "timeframe",
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]
    tmp_path = Path(str(out_path) + ".tmp")
    with gzip.open(tmp_path, mode="wt", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(
                [
                    row["id"],
                    row["ticker"],
                    row["timeframe"],
                    _to_iso(row["timestamp"]) or "",
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row["volume"],
                ]
            )
    tmp_path.replace(out_path)


def _timeframe_list(raw: Optional[str]) -> Optional[List[str]]:
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",")]
    cleaned = [p for p in parts if p]
    return cleaned or None


async def run_archive(
    archive_dir: Path,
    cutoff: datetime,
    batch_size: int,
    purge: bool,
    timeframes: Optional[List[str]],
    max_batches: Optional[int],
    max_rows: Optional[int],
    dry_run: bool,
) -> Dict[str, Any]:
    pool = await get_postgres_client()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = archive_dir / f"run_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    summary: Dict[str, Any] = {
        "run_id": run_id,
        "started_at": _to_iso(datetime.now(UTC)),
        "cutoff_utc": _to_iso(cutoff),
        "archive_dir": str(run_dir.resolve()),
        "batch_size": batch_size,
        "purge": purge,
        "dry_run": dry_run,
        "timeframes": timeframes or "all",
        "candidate_rows": 0,
        "rows_exported": 0,
        "rows_deleted": 0,
        "batches": [],
    }

    count_sql = """
        SELECT COUNT(*)
        FROM price_history
        WHERE timestamp < $1
          AND ($2::text[] IS NULL OR timeframe = ANY($2))
    """
    select_sql = """
        SELECT id, ticker, timeframe, timestamp, open, high, low, close, volume
        FROM price_history
        WHERE timestamp < $1
          AND id > $2
          AND ($3::text[] IS NULL OR timeframe = ANY($3))
        ORDER BY id ASC
        LIMIT $4
    """
    delete_sql = """
        WITH purged AS (
            DELETE FROM price_history
            WHERE id = ANY($1::int[])
            RETURNING 1
        )
        SELECT COUNT(*) FROM purged
    """

    async with pool.acquire() as conn:
        summary["candidate_rows"] = int(await conn.fetchval(count_sql, cutoff, timeframes) or 0)

    if dry_run or summary["candidate_rows"] == 0:
        summary["finished_at"] = _to_iso(datetime.now(UTC))
        manifest_path = run_dir / "manifest.json"
        manifest_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        summary["manifest_path"] = str(manifest_path.resolve())
        return summary

    cursor_id = 0
    batch_index = 0
    while True:
        if max_batches and batch_index >= max_batches:
            break
        if max_rows and summary["rows_exported"] >= max_rows:
            break

        async with pool.acquire() as conn:
            rows = await conn.fetch(select_sql, cutoff, cursor_id, timeframes, batch_size)

        if not rows:
            break

        batch_index += 1
        ids = [int(r["id"]) for r in rows]
        cursor_id = ids[-1]

        file_name = f"batch_{batch_index:05d}_id_{ids[0]}_{ids[-1]}.csv.gz"
        out_path = run_dir / file_name
        _write_batch_csv(rows, out_path)
        exported = len(rows)
        deleted = 0

        if purge:
            async with pool.acquire() as conn:
                deleted = int(await conn.fetchval(delete_sql, ids) or 0)
            if deleted != exported:
                logger.warning(
                    "Batch %d exported %d rows but deleted %d rows.",
                    batch_index,
                    exported,
                    deleted,
                )

        summary["rows_exported"] += exported
        summary["rows_deleted"] += deleted
        summary["batches"].append(
            {
                "batch": batch_index,
                "file": file_name,
                "rows_exported": exported,
                "rows_deleted": deleted,
                "first_id": ids[0],
                "last_id": ids[-1],
                "oldest_timestamp": _to_iso(rows[0]["timestamp"]),
                "newest_timestamp": _to_iso(rows[-1]["timestamp"]),
            }
        )

        logger.info(
            "Archived batch %d: exported=%d deleted=%d file=%s",
            batch_index,
            exported,
            deleted,
            out_path,
        )

    summary["finished_at"] = _to_iso(datetime.now(UTC))
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    summary["manifest_path"] = str(manifest_path.resolve())
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Archive old price_history rows to local compressed files.")
    parser.add_argument("--archive-dir", default=DEFAULT_ARCHIVE_DIR, help="Output folder for archive files.")
    parser.add_argument(
        "--older-than-days",
        type=int,
        default=DEFAULT_OLDER_THAN_DAYS,
        help="Archive rows older than this many days (ignored when --cutoff is set).",
    )
    parser.add_argument(
        "--cutoff",
        default=None,
        help="Explicit UTC cutoff timestamp, e.g. 2026-02-01T00:00:00Z.",
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Rows per batch file.")
    parser.add_argument(
        "--timeframes",
        default=None,
        help="Comma-separated timeframe filter, e.g. '5m,D'. Defaults to all.",
    )
    parser.add_argument("--purge", action="store_true", help="Delete archived rows from Postgres after export.")
    parser.add_argument("--dry-run", action="store_true", help="Only count candidates and write manifest.")
    parser.add_argument("--max-batches", type=int, default=None, help="Stop after N batches.")
    parser.add_argument("--max-rows", type=int, default=None, help="Stop after exporting N rows.")
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = _build_parser().parse_args()

    cutoff = _parse_cutoff(args.cutoff, args.older_than_days)
    archive_dir = Path(args.archive_dir)
    timeframes = _timeframe_list(args.timeframes)

    if args.batch_size <= 0:
        raise SystemExit("--batch-size must be > 0")
    if args.older_than_days <= 0 and not args.cutoff:
        raise SystemExit("--older-than-days must be > 0 when --cutoff is not set")
    if args.max_batches is not None and args.max_batches <= 0:
        raise SystemExit("--max-batches must be > 0")
    if args.max_rows is not None and args.max_rows <= 0:
        raise SystemExit("--max-rows must be > 0")

    async def _runner() -> Dict[str, Any]:
        try:
            return await run_archive(
                archive_dir=archive_dir,
                cutoff=cutoff,
                batch_size=args.batch_size,
                purge=args.purge,
                timeframes=timeframes,
                max_batches=args.max_batches,
                max_rows=args.max_rows,
                dry_run=args.dry_run,
            )
        finally:
            await close_postgres_client()

    result = asyncio.run(_runner())
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

