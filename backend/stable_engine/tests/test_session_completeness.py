"""R-IV.497(e) — a session below its universe never becomes the anchor.

The bars layer's coverage contract was per TICKER: "did this symbol answer at
all". A vendor can answer for 679 symbols and still hold a session for only 135
of them, and that run scores 100% coverage. Measured 2026-09-24:
stable_daily_bars held 679 bars for 09-18, 09-21 and 09-23 and **135** for 09-22,
while the run summary reported healthy — the bars layer had no per-date notion.

It matters because the ANCHOR IS A DATE, and the anchor feeds the regime, which
is the committee's trend tier. metrics and scoring already refuse an incomplete
date; the bars layer did not name one, so nothing upstream could see it coming.

Run:  PYTHONPATH=backend python -m pytest backend/stable_engine/tests
"""

import pytest

from stable_engine import scoring


def required_for(counts):
    """The rule under test, stated once: scoring's thresholds, not a local copy."""
    return max(scoring.ANCHOR_MIN_TICKERS_FLOOR,
               int(max(counts.values()) * scoring.ANCHOR_MIN_COVERAGE))


def incomplete(counts):
    req = required_for(counts)
    return [(d, n, req) for d, n in sorted(counts.items()) if n < req]


def test_the_live_2026_09_22_shape_is_named():
    """The real numbers: three full sessions and one holding 135 of 679."""
    counts = {"2026-09-18": 679, "2026-09-21": 679, "2026-09-22": 135, "2026-09-23": 679}
    bad = incomplete(counts)
    assert [d for d, _, _ in bad] == ["2026-09-22"]
    assert bad[0][1] == 135 and bad[0][2] == 543      # 80% of 679


def test_a_complete_window_names_nothing():
    counts = {"2026-09-21": 679, "2026-09-22": 679, "2026-09-23": 679}
    assert incomplete(counts) == []


def test_the_threshold_tracks_the_universe_rather_than_a_hardcoded_size():
    """A universe that grows or shrinks must not need this rule edited."""
    small = {"a": 100, "b": 79}
    big = {"a": 1000, "b": 799}
    assert incomplete(small) and incomplete(big)
    assert required_for(small) == 80 and required_for(big) == 800


def test_the_floor_protects_a_tiny_window():
    """Without a floor, a window whose largest session is itself tiny would call
    everything complete — the two-ticker anchor defect scoring already records."""
    counts = {"a": 3, "b": 2}
    assert required_for(counts) == scoring.ANCHOR_MIN_TICKERS_FLOOR
    assert len(incomplete(counts)) == 2, "both are below the floor and neither may anchor"


def test_a_session_exactly_at_the_threshold_is_allowed():
    counts = {"a": 100, "b": 80}
    assert incomplete(counts) == []


@pytest.mark.parametrize("n,ok", [(542, False), (543, True), (544, True)])
def test_the_boundary_is_where_it_is_stated(n, ok):
    counts = {"full": 679, "probe": n}
    assert (incomplete(counts) == []) is ok


def test_the_writer_and_the_reader_share_one_definition():
    """convention #9: the writer must not call a date healthy that the reader
    would refuse to anchor on, so both read scoring's constants."""
    assert scoring.ANCHOR_MIN_COVERAGE == 0.80
    assert scoring.ANCHOR_MIN_TICKERS_FLOOR == 50
