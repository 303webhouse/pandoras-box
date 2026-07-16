"""S-3 Phase 1 — canonical ticker normalization tests (§3.5).

Done-4 coverage:
- Normalization idempotence: normalize(normalize(x)) == normalize(x)
- Three-source canonical equality: all three crypto signal sources (Crypto
  Scanner "BTC-USD", crypto_setups "BTCUSDT", TradingView "BTCUSDT.P")
  produce the same canonical base symbol after normalization.
- Cross-source conflict-dismissal proof: `_check_and_clear_conflicting_signals`
  does UPPER(ticker) exact-string matching — once tickers are canonical, the
  same coin across engines produces an identical key, enabling dismissal.

No live DB calls; all tests are pure-function or constructed-dict.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from jobs.crypto_bars import normalize_crypto_ticker


# ── 1. Idempotence ─────────────────────────────────────────────────────────

def test_idempotent_all_six_symbols():
    """normalize(normalize(x)) == normalize(x) for all tracked base symbols."""
    for sym in ("BTC", "ETH", "SOL", "HYPE", "ZEC", "FARTCOIN"):
        first = normalize_crypto_ticker(sym)
        second = normalize_crypto_ticker(first)
        assert first is not None, f"{sym}: first pass returned None"
        assert first == second, f"{sym}: not idempotent ({first!r} → {second!r})"


def test_idempotent_various_raw_forms():
    pairs = [
        ("BTCUSDT", "BTC"),
        ("ETHUSD", "ETH"),
        ("SOL-USD", "SOL"),
        ("HYPEUSDT", "HYPE"),
        ("ZECUSD", "ZEC"),
        ("FARTCOINUSDT", "FARTCOIN"),
        ("BTC.P", "BTC"),
        ("BTCUSDT.P", "BTC"),
    ]
    for raw, expected in pairs:
        canon = normalize_crypto_ticker(raw)
        assert canon == expected, f"{raw!r}: expected {expected!r}, got {canon!r}"
        # idempotent
        assert normalize_crypto_ticker(canon) == expected


def test_unknown_tickers_return_none():
    for raw in ("AAPL", "SPY", "MATIC-USD", "UNI-USD", "APT-USD", "", None, "???"):
        result = normalize_crypto_ticker(raw)
        assert result is None, f"{raw!r}: expected None, got {result!r}"


# ── 2. Three-source canonical equality ─────────────────────────────────────

def test_three_sources_btc_canonical_equality():
    """BTC-USD (Crypto Scanner), BTCUSDT (crypto_setups), BTCUSD.P (TV) → BTC."""
    crypto_scanner_ticker = "BTC-USD"      # bias_scheduler.py CRYPTO_TICKERS format
    crypto_setups_ticker  = "BTCUSDT"      # Binance-native from crypto_setups.py
    tradingview_ticker    = "BTCUSD.P"     # TradingView .P suffix variant

    results = [
        normalize_crypto_ticker(crypto_scanner_ticker),
        normalize_crypto_ticker(crypto_setups_ticker),
        normalize_crypto_ticker(tradingview_ticker),
    ]
    assert all(r == "BTC" for r in results), (
        f"Not all three sources canonicalized to BTC: {results}"
    )


def test_three_sources_eth_canonical_equality():
    crypto_scanner_ticker = "ETH-USD"
    crypto_setups_ticker  = "ETHUSDT"
    tradingview_ticker    = "ETHUSD"

    results = [
        normalize_crypto_ticker(crypto_scanner_ticker),
        normalize_crypto_ticker(crypto_setups_ticker),
        normalize_crypto_ticker(tradingview_ticker),
    ]
    assert all(r == "ETH" for r in results), (
        f"Not all three sources canonicalized to ETH: {results}"
    )


def test_three_sources_sol_canonical_equality():
    results = [
        normalize_crypto_ticker("SOL-USD"),
        normalize_crypto_ticker("SOLUSDT"),
        normalize_crypto_ticker("SOLUSD"),
    ]
    assert all(r == "SOL" for r in results), (
        f"Not all three sources canonicalized to SOL: {results}"
    )


# ── 3. Cross-source conflict-dismissal proof ────────────────────────────────

def _conflict_key(ticker: str) -> str:
    """Mirrors `_check_and_clear_conflicting_signals` exact-match logic:
    WHERE UPPER(ticker) = $1  with  ticker = signal_data['ticker'].upper()"""
    return (ticker or "").upper()


def test_conflict_dismissal_key_equality_after_normalization():
    """The conflict-check SQL key is identical for the same coin from all three
    sources once tickers are normalized at ingress."""
    sources = {
        "crypto_scanner": "BTC-USD",
        "crypto_setups":  "BTCUSDT",
        "tradingview":    "BTCUSD.P",
    }
    canonical_keys = {
        name: _conflict_key(normalize_crypto_ticker(raw) or raw)
        for name, raw in sources.items()
    }
    keys = list(canonical_keys.values())
    assert len(set(keys)) == 1, (
        f"Sources produce different conflict keys (no cross-source dismissal possible): "
        f"{canonical_keys}"
    )
    assert keys[0] == "BTC", f"Expected conflict key 'BTC', got {keys[0]!r}"


def test_conflict_key_mismatch_without_normalization():
    """Without normalization the three raw formats produce DIFFERENT keys,
    proving the normalization fix is load-bearing (not a no-op)."""
    raw_sources = {
        "crypto_scanner": "BTC-USD",
        "crypto_setups":  "BTCUSDT",
        "tradingview":    "BTCUSD.P",
    }
    raw_keys = {name: _conflict_key(raw) for name, raw in raw_sources.items()}
    assert len(set(raw_keys.values())) > 1, (
        "Test invalid: raw tickers already produce the same key (normalization not needed?)"
    )


# ── 4. Pruned delisting tickers no longer normalize ────────────────────────

def test_delisted_tickers_return_none():
    """MATIC-USD, UNI-USD, APT-USD — not in the tracked six-symbol universe;
    normalize_crypto_ticker returns None (not a fake resolution)."""
    for raw in ("MATIC-USD", "MATICUSD", "UNI-USD", "UNIUSD", "APT-USD", "APTUSD"):
        result = normalize_crypto_ticker(raw)
        assert result is None, (
            f"{raw!r}: expected None (delisted/out-of-scope), got {result!r}"
        )
