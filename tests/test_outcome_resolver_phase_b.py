"""Phase B regression test — pre-signal bar filter in _walk_bars."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pandas as pd
import pytest

from backend.jobs.outcome_resolver import _walk_bars


def _make_bars(rows):
    """rows: list of (bar_ts_iso, high, low). Returns DataFrame indexed by ts."""
    idx = pd.DatetimeIndex([pd.Timestamp(ts, tz="UTC") for ts, _, _ in rows])
    return pd.DataFrame(
        {"High": [h for _, h, _ in rows], "Low": [l for _, _, l in rows]},
        index=idx,
    )


def test_pre_signal_bar_does_not_match_target():
    """Pre-signal bar high above target must NOT register a WIN."""
    signal_ts = datetime(2026, 4, 23, 19, 20, 57, tzinfo=timezone.utc)
    bars = _make_bars([
        ("2026-04-23T19:00:00+00:00", 6.50, 5.00),  # PRE-SIGNAL: high above target
        ("2026-04-23T19:30:00+00:00", 5.05, 4.95),  # post-signal: no touch
    ])
    with patch("yfinance.download", return_value=bars):
        outcome, pnl, _ = _walk_bars("TEST", "LONG", 5.04, 6.02, 4.55, signal_ts)
    assert outcome is None, "Resolver matched on pre-signal bar (Phase B regression)"


def test_post_signal_bar_matches_correctly():
    """Post-signal bar that hits target must register WIN."""
    signal_ts = datetime(2026, 4, 23, 19, 20, 57, tzinfo=timezone.utc)
    bars = _make_bars([
        ("2026-04-23T19:00:00+00:00", 5.00, 5.00),  # PRE-SIGNAL: ignored
        ("2026-04-23T19:30:00+00:00", 6.10, 5.05),  # post-signal: HIGH ≥ target
    ])
    with patch("yfinance.download", return_value=bars):
        outcome, pnl, ts = _walk_bars("TEST", "LONG", 5.04, 6.02, 4.55, signal_ts)
    assert outcome == "WIN"
    assert abs(pnl - 19.44) < 0.01


def test_post_signal_stop_hit_returns_loss():
    signal_ts = datetime(2026, 4, 23, 19, 20, 57, tzinfo=timezone.utc)
    bars = _make_bars([
        ("2026-04-23T19:30:00+00:00", 5.05, 4.50),  # post-signal: LOW ≤ stop
    ])
    with patch("yfinance.download", return_value=bars):
        outcome, pnl, _ = _walk_bars("TEST", "LONG", 5.04, 6.02, 4.55, signal_ts)
    assert outcome == "LOSS"


def test_same_bar_target_and_stop_is_conservative_loss():
    signal_ts = datetime(2026, 4, 23, 19, 20, 57, tzinfo=timezone.utc)
    bars = _make_bars([
        ("2026-04-23T19:30:00+00:00", 6.10, 4.50),  # both hit in one bar
    ])
    with patch("yfinance.download", return_value=bars):
        outcome, _, _ = _walk_bars("TEST", "LONG", 5.04, 6.02, 4.55, signal_ts)
    assert outcome == "LOSS", "Same-bar target+stop must be conservative LOSS"


def test_short_direction_pre_signal_bar_does_not_match():
    signal_ts = datetime(2026, 4, 23, 19, 20, 57, tzinfo=timezone.utc)
    bars = _make_bars([
        ("2026-04-23T19:00:00+00:00", 5.00, 4.00),  # PRE-SIGNAL: low below target
        ("2026-04-23T19:30:00+00:00", 5.05, 4.95),  # post-signal: no touch
    ])
    with patch("yfinance.download", return_value=bars):
        outcome, _, _ = _walk_bars("TEST", "SHORT", 5.04, 4.20, 5.50, signal_ts)
    assert outcome is None
