"""
Aggregate parsed UW flow alerts into per-ticker summaries and a discovery list.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from discord_bridge.uw.filter import FlowFilter

logger = logging.getLogger(__name__)

FLOW_WINDOW_MINUTES = 120  # rolling window


class FlowAggregator:
    """Accumulates flow alerts and produces summaries."""

    def __init__(self) -> None:
        self._flows: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._ticker_summaries: Dict[str, Dict[str, Any]] = {}

    def add_flow(self, flow: dict) -> None:
        """Add a parsed, filtered flow alert."""
        ticker = flow["ticker"].upper()
        flow["_received_at"] = datetime.now(timezone.utc)
        self._flows[ticker].append(flow)

    def update_ticker_summary(self, summary: dict) -> None:
        """Update the latest ticker summary from the Ticker Updates channel."""
        ticker = summary.get("ticker")
        if ticker:
            self._ticker_summaries[ticker.upper()] = summary

    def get_flow_summaries(self) -> List[Dict[str, Any]]:
        """Produce per-ticker flow summaries for all tickers with recent activity."""
        self._prune_old()
        summaries: List[Dict[str, Any]] = []

        for ticker, flows in self._flows.items():
            if not flows:
                continue

            call_premium = 0.0
            put_premium = 0.0
            buy_count = 0
            sell_count = 0
            unusual_count = len(flows)
            total_dte = 0
            dte_count = 0
            max_premium_trade = None
            max_premium = 0.0

            for f in flows:
                premium = f.get("premium") or 0.0
                option_type = f.get("option_type")
                side = f.get("side")

                if option_type == "CALL":
                    if side == "BUY":
                        call_premium += premium
                        buy_count += 1
                    elif side == "SELL":
                        call_premium -= premium
                        sell_count += 1
                    else:
                        call_premium += premium
                elif option_type == "PUT":
                    if side == "BUY":
                        put_premium += premium
                        buy_count += 1
                    elif side == "SELL":
                        put_premium -= premium
                        sell_count += 1
                    else:
                        put_premium += premium

                if f.get("dte") is not None:
                    total_dte += f["dte"]
                    dte_count += 1

                if premium > max_premium:
                    max_premium = premium
                    max_premium_trade = f

            net_premium = call_premium - put_premium
            avg_dte = round(total_dte / dte_count) if dte_count > 0 else None

            if net_premium > 0 and call_premium > put_premium * 1.5:
                sentiment = "BULLISH"
            elif net_premium < 0 and put_premium > call_premium * 1.5:
                sentiment = "BEARISH"
            else:
                sentiment = "MIXED"

            novelty_scores = [f.get("_novelty_score", 1.0) for f in flows]
            avg_novelty = sum(novelty_scores) / len(novelty_scores) if novelty_scores else 1.0

            unusualness_score = round(
                (min(abs(net_premium), 5_000_000) / 5_000_000)
                * avg_novelty
                * min(unusual_count / 3, 1.0)
                * 100,
                1,
            )

            summary = {
                "ticker": ticker,
                "net_premium": round(net_premium, 2),
                "call_premium": round(call_premium, 2),
                "put_premium": round(put_premium, 2),
                "sentiment": sentiment,
                "unusual_count": unusual_count,
                "buy_count": buy_count,
                "sell_count": sell_count,
                "avg_dte": avg_dte,
                "novelty": round(avg_novelty, 2),
                "unusualness_score": unusualness_score,
                "largest_trade": {
                    "premium": max_premium,
                    "strike": max_premium_trade.get("strike") if max_premium_trade else None,
                    "expiry": max_premium_trade.get("expiry") if max_premium_trade else None,
                    "option_type": max_premium_trade.get("option_type") if max_premium_trade else None,
                }
                if max_premium_trade
                else None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            ticker_summary = self._ticker_summaries.get(ticker)
            if ticker_summary:
                summary["put_call_ratio"] = ticker_summary.get("put_call_ratio")
                summary["share_volume"] = ticker_summary.get("share_volume")

            summaries.append(summary)

        return summaries

    def get_discovery_list(self) -> List[Dict[str, Any]]:
        """Produce ranked discovery list of tickers not in blacklist."""
        flow_filter = FlowFilter()
        summaries = self.get_flow_summaries()

        discovery = []
        for summary in summaries:
            if flow_filter.is_discovery_eligible(summary["ticker"]):
                discovery.append(
                    {
                        "ticker": summary["ticker"],
                        "unusualness_score": summary["unusualness_score"],
                        "sentiment": summary["sentiment"],
                        "net_premium": summary["net_premium"],
                        "unusual_count": summary["unusual_count"],
                        "avg_dte": summary["avg_dte"],
                    }
                )

        discovery.sort(key=lambda x: x["unusualness_score"], reverse=True)
        return discovery[:20]

    def _prune_old(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=FLOW_WINDOW_MINUTES)
        for ticker in list(self._flows.keys()):
            self._flows[ticker] = [
                f for f in self._flows[ticker] if f.get("_received_at", cutoff) > cutoff
            ]
            if not self._flows[ticker]:
                del self._flows[ticker]
