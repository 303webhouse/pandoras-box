"""STRIKE-SPEC-01 converter — pure-function tests. No live DB.

Covers the brief's Task 7 list: signal_id/dedup format, each validation reject
rule, direction-from-alert_type (payload direction ignored), reversal tagging,
stop/target math both directions, Fri->Wed expiry roll, dry-run performs no
insert, cap halt. Plus D9's INSUFFICIENT render states from the addendum.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from jobs.strike_ib_converter import (
    BASELINE_SESSIONS_GATE,
    MAX_IB_HEIGHT_FRAC,
    SESSION_CAP,
    STRIKE_TICKER_ALLOWLIST,
    build_signal_data,
    build_signal_id,
    compute_expires_at,
    compute_levels,
    direction_from_alert_type,
    next_weekday,
    validate_event,
    watermark_state,
)


def _ev(**over):
    base = {
        "id": 4242,
        "ticker": "QQQ",
        "alert_type": "ib_break_up",
        "price": 100.0,
        "volume_quality": "high",
        "ib_high": 100.5,
        "ib_low": 99.5,
        "timestamp": datetime(2026, 9, 2, 14, 45, tzinfo=timezone.utc),
    }
    base.update(over)
    return base


# ── direction ───────────────────────────────────────────────────────────────

def test_direction_from_alert_type():
    assert direction_from_alert_type("ib_break_up") == "LONG"
    assert direction_from_alert_type("ib_break_down") == "SHORT"
    assert direction_from_alert_type("ib_break_sideways") is None
    assert direction_from_alert_type("") is None


def test_payload_direction_field_is_ignored():
    """alert_type is the ONLY direction source. A payload claiming the opposite
    must not invert the trade."""
    ev = _ev(alert_type="ib_break_up", direction="SHORT")
    sd = build_signal_data(ev, direction_from_alert_type(ev["alert_type"]),
                           date(2026, 9, 2), False)
    assert sd["direction"] == "LONG"
    assert sd["signal_id"].endswith("_UP")


# ── signal_id / dedup ───────────────────────────────────────────────────────

def test_signal_id_format_and_dedup_key():
    assert build_signal_id("QQQ", date(2026, 9, 2), "LONG") == "STRIKE_IB_QQQ_20260902_UP"
    assert build_signal_id("TLT", date(2026, 9, 2), "SHORT") == "STRIKE_IB_TLT_20260902_DOWN"


def test_signal_id_is_stable_across_repeat_events():
    """Same ticker/direction/session -> identical id, so ON CONFLICT absorbs the
    second event. This IS the dedup mechanism; there is no separate check."""
    a = build_signal_id("SMH", date(2026, 9, 2), "LONG")
    b = build_signal_id("SMH", date(2026, 9, 2), "LONG")
    assert a == b


def test_opposite_directions_get_distinct_ids():
    """Both directions must be emittable in one session — that is the whole
    point of bypassing process_signal_unified()."""
    up = build_signal_id("IWM", date(2026, 9, 2), "LONG")
    dn = build_signal_id("IWM", date(2026, 9, 2), "SHORT")
    assert up != dn


# ── validation, one test per reject rule ────────────────────────────────────

def test_validate_accepts_a_clean_event():
    ok, reason = validate_event(_ev())
    assert ok and reason is None


def test_reject_ticker_not_in_allowlist():
    ok, reason = validate_event(_ev(ticker="GME"))
    assert not ok and reason == "ticker_not_in_allowlist"


def test_reject_unrecognized_alert_type():
    ok, reason = validate_event(_ev(alert_type="opening_range_break"))
    assert not ok and reason == "unrecognized_alert_type"


@pytest.mark.parametrize("field", ["ib_high", "ib_low"])
def test_reject_null_ib_bounds(field):
    ok, reason = validate_event(_ev(**{field: None}))
    assert not ok and reason == "ib_bounds_null"


def test_reject_non_positive_ib_height():
    ok, reason = validate_event(_ev(ib_high=99.5, ib_low=99.5))
    assert not ok and reason == "ib_height_non_positive"


def test_reject_null_price():
    ok, reason = validate_event(_ev(price=None))
    assert not ok and reason == "price_null"


def test_reject_price_outside_ib_envelope():
    ok, reason = validate_event(_ev(price=500.0))
    assert not ok and reason == "price_outside_ib_envelope"
    ok, reason = validate_event(_ev(price=1.0))
    assert not ok and reason == "price_outside_ib_envelope"


def test_reject_ib_height_exceeding_price_fraction():
    # height 10 on price 100 = 10% > the 5% cap
    ok, reason = validate_event(_ev(price=100.0, ib_low=95.0, ib_high=105.0))
    assert not ok and reason == "ib_height_exceeds_price_fraction"


def test_ib_height_exactly_at_the_cap_is_accepted():
    """Boundary is inclusive — a gate that rejects its own stated limit would
    make the documented threshold unreachable."""
    price = 100.0
    height = MAX_IB_HEIGHT_FRAC * price  # 5.00
    ok, reason = validate_event(_ev(price=price, ib_low=97.5, ib_high=97.5 + height))
    assert ok, reason


# ── stop / target math ──────────────────────────────────────────────────────

def test_levels_long():
    lv = compute_levels("LONG", price=100.0, ib_high=100.5, ib_low=99.5)
    assert lv["ib_height"] == pytest.approx(1.0)
    assert lv["stop_loss"] == pytest.approx(100.0)          # IB midpoint
    assert lv["target_1"] == pytest.approx(100.5)           # +0.5 x height
    assert lv["target_2"] == pytest.approx(101.0)           # +1.0 x height
    assert lv["stop_variant_opposite_extreme"] == pytest.approx(99.5)


def test_levels_short_mirror():
    lv = compute_levels("SHORT", price=100.0, ib_high=100.5, ib_low=99.5)
    assert lv["stop_loss"] == pytest.approx(100.0)
    assert lv["target_1"] == pytest.approx(99.5)            # -0.5 x height
    assert lv["target_2"] == pytest.approx(99.0)            # -1.0 x height
    assert lv["stop_variant_opposite_extreme"] == pytest.approx(100.5)


def test_targets_are_on_opposite_sides_by_direction():
    long_lv = compute_levels("LONG", 100.0, 100.5, 99.5)
    short_lv = compute_levels("SHORT", 100.0, 100.5, 99.5)
    assert long_lv["target_2"] > long_lv["entry_price"]
    assert short_lv["target_2"] < short_lv["entry_price"]


def test_risk_reward_is_none_when_entry_sits_on_the_stop():
    """Zero risk must render None, never a division blow-up and never 0.0 —
    an unavailable ratio is not a ratio of zero."""
    lv = compute_levels("LONG", price=100.0, ib_high=101.0, ib_low=99.0)
    assert lv["stop_loss"] == pytest.approx(100.0)
    assert lv["risk_reward"] is None


# ── expiry roll ─────────────────────────────────────────────────────────────

def test_expiry_friday_rolls_to_wednesday():
    """2026-09-04 is a Friday; +3 trading sessions = Wed 2026-09-09."""
    assert date(2026, 9, 4).weekday() == 4
    exp = compute_expires_at(date(2026, 9, 4))
    assert exp.date() == date(2026, 9, 9)
    assert exp.hour == 20 and exp.tzinfo == timezone.utc


def test_expiry_monday_rolls_to_thursday():
    assert date(2026, 8, 31).weekday() == 0
    assert compute_expires_at(date(2026, 8, 31)).date() == date(2026, 9, 3)


def test_next_weekday_skips_the_weekend():
    assert next_weekday(date(2026, 9, 4)) == date(2026, 9, 7)   # Fri -> Mon
    assert next_weekday(date(2026, 9, 7)) == date(2026, 9, 8)   # Mon -> Tue


# ── shadow invariants ───────────────────────────────────────────────────────

def test_emitted_row_carries_both_shadow_markers():
    """Binding condition 2 — status AND the L0 tag. Neither alone covers all
    read surfaces, so a test asserting only one would pass on a leaking row."""
    sd = build_signal_data(_ev(), "LONG", date(2026, 9, 2), False)
    assert sd["status"] == "SHADOW"
    assert sd["triggering_factors"]["l0_shadow"]["would_suppress"] is True
    assert sd["feed_tier"] == "research_log"


def test_raw_payload_is_never_copied_into_the_signal_row():
    sd = build_signal_data(_ev(raw_payload={"secret": "nope"}), "LONG", date(2026, 9, 2), False)
    assert "raw_payload" not in sd
    assert "raw_payload" not in sd["triggering_factors"]["strike"]
    assert "nope" not in str(sd)


def test_reversal_tagging():
    plain = build_signal_data(_ev(), "LONG", date(2026, 9, 2), False)
    rev = build_signal_data(_ev(alert_type="ib_break_down"), "SHORT", date(2026, 9, 2), True)
    assert plain["triggering_factors"]["strike"]["ib_reversal"] is False
    assert rev["triggering_factors"]["strike"]["ib_reversal"] is True


def test_signal_metadata_carries_provenance():
    sd = build_signal_data(_ev(), "LONG", date(2026, 9, 2), False)
    st = sd["triggering_factors"]["strike"]
    assert st["pythia_event_id"] == 4242
    assert st["volume_quality"] == "high"
    assert sd["source"] == "STRIKE_IB_BREAK"


# ── watermark render states (addendum s3 / D9) ──────────────────────────────

def test_d9_first_deploy_renders_insufficient_zero():
    """D9: on first deploy every allowlist ticker renders INSUFFICIENT n=0."""
    assert watermark_state(0, seen_this_session=False, latched=False) == "INSUFFICIENT n=0"


def test_below_gate_never_renders_ok_or_silent():
    """No alarm until n >= 3, and INSUFFICIENT must not be confusable with OK."""
    for n in range(BASELINE_SESSIONS_GATE):
        assert watermark_state(n, seen_this_session=True, latched=False) == f"INSUFFICIENT n={n}"
        assert watermark_state(n, seen_this_session=False, latched=False) == f"INSUFFICIENT n={n}"


def test_at_gate_renders_ok_or_silent():
    assert watermark_state(BASELINE_SESSIONS_GATE, True, False) == "OK"
    assert watermark_state(BASELINE_SESSIONS_GATE, False, False) == "SILENT"


def test_gate_is_literally_three_per_d9():
    """D9 fixes the gate at n >= 3. Asserted as a LITERAL, not against the
    constant: a test parameterized on the value it verifies moves with the bug
    and cannot fail. Caught by mutation — setting the constant to 1 passed all
    36 tests before this was added."""
    assert BASELINE_SESSIONS_GATE == 3


def test_n_two_is_still_insufficient_literal():
    assert watermark_state(2, seen_this_session=True, latched=False) == "INSUFFICIENT n=2"


def test_n_three_is_the_first_ok_literal():
    assert watermark_state(3, seen_this_session=True, latched=False) == "OK"
    assert watermark_state(3, seen_this_session=False, latched=False) == "SILENT"


def test_latched_renders_silent_regardless():
    assert watermark_state(99, seen_this_session=True, latched=True) == "SILENT"


def test_absent_and_healthy_do_not_render_alike():
    """The defect this block exists to prevent."""
    assert watermark_state(0, False, False) != watermark_state(BASELINE_SESSIONS_GATE, True, False)


# ── structural constants ────────────────────────────────────────────────────

def test_session_cap_is_two_per_ticker():
    assert SESSION_CAP == 2 * len(STRIKE_TICKER_ALLOWLIST) == 16


def test_allowlist_is_the_ruled_eight():
    assert STRIKE_TICKER_ALLOWLIST == {"QQQ", "IWM", "SMH", "DIA", "XLF", "XLK", "XLE", "TLT"}


def test_allowlist_is_immutable():
    """Code constant per binding condition 5 — not env, not DB."""
    assert isinstance(STRIKE_TICKER_ALLOWLIST, frozenset)


# ── dry-run ─────────────────────────────────────────────────────────────────

def test_dry_run_flag_is_empty_safe(monkeypatch):
    """Railway returns '' for an unset reference; os.getenv(name, default) would
    yield '' and silently defeat the default."""
    from jobs import strike_ib_converter as m
    monkeypatch.setenv("STRIKE_IB_DRY_RUN", "")
    assert m.is_dry_run() is False
    monkeypatch.setenv("STRIKE_IB_DRY_RUN", "true")
    assert m.is_dry_run() is True
    monkeypatch.setenv("STRIKE_IB_ENABLED", "")
    assert m.is_enabled() is True          # default true survives the empty string
    monkeypatch.setenv("STRIKE_IB_ENABLED", "false")
    assert m.is_enabled() is False


@pytest.mark.asyncio
async def test_dry_run_performs_no_insert(monkeypatch):
    """Dry run assembles the row and logs it; log_signal must never be called."""
    from jobs import strike_ib_converter as m
    monkeypatch.setenv("STRIKE_IB_DRY_RUN", "true")

    calls = []

    class _Conn:
        async def fetch(self, *a, **k):
            return [_ev()]
        async def execute(self, *a, **k):
            return "INSERT 0 1"
        async def fetchval(self, *a, **k):
            return None

    import database.postgres_client as pc
    async def _boom(*a, **k):
        calls.append(a)
        raise AssertionError("log_signal must not be called in dry run")
    monkeypatch.setattr(pc, "log_signal", _boom, raising=False)

    stats = await m.process_events(_Conn(), None, datetime(2026, 9, 2, 14, 45, tzinfo=timezone.utc))
    assert calls == []
    assert stats["emitted"] == 0
    assert stats["seen"] == 1
