"""DEF-FEED-TRIAGE D4 -- Discord 429-aware retry + inter-post spacing +
deferred seen-marking (scripts/signal_notifier.py).

Root cause (2026-07-20): the notifier's post functions treated a Discord
429 identically to any other failure -- one attempt, then the alert was
dropped PERMANENTLY, because seen_ids was marked BEFORE the post attempt
regardless of outcome. Evidence: /var/log/signal_notifier.log 07-20T14:00:02Z
run, 10 signals fetched, 7 posted, 3 (AMD/LYFT/TFC) hit HTTP 429 and were
lost for good.

Fix: a shared _post_discord_with_retry() honoring Discord's retry_after
(bounded to DISCORD_POST_MAX_ATTEMPTS within one run), inter-post spacing
via time.sleep(DISCORD_POST_SPACING_SECONDS) in main()'s loop, and deferred
seen-marking -- a signal is only marked seen on success or a genuinely
terminal skip (non-trade route, aged out), never on a failed post, so a
failure is retried on the NEXT run bounded by the existing
is_signal_too_old()/SIGNAL_MAX_AGE_MIN cutoff rather than lost outright.

signal_notifier.py lives outside backend/ (a standalone VPS script), so
this test file imports it via sys.path insert, matching
test_s4_phase2_notifier_embed.py's established pattern. No live HTTP or
sleep calls -- http_json and time.sleep are mocked throughout.
"""

import io
import json
import sys
import os
import urllib.error
from unittest.mock import patch, MagicMock, call

_ARGV_PATCH = patch.object(sys, "argv", ["signal_notifier.py"])

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
sys.path.insert(0, os.path.abspath(SCRIPTS_DIR))

import signal_notifier as sn  # noqa: E402


def _http_error(code, retry_after_body=None, retry_after_header=None, reason="error"):
    hdrs = {}
    if retry_after_header is not None:
        hdrs["Retry-After"] = str(retry_after_header)
    body = b""
    if retry_after_body is not None:
        body = json.dumps({"retry_after": retry_after_body}).encode("utf-8")
    fp = io.BytesIO(body)
    return urllib.error.HTTPError(
        url="https://discord.com/api/v10/channels/x/messages",
        code=code,
        msg=reason,
        hdrs=hdrs,
        fp=fp,
    )


# ---------------------------------------------------------------------------
# _extract_retry_after
# ---------------------------------------------------------------------------

def test_extract_retry_after_prefers_json_body():
    err = _http_error(429, retry_after_body=2.5, retry_after_header=9)
    assert sn._extract_retry_after(err) == 2.5


def test_extract_retry_after_falls_back_to_header():
    err = _http_error(429, retry_after_header=4)
    assert sn._extract_retry_after(err) == 4.0


def test_extract_retry_after_default_when_neither_present():
    err = _http_error(429)
    assert sn._extract_retry_after(err) == 1.0


# ---------------------------------------------------------------------------
# _post_discord_with_retry
# ---------------------------------------------------------------------------

def test_post_with_retry_success_first_attempt():
    with patch.object(sn, "http_json", return_value={"id": "1"}) as mock_http, \
         patch.object(sn.time, "sleep") as mock_sleep:
        result = sn._post_discord_with_retry("url", {}, {}, label="AMD")
    assert result == {"id": "1"}
    assert mock_http.call_count == 1
    mock_sleep.assert_not_called()


def test_post_with_retry_429_then_success():
    err = _http_error(429, retry_after_body=0.05)
    with patch.object(sn, "http_json", side_effect=[err, {"id": "2"}]) as mock_http, \
         patch.object(sn.time, "sleep") as mock_sleep:
        result = sn._post_discord_with_retry("url", {}, {}, label="LYFT")
    assert result == {"id": "2"}
    assert mock_http.call_count == 2
    mock_sleep.assert_called_once_with(0.55)  # retry_after (0.05) + 0.5s buffer


def test_post_with_retry_429_exhausts_all_attempts_returns_none():
    err = _http_error(429, retry_after_body=0.01)
    with patch.object(sn, "http_json", side_effect=[err, err, err]) as mock_http, \
         patch.object(sn.time, "sleep"):
        result = sn._post_discord_with_retry("url", {}, {}, label="TFC", max_attempts=3)
    assert result is None
    assert mock_http.call_count == 3  # bounded, not infinite


def test_post_with_retry_non_429_http_error_no_retry():
    err = _http_error(403, reason="Forbidden")
    with patch.object(sn, "http_json", side_effect=err) as mock_http, \
         patch.object(sn.time, "sleep") as mock_sleep:
        result = sn._post_discord_with_retry("url", {}, {}, label="XYZ")
    assert result is None
    assert mock_http.call_count == 1  # non-429 is not retryable
    mock_sleep.assert_not_called()


def test_post_with_retry_generic_exception_no_retry():
    with patch.object(sn, "http_json", side_effect=RuntimeError("network down")) as mock_http, \
         patch.object(sn.time, "sleep") as mock_sleep:
        result = sn._post_discord_with_retry("url", {}, {}, label="XYZ")
    assert result is None
    assert mock_http.call_count == 1
    mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# post_signal_alert / post_crypto_signal_alert route through the shared helper
# ---------------------------------------------------------------------------

_EQUITY_SIGNAL = {
    "ticker": "AMD",
    "direction": "LONG",
    "score": 80,
    "strategy": "BREAKOUT",
    "entry_price": 150.0,
    "stop_loss": 148.0,
    "target_1": 155.0,
}


def test_post_signal_alert_uses_retry_helper_with_ticker_label():
    with patch.object(sn, "_post_discord_with_retry", return_value={"id": "9"}) as mock_retry:
        result = sn.post_signal_alert("tok", "chan", _EQUITY_SIGNAL, "sig-1")
    assert result == {"id": "9"}
    assert mock_retry.call_count == 1
    args, kwargs = mock_retry.call_args
    label = kwargs.get("label") if "label" in kwargs else args[3]
    assert label == "AMD"


def test_post_crypto_signal_alert_uses_retry_helper_with_crypto_label():
    signal = {"ticker": "BTC", "direction": "LONG", "score": 75, "strategy": "CVD"}
    with patch.object(sn, "_post_discord_with_retry", return_value={"id": "10"}) as mock_retry:
        result = sn.post_crypto_signal_alert("tok", "chan", signal, "sig-2")
    assert result == {"id": "10"}
    args, kwargs = mock_retry.call_args
    label = kwargs.get("label") if "label" in kwargs else args[3]
    assert label == "BTC (crypto)"


# ---------------------------------------------------------------------------
# main() loop -- deferred seen-marking + inter-post spacing
# ---------------------------------------------------------------------------

def _base_main_mocks(signals, post_side_effect):
    """Patch every I/O boundary main() touches; return the patch context list
    plus a mutable capture dict for save_seen_ids' argument."""
    captured = {}

    def _capture_save_seen_ids(seen_ids):
        captured["seen_ids"] = list(seen_ids)

    patches = [
        patch.object(sn, "load_openclaw_config", return_value={}),
        patch.object(sn, "load_env_file", return_value={}),
        patch.object(sn, "pick_env", side_effect=lambda name, cfg, env_file: "fake-key" if name == "PIVOT_API_KEY" else ""),
        patch.object(sn, "load_discord_token", return_value="tok"),
        patch.object(sn, "fetch_signals", return_value=signals),
        patch.object(sn, "load_seen_ids", return_value=[]),
        patch.object(sn, "save_seen_ids", side_effect=_capture_save_seen_ids),
        patch.object(sn, "is_signal_crypto", return_value=False),
        patch.object(sn, "classify_signal", return_value="trade"),
        patch.object(sn, "is_signal_too_old", return_value=False),
        patch.object(sn, "post_signal_alert", side_effect=post_side_effect),
        patch.object(sn, "save_pending_signal"),
        patch.object(sn.time, "sleep"),
    ]
    return patches, captured


def test_main_marks_seen_on_successful_post():
    signals = [{"signal_id": "s1", "ticker": "AMD"}]
    patches, captured = _base_main_mocks(signals, post_side_effect=[{"id": "ok"}])
    with _ARGV_PATCH, patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
         patches[6], patches[7], patches[8], patches[9], patches[10], patches[11], patches[12]:
        rc = sn.main()
    assert rc == 0
    assert captured["seen_ids"] == ["s1"]


def test_main_does_not_mark_seen_on_failed_post():
    """The core D4 regression: a signal whose post attempt returns None
    (retries exhausted) must NOT be added to seen_ids -- it should be
    retried by the next run, not lost."""
    signals = [{"signal_id": "s2", "ticker": "LYFT"}]
    patches, captured = _base_main_mocks(signals, post_side_effect=[None])
    with _ARGV_PATCH, patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
         patches[6], patches[7], patches[8], patches[9], patches[10], patches[11], patches[12]:
        rc = sn.main()
    assert rc == 0
    assert captured["seen_ids"] == []


def test_main_mixed_batch_only_marks_seen_for_successes():
    signals = [
        {"signal_id": "ok-1", "ticker": "AMD"},
        {"signal_id": "fail-1", "ticker": "LYFT"},
        {"signal_id": "ok-2", "ticker": "TFC"},
    ]
    patches, captured = _base_main_mocks(signals, post_side_effect=[{"id": "1"}, None, {"id": "2"}])
    with _ARGV_PATCH, patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
         patches[6], patches[7], patches[8], patches[9], patches[10], patches[11], patches[12]:
        rc = sn.main()
    assert rc == 0
    assert set(captured["seen_ids"]) == {"ok-1", "ok-2"}
    assert "fail-1" not in captured["seen_ids"]


def test_main_marks_seen_for_non_trade_route_without_posting():
    signals = [{"signal_id": "s3", "ticker": "SPY"}]
    patches, captured = _base_main_mocks(signals, post_side_effect=[{"id": "unused"}])
    with _ARGV_PATCH, patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
         patches[6], patches[7], patches[8], patches[10], patches[11], patches[12], \
         patch.object(sn, "classify_signal", return_value="watch"):
        rc = sn.main()
    assert rc == 0
    assert captured["seen_ids"] == ["s3"]  # terminal skip -- marked seen, never posted


def test_main_marks_seen_for_aged_out_signal_without_posting():
    signals = [{"signal_id": "s4", "ticker": "SPY"}]
    patches, captured = _base_main_mocks(signals, post_side_effect=[{"id": "unused"}])
    with _ARGV_PATCH, patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
         patches[6], patches[7], patches[9], patches[10], patches[11], patches[12], \
         patch.object(sn, "is_signal_too_old", return_value=True):
        rc = sn.main()
    assert rc == 0
    assert captured["seen_ids"] == ["s4"]


def test_main_sleeps_between_posts_for_inter_post_spacing():
    signals = [
        {"signal_id": "a", "ticker": "AMD"},
        {"signal_id": "b", "ticker": "LYFT"},
    ]
    patches, captured = _base_main_mocks(signals, post_side_effect=[{"id": "1"}, {"id": "2"}])
    with _ARGV_PATCH, patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
         patches[6], patches[7], patches[8], patches[9], patches[10], patches[11] as mock_save_pending, \
         patch.object(sn.time, "sleep") as mock_sleep:
        rc = sn.main()
    assert rc == 0
    assert mock_sleep.call_count == 2
    mock_sleep.assert_called_with(sn.DISCORD_POST_SPACING_SECONDS)
