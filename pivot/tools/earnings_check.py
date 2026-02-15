"""
Check upcoming earnings dates and catalyst risk for a ticker.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from typing import Optional

import yfinance as yf

from tools.helpers import _now_iso, _error_response
from tools import YF_LOCK

logger = logging.getLogger(__name__)


async def check_earnings(ticker: str) -> dict:
    """
    Check next earnings date, days until, and catalyst risk warning.

    Returns None for next_earnings_date if the ticker is an ETF or has no earnings.
    """
    try:
        return await asyncio.to_thread(_check_earnings_sync, ticker)
    except Exception as exc:
        logger.error(f"check_earnings({ticker}) failed: {exc}", exc_info=True)
        return _error_response(ticker, str(exc))


def _check_earnings_sync(ticker: str) -> dict:
    """Synchronous implementation of earnings check."""
    try:
        t = yf.Ticker(ticker)

        next_date: Optional[date] = None
        timing: str = "unknown"
        estimate_eps: Optional[float] = None

        # Try .calendar first
        try:
            cal = t.calendar
            if cal is not None and not (hasattr(cal, "empty") and cal.empty):
                # calendar can be a dict or DataFrame depending on yfinance version
                if isinstance(cal, dict):
                    earnings_raw = cal.get("Earnings Date")
                    if earnings_raw:
                        if isinstance(earnings_raw, list) and len(earnings_raw) > 0:
                            ed = earnings_raw[0]
                        else:
                            ed = earnings_raw
                        if ed is not None:
                            next_date = _parse_date(ed)
                    # Estimate EPS
                    eps_est = cal.get("EPS Estimate")
                    if eps_est is not None:
                        try:
                            estimate_eps = float(eps_est)
                        except (TypeError, ValueError):
                            pass
                else:
                    # DataFrame form
                    try:
                        if hasattr(cal, "loc"):
                            if "Earnings Date" in cal.index:
                                ed_vals = cal.loc["Earnings Date"]
                                ed = ed_vals.iloc[0] if hasattr(ed_vals, "iloc") else ed_vals
                                next_date = _parse_date(ed)
                            if "EPS Estimate" in cal.index:
                                eps_val = cal.loc["EPS Estimate"].iloc[0]
                                try:
                                    estimate_eps = float(eps_val)
                                except (TypeError, ValueError):
                                    pass
                    except Exception:
                        pass
        except Exception as exc:
            logger.debug(f"calendar fetch failed for {ticker}: {exc}")

        # Fall back to earnings_dates if no date found
        if next_date is None:
            try:
                ed_df = t.earnings_dates
                if ed_df is not None and not ed_df.empty:
                    today = date.today()
                    # earnings_dates index is datetime — filter for future dates
                    future = ed_df[ed_df.index.date >= today] if hasattr(ed_df.index, "date") else ed_df
                    if not future.empty:
                        nearest_idx = future.index[0]
                        next_date = nearest_idx.date() if hasattr(nearest_idx, "date") else _parse_date(nearest_idx)
                        # Try to get EPS estimate
                        if "EPS Estimate" in future.columns and estimate_eps is None:
                            try:
                                estimate_eps = float(future["EPS Estimate"].iloc[0])
                            except (TypeError, ValueError):
                                pass
            except Exception as exc:
                logger.debug(f"earnings_dates fetch failed for {ticker}: {exc}")

        # If still no date, assume ETF/no earnings
        if next_date is None:
            return {
                "status": "ok",
                "ticker": ticker.upper(),
                "next_earnings_date": None,
                "note": "ETF or no earnings date available",
                "timestamp": _now_iso(),
            }

        today = date.today()
        days_until = (next_date - today).days

        # Determine timing (BMO/AMC) — yfinance sometimes embeds this
        # Best effort: check info for earningsTimingType
        try:
            info = t.info
            timing_raw = info.get("earningsTimingType", "")
            if timing_raw:
                if "before" in timing_raw.lower() or "bmo" in timing_raw.lower():
                    timing = "BMO"
                elif "after" in timing_raw.lower() or "amc" in timing_raw.lower():
                    timing = "AMC"
        except Exception:
            pass

        # Warning logic
        warning: Optional[str] = None
        if days_until <= 7:
            warning = f"⚠️ Earnings in {days_until} days — elevated IV and catalyst risk"
        elif days_until <= 14:
            warning = f"📅 Earnings in {days_until} days — factor into DTE and IV decisions"

        is_within_dte = days_until <= 21

        return {
            "status": "ok",
            "ticker": ticker.upper(),
            "next_earnings_date": str(next_date),
            "days_until": days_until,
            "timing": timing,
            "estimate_eps": estimate_eps,
            "is_within_dte": is_within_dte,
            "warning": warning,
            "timestamp": _now_iso(),
        }
    except Exception as exc:
        logger.error(f"_check_earnings_sync({ticker}) error: {exc}", exc_info=True)
        return _error_response(ticker, str(exc))


def _parse_date(value) -> Optional[date]:
    """Parse various date formats to a date object."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if hasattr(value, "date"):
        return value.date()
    try:
        s = str(value).strip()
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(s[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
    except Exception:
        pass
    return None
