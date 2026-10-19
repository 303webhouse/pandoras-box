"""B3: the yield-curve labels, the shape word, the un-inverted flag, and the fire rates.

The labels are R-IV.1220(b)'s: UNUSUAL at |z| >= 2, EXTREME at |z| >= 3 or a 10Y day of 10bp
or more, "RARE" retired, EXTREME still pulsing, and EVERY LABEL OWING ITS MEASURED FIRES PER
YEAR. The measurement is the part worth testing hardest: a tooltip that states a frequency is
making a claim, and the Gaussian answer is wrong for rates.
"""
from __future__ import annotations

import datetime as _dt
import random

import pytest

from models import yield_curve_b3 as yc


# ── 1. the labels ─────────────────────────────────────────────────────────

def test_RARE_IS_RETIRED_AND_THERE_IS_NO_THIRD_LABEL():
    """R-IV.1220(b). Checked on the module's own constants, not on its prose."""
    assert yc.UNUSUAL == "UNUSUAL" and yc.EXTREME == "EXTREME"
    names = {v for k, v in vars(yc).items()
             if k.isupper() and isinstance(v, str) and k not in ("SHAPE_WORDS",)}
    assert "RARE" not in names
    assert not any("RARE" == w for w in yc.SHAPE_WORDS)


def test_THE_THRESHOLDS_ARE_ONE_NUMBER_EACH():
    """Two numbers for one threshold is a fault this lane has shipped. The label function must
    read the same constants the payload publishes."""
    assert (yc.UNUSUAL_Z, yc.EXTREME_Z) == (2.0, 3.0)
    assert not hasattr(yc, "EXTREME_10Y_BP"), "R-IV.1239(b) removed the 10bp route"
    assert yc.label_for(1.99) is None
    assert yc.label_for(2.0) == yc.UNUSUAL
    assert yc.label_for(-2.5) == yc.UNUSUAL
    assert yc.label_for(3.0) == yc.EXTREME
    assert yc.label_for(-7.0) == yc.EXTREME


def test_THE_10BP_ROUTE_IS_GONE_AND_ONE_RULE_COVERS_EVERY_ROW():
    """R-IV.1239(b) removed it, and the ruling says the error was its own.

    THE MEASUREMENT IS WHAT FOUND IT, which is the clearest argument this session makes for
    requiring a rule to state its own fire rate. With the 10bp route live the counts came back
    10Y EXTREME 23.2/yr against 1.9 for the spreads, and 10Y UNUSUAL collapsed to 2.2 because
    the 10bp test ran first and took the days that would have read UNUSUAL. One row's EXTREME
    meant something different from every other row's. The rule read perfectly sensibly as
    prose; only the count showed what it did.

    So: no tenor argument, no change_bp argument, and calling it with them now RAISES rather
    than silently ignoring them -- a dead keyword left in a signature is an invitation to pass
    it again and wonder why nothing happens.
    """
    assert yc.label_for(2.9) == yc.UNUSUAL
    assert yc.label_for(3.0) == yc.EXTREME
    import pytest as _pytest
    with _pytest.raises(TypeError):
        yc.label_for(0.2, tenor="10Y", change_bp=12.0)
    with _pytest.raises(TypeError):
        yc.fires_per_year([1.0, 2.0], tenor="10Y")


def test_AN_UNMEASURABLE_Z_IS_NONE_NOT_ZERO():
    """A zero z reads as "a perfectly ordinary day", which is a claim. This lane's standing
    rule is that an unavailable reading is None and never 0.0."""
    assert yc.zscore([]) is None
    assert yc.zscore([1.0]) is None
    assert yc.zscore([1.0] * 20) is None, "20 changes is not enough history"
    assert yc.zscore([0.0] * 100) is None, "a flat series has no spread to score against"
    # The control: real variation gives a real z.
    series = [1.0, -2.0, 0.5, 3.0, -1.0] * 20 + [25.0]
    z = yc.zscore(series)
    assert z is not None and z > 3


# ── 2. holidays must not inflate every label ──────────────────────────────

def test_A_HOLIDAY_HOLE_IS_SKIPPED_NOT_CARRIED_FORWARD():
    """FRED's daily series carry None on holidays. Carrying the previous value forward would
    add a ZERO change, shrink the standard deviation and push more days over the threshold --
    a quiet inflation of every label on the panel.
    """
    with_hole = yc.diffs([4.0, None, 4.10])
    assert with_hole == pytest.approx([10.0]), "one 10bp change, not a 0 then a 10"
    carried = yc.diffs([4.0, 4.0, 4.10])
    assert carried == pytest.approx([0.0, 10.0])
    # And the inflation is measurable, which is why it is worth a test rather than a comment.
    real = [1.0, -1.0] * 60
    padded = []
    for v in real:
        padded.extend([v, 0.0])
    import statistics
    assert statistics.pstdev(padded) < statistics.pstdev(real)


def test_DIFFS_ARE_IN_BASIS_POINTS():
    """FRED publishes these series in PERCENTAGE POINTS. Mixing the units is how a 0.42 spread
    is shown as 0.4bp."""
    assert yc.diffs([4.00, 4.25]) == pytest.approx([25.0])


# ── 3. the measured fire rate ─────────────────────────────────────────────

def test_THE_FIRE_RATE_IS_MEASURED_BY_REPLAYING_THE_PUBLISHED_RULE():
    """Not a closed-form approximation. The same zscore and label_for the live reading uses,
    so if the rule changes the tooltip's number changes with it."""
    rnd = random.Random(11)
    changes = [rnd.gauss(0, 5) for _ in range(252 * 6)]
    stats = yc.fires_per_year(changes)
    assert stats["sessions_tested"] > 1000
    # A normal series fires |z|>=2 at roughly 11 a year and |z|>=3 at roughly 1.
    assert 5 <= stats["unusual_per_year"] <= 20
    assert 0 <= stats["extreme_per_year"] <= 5
    assert "replaying the published rule" in stats["basis"]
    assert "years" in stats["basis"]


def test_FAT_TAILS_FIRE_MORE_OFTEN_THAN_THE_GAUSSIAN_ANSWER():
    """THE REASON THE RATE IS MEASURED AT ALL. Rates' daily changes are fat-tailed, so quoting
    the textbook 11-a-year figure for |z|>=3 would understate how often the panel will pulse.
    A mixture of a quiet and a violent regime -- which is what a rate series is -- fires EXTREME
    materially more often than a normal one.
    """
    rnd = random.Random(7)
    normal = [rnd.gauss(0, 5) for _ in range(252 * 6)]
    fat = [rnd.gauss(0, 2) if rnd.random() < 0.9 else rnd.gauss(0, 18)
           for _ in range(252 * 6)]
    assert (yc.fires_per_year(fat)["extreme_per_year"]
            > yc.fires_per_year(normal)["extreme_per_year"])


def test_TOO_LITTLE_HISTORY_SAYS_SO_RATHER_THAN_REPORTING_ZERO():
    """A rate of 0.0 a year and "we cannot measure it" are different claims, and the first one
    is the comfortable one."""
    stats = yc.fires_per_year([1.0, 2.0, 3.0])
    assert stats["sessions_tested"] == 0
    assert stats["unusual_per_year"] is None
    assert "not enough history" in stats["basis"]
    assert "not enough history" in yc.tooltip("10Y", stats)


def test_THE_TOOLTIP_CARRIES_THE_RULE_THE_RATE_AND_THE_AS_OF():
    """R-IV.1220(b) requires the measured fires per year in the tooltip; Convention #37 as
    clarified by R-IV.1224(g) requires source, universe and as-of in the SAME SENTENCE."""
    rnd = random.Random(3)
    stats = yc.fires_per_year([rnd.gauss(0, 4) for _ in range(252 * 3)])
    stats["as_of"] = "2026-10-17"
    tip = yc.tooltip("2s10s", stats)
    assert "UNUSUAL" in tip and "EXTREME" in tip
    assert "times a year" in tip
    assert "FRED" in tip and "2026-10-17" in tip
    assert "RARE" not in tip


# ── 4. the shape word ─────────────────────────────────────────────────────

def test_EITHER_SPREAD_NEGATIVE_MEANS_INVERTED():
    """Not both. A 3m10s inversion with a positive 2s10s is still an inverted front end, and
    that is the part the recession literature reads. NORMAL there would be the comfortable
    answer rather than the true one."""
    word, why = yc.shape_word(40.0, -15.0)
    assert word == "INVERTED" and "3m10s" in why
    word2, why2 = yc.shape_word(-8.0, 30.0)
    assert word2 == "INVERTED" and "2s10s" in why2


def test_THE_SHAPE_WORD_CARRIES_THE_THRESHOLD_THAT_PICKED_IT():
    assert yc.shape_word(10.0, 20.0)[0] == "FLAT"
    assert yc.shape_word(80.0, 90.0)[0] == "NORMAL"
    assert yc.shape_word(180.0, 200.0)[0] == "STEEP"
    for bp in (10.0, 80.0, 180.0):
        assert "bp" in yc.shape_word(bp, bp)[1]
    assert yc.shape_word(None, None) == (None, "neither spread is available")


# ── 5. the un-inverted flag ───────────────────────────────────────────────

def test_UN_INVERTED_IS_NONE_WHEN_IT_NEVER_HAPPENED():
    """None, not False: "it did not un-invert" and "it was never inverted" are different
    facts, and the second is most of history."""
    assert yc.un_inverted([50.0] * 40) is None
    assert yc.un_inverted([-30.0] * 40) is None, "still inverted is not un-inverted"


def test_UN_INVERTED_FIRES_ON_THE_CROSSING_AND_DATES_IT():
    series = [-20.0] * 30 + [-5.0, 2.0, 6.0]
    got = yc.un_inverted(series)
    assert got["flag"] == "UN-INVERTED"
    assert got["sessions_ago"] == 1
    assert got["from_bp"] == -5.0 and got["to_bp"] == 2.0
    assert "crossed from" in got["basis"]


def test_A_SPREAD_AT_EXACTLY_ZERO_HAS_STOPPED_BEING_INVERTED():
    """Treating 0 as still-negative would hold the flag back a day on precisely the day it
    matters."""
    assert yc.un_inverted([-10.0] * 10 + [0.0])["to_bp"] == 0.0


def test_AN_OLD_CROSSING_IS_NOT_NEWS():
    series = [-20.0] * 10 + [5.0] * 60
    assert yc.un_inverted(series) is None
    assert yc.un_inverted(series, window=80) is not None
