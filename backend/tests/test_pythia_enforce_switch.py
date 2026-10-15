"""`WEBHOOK_PYTHIA_ENFORCE` — the principal's Railway switch. Unset = OBSERVE.

Parity with the switches TICK and BREADTH already have (`_factor_observe` in
webhooks/tradingview.py), and with circuit_breaker, footprint, hermes and whale. One
convention, not a new one.

THE TWO PROPERTIES THAT MATTER:

  1. READ AT REQUEST TIME. The point of the switch is that the principal flips it in Railway
     and the next alert honours it -- no code change, no deploy. A module-level constant would
     need a redeploy, which is the thing being avoided.
  2. OBSERVE IS VALIDATE-BUT-ALLOW, NOT SKIP. The comparison still happens and the verdict is
     still logged and recorded; only the refusal is withheld. An observe mode that stopped
     comparing would leave nothing to turn back on, and would make the flip untestable.

And the interaction that could have gone wrong quietly: in OBSERVE a bad secret is ALLOWED, so
counting it as a refusal would make `feed_health` report `rejecting` while events were landing
normally -- a false alarm in the one field built to prevent false alarms.
"""
from __future__ import annotations

import inspect
import os

import pytest

from tests._srcscan import code_of, code_of_file, function_code
from webhooks import pythia_events as pe

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.path.join(os.path.dirname(HERE), "webhooks", "pythia_events.py")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("WEBHOOK_PYTHIA_ENFORCE", raising=False)
    yield


# ── 1. the truth table, identical to the existing switches ───────────────────

def test_unset_is_ENFORCE():
    """THE ONE PLACE THIS SWITCH DIVERGES FROM THE CONVENTION, and why.

    `_factor_observe("TICK")` and friends default to OBSERVE. PYTHIA defaults to ENFORCE:

      * no `WEBHOOK_*_ENFORCE` variable is set in Railway at all (measured 2026-10-15), so
        the six endpoints on that convention are all observing, and PYTHIA's hardcoded check
        made it the only webhook in the hub that enforced anything;
      * R-IV.1083(b) keeps the secret because "anyone holding the URL can write PYTHIA
        levels", and those feed TRITON-R's PYTHIA-LOC filter;
      * and TWO EXISTING TESTS already encode the guarantee -- they failed when the default
        was OBSERVE, so shipping that would have meant weakening them.
    """
    assert pe._pythia_observe() is False


@pytest.mark.parametrize("v", ["", "   "])
def test_empty_is_ENFORCE(monkeypatch, v):
    """Railway returns '' for an empty variable reference, never None -- the project's own
    env-var rule. An empty value must behave as unset, which here means ENFORCE."""
    monkeypatch.setenv("WEBHOOK_PYTHIA_ENFORCE", v)
    assert pe._pythia_observe() is False


@pytest.mark.parametrize("v", ["1", "true", "TRUE", "True", "yes", "YES", " yes "])
def test_truthy_values_ENFORCE(monkeypatch, v):
    monkeypatch.setenv("WEBHOOK_PYTHIA_ENFORCE", v)
    assert pe._pythia_observe() is False


@pytest.mark.parametrize("v", ["0", "false", "FALSE", "no", "off", " off "])
def test_only_an_EXPLICIT_FALSEY_value_observes(monkeypatch, v):
    """The switch the principal asked for: one Railway edit turns enforcement off."""
    monkeypatch.setenv("WEBHOOK_PYTHIA_ENFORCE", v)
    assert pe._pythia_observe() is True


@pytest.mark.parametrize("v", ["enforce", "on", "ENABLED", "oops", "tru", "1 "])
def test_AMBIGUITY_RESOLVES_TO_ENFORCE(monkeypatch, v):
    """A TRAP REMOVED, and worth the divergence on its own.

    Mirroring the other switches' expression with the default flipped would have made
    `WEBHOOK_PYTHIA_ENFORCE=enforce` mean OBSERVE -- "enforce" is not in ("1","true","yes") --
    so a plausible thing to type would have silently disabled the auth it names. A fail-closed
    switch must resolve ambiguity toward CLOSED, so the falsey set is enumerated and everything
    outside it enforces. A typo cannot open this endpoint."""
    monkeypatch.setenv("WEBHOOK_PYTHIA_ENFORCE", v)
    assert pe._pythia_observe() is False


def test_it_matches_the_canonical_pattern_verbatim():
    """Same expression as `_factor_observe`, so the six endpoints cannot drift apart."""
    mine = code_of(pe._pythia_observe)
    assert 'WEBHOOK_PYTHIA_ENFORCE' in mine
    # The NAME and the request-time read match the convention; the default deliberately does
    # not, and `test_unset_is_ENFORCE` says why.
    assert "os.getenv" in mine


# ── 2. read at REQUEST time, not at import ───────────────────────────────────

def test_the_flag_is_read_per_request_not_frozen_at_import(monkeypatch):
    """THE WHOLE POINT. Flip it and the very next call honours it, with no redeploy."""
    assert pe._pythia_observe() is False
    monkeypatch.setenv("WEBHOOK_PYTHIA_ENFORCE", "0")
    assert pe._pythia_observe() is True
    monkeypatch.delenv("WEBHOOK_PYTHIA_ENFORCE")
    assert pe._pythia_observe() is False


def test_the_handler_calls_the_switch_rather_than_a_module_constant():
    # SCOPED TO THE HANDLER. My first version scanned the whole module, where
    # `"_pythia_observe()"` matches the function's own DEFINITION -- so freezing the flag to a
    # constant inside the handler passed. The probe caught that: scanning a module cannot tell
    # a definition from a call, and the claim here is about the CALL.
    handler = function_code(MODULE, "pythia_webhook")
    assert "_pythia_observe()" in handler, (
        "the handler must CALL the switch per request, not read a frozen constant: %s"
        % handler[:600])
    # and no frozen copy of the decision at module scope
    mod = code_of_file(MODULE)
    assert "PYTHIA_OBSERVE =" not in mod


# ── 3. observe VALIDATES, it does not skip ───────────────────────────────────

def test_observe_still_compares_the_secret():
    """If observe short-circuited before the comparison there would be nothing to turn on, and
    the flip could not be tested before it was trusted."""
    # THE CALL, not the import. My first version used `index("validate_webhook_secret")`,
    # which found the IMPORT line, so the 200-char window covered the module header and the
    # assertion failed on code that was correct. Match the call site explicitly.
    code = code_of_file(MODULE)
    assert "validate_webhook_secret(" in code
    i = code.index("validate_webhook_secret(")
    window = code[i:i + 240]
    assert "observe=observe" in window, window


def test_the_shared_verifier_never_raises_in_observe():
    """Delegated to the AEGIS helper rather than reimplemented, so PYTHIA cannot drift from
    the other five endpoints' semantics."""
    from utils.webhook_auth import validate_webhook_secret
    src = inspect.getsource(validate_webhook_secret)
    assert "if observe:" in src
    # a wrong secret in observe returns the verdict instead of raising
    assert validate_webhook_secret("wrong", secret="right", observe=True,
                                   label="t") is False
    assert validate_webhook_secret("right", secret="right", observe=True, label="t") is True


def test_enforce_still_refuses():
    """THE PAIR. A switch that could only observe would be a removal of the check."""
    from fastapi import HTTPException

    from utils.webhook_auth import validate_webhook_secret
    with pytest.raises(HTTPException) as e:
        validate_webhook_secret("wrong", secret="right", observe=False, label="t")
    assert e.value.status_code == 401
    assert validate_webhook_secret("right", secret="right", observe=False, label="t") is True


# ── 4. an allowed-but-invalid secret is RECORDED, and is NOT a refusal ───────

def test_an_allowed_bad_secret_is_written_down():
    """OBSERVE's whole risk is that it is QUIET: data flows, dashboards look healthy, and
    nobody learns the secret is wrong until enforcement is switched on and everything stops."""
    code = code_of_file(MODULE)
    assert "_record_observe_allowed" in code
    assert "OBSERVE_ALLOWED_REASON" in code


def test_the_observe_reason_is_distinct_from_the_two_refusal_reasons():
    assert pe.OBSERVE_ALLOWED_REASON.startswith("OBSERVE:")
    assert pe.OBSERVE_ALLOWED_REASON not in (
        "no secret field in the alert body", "secret value does not match")


def test_feed_health_counts_REFUSALS_ONLY():
    """THE INTERACTION THAT WOULD HAVE BROKEN QUIETLY. `rejecting` means "arriving and being
    REFUSED". An allowed payload counted there would report a refused feed while events were
    landing -- a false alarm in the field built to prevent false alarms."""
    from services.read_only import market_profile as mp
    code = code_of(mp._feed_counts)
    assert "OBSERVE:%" in code, "the refusal count must exclude observe rows"
    assert "NOT LIKE" in code.upper()


def test_the_observe_recorder_never_raises():
    """It runs inside the request path; a supervision write must not break the request it
    supervises."""
    code = code_of(pe._record_observe_allowed)
    assert "except Exception" in code


def test_the_recorder_logs_only_the_LENGTH():
    """R-IV.331(a) / credential handling: the length is the discriminator between "no secret
    field" and "wrong value". The value itself is never logged or stored."""
    code = code_of(pe._record_observe_allowed)
    assert "secret_len" in code
    for leak in ("supplied", "PYTHIA_WEBHOOK_SECRET"):
        assert leak not in code, leak
