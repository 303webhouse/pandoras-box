"""Batched yfinance daily OHLCV downloader for the Stable Engine.

Adapted from Stable Market Board by Ryan Scott (shared within The Stable, 2026).
Data layer swapped Polygon->yfinance (sanctioned fallback: EOD/context data, not
execution-path data). Zero UW calls.

Coverage contract (house rule): every batch logs fetched/missing counts; callers
mark a run degraded when coverage < 90% and log which tickers failed. We NEVER fill
gaps with fabricated or stale-as-fresh values — a missing ticker is simply absent.
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta

import pandas as pd

from . import config, db

logger = logging.getLogger(__name__)

# Prices use auto-adjusted OHLC (splits + dividends) so MAs/returns/ATR have no
# artificial gaps — standard for technical metrics.
_AUTO_ADJUST = True


_SHARE_CLASS = __import__("re").compile(r"^([A-Z]+)\.([A-Z])$")


def to_yahoo_symbol(ticker: str) -> str:
    """R-IV.426(d) — the ONE mapping from a universe symbol to Yahoo's.

    US share classes are written with a dot in the universe (BRK.B, BF.B) and with a hyphen
    by Yahoo (BRK-B, BF-B); requested as-is they fail as "possibly delisted". Only a
    letters-dot-single-letter symbol is rewritten, so exchange suffixes (7203.T, SHOP.TO)
    and pairs already in Yahoo form (BTC-USD) pass through unchanged. Rows are stored under
    the UNIVERSE symbol; the Yahoo form never leaves this module.
    """
    m = _SHARE_CLASS.match(ticker or "")
    return "%s-%s" % (m.group(1), m.group(2)) if m else ticker


def _extract_ticker_frame(data: pd.DataFrame, ticker: str, single: bool) -> pd.DataFrame | None:
    """Pull a single ticker's OHLCV frame out of a yfinance download result."""
    try:
        if single:
            sub = data
        elif isinstance(data.columns, pd.MultiIndex):
            if ticker not in data.columns.get_level_values(0):
                return None
            sub = data[ticker]
        else:
            sub = data
    except Exception:
        return None

    if sub is None or sub.empty:
        return None
    sub = sub.dropna(how="all")
    if sub.empty or "Close" not in sub.columns:
        return None

    out = pd.DataFrame({
        "date": pd.to_datetime(sub.index).date,
        "o": sub["Open"].astype(float) if "Open" in sub else None,
        "h": sub["High"].astype(float) if "High" in sub else None,
        "l": sub["Low"].astype(float) if "Low" in sub else None,
        "c": sub["Close"].astype(float),
        "v": sub["Volume"].fillna(0).astype("int64") if "Volume" in sub else 0,
    })
    out = out.dropna(subset=["c"])
    return out if not out.empty else None


# R-IV.599(d): A PARTIAL ANSWER IS NOT AN ANSWER.
#
# 2026-09-29 landed in `stable_daily_bars` for 2 of 679 tickers. 2026-09-22 did the same for 135
# and later healed. FANUY survived both times, which is the tell: the vendor returned a frame
# containing a couple of symbols, and `fetch_batch` handed that back as the batch's result.
#
# TWO FAULTS, and the retry was only the second of them.
#
#   1. `return out` sat INSIDE the `try`. A call that succeeded but returned an empty or
#      near-empty frame raised nothing, so it returned on attempt 1 and THE RETRY NEVER RAN. A
#      silent shortfall was indistinguishable from a genuine "these symbols have no bars".
#   2. A batch that did raise twice returned `{}`, abandoning all 100 tickers, with no attempt
#      to find out whether one bad symbol had taken the other 99 down with it.
#
# So: incompleteness is now a reason to retry, and after the retry the batch is SPLIT and the
# stragglers are asked for one at a time. yfinance is free and off the UW governor, but a serial
# fallback across a 679-ticker universe is slow, so it is capped -- a total vendor outage must
# not become 679 sequential requests.
#
# The caller already measured this and flagged the run degraded below 90% coverage. The miss was
# visible; nothing asked again. That is what changed.

# A batch yielding less than this fraction is treated as a failed attempt, not a thin answer.
_MIN_BATCH_YIELD = 0.5
# Most individual re-asks per batch, so an outage degrades rather than stalling the job.
_MAX_SINGLE_RETRIES = 40


def _download_batch(yahoo: dict[str, str], tickers: list[str],
                    start: date, end: date) -> dict[str, pd.DataFrame]:
    """One `yf.download` call, unwrapped into {universe symbol: frame}. May raise."""
    import yfinance as yf

    data = yf.download(
        list(yahoo.values()), start=start.isoformat(), end=end.isoformat(),
        auto_adjust=_AUTO_ADJUST, group_by="ticker",
        progress=False, threads=True, actions=False,
    )
    single = len(tickers) == 1
    out: dict[str, pd.DataFrame] = {}
    if data is not None and not data.empty:
        for t in tickers:
            frame = _extract_ticker_frame(data, yahoo[t], single)
            if frame is not None:
                out[t] = frame                      # stored under the UNIVERSE symbol
    return out


def fetch_batch(tickers: list[str], start: date, end: date) -> dict[str, pd.DataFrame]:
    """Download one batch. Retries a SHORTFALL as well as an exception, then splits.

    Returns {ticker: frame} for whatever answered. A ticker genuinely without bars is simply
    absent, which is what the caller counts as missing -- the point of the change is that it is
    absent because it was asked twice and once more alone, not because a frame arrived thin.
    """
    tickers = [t for t in tickers if t]
    if not tickers:
        return {}
    yahoo = {t: to_yahoo_symbol(t) for t in tickers}

    need = max(1, int(len(tickers) * _MIN_BATCH_YIELD))
    best: dict[str, pd.DataFrame] = {}
    last_err = None

    for attempt in (1, 2):
        try:
            out = _download_batch(yahoo, tickers, start, end)
        except Exception as e:                      # transient network/yfinance error
            last_err = e
            logger.warning("[stable_bars] batch attempt %d raised (%d tickers): %s",
                           attempt, len(tickers), e)
            if attempt == 1:
                time.sleep(1.5)
            continue

        if len(out) > len(best):
            best = out
        if len(out) >= need:
            return out
        # A SHORTFALL IS A FAILED ATTEMPT. This is the branch that did not exist: it used to
        # return here, on attempt 1, with 2 of 100 frames.
        logger.warning("[stable_bars] batch attempt %d yielded %d/%d frames — retrying",
                       attempt, len(out), len(tickers))
        if attempt == 1:
            time.sleep(1.5)

    if last_err is not None and not best:
        logger.error("[stable_bars] batch raised on both attempts: %s", last_err)

    # SPLIT. One unanswerable symbol must not take the rest of its batch with it.
    stragglers = [t for t in tickers if t not in best]
    if stragglers:
        capped = stragglers[:_MAX_SINGLE_RETRIES]
        logger.warning("[stable_bars] asking %d/%d stragglers individually",
                       len(capped), len(stragglers))
        for t in capped:
            try:
                one = _download_batch({t: yahoo[t]}, [t], start, end)
            except Exception as e:                  # noqa: BLE001
                logger.debug("[stable_bars] %s alone also failed: %s", t, e)
                continue
            if t in one:
                best[t] = one[t]
        if len(stragglers) > len(capped):
            logger.error("[stable_bars] %d straggler(s) left unasked (cap %d) — the run is "
                         "incomplete and the caller's coverage will say so",
                         len(stragglers) - len(capped), _MAX_SINGLE_RETRIES)

    return best


def incomplete_sessions(lookback_days: int = 10) -> list:
    """[(date, bars_held, required)] for recent sessions below the anchor threshold.

    The thresholds are scoring's, not this module's: one definition, so a session the
    writer calls complete is one the reader will anchor on, and vice versa
    (convention #9). `required` is a share of the largest session seen in the window,
    which tracks the universe without hardcoding its size.

    Read-only. Naming an incomplete session is this function's whole job; deciding
    what to do about it belongs to the caller and to the reader that would anchor.
    """
    from . import scoring

    try:
        df = db.read_df(
            "SELECT date, COUNT(*) AS n FROM stable_daily_bars "
            "WHERE date >= CURRENT_DATE - %s::int GROUP BY date ORDER BY date",
            (lookback_days,),
        )
    except Exception as exc:
        logger.warning("[stable_bars] completeness read failed: %s", type(exc).__name__)
        return []
    if df is None or df.empty:
        return []
    counts = {str(r["date"]): int(r["n"]) for _, r in df.iterrows()}
    if not counts:
        return []
    required = max(scoring.ANCHOR_MIN_TICKERS_FLOOR,
                   int(max(counts.values()) * scoring.ANCHOR_MIN_COVERAGE))
    return [(d, n, required) for d, n in sorted(counts.items()) if n < required]


def download_and_store(
    tickers: list[str],
    years: int | None = None,
    days: int | None = None,
    end: date | None = None,
    batch_size: int = 100,
    block_tickers: set[str] | None = None,
) -> dict:
    """Download daily bars for `tickers`, upsert to stable_daily_bars.

    Args:
        years: history length (backfill). Ignored if `days` is given.
        days: incremental window (nightly refresh) — start = end - days.
        block_tickers: simulate a partial outage — these tickers are skipped from the
            request entirely (degraded-run test), never fabricated.

    Returns a coverage summary. degraded=True when coverage < 90% of the request.
    """
    end = end or (date.today() + timedelta(days=1))  # yfinance end is exclusive
    if days is not None:
        start = end - timedelta(days=days)
    else:
        years = years or config.HISTORY_YEARS
        start = date(end.year - years, end.month, end.day)
    block_tickers = block_tickers or set()

    requested = [t for t in dict.fromkeys(tickers) if t and t not in block_tickers]  # dedupe, drop blocked
    skipped_blocked = [t for t in tickers if t in block_tickers]

    db.init_schema()

    fetched: list[str] = []
    missing: list[str] = []
    rows_written = 0

    for i in range(0, len(requested), batch_size):
        batch = requested[i:i + batch_size]
        result = fetch_batch(batch, start, end)
        batch_rows = []
        for t in batch:
            frame = result.get(t)
            if frame is None or frame.empty:
                missing.append(t)
                continue
            fetched.append(t)
            for r in frame.itertuples(index=False, name=None):
                # r = (date, o, h, l, c, v)
                d, o, h, l, c, v = r
                batch_rows.append((t, d,
                                   None if pd.isna(o) else float(o),
                                   None if pd.isna(h) else float(h),
                                   None if pd.isna(l) else float(l),
                                   None if pd.isna(c) else float(c),
                                   int(v) if not pd.isna(v) else 0))
        rows_written += db.upsert_bars(batch_rows)
        logger.info("[stable_bars] batch %d-%d: %d/%d fetched, %d rows",
                    i, i + len(batch), len(batch) - sum(1 for t in batch if t in missing),
                    len(batch), len(batch_rows))

    total_target = len(requested) + len(skipped_blocked)
    coverage_pct = round(100.0 * len(fetched) / total_target, 2) if total_target else 0.0
    # Blocked tickers count against coverage (they are genuinely absent this run).
    degraded = coverage_pct < 90.0 or bool(skipped_blocked)

    # R-IV.497(e) — PER-DATE COMPLETENESS, because per-ticker coverage cannot see this.
    #
    # The contract above is per TICKER: "did this symbol answer at all". A vendor can
    # answer for 679 symbols and still hold a session for only 135 of them, and that
    # run scores 100% coverage. Measured 2026-09-24: stable_daily_bars held 679 bars
    # for 09-18, 09-21 and 09-23 and **135** for 09-22, while this summary reported a
    # healthy run — the bars layer had no per-date notion at all.
    #
    # It matters because the anchor is a DATE. An incomplete session that becomes the
    # anchor feeds the regime, which is the committee's trend tier, off a fraction of
    # the universe. metrics and scoring already refuse such a date; the bars layer did
    # not name it, so nothing upstream could see it coming.
    #
    # Uses scoring's thresholds rather than its own, so the writer cannot report a date
    # healthy that the reader would refuse to anchor on (convention #9).
    incomplete_dates = incomplete_sessions()
    if incomplete_dates:
        degraded = True
        logger.warning(
            "[stable_bars] INCOMPLETE session(s) after this run: %s — each holds fewer "
            "bars than the universe expects and MUST NOT become the anchor",
            ", ".join("%s=%d/%d" % (d, n, exp) for d, n, exp in incomplete_dates))

    summary = {
        "incomplete_dates": [{"date": d, "bars": n, "expected_at_least": exp}
                             for d, n, exp in (incomplete_dates or [])],
        "requested": len(requested),
        "blocked": len(skipped_blocked),
        "target": total_target,
        "fetched": len(fetched),
        "missing": len(missing) + len(skipped_blocked),
        "rows_written": rows_written,
        "coverage_pct": coverage_pct,
        "degraded": degraded,
        "missing_tickers": sorted(missing),
        "blocked_tickers": sorted(skipped_blocked),
        "start": start.isoformat(),
        "end": end.isoformat(),
    }
    logger.info("[stable_bars] coverage %.1f%% (%d/%d) degraded=%s missing=%d blocked=%d",
                coverage_pct, len(fetched), total_target, degraded,
                len(missing), len(skipped_blocked))
    return summary
