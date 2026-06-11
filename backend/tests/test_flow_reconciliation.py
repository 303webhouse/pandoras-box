"""Flow reconciliation tests (sub-brief 3 Chunk 2-R)."""

from scoring.flow_reconciliation import fixed_p2_read, reconcile_flow


# --- fixed_p2_read: the read-fix + hedging damp ---

def test_xlk_hedging_case_suppressed():
    # XLK pc=13.31, bullish premium → cheap-put hedging, NOT directional bearishness.
    # Live P2 fired -13; the fix must suppress to 0 (no penalty).
    r = fixed_p2_read(13.31, "bullish", "LONG")
    assert r["hedging_suppressed"] is True
    assert r["bonus"] == 0


def test_confirming_bullish_long_small_nudge():
    r = fixed_p2_read(0.6, "bullish", "LONG")
    assert r["hedging_suppressed"] is False
    assert r["bonus"] == 3  # small positive nudge


def test_contradicting_never_negative():
    # bearish premium on a LONG → must floor at 0, never a penalty
    r = fixed_p2_read(1.4, "bearish", "LONG")
    assert r["bonus"] == 0


def test_moderate_put_volume_not_hedging():
    # pc just below the 3.0 hedging threshold → not auto-suppressed
    r = fixed_p2_read(2.5, "bullish", "LONG")
    assert r["hedging_suppressed"] is False


# --- reconcile_flow: path selection + distinct flags ---

def _p4a(**kw):
    base = dict(
        signal_direction="LONG", p4a_sentiment="BULLISH",
        p4a_call_premium=3_000_000, p4a_put_premium=0, p4a_age_min=5,
        p4a_raw_bonus=6, p2_pc_ratio=0.6, p2_net_premium_direction="bullish",
        p2_raw_bonus=3,
    )
    base.update(kw)
    return reconcile_flow(**base)


def test_overlap_p4a_authoritative_p2_suppressed():
    r = _p4a()
    assert r["path"] == "overlap"
    assert r["reconciled_bonus"] == 6   # P4A wins
    assert r["suppressed_p2"] is True
    assert r["p4a_fresh"] is True and r["p4a_conviction"] is True


def test_fresh_but_weak_is_distinct_not_gapfill():
    # fresh (age 5) but <$2M conviction → 'weak', flags distinct, P2 still suppressed
    r = _p4a(p4a_call_premium=1_000_000, p4a_raw_bonus=2)
    assert r["path"] == "weak"
    assert r["p4a_fresh"] is True
    assert r["p4a_conviction"] is False
    assert r["suppressed_p2"] is True


def test_stale_p4a_falls_to_gapfill():
    # age 120 > 45 → not fresh → P2 gap-fills (confirming bullish LONG → +3)
    r = _p4a(p4a_age_min=120)
    assert r["path"] == "gapfill"
    assert r["p4a_fresh"] is False
    assert r["reconciled_bonus"] == 3
    assert r["suppressed_p2"] is False


def test_neutral_p4a_falls_to_gapfill():
    r = _p4a(p4a_sentiment="NEUTRAL")
    assert r["path"] == "gapfill"


def test_gapfill_never_negative_on_contradiction():
    # stale P4A + P2 contradicts the signal → floored at 0, never a penalty
    r = _p4a(p4a_age_min=None, p2_net_premium_direction="bearish")
    assert r["path"] == "gapfill"
    assert r["reconciled_bonus"] == 0


def test_xlk_in_gapfill_suppressed_not_penalized():
    # stale P4A, XLK-style hedging P2 → gap-fill picks the fixed read → 0, not -13
    r = _p4a(p4a_age_min=None, p2_pc_ratio=13.31, p2_net_premium_direction="bullish", p2_raw_bonus=-13)
    assert r["path"] == "gapfill"
    assert r["hedging_suppressed"] is True
    assert r["reconciled_bonus"] == 0
    assert r["p2_raw_bonus"] == -13  # raw still logged for the report
