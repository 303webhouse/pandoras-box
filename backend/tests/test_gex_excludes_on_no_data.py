"""gex returns None on no-data instead of fabricating a neutral (R-IV.329(b)).

DEF-BIAS-NULL-AS-NEUTRAL's live instance: 35 of 695 gex readings carried score 0.0
with raw_data = {}. None is the exclusion signal — factor_scorer.py:87-97 deletes the
cached key so the composite drops the factor rather than averaging in a neutral
nobody measured.
"""

import pathlib
import re

import pytest

SRC = pathlib.Path(__file__).resolve().parents[1] / "bias_filters" / "gex.py"


def _body() -> str:
    """Source with comments and docstrings stripped enough for structural asserts."""
    t = SRC.read_text(encoding="utf-8")
    return "\n".join(l for l in t.split("\n") if not l.strip().startswith("#"))


def test_gex_no_longer_fabricates():
    """The whole fix in one assertion: gex must not call neutral_reading anywhere."""
    assert "neutral_reading(" not in _body()


def test_compute_score_is_optional_so_none_is_legal():
    """A filter that cannot return None can never be excluded — dxy_trend's shape,
    which is why this is asserted rather than assumed."""
    assert re.search(r"async def compute_score\(\)\s*->\s*Optional\[FactorReading\]", _body())


def test_both_no_data_branches_return_none():
    b = _body()
    assert "returning None so the composite EXCLUDES it" in b
    # the UW-unavailable branch and the insufficient-contracts branch
    assert b.count("returning None so the composite EXCLUDES it") == 2


def test_the_exclusion_path_it_depends_on_still_exists():
    """gex returning None is only a fix because factor_scorer deletes the key.
    If that behaviour goes, this fix silently becomes a no-op."""
    fs = (SRC.parents[1] / "bias_engine" / "factor_scorer.py").read_text(encoding="utf-8")
    assert "compute_score() returned None" in fs
    assert "client.delete(key)" in fs
