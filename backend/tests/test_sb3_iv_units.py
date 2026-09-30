"""Unit-assertion test for the iv_rank 0–1 → 0–100 conversion (sub-brief 3 Chunk 1b).

Guards the forward unit-trap: UW iv_rank_1y is a 0–1 fraction; the scorer's
thresholds are 0–100. If the ×100 is ever dropped, these fail.
"""

from scoring.sb3_iv_units import iv_rank_1y_to_100, iv_bonus_from_rank


def test_x100_conversion_applied():
    # 0.65 fraction → 65.0 on the 0–100 scale (the core assertion)
    assert iv_rank_1y_to_100(0.65) == 65.0
    assert iv_rank_1y_to_100(0.0) == 0.0
    assert iv_rank_1y_to_100(1.0) == 100.0
    assert iv_rank_1y_to_100(0.137) == 13.7


def test_string_input_coerced():
    assert iv_rank_1y_to_100("0.42") == 42.0


def test_out_of_range_is_refused_not_clamped():
    """THIS TEST USED TO ASSERT THE DEFECT, and that is why it went uncaught.

    It read:

        assert iv_rank_1y_to_100(1.5) == 100.0   # defensive upper clamp
        assert iv_rank_1y_to_100(-0.1) == 0.0    # defensive lower clamp

    The clamp is not defensive. Measured 2026-09-30 on the column this function feeds:
    **7,553 of 7,606 rows are exactly 100.0** and 35 more are exactly 0.0 — the two bounds this
    test blessed — across 7,606 readings since 2026-06-11. The unrelated proxy rank has 711
    distinct values and none at 100, so the constant is the conversion, not the market.

    The module's docstring asserted the input is a 0–1 fraction, and this test checked the
    conversion against that assertion rather than against the payload. A quantity defined on
    [0, 1] cannot exceed 1 in 99.3% of observations, so the assertion was wrong and the clamp
    hid it by turning every out-of-range input into "IV at its one-year high".
    """
    assert iv_rank_1y_to_100(1.5) is None
    assert iv_rank_1y_to_100(-0.1) is None
    assert iv_rank_1y_to_100(41.7) is None       # a percent, which is what the payload sends
    # POSITIVE CONTROL: a genuine fraction is still converted, so the refusal is narrow.
    assert iv_rank_1y_to_100(0.417) == 41.7
    assert iv_rank_1y_to_100(1.0) == 100.0       # the boundary is IN range


def test_missing_is_none_not_zero():
    # no_data must be None (caller labels reason), never a fake 0
    assert iv_rank_1y_to_100(None) is None
    assert iv_rank_1y_to_100("abc") is None


def test_range_invariant():
    for raw in (0.0, 0.01, 0.5, 0.999, 1.0):
        v = iv_rank_1y_to_100(raw)
        assert 0.0 <= v <= 100.0


def test_bonus_banding_matches_scorer_0_100_scale():
    # Confirms the new value bands on the SAME 0–100 thresholds as the live scorer
    assert iv_bonus_from_rank(15.0) == 3     # <=20
    assert iv_bonus_from_rank(35.0) == 1     # <=40
    assert iv_bonus_from_rank(55.0) == 0     # <=60
    assert iv_bonus_from_rank(75.0) == -2    # <=80
    assert iv_bonus_from_rank(90.0) == -5    # >80
    assert iv_bonus_from_rank(None) == 0     # no_data → 0 (labeled by caller)
