"""
Unit tests for utils/crypto_sessions.py (S-2, R-1 session engine).

Covers: continuous-partition edges, event-window activation (incl. the
Friday-only gate), DST correctness across real 2026 US transitions (spring
2026-03-08, fall 2026-11-01) for the seeded America/New_York-anchored
windows, Denver dual-label correctness on both MDT and MST dates, and a
generic (non-US) IANA zone to prove the mechanism isn't NY-hardcoded --
covering the spirit of the brief's "UK DST" case even though Phase 1's
actual seed anchors all five legacy windows to America/New_York (Fable
amendment B; venue-native re-anchoring is a later config tune).

Real 2026 transition dates (independently computed via zoneinfo, not
assumed): US DST spring 2026-03-08, fall 2026-11-01. UK DST spring
2026-03-29, fall 2026-10-25.
"""

import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.crypto_sessions import (
    get_partition,
    get_active_event_windows,
    is_weekend_or_holiday,
    get_session_state,
    _dual_label,
    _next_window_transition,
)

PARTITION_UTC = {"ASIA": [0, 8], "LONDON": [8, 16], "NY": [16, 24]}

EVENT_WINDOWS = {
    "asia_handoff": {"anchor_tz": "America/New_York", "start_hour": 20, "start_minute": 0, "end_hour": 21, "end_minute": 0},
    "london_open": {"anchor_tz": "America/New_York", "start_hour": 4, "start_minute": 0, "end_hour": 6, "end_minute": 0},
    "peak_volume": {"anchor_tz": "America/New_York", "start_hour": 11, "start_minute": 0, "end_hour": 13, "end_minute": 0},
    "etf_fixing": {"anchor_tz": "America/New_York", "start_hour": 15, "start_minute": 0, "end_hour": 16, "end_minute": 0},
    "friday_close": {"anchor_tz": "America/New_York", "weekday": 4, "start_hour": 15, "start_minute": 55, "end_hour": 16, "end_minute": 0},
}

HOLIDAYS = ["2026-09-07", "2026-11-26", "2026-12-25"]


def _utc(y, m, d, hh, mm=0, ss=0):
    return datetime(y, m, d, hh, mm, ss, tzinfo=timezone.utc)


# ── Partition edges ──────────────────────────────────────────────────────

def test_partition_edges():
    assert get_partition(_utc(2026, 7, 15, 0, 0), PARTITION_UTC) == "ASIA"
    assert get_partition(_utc(2026, 7, 15, 7, 59), PARTITION_UTC) == "ASIA"
    assert get_partition(_utc(2026, 7, 15, 8, 0), PARTITION_UTC) == "LONDON"
    assert get_partition(_utc(2026, 7, 15, 15, 59), PARTITION_UTC) == "LONDON"
    assert get_partition(_utc(2026, 7, 15, 16, 0), PARTITION_UTC) == "NY"
    assert get_partition(_utc(2026, 7, 15, 23, 59), PARTITION_UTC) == "NY"


# ── Event window activation ──────────────────────────────────────────────

def test_friday_close_only_active_on_friday():
    # 2026-07-17 is a Friday; 2026-07-16 is a Thursday.
    friday_in_window = _utc(2026, 7, 17, 19, 57)   # 15:57 EDT (UTC-4) on a Friday
    thursday_same_local_time = _utc(2026, 7, 16, 19, 57)
    assert "friday_close" in get_active_event_windows(friday_in_window, EVENT_WINDOWS)
    assert "friday_close" not in get_active_event_windows(thursday_same_local_time, EVENT_WINDOWS)


def test_peak_volume_window_boundaries():
    # 11:00-13:00 America/New_York, mid-summer = EDT (UTC-4) -> 15:00-17:00 UTC.
    just_before = _utc(2026, 7, 15, 14, 59)
    at_start = _utc(2026, 7, 15, 15, 0)
    just_before_end = _utc(2026, 7, 15, 16, 59)
    at_end = _utc(2026, 7, 15, 17, 0)
    assert "peak_volume" not in get_active_event_windows(just_before, EVENT_WINDOWS)
    assert "peak_volume" in get_active_event_windows(at_start, EVENT_WINDOWS)
    assert "peak_volume" in get_active_event_windows(just_before_end, EVENT_WINDOWS)
    assert "peak_volume" not in get_active_event_windows(at_end, EVENT_WINDOWS)


# ── US DST boundaries (real 2026 transition dates) ───────────────────────

def test_us_dst_spring_moves_etf_fixing_in_utc():
    """etf_fixing is 15:00-16:00 America/New_York year-round. Before the
    2026-03-08 spring-forward (EST, UTC-5) that's 20:00-21:00 UTC; after
    (EDT, UTC-4) it's 19:00-20:00 UTC -- the UTC window shifts by an hour
    while the NY-local definition never changes."""
    before_transition = _utc(2026, 3, 7, 20, 30)   # 15:30 EST
    after_transition = _utc(2026, 3, 9, 19, 30)    # 15:30 EDT
    assert "etf_fixing" in get_active_event_windows(before_transition, EVENT_WINDOWS)
    assert "etf_fixing" in get_active_event_windows(after_transition, EVENT_WINDOWS)
    # The pre-transition UTC hour would NOT be in-window post-transition, proving the shift:
    assert "etf_fixing" not in get_active_event_windows(_utc(2026, 3, 9, 20, 30), EVENT_WINDOWS)


def test_us_dst_fall_moves_friday_close_in_utc():
    """friday_close is Fri 15:55-16:00 America/New_York. 2026-11-01 is the
    fall-back Sunday; the next Friday close (2026-11-06) is in EST
    (UTC-5) = 20:55-21:00 UTC, vs. the prior Friday (2026-10-30, EDT,
    UTC-4) = 19:55-20:00 UTC."""
    pre_fallback_friday = _utc(2026, 10, 30, 19, 57)   # EDT Friday
    post_fallback_friday = _utc(2026, 11, 6, 20, 57)   # EST Friday
    assert "friday_close" in get_active_event_windows(pre_fallback_friday, EVENT_WINDOWS)
    assert "friday_close" in get_active_event_windows(post_fallback_friday, EVENT_WINDOWS)
    # Same UTC clock time, wrong side of the fall-back -> not active:
    assert "friday_close" not in get_active_event_windows(_utc(2026, 11, 6, 19, 57), EVENT_WINDOWS)


def test_next_transition_crosses_dst_correctly():
    """_next_window_transition must land on a real, DST-correct boundary --
    not silently drift by not re-deriving the UTC offset per candidate day."""
    just_before_spring = _utc(2026, 3, 8, 6, 0)  # early on transition day (pre 2am local)
    nxt = _next_window_transition(just_before_spring, EVENT_WINDOWS["etf_fixing"])
    assert nxt.tzinfo is not None
    # Should resolve to 15:00 local on 2026-03-08, and since the US clock
    # springs forward at 2am local that day, 15:00 is already EDT (UTC-4).
    assert nxt == _utc(2026, 3, 8, 19, 0)


# ── Generic IANA-zone mechanism (not NY-hardcoded) — covers the spirit of
# the brief's "UK DST" case; the actual Phase-1 seed uses NY for all five
# legacy windows per Fable amendment B, this proves the code generalizes ──

def test_generic_uk_anchored_window_handles_uk_dst():
    london_window = {"anchor_tz": "Europe/London", "start_hour": 8, "start_minute": 0, "end_hour": 9, "end_minute": 0}
    before_bst = _utc(2026, 3, 28, 8, 30)   # 08:30 GMT (UTC+0)
    after_bst = _utc(2026, 3, 30, 7, 30)    # 08:30 BST (UTC+1)
    assert _window_active(before_bst, london_window)
    assert _window_active(after_bst, london_window)
    assert not _window_active(_utc(2026, 3, 30, 8, 30), london_window)  # would be 09:30 BST, past the window


def _window_active(ts, window_cfg):
    return "w" in get_active_event_windows(ts, {"w": window_cfg})


# ── Denver dual-label correctness on both MDT and MST dates ──────────────

def test_denver_dual_label_mdt():
    labels = _dual_label(_utc(2026, 7, 15, 18, 0))  # mid-summer -> MDT (UTC-6)
    assert labels["america_denver"].endswith("-06:00")


def test_denver_dual_label_mst():
    labels = _dual_label(_utc(2026, 1, 15, 18, 0))  # mid-winter -> MST (UTC-7)
    assert labels["america_denver"].endswith("-07:00")


# ── Weekend / holiday flag ────────────────────────────────────────────────

def test_weekend_flag():
    saturday = _utc(2026, 7, 18, 12, 0)  # a Saturday
    tuesday = _utc(2026, 7, 14, 12, 0)   # a Tuesday
    assert is_weekend_or_holiday(saturday, HOLIDAYS) is True
    assert is_weekend_or_holiday(tuesday, HOLIDAYS) is False


def test_holiday_flag():
    christmas = _utc(2026, 12, 25, 12, 0)  # a Friday, also a listed holiday
    assert is_weekend_or_holiday(christmas, HOLIDAYS) is True


# ── Full session state shape ──────────────────────────────────────────────

def test_get_session_state_shape():
    config = {"sessions": {"partition_utc": PARTITION_UTC, "event_windows": EVENT_WINDOWS, "holiday_dates": HOLIDAYS}}
    state = get_session_state(_utc(2026, 7, 15, 15, 30), config)
    assert state["as_of_utc"].startswith("2026-07-15T15:30:00")
    assert state["as_of_denver"].endswith("-06:00")
    assert state["partition"] == "LONDON"
    assert isinstance(state["event_windows_active"], list)
    assert isinstance(state["next_transitions"], list)
    assert all({"window", "at_utc", "at_denver"} <= t.keys() for t in state["next_transitions"])
    assert state["weekend_holiday_flag"] is False


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS: {t.__name__}")
    print(f"\nAll {len(tests)} crypto_sessions tests passed.")
