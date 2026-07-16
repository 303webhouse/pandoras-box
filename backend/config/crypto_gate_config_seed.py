"""Stater Swap v2 S-2 (R-1) — seed payload for `crypto_gate_config` version 1.

This is config, not code: every threshold/mapping here is meant to be tuned
via a fresh `crypto_gate_config` row (hot-reload, no redeploy — see
backend/config/crypto_gate_loader.py), not by editing this file after the
initial seed. This module only supplies the SEED_CONFIG_V1 payload that
`init_database()` inserts once, idempotently, if the table is empty.

`strategy_classes` (Fable amendment A, 2026-07-15): keys use the EXACT
strategy strings `process_signal_unified` actually persists (confirmed live
via `s2-phase0-findings.md` 0.6 — only "Crypto Scanner" and "Session_Sweep"
have ever fired for a crypto ticker; "Holy_Grail"/"Funding_Rate_Fade"/
"Liquidation_Flush"/"Exhaustion" exist in code but have never fired). The
evaluator (crypto_gates.py) does an EXACT dict-key match — no `.lower()`,
no case normalization anywhere. Everything not listed falls to
"unclassified" -> WOULD_PASS_WITH_NOTE (visible in shadow, never a silent
gap). "Crypto Scanner" -> momentum_continuation is a hypothesis (it emits
pullback/setup entries, i.e. trend-continuation) — hot-reloadable if wrong.

`sessions.event_windows` (Fable amendment B, 2026-07-15): the five legacy
windows from `/api/btc/sessions` (`s2-phase0-findings.md` 0.4), reproduced
behavior-preserving — same NY-local boundaries, all anchor_tz=
"America/New_York" (that route's actual convention, confirmed live; it is
NOT fixed-UTC despite the brief's original assumption). Venue-native
re-anchoring (e.g. london_open -> Europe/London) is a later config tune,
not Phase 1. The continuous ASIA/LONDON/NY partition is a separate,
fixed-UTC layer (`sessions.partition_utc`) per the brief's own §6.2 split.
"""

from __future__ import annotations

SEED_CONFIG_V1 = {
    "gating_enabled": False,
    "regime": {
        "slope_threshold_pct": 0.5,
        "adx_trend_min": 20,
        "slope_lookback_bars": 10,
        "stale_bars_max_hours": 48,
        "min_bars_compute": 60,
        "thin_history_bars": 120,
        "recompute_minutes": 60,
    },
    "tiers": {
        "BTC-USD": 1,
        "ETH-USD": 1,
        "SOL-USD": 2,
        "HYPE-USD": 3,
        "ZEC-USD": 3,
        "FARTCOIN-USD": 3,
    },
    "master_rules": {
        "btc_trend_down_blocks_tier3_all_entries": True,
        "btc_trend_down_blocks_tier2_longs": True,
        "unknown_master_blocks_regime_dependent": True,
    },
    "alt_gate": {
        "status": "NOT_AVAILABLE",
        "note": "R-4 dominance/ETH-BTC/alt-breadth strip; A-3 minimum bar (BTC-regime-not-down) enforced via master_rules until then",
    },
    "strategy_classes": {
        "momentum_continuation": {
            "strategies": ["Crypto Scanner", "Holy_Grail"],
            "long_allowed_in": ["TREND_UP"],
            "short_allowed_in": ["TREND_DOWN"],
        },
        "fade_mean_reversion": {
            "strategies": ["Funding_Rate_Fade", "Exhaustion"],
            "long_allowed_in": ["CHOP", "TREND_UP"],
            "short_allowed_in": ["CHOP", "TREND_DOWN"],
        },
        "sweep_reclaim": {
            "strategies": ["Session_Sweep"],
            "long_allowed_in": ["CHOP", "TREND_UP"],
            "short_allowed_in": ["CHOP", "TREND_DOWN"],
            "requires_event_window": True,
        },
        "cascade_fade": {
            "strategies": ["Liquidation_Flush"],
            "long_allowed_in": ["CHOP", "TREND_UP"],
            "short_allowed_in": ["CHOP", "TREND_DOWN"],
        },
        "unclassified": {
            "strategies": ["*"],
            "policy": "WOULD_PASS_WITH_NOTE",
        },
    },
    "sessions": {
        "partition_utc": {"ASIA": [0, 8], "LONDON": [8, 16], "NY": [16, 24]},
        "event_windows": {
            "asia_handoff": {
                "anchor_tz": "America/New_York",
                "start_hour": 20, "start_minute": 0,
                "end_hour": 21, "end_minute": 0,
            },
            "london_open": {
                "anchor_tz": "America/New_York",
                "start_hour": 4, "start_minute": 0,
                "end_hour": 6, "end_minute": 0,
            },
            "peak_volume": {
                "anchor_tz": "America/New_York",
                "start_hour": 11, "start_minute": 0,
                "end_hour": 13, "end_minute": 0,
            },
            "etf_fixing": {
                "anchor_tz": "America/New_York",
                "start_hour": 15, "start_minute": 0,
                "end_hour": 16, "end_minute": 0,
            },
            "friday_close": {
                "anchor_tz": "America/New_York",
                "weekday": 4,
                "start_hour": 15, "start_minute": 55,
                "end_hour": 16, "end_minute": 0,
            },
        },
        "holiday_dates": ["2026-09-07", "2026-11-26", "2026-12-25"],
    },
    "advisories": {"weekend_holiday_size_reduce": True},
}
