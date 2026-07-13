"""Stater Swap v2 S-1 — Crypto Symbol Capability Matrix (F-1 / A-1 deliverable).

Machine-readable coverage record for the six-symbol crypto universe (BTC, ETH,
SOL, HYPE, ZEC, FARTCOIN — Nick decision D2, 2026-07-12). Every cell below was
live-verified from the Railway container (`railway ssh`) on 2026-07-13 — see
`docs/strategy-reviews/stater-swap-redesign/symbol-capability-matrix.md` for
the full evidence log (raw HTTP statuses, response snippets, per-endpoint
notes). This module is the value the rest of the codebase should import;
the markdown doc is the audit trail for how each value was established.

Why a Python config module, not a Postgres table (CC's call per brief F-1.2):
this data changes only when the matrix is re-verified (expected cadence:
alongside each new symbol/vendor decision, not live-market-driven), so it has
none of the properties that motivate a table — no concurrent writers, no
per-row TTL, no need for SQL joins against it. A git-tracked module makes
every change PR-reviewable (matches the "config-driven" theme used elsewhere
in this brief for R-1+ thresholds) and needs no migration to update. Runtime
consumers (hub MCP tools, F-3's state envelope) import CRYPTO_SYMBOL_MATRIX
directly — no loader, no cache invalidation.

Status vocabulary:
  LIVE        — verified working with real, non-empty data at test time.
  UNAVAILABLE — verified NOT working (empty/null data, invalid symbol, or not
                listed), with a `reason` explaining what was observed.
  GEO_BLOCKED — verified blocked specifically by IP/region restriction (HTTP
                451), distinct from UNAVAILABLE (a listing/coverage gap).
  UNVERIFIED  — not empirically tested in this pass; a `reason` names what
                would need checking and when (never used as a silent default).

Never treat a symbol/vendor cell as covered without one of the above tags —
per PROJECT_RULES's fail-visible principle, an absent cell is a bug, not "no".
"""

from __future__ import annotations

from typing import Optional

TIER_1 = frozenset({"BTC", "ETH"})
TIER_2 = frozenset({"SOL"})
TIER_3 = frozenset({"HYPE", "ZEC", "FARTCOIN"})

SYMBOL_TIER = {sym: 1 for sym in TIER_1}
SYMBOL_TIER.update({sym: 2 for sym in TIER_2})
SYMBOL_TIER.update({sym: 3 for sym in TIER_3})


CRYPTO_SYMBOL_MATRIX: dict[str, dict] = {
    "BTC": {
        "tier": 1,
        "coinalyze_funding_oi_liq_term": {
            "status": "LIVE",
            "symbol_used": "BTCUSD_PERP.A",
            "verified": "2026-07-13: funding-rate read HTTP 200, non-empty payload",
        },
        "deribit_25d_skew": {
            "status": "LIVE",
            "verified": "2026-07-13: get_book_summary_by_currency HTTP 200, 838 option instruments",
        },
        "binance_quarterly_basis": {
            "status": "GEO_BLOCKED",
            "reason": "fapi.binance.com returned HTTP 451 from Railway (verified 2026-07-13, exact body: 'Service unavailable from a restricted location')",
            "fallback_vendor": "okx",
            "fallback_status": "LIVE",
            "fallback_verified": "2026-07-13: OKX BTC-USDT-SWAP ticker HTTP 200 with data",
        },
        "binance_spot_orderbook": {
            "status": "LIVE",
            "verified": "2026-07-13: data-api.binance.vision ticker/price HTTP 200, price=62143.58",
        },
        "uw_crypto_quote": {
            "status": "LIVE",
            "pair_format": "BTC-USD",
            "verified": "2026-07-13: /api/crypto/BTC-USD/state HTTP 200 with real OHLCV",
        },
        "tv_coverage": {
            "status": "LIVE",
            "note": "already in tradingview.py CRYPTO_TICKERS set",
        },
        "bar_walk_source": {
            "vendor": "uw_crypto_ohlc",
            "status": "LIVE",
            "verified": "2026-07-13: /api/crypto/BTC-USD/ohlc/1d HTTP 200, real candles",
        },
        "binance_fail_fallback": "okx",
    },
    "ETH": {
        "tier": 1,
        "coinalyze_funding_oi_liq_term": {
            "status": "LIVE",
            "symbol_used": "ETHUSD_PERP.A",
            "verified": "2026-07-13: funding-rate read HTTP 200, non-empty payload",
        },
        "deribit_25d_skew": {
            "status": "LIVE",
            "verified": "2026-07-13: get_book_summary_by_currency HTTP 200, 662 option instruments",
        },
        "binance_quarterly_basis": {
            "status": "GEO_BLOCKED",
            "reason": "fapi.binance.com returned HTTP 451 from Railway (verified 2026-07-13)",
            "fallback_vendor": "okx",
            "fallback_status": "LIVE",
            "fallback_verified": "2026-07-13: OKX ETH-USDT-SWAP ticker HTTP 200 with data",
        },
        "binance_spot_orderbook": {
            "status": "LIVE",
            "verified": "2026-07-13: data-api.binance.vision ticker/price HTTP 200, price=1766.85",
        },
        "uw_crypto_quote": {
            "status": "LIVE",
            "pair_format": "ETH-USD",
            "verified": "2026-07-13: /api/crypto/ETH-USD/state HTTP 200 with real OHLCV",
        },
        "tv_coverage": {
            "status": "LIVE",
            "note": "already in tradingview.py CRYPTO_TICKERS set",
        },
        "bar_walk_source": {
            "vendor": "uw_crypto_ohlc",
            "status": "LIVE",
            "verified": "2026-07-13: /api/crypto/ETH-USD/ohlc/1d HTTP 200, real candles",
        },
        "binance_fail_fallback": "okx",
    },
    "SOL": {
        "tier": 2,
        "coinalyze_funding_oi_liq_term": {
            "status": "LIVE",
            "symbol_used": "SOLUSD_PERP.A",
            "verified": "2026-07-13: funding-rate read HTTP 200, non-empty payload",
        },
        "deribit_25d_skew": {
            "status": "UNAVAILABLE",
            "reason": "SOL is a listed Deribit currency but get_book_summary_by_currency returned ZERO option instruments (2026-07-13) — skew calc will error 'insufficient options data' in practice despite the currency existing",
        },
        "binance_quarterly_basis": {
            "status": "GEO_BLOCKED",
            "reason": "fapi.binance.com returned HTTP 451 from Railway (verified 2026-07-13)",
            "fallback_vendor": "okx",
            "fallback_status": "LIVE",
            "fallback_verified": "2026-07-13: OKX SOL-USDT-SWAP ticker HTTP 200 with data",
        },
        "binance_spot_orderbook": {
            "status": "LIVE",
            "verified": "2026-07-13: data-api.binance.vision ticker/price HTTP 200, price=74.71",
        },
        "uw_crypto_quote": {
            "status": "LIVE",
            "pair_format": "SOL-USD",
            "verified": "2026-07-13: /api/crypto/SOL-USD/state HTTP 200 with real OHLCV",
        },
        "tv_coverage": {
            "status": "LIVE",
            "note": "already in tradingview.py CRYPTO_TICKERS set",
        },
        "bar_walk_source": {
            "vendor": "uw_crypto_ohlc",
            "status": "LIVE",
            "verified": "2026-07-13: /api/crypto/SOL-USD/ohlc/1d HTTP 200, real candles",
        },
        "binance_fail_fallback": "okx",
    },
    "HYPE": {
        "tier": 3,
        "coinalyze_funding_oi_liq_term": {
            "status": "LIVE",
            "symbol_used": "HYPEUSDT_PERP.A",
            "verified": "2026-07-13: funding-rate read HTTP 200, non-empty payload. Only 1 aggregated symbol candidate discovered (vs 2-3 for majors) — likely single-venue-sourced (Hyperliquid, per Coinalyze's own exchange list including 'Hyperliquid' code H); not independently confirmed which underlying exchange feeds the aggregate.",
        },
        "deribit_25d_skew": {
            "status": "UNAVAILABLE",
            "reason": "HYPE not present in Deribit get_currencies list (verified 2026-07-13)",
        },
        "binance_quarterly_basis": {
            "status": "GEO_BLOCKED",
            "reason": "fapi.binance.com returned HTTP 451 from Railway (verified 2026-07-13)",
            "fallback_vendor": "okx",
            "fallback_status": "LIVE",
            "fallback_verified": "2026-07-13: OKX HYPE-USDT-SWAP ticker HTTP 200 with data",
        },
        "binance_spot_orderbook": {
            "status": "UNAVAILABLE",
            "reason": "data-api.binance.vision returned HTTP 400 'Invalid symbol' for HYPEUSDT (verified 2026-07-13) — not listed on Binance spot",
            "fallback_vendor": "okx",
            "fallback_status": "LIVE",
        },
        "uw_crypto_quote": {
            "status": "UNAVAILABLE",
            "reason": "FAKE-HEALTHY TRAP: /api/crypto/HYPE-USD/state returns HTTP 200 with body {\"data\": null} (verified 2026-07-13) — endpoint exists, symbol has no data. Do not treat HTTP 200 alone as coverage.",
        },
        "tv_coverage": {
            "status": "UNAVAILABLE",
            "reason": "HYPE not in backend/webhooks/tradingview.py CRYPTO_TICKERS set (verified 2026-07-13) — an incoming HYPE alert would NOT be tagged asset_class=CRYPTO today",
            "fix_applied": "added to CRYPTO_TICKERS in this same Phase 1 pass — see s1(phase1) commit",
        },
        "bar_walk_source": {
            "vendor": "okx_candles",
            "status": "LIVE",
            "verified": "2026-07-13: OKX /market/candles HYPE-USDT-SWAP HTTP 200, 5 real daily candles returned",
        },
        "binance_fail_fallback": "okx",
    },
    "ZEC": {
        "tier": 3,
        "coinalyze_funding_oi_liq_term": {
            "status": "LIVE",
            "symbol_used": "ZECUSDT_PERP.A",
            "verified": "2026-07-13: funding-rate read HTTP 200, non-empty payload",
        },
        "deribit_25d_skew": {
            "status": "UNAVAILABLE",
            "reason": "ZEC not present in Deribit get_currencies list (verified 2026-07-13)",
        },
        "binance_quarterly_basis": {
            "status": "GEO_BLOCKED",
            "reason": "fapi.binance.com returned HTTP 451 from Railway (verified 2026-07-13)",
            "fallback_vendor": "okx",
            "fallback_status": "LIVE",
            "fallback_verified": "2026-07-13: OKX ZEC-USDT-SWAP ticker HTTP 200 with data",
        },
        "binance_spot_orderbook": {
            "status": "LIVE",
            "verified": "2026-07-13: data-api.binance.vision ticker/price HTTP 200, price=496.39 — ZEC IS listed on Binance spot",
        },
        "uw_crypto_quote": {
            "status": "LIVE",
            "pair_format": "ZEC-USD",
            "verified": "2026-07-13: /api/crypto/ZEC-USD/state HTTP 200 with real OHLCV (quote only — see bar_walk_source)",
        },
        "tv_coverage": {
            "status": "UNAVAILABLE",
            "reason": "ZEC not in backend/webhooks/tradingview.py CRYPTO_TICKERS set (verified 2026-07-13)",
            "fix_applied": "added to CRYPTO_TICKERS in this same Phase 1 pass — see s1(phase1) commit",
        },
        "bar_walk_source": {
            "vendor": "binance_spot_klines",
            "status": "LIVE",
            "verified": "2026-07-13: ZEC confirmed listed on Binance spot (data-api.binance.vision) and OKX SWAP — candle-history endpoint not independently pulled in S-1, deferred to F-2 implementation. NOTE: UW crypto OHLC does NOT work for ZEC despite /state working — /api/crypto/ZEC-USD/ohlc/1d returned an empty array (verified 2026-07-13). Do not use UW as ZEC's bar-walk source.",
        },
        "binance_fail_fallback": "okx",
    },
    "FARTCOIN": {
        "tier": 3,
        "coinalyze_funding_oi_liq_term": {
            "status": "LIVE",
            "symbol_used": "FARTCOINUSDT_PERP.A",
            "verified": "2026-07-13: funding-rate read HTTP 200, non-empty payload. Only 1 aggregated symbol candidate discovered (thin-coverage signal, same pattern as HYPE).",
        },
        "deribit_25d_skew": {
            "status": "UNAVAILABLE",
            "reason": "FARTCOIN not present in Deribit get_currencies list (verified 2026-07-13) — expected, no listed options market exists for this token anywhere",
        },
        "binance_quarterly_basis": {
            "status": "GEO_BLOCKED",
            "reason": "fapi.binance.com returned HTTP 451 from Railway (verified 2026-07-13)",
            "fallback_vendor": "okx",
            "fallback_status": "LIVE",
            "fallback_verified": "2026-07-13: OKX FARTCOIN-USDT-SWAP ticker HTTP 200 with data",
        },
        "binance_spot_orderbook": {
            "status": "UNAVAILABLE",
            "reason": "data-api.binance.vision returned HTTP 400 'Invalid symbol' for FARTCOINUSDT (verified 2026-07-13) — not listed on Binance spot",
            "fallback_vendor": "okx",
            "fallback_status": "LIVE",
        },
        "uw_crypto_quote": {
            "status": "UNAVAILABLE",
            "reason": "FAKE-HEALTHY TRAP: /api/crypto/FARTCOIN-USD/state returns HTTP 200 with body {\"data\": null} (verified 2026-07-13). Do not treat HTTP 200 alone as coverage.",
        },
        "tv_coverage": {
            "status": "UNAVAILABLE",
            "reason": "FARTCOIN not in backend/webhooks/tradingview.py CRYPTO_TICKERS set (verified 2026-07-13)",
            "fix_applied": "added to CRYPTO_TICKERS in this same Phase 1 pass — see s1(phase1) commit",
        },
        "bar_walk_source": {
            "vendor": "okx_candles",
            "status": "LIVE",
            "verified": "2026-07-13: OKX /market/candles FARTCOIN-USDT-SWAP HTTP 200, 5 real daily candles returned",
        },
        "binance_fail_fallback": "okx",
    },
}


# DeFiLlama is intentionally absent from the per-symbol matrix above: it is a
# market-wide stablecoin-yield sentiment gauge (get_stablecoin_aprs), not a
# per-crypto-asset data source. Verified LIVE and reachable 2026-07-13
# (GET https://yields.llama.fi/pools -> HTTP 200, 15,410 pools). Applies
# uniformly to all six symbols as B1 risk-sentiment context, not a coverage
# cell.
DEFILLAMA_STATUS = {
    "status": "LIVE",
    "scope": "market-wide, not symbol-specific",
    "verified": "2026-07-13: /pools HTTP 200, 15410 pools",
}

# Hyperliquid public API (api.hyperliquid.xyz/info, POST {"type": "meta"}) was
# live-tested as the A-1 conditional sanction candidate. NOT sanctioned as a
# new vendor: Coinalyze already covers all six symbols (see per-symbol cells
# above), so the brief's trigger condition ("if Coinalyze lacks
# Hyperliquid-native pairs") was not met. Recorded here as a verified,
# ready-to-activate backup if Coinalyze's thin HYPE/FARTCOIN aggregation
# (only 1 discovered symbol vs 2-3 for majors) ever proves unreliable.
HYPERLIQUID_BACKUP_CANDIDATE = {
    "status": "LIVE_VERIFIED_NOT_SANCTIONED",
    "verified": "2026-07-13: POST /info {type: meta} HTTP 200, 232-asset universe, all 6 target symbols present (BTC, ETH, SOL, HYPE, ZEC, FARTCOIN)",
    "auth": "none (public, keyless)",
    "sanctioned": False,
    "reason_not_sanctioned": "Coinalyze already covers all 6 symbols; no gap to fill",
}


def get_symbol_entry(symbol: str) -> Optional[dict]:
    """Return the matrix entry for `symbol` (case-insensitive), or None if untracked."""
    return CRYPTO_SYMBOL_MATRIX.get((symbol or "").upper())


def get_tier(symbol: str) -> Optional[int]:
    """Return the symbol's tier (1/2/3), or None if not in the tracked universe."""
    return SYMBOL_TIER.get((symbol or "").upper())


def is_tracked(symbol: str) -> bool:
    return (symbol or "").upper() in CRYPTO_SYMBOL_MATRIX
