"""R-IV.435(e) — the scoring anchor is the newest COMPLETE date, and a partial date is held.

The outage: theme scores stopped 2026-09-04 while metrics landed through 09-15, because the
newest metrics date (09-16) carried TWO tickers against 677 on every prior date and MAX(date)
made it the anchor.
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stable_engine import metrics, scoring  # noqa: E402


def _counts_frame(rows):
    return pd.DataFrame(rows, columns=["date", "n"])


def test_the_two_ticker_date_is_not_the_anchor():
    """The measured shape: 09-16 holds 2, 09-15 holds 677, universe 690."""
    with patch.object(scoring, "_scalar", return_value=690), \
         patch.object(scoring.db, "read_df", return_value=_counts_frame([("2026-09-15", 677)])) as rd:
        date, coverage, required = scoring.anchor_date()
    assert (date, coverage) == ("2026-09-15", 677)
    assert required == int(690 * 0.80)
    sql, params = rd.call_args.args[0], rd.call_args.args[1]
    assert "COUNT(DISTINCT ticker) >= %s" in sql and "ORDER BY date DESC" in sql
    assert params[-1] == required


def test_no_complete_date_returns_empty_and_never_falls_back():
    with patch.object(scoring, "_scalar", return_value=690), \
         patch.object(scoring.db, "read_df", return_value=pd.DataFrame()):
        date, coverage, required = scoring.anchor_date()
        assert date is None and coverage == 0
        assert scoring.compute_theme_scores().empty          # and the reader says nothing


def test_the_floor_holds_when_the_universe_is_tiny_or_unreadable():
    for universe, expected in ((0, scoring.ANCHOR_MIN_TICKERS_FLOOR),
                               (10, scoring.ANCHOR_MIN_TICKERS_FLOOR),
                               (690, 552)):
        with patch.object(scoring, "_scalar", return_value=universe), \
             patch.object(scoring.db, "read_df", return_value=pd.DataFrame()):
            assert scoring.anchor_date()[2] == expected


def test_every_reader_uses_the_same_anchor():
    """constituents and the regime read anchored on MAX(date) too."""
    import inspect
    for fn in (scoring.compute_theme_scores, scoring.get_theme_constituents, scoring.get_regime_read):
        src = inspect.getsource(fn)
        assert "anchor_date(" in src, fn.__name__
        assert "MAX(date) FROM stable_metrics" not in src, fn.__name__


# ── the writer: a date is published only when its universe has landed ───────────

def _metrics_df(per_date):
    rows = []
    for d, n in per_date.items():
        for i in range(n):
            rows.append({"date": d, "ticker": f"T{i:04d}"})
    return pd.DataFrame(rows)


def test_a_partial_date_is_held_back_not_published():
    df = _metrics_df({"2026-09-15": 677, "2026-09-16": 2})
    kept, held = metrics._hold_incomplete_dates(df)
    assert set(kept["date"]) == {"2026-09-15"}
    assert held == [("2026-09-16", 2)]


def test_a_complete_date_is_published():
    df = _metrics_df({"2026-09-15": 677, "2026-09-16": 660})
    kept, held = metrics._hold_incomplete_dates(df)
    assert set(kept["date"]) == {"2026-09-15", "2026-09-16"} and held == []


def test_the_writer_and_the_reader_share_one_minimum():
    import inspect
    src = inspect.getsource(metrics._hold_incomplete_dates)
    assert "scoring.ANCHOR_MIN_COVERAGE" in src and "scoring.ANCHOR_MIN_TICKERS_FLOOR" in src


def test_a_subset_run_does_not_judge_coverage():
    import inspect
    src = inspect.getsource(metrics.compute_metrics)
    assert "if tickers is None:" in src and "held_dates = []" in src


# ── the backfill ────────────────────────────────────────────────────────────────

def test_missing_dates_are_complete_dates_without_scores():
    with patch.object(scoring, "_scalar", return_value=690), \
         patch.object(scoring.db, "read_df",
                      return_value=pd.DataFrame({"date": ["2026-09-08", "2026-09-09"]})) as rd:
        out = scoring.missing_score_dates("close")
    assert out == ["2026-09-08", "2026-09-09"]
    sql = rd.call_args.args[0]
    assert "LEFT JOIN" in sql and "s.date IS NULL" in sql and "m.n >= %s" in sql


def test_backfill_stores_each_date_and_skips_what_it_cannot_compute():
    calls = []

    def fake_compute(as_of=None):
        if as_of == "2026-09-09":
            return pd.DataFrame()
        return pd.DataFrame([{"theme": "AI", "date": as_of}])

    def fake_store(scores, anchor, degraded=False, **kw):
        calls.append((scores.iloc[0]["date"], anchor, degraded))
        return len(scores)

    with patch.object(scoring, "missing_score_dates", return_value=["2026-09-08", "2026-09-09"]), \
         patch.object(scoring, "compute_theme_scores", side_effect=fake_compute), \
         patch.object(scoring, "store_theme_scores", side_effect=fake_store):
        out = scoring.backfill_missing_theme_scores(anchor="close", degraded=True)
    assert out == [("2026-09-08", 1)]
    assert calls == [("2026-09-08", "close", True)]


def test_backfill_is_bounded_per_pass():
    with patch.object(scoring, "missing_score_dates", return_value=[f"d{i}" for i in range(50)]), \
         patch.object(scoring, "compute_theme_scores", return_value=pd.DataFrame()), \
         patch.object(scoring, "store_theme_scores", return_value=0):
        with patch.object(scoring, "logger"):
            out = scoring.backfill_missing_theme_scores(limit=5)
    assert out == []            # none computable here, but the cap is what is asserted
    assert scoring.BACKFILL_MAX_DATES_PER_PASS == 20


def test_the_nightly_backfills_and_reports_held_dates():
    import inspect
    from jobs import stable_jobs
    src = inspect.getsource(stable_jobs._nightly_work)
    assert "backfill_missing_theme_scores" in src
    assert '"held_dates"' in src and '"themes_backfilled"' in src
