"""S-3 Phase 2 — initial seed for crypto_cycle_config (v1, gating_enabled=false).

All thresholds config-driven per §4.2/§4.4 hard rules. Append-only per FA-6.
Never modify this dict after SEED_S3 row is inserted — INSERT a new config row.
"""

SEED_CONFIG_V1 = {
    # --- Staleness thresholds (seconds) per data source cadence ---
    "staleness_thresholds": {
        "coinalyze":  360,     # 5-min cadence + 1-min buffer
        "deribit":    360,
        "binance":    360,
        "defillama":  3600,    # 1-hour cadence
        "yfinance":   86400,   # Daily cadence
        "okx":        360,
    },

    # --- FROTH column thresholds (§4.4) ---
    "froth": {
        "basis_extreme_pct":      10.0,   # quarterly basis annualized > 10% triggers FROTH
        "funding_blowout_pct":     0.05,  # funding rate > 0.05% = overleveraged longs
        "oi_extreme_change_pct":   5.0,   # OI increase > 5% in 4h = crowding
        "skew_call_extreme_pct":  -5.0,   # 25d skew < -5 = extreme call demand (froth)
    },

    # --- CAPITULATION column (§4.3) — existing 9 signal thresholds unchanged ---
    # These are informational; the actual computation reuses btc_bottom_signals thresholds.
    "capitulation": {
        "vix_spike_threshold":         25.0,
        "funding_negative_threshold":  -0.03,
        "oi_divergence_pct":           2.0,
        "liquidation_total_usd":       5_000_000,
        "liquidation_long_pct":        75.0,
        "basis_backwardation_pct":    -5.0,
        "skew_put_extreme_pct":        5.0,
        "orderbook_imbalance_pct":     0.15,
    },

    # --- Composite degraded flag threshold ---
    # If fewer than this many cells are LIVE, composite is marked degraded
    "min_live_cells_btc_eth":    3,   # BTC/ETH: full two-column → degrade if < 3 LIVE
    "min_live_cells_others":     2,   # Other symbols: partial dial → degrade if < 2 LIVE

    # --- Tape-health CVD split thresholds (§5.2) ---
    "tape_health": {
        "spot_led_threshold":   0.60,   # spot_cvd / total_cvd > 60% → SPOT_LED
        "perp_led_threshold":   0.60,   # perp_cvd / total_cvd > 60% → PERP_LED
        "staleness_seconds":    120,    # tape-health stale after 2 min with no update
    },

    # --- CVD event detection (§5.3) ---
    "cvd_events": {
        "divergence_cooldown_seconds":  900,    # 15 min per-symbol-per-type cooldown
        "absorption_cooldown_seconds":  900,
        "divergence_signal_expiry_hours": 24,
        "absorption_signal_expiry_hours": 24,
    },

    # --- Shadow flag: dial never writes to signals table (§4.9, D3) ---
    "dial_writes_to_feed":  False,  # assertion-enforced in cycle engine

    # --- Signal #10 (ETF-flow exhaustion) deferred to S-5 (§4.6) ---
    "signal_10_etf_flow_state": "DEFERRED_S5_BUDGET_SIZING",
}
