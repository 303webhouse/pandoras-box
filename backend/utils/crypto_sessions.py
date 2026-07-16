"""Stater Swap v2 S-2 (R-1) — crypto session engine. Pure functions, no I/O.

Two layers, deliberately separate (brief §6.2):
1. Continuous ASIA/LONDON/NY partition -- fixed-UTC, every timestamp maps to
   exactly one.
2. Named event windows (Asia Handoff, London Open, Peak Volume, ETF Fixing,
   Friday CME Close) -- config-defined, each carrying its own `anchor_tz` so
   DST moves it correctly (IANA `zoneinfo` only, hard rule 3 -- no hardcoded
   UTC offsets anywhere). Seeded (Fable amendment B, 2026-07-15) as the five
   legacy `/api/btc/sessions` windows, behavior-preserving: all anchor_tz=
   "America/New_York", same NY-local boundaries that route has always used.

Every returned timestamp/label is dual-labeled (utc + america_denver), per
the brief's HELIOS carry-forward ("Denver dual-label") and hard rule 3 (no
string math -- zoneinfo-derived only).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

DENVER_TZ = ZoneInfo("America/Denver")
UTC_TZ = ZoneInfo("UTC")


def _as_aware_utc(ts: datetime) -> datetime:
    """Normalize to a tz-aware datetime in UTC (assume naive == UTC)."""
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(UTC_TZ)


def _dual_label(ts: datetime) -> Dict[str, str]:
    utc_ts = _as_aware_utc(ts)
    denver_ts = utc_ts.astimezone(DENVER_TZ)
    return {"utc": utc_ts.isoformat(), "america_denver": denver_ts.isoformat()}


def get_partition(ts: datetime, partition_utc: Dict[str, List[int]]) -> str:
    """Continuous ASIA/LONDON/NY partition, fixed-UTC. `partition_utc` is the
    config's {"ASIA": [0, 8], "LONDON": [8, 16], "NY": [16, 24]} shape --
    every hour 0-23 must map to exactly one name."""
    hour = _as_aware_utc(ts).hour
    for name, (start, end) in partition_utc.items():
        if start <= hour < end:
            return name
    return "UNKNOWN"


def _window_bounds_minutes(window_cfg: Dict[str, Any]) -> tuple[int, int]:
    start = window_cfg.get("start_hour", 0) * 60 + window_cfg.get("start_minute", 0)
    end = window_cfg.get("end_hour", 0) * 60 + window_cfg.get("end_minute", 0)
    return start, end


def _window_is_active(ts: datetime, window_cfg: Dict[str, Any]) -> bool:
    tz = ZoneInfo(window_cfg["anchor_tz"])
    local = _as_aware_utc(ts).astimezone(tz)

    weekday_req = window_cfg.get("weekday")
    if weekday_req is not None and local.weekday() != weekday_req:
        return False

    start_min, end_min = _window_bounds_minutes(window_cfg)
    local_min = local.hour * 60 + local.minute
    return start_min <= local_min < end_min


def get_active_event_windows(ts: datetime, event_windows_cfg: Dict[str, Dict[str, Any]]) -> List[str]:
    """Names of every event window active at `ts`. May be empty; windows can
    overlap the continuous partition (they're a separate layer)."""
    return [name for name, cfg in event_windows_cfg.items() if _window_is_active(ts, cfg)]


def _next_window_transition(ts: datetime, window_cfg: Dict[str, Any]) -> datetime:
    """Next boundary (start or end, whichever comes first) after `ts`, in UTC.
    Searches day-by-day up to 8 days ahead (covers a weekday-gated window like
    friday_close in the worst case)."""
    tz = ZoneInfo(window_cfg["anchor_tz"])
    weekday_req = window_cfg.get("weekday")
    start_h, start_m = window_cfg.get("start_hour", 0), window_cfg.get("start_minute", 0)
    end_h, end_m = window_cfg.get("end_hour", 0), window_cfg.get("end_minute", 0)

    local_now = _as_aware_utc(ts).astimezone(tz)
    for day_offset in range(0, 8):
        candidate_date = (local_now + timedelta(days=day_offset)).date()
        if weekday_req is not None and candidate_date.weekday() != weekday_req:
            continue
        for hh, mm in ((start_h, start_m), (end_h, end_m)):
            candidate = datetime(
                candidate_date.year, candidate_date.month, candidate_date.day,
                hh, mm, tzinfo=tz,
            )
            if candidate > local_now:
                return candidate.astimezone(UTC_TZ)
    # Should be unreachable given the 8-day search window; fail visible.
    raise RuntimeError(f"could not find next transition for window config {window_cfg!r}")


def is_weekend_or_holiday(ts: datetime, holiday_dates: List[str]) -> bool:
    """Saturday/Sunday in America/New_York terms, or an explicit holiday date."""
    ny_ts = _as_aware_utc(ts).astimezone(ZoneInfo("America/New_York"))
    if ny_ts.weekday() >= 5:  # Saturday=5, Sunday=6
        return True
    return ny_ts.date().isoformat() in (holiday_dates or [])


def get_session_state(ts: datetime, config: dict) -> Dict[str, Any]:
    """Full session state at `ts` per the §7 /api/crypto/clock payload
    contract. `config` is a crypto_gate_config row's decoded JSON."""
    sessions_cfg = config.get("sessions", {})
    partition_utc = sessions_cfg.get("partition_utc", {"ASIA": [0, 8], "LONDON": [8, 16], "NY": [16, 24]})
    event_windows_cfg = sessions_cfg.get("event_windows", {})
    holiday_dates = sessions_cfg.get("holiday_dates", [])

    partition = get_partition(ts, partition_utc)
    active_windows = get_active_event_windows(ts, event_windows_cfg)
    weekend_holiday = is_weekend_or_holiday(ts, holiday_dates)

    next_transitions = []
    for name, cfg in event_windows_cfg.items():
        try:
            at_utc = _next_window_transition(ts, cfg)
            labels = _dual_label(at_utc)
            next_transitions.append({"window": name, "at_utc": labels["utc"], "at_denver": labels["america_denver"]})
        except Exception:
            continue
    next_transitions.sort(key=lambda t: t["at_utc"])

    as_of_labels = _dual_label(ts)
    return {
        "as_of_utc": as_of_labels["utc"],
        "as_of_denver": as_of_labels["america_denver"],
        "partition": partition,
        "event_windows_active": active_windows,
        "next_transitions": next_transitions,
        "weekend_holiday_flag": weekend_holiday,
    }
