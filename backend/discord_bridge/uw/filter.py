"""
Filter UW flow alerts to keep only swing-relevant institutional activity.
"""
from __future__ import annotations

import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# --- Configuration ---
MIN_DTE = int(os.getenv("UW_MIN_DTE", "7"))
MAX_DTE = int(os.getenv("UW_MAX_DTE", "180"))
MIN_PREMIUM = float(os.getenv("UW_MIN_PREMIUM", "50000"))

DISCOVERY_BLACKLIST = {
    t.strip().upper()
    for t in os.getenv(
        "UW_DISCOVERY_BLACKLIST",
        "SPY,QQQ,IWM,NVDA,TSLA,AAPL,AMZN,META,MSFT,GOOG,AMD",
    ).split(",")
    if t.strip()
}

NOVELTY_DECAY_THRESHOLD = int(os.getenv("UW_NOVELTY_THRESHOLD", "5"))
NOVELTY_WINDOW_MINUTES = int(os.getenv("UW_NOVELTY_WINDOW", "60"))


class FlowFilter:
    """Stateful filter that tracks alert frequency for novelty scoring."""

    def __init__(self) -> None:
        self._alert_history: Dict[str, list[datetime]] = defaultdict(list)
        self.last_reject_reason: Optional[str] = None

    def passes(self, flow: dict) -> bool:
        """Return True if this flow alert passes all filters."""
        self.last_reject_reason = None
        ticker = (flow.get("ticker") or "").upper()

        dte = flow.get("dte")
        if dte is not None:
            if dte < MIN_DTE:
                self.last_reject_reason = f"DTE too low: {dte} < {MIN_DTE}"
                return False
            if dte > MAX_DTE:
                self.last_reject_reason = f"DTE too high: {dte} > {MAX_DTE}"
                return False

        premium = flow.get("premium")
        if premium is not None and premium < MIN_PREMIUM:
            self.last_reject_reason = (
                f"Premium too low: ${premium:,.0f} < ${MIN_PREMIUM:,.0f}"
            )
            return False

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=NOVELTY_WINDOW_MINUTES)

        # Clean old entries
        self._alert_history[ticker] = [
            t for t in self._alert_history[ticker] if t > cutoff
        ]

        # Add current
        self._alert_history[ticker].append(now)

        alert_count = len(self._alert_history[ticker])
        flow["_novelty_score"] = min(1.0, NOVELTY_DECAY_THRESHOLD / max(alert_count, 1))
        flow["_alert_count_1h"] = alert_count

        return True

    def is_discovery_eligible(self, ticker: str) -> bool:
        """Return True if this ticker should be included in discovery list."""
        return ticker.upper() not in DISCOVERY_BLACKLIST

    def get_novelty_score(self, ticker: str) -> float:
        """Return current novelty score for a ticker (0.0 to 1.0)."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=NOVELTY_WINDOW_MINUTES)
        recent = [t for t in self._alert_history.get(ticker, []) if t > cutoff]
        count = len(recent)
        if count == 0:
            return 1.0
        return min(1.0, NOVELTY_DECAY_THRESHOLD / count)
