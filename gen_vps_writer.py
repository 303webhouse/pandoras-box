import base64, os, sys

# All file contents inline
FILES = {
'/opt/openclaw/workspace/scripts/uw_forward_logger/fetchers/base.py': b"""\
\"\"\"
Shared base: auth header, retry logic, 429 backoff, response envelope unwrap.
\"\"\"
import logging
import time
from typing import Any
import requests
logger = logging.getLogger(__name__)
UW_BASE = "https://api.unusualwhales.com"
MAX_RETRIES_429 = 5
MAX_RETRIES_5XX = 3
BACKOFF_429_BASE_S = 2.0
BACKOFF_5XX_S = 5.0
BACKOFF_NET_S = 2.0
MAX_RETRIES_NET = 3

def build_headers(api_key):
    return {"Authorization": f"Bearer {api_key}"}

def _extract_rows(response_json):
    if isinstance(response_json, list):
        return response_json
    for key in ("data", "chains"):
        if key in response_json:
            return response_json[key]
    logger.warning("Unexpected response envelope -- keys: %s",
                   list(response_json.keys()) if isinstance(response_json, dict) else type(response_json))
    return []

def uw_get(path, api_key, params=None, timeout=30):
    url = UW_BASE + path
    headers = build_headers(api_key)
    attempt_429 = 0
    attempt_5xx = 0
    attempt_net = 0
    while True:
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as e:
            attempt_net += 1
            if attempt_net > MAX_RETRIES_NET:
                raise RuntimeError(f"Network error on {path} after {MAX_RETRIES_NET} retries: {e}") from e
            time.sleep(BACKOFF_NET_S * attempt_net)
            continue
        if resp.status_code == 200:
            try:
                return _extract_rows(resp.json())
            except Exception as e:
                raise RuntimeError(f"Failed to parse JSON from {path}: {e}") from e
        elif resp.status_code == 429:
            attempt_429 += 1
            if attempt_429 > MAX_RETRIES_429:
                raise RuntimeError(f"Rate-limited on {path} after {MAX_RETRIES_429} retries")
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else BACKOFF_429_BASE_S * (2 ** (attempt_429 - 1))
            logger.warning("429 on %s (attempt %d/%d) -- waiting %.1fs", path, attempt_429, MAX_RETRIES_429, wait)
            time.sleep(wait)
        elif resp.status_code in (500, 502, 503, 504):
            attempt_5xx += 1
            if attempt_5xx > MAX_RETRIES_5XX:
                raise RuntimeError(f"{resp.status_code} on {path} after {MAX_RETRIES_5XX} retries")
            time.sleep(BACKOFF_5XX_S)
        elif resp.status_code == 403:
            try:
                body = resp.json()
            except Exception:
                body = {}
            code_field = body.get("code", "") or body.get("error", "")
            if "historic_data_access_missing" in str(code_field):
                logger.warning("403 historic_data_access_missing on %s -- skipping", path)
                return []
            raise RuntimeError(f"403 Forbidden on {path}: {body}")
        elif resp.status_code == 401:
            raise RuntimeError(f"401 Unauthorized on {path} -- check UW_API_KEY")
        else:
            raise RuntimeError(f"Unexpected {resp.status_code} on {path}: {resp.text[:200]}")
""",

'/opt/openclaw/workspace/scripts/uw_forward_logger/fetchers/flow_alerts.py': b"""\
import logging
import pandas as pd
from .base import uw_get
logger = logging.getLogger(__name__)

def fetch(ticker, api_key):
    rows = uw_get(f"/api/stock/{ticker}/flow-alerts", api_key, params={"limit": 500})
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    logger.debug("flow_alerts %s: %d rows", ticker, len(df))
    return df
""",

'/opt/openclaw/workspace/scripts/uw_forward_logger/fetchers/darkpool.py': b"""\
import logging
import pandas as pd
from .base import uw_get
logger = logging.getLogger(__name__)
_PAGE_LIMIT = 500
_MAX_ROWS = 25000

def fetch(ticker, api_key, date=None):
    all_rows = []
    cursor = None
    page = 0
    while True:
        params = {"limit": _PAGE_LIMIT}
        if date:
            params["date"] = date
        if cursor:
            params["older_than"] = cursor
        rows = uw_get(f"/api/darkpool/{ticker}", api_key, params=params)
        if not rows:
            break
        all_rows.extend(rows)
        page += 1
        if len(rows) < _PAGE_LIMIT:
            break
        if len(all_rows) >= _MAX_ROWS:
            logger.warning("darkpool %s on %s exceeded %d rows -- truncating", ticker, date, _MAX_ROWS)
            break
        cursor = rows[-1].get("executed_at") or rows[-1].get("timestamp")
        if not cursor:
            logger.warning("darkpool %s: no cursor field -- stopping pagination", ticker)
            break
    if not all_rows:
        return pd.DataFrame()
    df = pd.DataFrame(all_rows)
    logger.debug("darkpool %s (date=%s): %d rows, %d pages", ticker, date, len(df), page)
    return df
""",

'/opt/openclaw/workspace/scripts/uw_forward_logger/fetchers/net_prem_ticks.py': b"""\
import logging
import pandas as pd
from .base import uw_get
logger = logging.getLogger(__name__)

def fetch(ticker, api_key):
    rows = uw_get(f"/api/stock/{ticker}/net-prem-ticks", api_key)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    logger.debug("net_prem_ticks %s: %d rows", ticker, len(df))
    return df
""",

'/opt/openclaw/workspace/scripts/uw_forward_logger/fetchers/spot_exposures.py': b"""\
import logging
import pandas as pd
from .base import uw_get
logger = logging.getLogger(__name__)

def fetch(ticker, api_key):
    rows = uw_get(f"/api/stock/{ticker}/spot-exposures", api_key)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    logger.debug("spot_exposures %s: %d rows", ticker, len(df))
    return df
""",

'/opt/openclaw/workspace/scripts/uw_forward_logger/fetchers/greek_exposure.py': b"""\
import logging
import os
from datetime import datetime, timezone
import pandas as pd
from .base import uw_get
logger = logging.getLogger(__name__)
_CANARY_THRESHOLD = 200
_CANARY_FLAG_DIR = "/opt/openclaw/workspace/data/cache/uw/.canary_flags"

class CarveOutCanaryTriggered(Exception):
    def __init__(self, ticker, row_count):
        self.ticker = ticker
        self.row_count = row_count
        super().__init__(f"CARVE_OUT_CANARY: {ticker} returned only {row_count} rows")

def fetch(ticker, api_key):
    rows = uw_get(f"/api/stock/{ticker}/greek-exposure", api_key)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    logger.debug("greek_exposure %s: %d rows", ticker, len(df))
    _run_canary(ticker, len(df))
    return df

def _run_canary(ticker, row_count):
    if row_count >= _CANARY_THRESHOLD:
        return
    flag_file = os.path.join(_CANARY_FLAG_DIR, f"canary_{ticker}.txt")
    os.makedirs(_CANARY_FLAG_DIR, exist_ok=True)
    today = datetime.now(timezone.utc)
    if os.path.exists(flag_file):
        try:
            with open(flag_file) as f:
                last_alerted = datetime.fromisoformat(f.read().strip())
            days_since = (today - last_alerted).days
            if days_since < 7:
                logger.warning("CARVE_OUT_CANARY: %s greek-exposure only %d rows (suppressed this week)", ticker, row_count)
                return
        except Exception:
            pass
    logger.warning("CARVE_OUT_CANARY: %s greek-exposure returned only %d rows. UW may have tightened the carve-out.", ticker, row_count)
    try:
        with open(flag_file, "w") as f:
            f.write(today.isoformat())
    except Exception as e:
        logger.debug("Failed to write canary flag for %s: %s", ticker, e)
    raise CarveOutCanaryTriggered(ticker, row_count)
""",

'/opt/openclaw/workspace/scripts/uw_forward_logger/cache.py': b"""\
\"\"\"Parquet cache helpers -- atomic read/merge/write.\"\"\"
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
logger = logging.getLogger(__name__)
CACHE_BASE = "/opt/openclaw/workspace/data/cache/uw"

def _monthly_path(data_type, ticker, yyyymm):
    return os.path.join(CACHE_BASE, data_type, ticker, f"{yyyymm}.parquet")

def _rolling_path(ticker):
    return os.path.join(CACHE_BASE, "greek_exposure_daily", ticker, f"{ticker}_rolling.parquet")

def merge_and_write(data_type, ticker, new_df, dry_run=False):
    if new_df.empty:
        return 0
    now = datetime.now(timezone.utc)
    if data_type == "greek_exposure_daily":
        path = _rolling_path(ticker)
        total_rows = len(new_df)
        if dry_run:
            logger.info("[DRY-RUN] Would overwrite %s (%d rows)", path, total_rows)
            return total_rows
        _write_atomic(path, new_df)
        logger.info("cache: wrote rolling %s (%d rows) -> %s", ticker, total_rows, path)
        return total_rows
    yyyymm = now.strftime("%Y%m")
    path = _monthly_path(data_type, ticker, yyyymm)
    if os.path.exists(path):
        try:
            existing = pd.read_parquet(path)
            combined = pd.concat([existing, new_df], ignore_index=True).drop_duplicates()
        except Exception as e:
            logger.warning("cache: failed to read existing %s -- overwriting: %s", path, e)
            combined = new_df
    else:
        combined = new_df
    total_rows = len(combined)
    if dry_run:
        logger.info("[DRY-RUN] Would write %s (%d rows)", path, total_rows)
        return total_rows
    _write_atomic(path, combined)
    logger.info("cache: wrote %s %s (%d rows) -> %s", data_type, ticker, total_rows, path)
    return total_rows

def _write_atomic(path, df):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(Path(path).parent), suffix=".parquet.tmp")
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
""",

'/opt/openclaw/workspace/scripts/uw_forward_logger/alerts.py': b"""\
\"\"\"Alert dispatch -- Discord webhook, matches committee_heartbeat.py pattern.\"\"\"
import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
logger = logging.getLogger(__name__)
_WEBHOOK_URL = (os.environ.get("DISCORD_WEBHOOK_SIGNALS") or
                os.environ.get("DISCORD_WEBHOOK_BRIEFS") or "")
_NICK_USER_ID = os.environ.get("NICK_DISCORD_USER_ID", "")

def _send(title, description, color=0xE05A5A):
    if not _WEBHOOK_URL:
        logger.warning("DISCORD_WEBHOOK_SIGNALS not set -- alert not sent: %s", title)
        return
    mention = f"<@{_NICK_USER_ID}> " if _NICK_USER_ID else ""
    payload = json.dumps({
        "content": mention,
        "embeds": [{"title": f"UW Forward-Logger: {title}", "description": description,
                    "color": color,
                    "footer": {"text": f"uw_forward_logger - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"}}]
    }).encode()
    req = urllib.request.Request(_WEBHOOK_URL, data=payload,
                                  headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status not in (200, 204):
                logger.warning("Discord webhook returned %d", resp.status)
    except Exception as e:
        logger.warning("Failed to send Discord alert: %s", e)

def alert_consecutive_empty(ticker, data_type, days=2):
    _send(f"Data Gap -- {ticker} {data_type}",
          f"**{ticker}** `{data_type}` empty for **{days}+ consecutive days**. Check UW plan status.")

def alert_rate_limit_failure(ticker, data_type, detail):
    _send(f"Rate-Limit Failure -- {ticker} {data_type}",
          f"**{ticker}** `{data_type}` failed after max 429 retries.\\nDetail: `{detail}`")

def alert_auth_error(ticker, path, detail):
    _send("Auth Error -- UW API",
          f"**{ticker}** endpoint `{path}` returned 401/403.\\nDetail: `{detail}`", color=0xFF0000)

def alert_slow_run(elapsed_minutes):
    _send("Slow Run Warning",
          f"Logger took **{elapsed_minutes:.1f} minutes** -- threshold 30 min.", color=0xF0A500)

def alert_carve_out_canary(ticker, row_count):
    _send(f"GEX Carve-Out Canary -- {ticker}",
          f"**{ticker}** `greek-exposure` returned only **{row_count} rows** (threshold 200). "
          f"UW may have tightened the 1yr carve-out. Review with ATHENA.", color=0xF0A500)

def alert_logger_online():
    _send("Logger Online",
          "UW forward-logger first production run complete. Shadow data accumulation begun.",
          color=0x4ECDC4)

def check_consecutive_empty(ticker, data_type, today_empty, empty_tracker):
    key = (ticker, data_type)
    if today_empty:
        empty_tracker[key] = empty_tracker.get(key, 0) + 1
        if empty_tracker[key] >= 2:
            alert_consecutive_empty(ticker, data_type, empty_tracker[key])
    else:
        empty_tracker[key] = 0
""",

'/opt/openclaw/workspace/scripts/uw_forward_logger/config.py': b"""\
\"\"\"Config loader -- watchlist YAML + rate-limit throttle.\"\"\"
import os
from pathlib import Path
import yaml

THROTTLE_SLEEP_BETWEEN_CALLS_S = 1.0
THROTTLE_MAX_BURST = 10
THROTTLE_BURST_PAUSE_S = 15.0

_WORKSPACE = Path(__file__).resolve().parents[2]
_CONFIG_DIR = _WORKSPACE / "config"
_WATCHLIST_PATH = _CONFIG_DIR / "uw_logger_watchlist.yaml"
_WATCHLIST_OVERRIDE = os.environ.get("UW_LOGGER_WATCHLIST_PATH")

def load_watchlist():
    path = Path(_WATCHLIST_OVERRIDE) if _WATCHLIST_OVERRIDE else _WATCHLIST_PATH
    if not path.exists():
        raise FileNotFoundError(f"Watchlist not found at {path}")
    with open(path) as f:
        data = yaml.safe_load(f)
    tickers = data.get("tickers", [])
    if not tickers:
        raise ValueError(f"No tickers found in watchlist at {path}")
    return [str(t).upper() for t in tickers]

def get_api_key():
    key = os.environ.get("UW_API_KEY", "")
    if not key:
        raise EnvironmentError("UW_API_KEY not set. Source /etc/openclaw/openclaw.env first.")
    return key
""",

'/opt/openclaw/workspace/scripts/uw_forward_logger/logger.py': b"""\
\"\"\"UW Forward-Logger -- main entry point. Daily cron at 21:00 UTC Mon-Fri.\"\"\"
import argparse
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_WORKSPACE = Path(__file__).resolve().parents[2]
if str(_WORKSPACE) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE))

import pandas as pd

from scripts.uw_forward_logger import alerts, cache, config
from scripts.uw_forward_logger.fetchers import (
    darkpool, flow_alerts, greek_exposure,
    net_prem_ticks, spot_exposures,
)
from scripts.uw_forward_logger.fetchers.greek_exposure import CarveOutCanaryTriggered

logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO, stream=sys.stdout,
)
logger = logging.getLogger("uw_forward_logger")

_NYSE_HOLIDAYS_2026 = {
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16),
    date(2026, 4, 3), date(2026, 5, 25), date(2026, 7, 3),
    date(2026, 9, 7), date(2026, 11, 26), date(2026, 11, 27),
    date(2026, 12, 25),
}

def _market_was_open(run_date):
    if run_date.weekday() >= 5:
        return False
    if run_date in _NYSE_HOLIDAYS_2026:
        return False
    return True

def _yesterday():
    return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

def run(tickers, api_key, dry_run=False, first_run=False):
    today = datetime.now(timezone.utc).date()
    if not _market_was_open(today):
        logger.info("Market closed today (%s) -- skipping.", today)
        return
    yesterday = _yesterday()
    logger.info("Starting UW forward-logger -- %s -- %d tickers -- dry_run=%s", today, len(tickers), dry_run)
    t_start = time.time()
    empty_tracker = {}
    call_count = 0
    errors = []

    for ticker in tickers:
        logger.info("-- %s --", ticker)
        tasks = [
            ("flow_alerts",          lambda t=ticker: flow_alerts.fetch(t, api_key)),
            ("darkpool",             lambda t=ticker: darkpool.fetch(t, api_key, date=yesterday)),
            ("net_prem_ticks",       lambda t=ticker: net_prem_ticks.fetch(t, api_key)),
            ("spot_exposures",       lambda t=ticker: spot_exposures.fetch(t, api_key)),
            ("greek_exposure_daily", lambda t=ticker: greek_exposure.fetch(t, api_key)),
        ]

        for data_type, fetcher_fn in tasks:
            try:
                df = fetcher_fn()
                call_count += 1
                row_count = len(df) if df is not None else 0
                is_empty = row_count == 0
                logger.info("  %s.%s: %d rows%s", ticker, data_type, row_count, " [EMPTY]" if is_empty else "")
                alerts.check_consecutive_empty(ticker, data_type, is_empty, empty_tracker)
                if not is_empty:
                    cache.merge_and_write(data_type, ticker, df, dry_run=dry_run)
            except CarveOutCanaryTriggered as canary:
                alerts.alert_carve_out_canary(canary.ticker, canary.row_count)
                errors.append(f"{ticker}.{data_type}: carve-out canary ({canary.row_count} rows)")
            except RuntimeError as e:
                err_str = str(e)
                errors.append(f"{ticker}.{data_type}: {err_str}")
                if "429" in err_str or "Rate-limited" in err_str:
                    alerts.alert_rate_limit_failure(ticker, data_type, err_str)
                elif "401" in err_str or "403" in err_str:
                    alerts.alert_auth_error(ticker, f"/{data_type}/", err_str)
                else:
                    logger.error("  %s.%s FAILED: %s", ticker, data_type, e)
            if call_count > 0 and call_count % config.THROTTLE_MAX_BURST == 0:
                logger.debug("Burst pause (%.1fs)...", config.THROTTLE_BURST_PAUSE_S)
                time.sleep(config.THROTTLE_BURST_PAUSE_S)
            else:
                time.sleep(config.THROTTLE_SLEEP_BETWEEN_CALLS_S)

    elapsed_s = time.time() - t_start
    elapsed_min = elapsed_s / 60
    logger.info("Run complete -- %.1f min, %d API calls, %d errors", elapsed_min, call_count, len(errors))
    if errors:
        logger.warning("Errors:\\n  " + "\\n  ".join(errors))
    if elapsed_min > 30:
        alerts.alert_slow_run(elapsed_min)
    if first_run and not errors:
        alerts.alert_logger_online()

def main():
    parser = argparse.ArgumentParser(description="UW Forward-Logger")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ticker", help="Single ticker (testing)")
    parser.add_argument("--first-run", action="store_true")
    args = parser.parse_args()
    try:
        api_key = config.get_api_key()
    except EnvironmentError as e:
        logger.error(str(e))
        sys.exit(1)
    try:
        all_tickers = config.load_watchlist()
    except (FileNotFoundError, ValueError) as e:
        logger.error("Watchlist load failed: %s", e)
        sys.exit(1)
    tickers = [args.ticker.upper()] if args.ticker else all_tickers
    run(tickers, api_key, dry_run=args.dry_run, first_run=args.first_run)

if __name__ == "__main__":
    main()
""",

'/opt/openclaw/workspace/config/uw_logger_watchlist.yaml': b"""\
# UW forward-logger watchlist. Start small, expand once proven.
# Phase 0.5 launch set (10 tickers):
tickers:
  - SPY
  - QQQ
  - IWM
  - DIA
  - XLK
  - XLF
  - NVDA
  - TSLA
  - AAPL
  - AMZN
""",
}

lines = ['import os, base64']
for dest, content in FILES.items():
    b64 = base64.b64encode(content).decode()
    lines.append('os.makedirs(os.path.dirname(' + repr(dest) + '), exist_ok=True)')
    lines.append('open(' + repr(dest) + ', "wb").write(base64.b64decode(' + repr(b64) + '))')
    lines.append('print("wrote ' + dest + '")')

script = '\n'.join(lines)

# Write this as the VPS writer script
outpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vps_writer.py')
with open(outpath, 'w') as f:
    f.write(script)
print(f'VPS writer written to {outpath}: {len(script)} bytes, {len(lines)} lines')

# Also write b64 of the whole writer script so we can transfer it
full_b64 = base64.b64encode(script.encode()).decode()
chunks = [full_b64[i:i+700] for i in range(0, len(full_b64), 700)]
print(f'Writer b64 transfer: {len(full_b64)} chars -> {len(chunks)} SSH chunks needed')
