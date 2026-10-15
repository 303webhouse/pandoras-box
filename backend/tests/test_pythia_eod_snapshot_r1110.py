"""R-IV.1110(b) — PYTHIA v2.7's `eod_snapshot` is accepted as a LEVELS ROW and nothing else.

NO CODE CHANGE WAS NEEDED. The handler already accepts it, and this file exists to PIN that,
because "it happens to work" and "it is guaranteed to work" are different claims and TRITON-R's
PYTHIA-LOC filter now depends on the second. Verified against
`pythia-v2.7.pine` sha256 87c79bae7ad7fe5e97844b0129c571ffef8d65b34af6d957bdba83596349bc66.

WHY IT IS ACCEPTED, each gate checked rather than assumed:

  event allowlist     NONE -- `payload.get("alert_type") or payload.get("event") or ...`
                      takes the string verbatim, so a new event name needs no registration
  ticker              present
  vah / val / poc     carried in the Pine `comFields`, and the EOD alert is guarded by
                      `not na(pocPrice)` so a session with no profile sends nothing
  bar_time ±10 min    the Pine sends `timenow` -- the alert's FIRE time, not the bar's open.
                      This was the real risk: TradingView's `time` IS the bar open, so a
                      15-minute chart's final RTH bar would have been ~15 min stale and
                      REJECTED by the replay window. It sends `timenow`, so it is not.
  script              "v2.7" -> stored in `script_version`

AND THE DOWNSTREAM CLAIM, which is the half that matters most: the handler INSERTs the row,
refreshes the Redis levels cache, and returns. It calls nothing that creates a signal, a River
item, a notification or a trade idea.
"""
from __future__ import annotations

import ast
import hashlib
import io
import os

import pytest

from tests._srcscan import code_of, function_code

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANDLER = os.path.join(BACKEND, "webhooks", "pythia_events.py")
PINE = r"C:\temp\cc-query-handoff\lab\pythia\pythia-v2.7.pine"
PINE_SHA = "87c79bae7ad7fe5e97844b0129c571ffef8d65b34af6d957bdba83596349bc66"

#: Everything the handler does after a payload validates. Anything NOT in this list appearing
#: in the handler is a new downstream effect and must be ruled on, not absorbed.
ALLOWED_EFFECTS = ("INSERT INTO pythia_events", "redis", "ALTER TABLE pythia_events")

#: The names that would mean a signal, a River item, a notification or a trade idea.
FORBIDDEN_DOWNSTREAM = (
    "process_signal_unified",   # the signal pipeline
    "trade_idea", "trade_ideas",
    "river",
    "ntfy", "push_session_alert", "send_discord", "discord_webhook",
    "circuit_breaker",
)


def _handler_code() -> str:
    return function_code(HANDLER, "pythia_webhook")


# ── 1. the event name needs no registration ─────────────────────────────────

def test_there_is_no_event_allowlist():
    """A new event name must not require a code change. If an allowlist is ever added, this
    fails and whoever adds it has to decide about `eod_snapshot` deliberately."""
    code = _handler_code()
    assert 'payload.get(\'event\')' in code or 'payload.get("event")' in code
    # no membership test against a fixed set of event names
    for bad in ("ALLOWED_EVENTS", "VALID_EVENTS", "EVENT_ALLOWLIST"):
        assert bad not in code, bad


def test_an_unknown_event_name_still_reaches_the_insert():
    """The fallback is the string `"unknown"`, not a rejection -- so an unrecognised event is
    STORED, which is why eod_snapshot needs nothing."""
    code = _handler_code()
    assert "'unknown'" in code or '"unknown"' in code


# ── 2. the gates eod_snapshot must pass ─────────────────────────────────────

def test_the_levels_gate_rejects_zero_not_just_null():
    """`nz(valPrice, 0)` in the Pine means a missing level arrives as 0. The handler must
    refuse that rather than store a confident zero -- and that is the ONE path by which a
    genuine eod_snapshot could still be rejected, so it is named here rather than discovered."""
    code = _handler_code()
    assert "_pos_num(vah)" in code and "_pos_num(val)" in code and "_pos_num(poc)" in code


def test_the_replay_window_is_on_FIRE_time_and_the_pine_sends_fire_time():
    """THE RISK THAT WOULD HAVE BITTEN. TradingView's `time` is the bar's OPEN, so on any
    timeframe coarser than the ±10 min window the final RTH bar would be stale on arrival and
    rejected. v2.7 sends `timenow` instead."""
    src = io.open(HANDLER, encoding="utf-8").read()
    assert "REPLAY_WINDOW_MS = 10 * 60 * 1000" in src
    pine = io.open(PINE, encoding="utf-8", errors="replace").read()
    assert '"bar_time":"\' + str.tostring(timenow)' in pine.replace("\r\n", "\n"), (
        "the Pine must send timenow, not the bar open")


def test_the_pine_source_is_the_hashed_one():
    """A property proved against a different file is not proved."""
    if not os.path.exists(PINE):
        pytest.skip("the v2.7 Pine is not on this machine")
    assert hashlib.sha256(io.open(PINE, "rb").read()).hexdigest() == PINE_SHA


def test_the_eod_alert_is_guarded_by_a_real_profile():
    """`not na(pocPrice)` -- a session with no profile sends nothing at all, which is better
    than sending zeros the hub would reject."""
    pine = io.open(PINE, encoding="utf-8", errors="replace").read()
    assert "not na(pocPrice)" in pine
    assert "eod_snapshot" in pine


def test_it_fires_once_per_session():
    """`currentDate != eodSentDay` -- one snapshot per session, so the levels row is not
    rewritten on every subsequent bar."""
    pine = io.open(PINE, encoding="utf-8", errors="replace").read()
    assert "eodSentDay" in pine


# ── 3. THE DOWNSTREAM CLAIM: a levels row and nothing else ──────────────────

@pytest.mark.parametrize("name", FORBIDDEN_DOWNSTREAM)
def test_the_handler_creates_no_signal_river_notification_or_trade_idea(name):
    """R-IV.1110(b) verbatim. Scanned on PARSED code so a comment mentioning any of these
    cannot fail it, and so a real call cannot hide behind one."""
    code = _handler_code()
    assert name not in code, (
        "the PYTHIA handler reaches %r -- an eod_snapshot would then create a downstream "
        "effect, which R-IV.1110(b) forbids" % name)


def test_the_only_writes_are_the_row_and_the_levels_cache():
    """Stated positively as well as negatively: a test that only forbids names passes when a
    NEW kind of side effect is added under a name nobody thought to forbid."""
    code = _handler_code()
    assert "INSERT INTO pythia_events" in code
    assert "redis" in code.lower()
    # no other INSERT/UPDATE/DELETE anywhere in the handler
    import re
    writes = re.findall(r"(INSERT INTO|UPDATE|DELETE FROM)\s+([a-z_]+)", code, re.I)
    tables = {t.lower() for _v, t in writes}
    assert tables <= {"pythia_events", "pythia_webhook_rejections"}, tables


def test_the_redis_cache_is_a_LEVELS_cache_and_is_bounded():
    """The one state change beyond the row. It is levels, not a signal, and it expires -- but
    it IS read by scoring, so it is named here rather than left implicit."""
    code = _handler_code()
    assert "pythia:" in code
    assert "86400" in code, "the levels cache must expire"


# ── 4. first boot: the row's table exists before any writer runs ────────────

def test_pythia_events_is_created_at_startup():
    """R-IV.1052(b). The handler ALTERs `script_version` itself, but a READ of these rows must
    not wait on a writer -- and PYTHIA-LOC reads them tomorrow."""
    from tests.test_first_boot_reads_r1052 import STARTUP_FILES
    import re
    startup = ""
    for f in STARTUP_FILES:
        with open(os.path.join(BACKEND, f), encoding="utf-8-sig") as fh:
            startup += fh.read() + chr(10)
    created = {t.lower() for t in re.findall(
        r"CREATE TABLE IF NOT EXISTS\s+([a-z_][a-z0-9_]*)", startup, re.I)}
    assert "pythia_events" in created


def test_script_version_is_migrated_at_startup_too():
    """The column the eod_snapshot's `v2.7` lands in. Created idempotently by the handler AND
    at startup, so a first boot can read it."""
    import re
    with open(os.path.join(BACKEND, "main.py"), encoding="utf-8-sig") as fh:
        startup = fh.read()
    cols = {c.lower() for c in re.findall(
        r"ADD COLUMN IF NOT EXISTS\s+([a-z_][a-z0-9_]*)", startup, re.I)}
    assert "script_version" in cols


# ── 5. R-IV.1113(b): the Redis overwrite is a NAMED side effect ─────────────

def test_the_redis_overwrite_is_named_in_the_handler():
    """R-IV.1113(b) accepted the overwrite and asked for it to be RECORDED as a named side
    effect. A side effect a reader has to discover is the thing being fixed here: "it is a
    levels row only" was the claim, and a cache write is not a row."""
    src = io.open(HANDLER, encoding="utf-8").read()
    i = src.index("Also cache latest levels in Redis")
    window = src[i:i + 900]
    assert "NAMED SIDE EFFECT" in window
    assert "R-IV.1113(b)" in window
    assert "OVERWRITES" in window and "eod_snapshot" in window


# ── 6. R-IV.1113(c): a zero-level refusal is now DURABLE ───────────────────

def test_the_zero_level_refusal_is_recorded_not_just_logged():
    """THE GAP R-IV.1113(c) EXPOSED. It asked me to NAME any eod_snapshot rejected for a zero
    level. That was unanswerable: the path only logged and raised, and `railway logs` reaches
    only the current deployment. Worse, such a ticker would have read as "no alert arrived" --
    a different fault with a different fix."""
    code = _handler_code()
    assert "_record_validation_refusal" in code, (
        "a zero-level rejection must leave a durable record, or it cannot be reported")


def test_it_is_recorded_as_a_REAL_refusal_not_an_observe_row():
    """It arrived and was turned away, so it SHOULD count toward feed_health -- unlike an
    OBSERVE row, which was allowed through. The discriminator is the `OBSERVE:` prefix."""
    rec = code_of(__import__("webhooks.pythia_events", fromlist=["x"])
                  ._record_validation_refusal)
    assert "OBSERVE" not in rec, "a validation refusal must not carry the OBSERVE prefix"
    assert "INSERT INTO pythia_webhook_rejections" in rec


def test_the_reason_names_the_EVENT_so_the_fix_is_identifiable():
    """`eod_snapshot` failing this check means the Pine sent `nz(VAL/VAH, 0)` and SPINE fixes
    the script. An events-alert failure means something else. A reason that did not say which
    would leave the next reader guessing."""
    code = _handler_code()
    i = code.index("_record_validation_refusal")
    assert "alert_type" in code[i:i + 260]


def test_the_recorder_never_raises():
    """It runs on a request that is ALREADY being refused; losing the record must not change
    the status the caller sees."""
    rec = code_of(__import__("webhooks.pythia_events", fromlist=["x"])
                  ._record_validation_refusal)
    assert "except Exception" in rec


def test_the_zero_level_check_STILL_REJECTS():
    """R-IV.1113(c) verbatim: keep it rejecting. Recording the refusal must not have turned it
    into an acceptance -- a zero level must never be stored as a level."""
    code = _handler_code()
    i = code.index("_record_validation_refusal")
    after = code[i:i + 400]
    assert "HTTPException" in after and "400" in after
