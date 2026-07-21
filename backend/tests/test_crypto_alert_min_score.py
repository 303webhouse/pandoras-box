"""CRYPTO_ALERT_MIN_SCORE -- ratified crypto alert floor (2026-07-21, Nick+Fable).

Semantics under test, stated explicitly because the < vs <= distinction was
an explicit ratification requirement:

    effective score = COALESCE(score_v2, score)
    score <  CRYPTO_ALERT_MIN_SCORE  -> SUPPRESSED (no Discord alert)
    score == CRYPTO_ALERT_MIN_SCORE  -> ALERTED    (boundary is inclusive-to-alert)
    score >  CRYPTO_ALERT_MIN_SCORE  -> ALERTED

The gate is keyed on the signal being crypto (not on --crypto mode), and a
suppressed signal is marked seen (terminal), matching the non-trade/aged-out
skips -- the alert decision is made once when the signal first appears.

signal_notifier.py lives outside backend/, so it's imported via sys.path
insert, matching the sibling notifier test files. No live HTTP/Discord.
"""

import os
import sys
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
sys.path.insert(0, os.path.abspath(SCRIPTS_DIR))

import signal_notifier as sn  # noqa: E402

def _run_main(signals, is_crypto=True):
    """Drive main() with every I/O boundary mocked; return captured posts/seen.

    argv matches the real cron for the class under test: the crypto notifier
    runs with --crypto (*/5 24/7), the equity one without (*/15 RTH). Without
    this, crypto signals are dropped as `skipped_wrong_class` before ever
    reaching the alert floor -- which would make the suppression assertions
    pass for entirely the wrong reason.
    """
    argv = ["signal_notifier.py", "--crypto"] if is_crypto else ["signal_notifier.py"]
    _ARGV = patch.object(sys, "argv", argv)
    captured = {"seen": None, "posted": []}

    def _capture_save_seen_ids(seen_ids):
        captured["seen"] = list(seen_ids)

    def _fake_post_crypto(token, channel_id, signal, signal_id, api_url=""):
        captured["posted"].append(signal_id)
        return {"id": "ok"}

    def _fake_post_equity(token, channel_id, signal, signal_id):
        captured["posted"].append(signal_id)
        return {"id": "ok"}

    with _ARGV, \
         patch.object(sn, "load_openclaw_config", return_value={}), \
         patch.object(sn, "load_env_file", return_value={}), \
         patch.object(sn, "pick_env", side_effect=lambda n, c, e: "k" if n == "PIVOT_API_KEY" else ""), \
         patch.object(sn, "load_discord_token", return_value="tok"), \
         patch.object(sn, "fetch_signals", return_value=signals), \
         patch.object(sn, "load_seen_ids", return_value=[]), \
         patch.object(sn, "save_seen_ids", side_effect=_capture_save_seen_ids), \
         patch.object(sn, "is_signal_crypto", return_value=is_crypto), \
         patch.object(sn, "classify_signal", return_value="trade"), \
         patch.object(sn, "is_signal_too_old", return_value=False), \
         patch.object(sn, "post_crypto_signal_alert", side_effect=_fake_post_crypto), \
         patch.object(sn, "post_signal_alert", side_effect=_fake_post_equity), \
         patch.object(sn, "save_pending_signal"), \
         patch.object(sn.time, "sleep"):
        rc = sn.main()
    assert rc == 0
    return captured


def _sig(sid, score=None, score_v2=None):
    s = {"signal_id": sid, "ticker": "BTC", "direction": "LONG"}
    if score is not None:
        s["score"] = score
    if score_v2 is not None:
        s["score_v2"] = score_v2
    return s


# ---------------------------------------------------------------------------
# The ratified value + comparison semantics
# ---------------------------------------------------------------------------

def test_floor_value_is_ratified_28():
    assert sn.CRYPTO_ALERT_MIN_SCORE == 28


def test_score_below_floor_is_suppressed():
    cap = _run_main([_sig("low", score=27)])
    assert cap["posted"] == []
    assert "low" in cap["seen"]          # terminal -> marked seen


def test_score_exactly_at_floor_is_alerted():
    """The explicit < vs <= ruling: 28 is NOT suppressed."""
    cap = _run_main([_sig("boundary", score=28)])
    assert cap["posted"] == ["boundary"]


def test_score_above_floor_is_alerted():
    cap = _run_main([_sig("high", score=38)])
    assert cap["posted"] == ["high"]


def test_just_below_boundary_suppressed():
    cap = _run_main([_sig("just-under", score=27.9)])
    assert cap["posted"] == []


# ---------------------------------------------------------------------------
# Effective-score field selection (COALESCE(score_v2, score))
# ---------------------------------------------------------------------------

def test_score_v2_takes_precedence_over_score():
    # score would pass, score_v2 fails -> suppressed (v2 wins, same as the embed)
    cap = _run_main([_sig("v2-low", score=40, score_v2=11)])
    assert cap["posted"] == []


def test_falls_back_to_score_when_v2_absent():
    cap = _run_main([_sig("v1-only", score=33)])
    assert cap["posted"] == ["v1-only"]


def test_missing_score_treated_as_zero_and_suppressed():
    cap = _run_main([_sig("no-score")])
    assert cap["posted"] == []


def test_unparseable_score_is_not_silently_suppressed():
    """A malformed score must not be silently swallowed by the noise filter."""
    cap = _run_main([_sig("weird", score="not-a-number")])
    assert cap["posted"] == ["weird"]


# ---------------------------------------------------------------------------
# Scope: crypto-only, and the reported counter
# ---------------------------------------------------------------------------

def test_equity_signals_are_not_gated_by_the_crypto_floor():
    """A low-scoring EQUITY signal must still alert -- this floor is crypto-only."""
    cap = _run_main([_sig("equity-low", score=5)], is_crypto=False)
    assert cap["posted"] == ["equity-low"]


def test_mixed_batch_only_suppresses_below_floor():
    cap = _run_main([
        _sig("a", score=11),   # suppressed
        _sig("b", score=28),   # alerted (boundary)
        _sig("c", score=35),   # alerted
        _sig("d", score=18),   # suppressed
    ])
    assert cap["posted"] == ["b", "c"]
    assert set(cap["seen"]) == {"a", "b", "c", "d"}   # all terminal either way


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS: {t.__name__}")
    print(f"\nAll {len(tests)} CRYPTO_ALERT_MIN_SCORE tests passed.")
