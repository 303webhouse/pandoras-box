"""
Parquet cache helpers — read/merge/write per AEGIS §9.2 spec.

Cache paths:
  Monthly-partitioned (flow_alerts, darkpool, net_prem_ticks, spot_exposures):
    {base_dir}/{data_type}/{ticker}/{YYYYMM}.parquet

  Rolling overwrite (greek_exposure_daily):
    {base_dir}/greek_exposure_daily/{ticker}/{ticker}_rolling.parquet
"""

import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

CACHE_BASE = "/opt/openclaw/workspace/data/cache/uw"

# Data types using monthly-partitioned cache
MONTHLY_PARTITIONED = {"flow_alerts", "darkpool", "net_prem_ticks", "spot_exposures"}

# Data type using rolling overwrite
ROLLING = {"greek_exposure_daily"}


def _monthly_path(data_type: str, ticker: str, yyyymm: str) -> str:
    return os.path.join(CACHE_BASE, data_type, ticker, f"{yyyymm}.parquet")


def _rolling_path(ticker: str) -> str:
    return os.path.join(CACHE_BASE, "greek_exposure_daily", ticker, f"{ticker}_rolling.parquet")


def merge_and_write(
    data_type: str,
    ticker: str,
    new_df: pd.DataFrame,
    dry_run: bool = False,
) -> int:
    """
    Merge new_df into the appropriate cache file and write atomically.
    Returns the total row count after merge (or just len(new_df) if rolling).

    For monthly-partitioned: deduplicates on all columns before writing.
    For rolling (greek_exposure_daily): overwrites the rolling file entirely.

    dry_run=True: compute + log what would happen, but skip the actual write.
    """
    if new_df.empty:
        logger.debug("cache.merge_and_write %s %s: new_df empty, skipping", data_type, ticker)
        return 0

    now = datetime.now(timezone.utc)

    if data_type in ROLLING or data_type == "greek_exposure_daily":
        path = _rolling_path(ticker)
        total_rows = len(new_df)
        if dry_run:
            logger.info("[DRY-RUN] Would overwrite %s (%d rows)", path, total_rows)
            return total_rows
        _write_atomic(path, new_df)
        logger.info("cache: wrote rolling %s %s (%d rows) → %s", data_type, ticker, total_rows, path)
        return total_rows

    # Monthly-partitioned
    yyyymm = now.strftime("%Y%m")
    path = _monthly_path(data_type, ticker, yyyymm)

    if os.path.exists(path):
        try:
            existing = pd.read_parquet(path)
            combined = pd.concat([existing, new_df], ignore_index=True)
            combined = combined.drop_duplicates()
        except Exception as e:
            logger.warning("cache: failed to read existing %s — overwriting: %s", path, e)
            combined = new_df
    else:
        combined = new_df

    total_rows = len(combined)
    if dry_run:
        logger.info("[DRY-RUN] Would write %s (%d rows)", path, total_rows)
        return total_rows

    _write_atomic(path, combined)
    logger.info("cache: wrote %s %s (%d rows) → %s", data_type, ticker, total_rows, path)
    return total_rows


def get_prev_day_row_count(data_type: str, ticker: str) -> int | None:
    """
    Return the row count from the most recent cache write for empty-data detection.
    Returns None if no prior cache exists.
    """
    now = datetime.now(timezone.utc)
    yyyymm = now.strftime("%Y%m")
    path = _monthly_path(data_type, ticker, yyyymm)
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_parquet(path)
        return len(df)
    except Exception:
        return None


def _write_atomic(path: str, df: pd.DataFrame) -> None:
    """Write DataFrame to parquet atomically via temp file + rename."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(Path(path).parent), suffix=".parquet.tmp"
    )
    try:
        os.close(tmp_fd)
        df.to_parquet(tmp_path, index=False, engine="pyarrow")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise
