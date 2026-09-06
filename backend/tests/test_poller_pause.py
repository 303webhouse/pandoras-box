"""R-IV.274(a) — the poller pause flags.

These tests import and call the REAL helper. They do not reimplement its rule: a test
that mirrors the gate stays green when the gate is mutated, which is how the MP
freshness test passed against a broken gate (R-IV.231). Mutating `is_paused` must
break these.
"""

import importlib

import pytest

pause = importlib.import_module("jobs.poller_pause")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in pause.PAUSE_FLAGS.values():
        monkeypatch.delenv(var, raising=False)
    for name in pause.PAUSE_FLAGS:
        pause._last_seen[name] = None


@pytest.mark.parametrize("poller", sorted(pause.PAUSE_FLAGS))
def test_unset_runs(poller):
    """FAIL-OPEN: an absent flag must never pause a poller."""
    assert pause.is_paused(poller) is False


@pytest.mark.parametrize("poller", sorted(pause.PAUSE_FLAGS))
def test_empty_string_runs(poller, monkeypatch):
    """Railway returns '' for an unset reference — '' must not pause."""
    monkeypatch.setenv(pause.PAUSE_FLAGS[poller], "")
    assert pause.is_paused(poller) is False


@pytest.mark.parametrize("poller", sorted(pause.PAUSE_FLAGS))
@pytest.mark.parametrize("value", ["true", "TRUE", "True", " true "])
def test_true_pauses(poller, value, monkeypatch):
    monkeypatch.setenv(pause.PAUSE_FLAGS[poller], value)
    assert pause.is_paused(poller) is True


@pytest.mark.parametrize("poller", sorted(pause.PAUSE_FLAGS))
@pytest.mark.parametrize("value", ["false", "1", "yes", "paused", "TRUEISH"])
def test_only_the_word_true_pauses(poller, value, monkeypatch):
    """Anything else runs. A pause must be an act, not an approximation."""
    monkeypatch.setenv(pause.PAUSE_FLAGS[poller], value)
    assert pause.is_paused(poller) is False


def test_flags_are_independent(monkeypatch):
    """Pausing one poller must not pause the other."""
    monkeypatch.setenv(pause.PAUSE_FLAGS["tide"], "true")
    assert pause.is_paused("tide") is True
    assert pause.is_paused("darkpool") is False


def test_check_paused_logs_once_per_transition(monkeypatch, caplog):
    """Transition-logged, not per-cycle: the Railway buffer is 500 lines and a
    5-minute heartbeat would evict the evidence the next diagnosis needs."""
    monkeypatch.setenv(pause.PAUSE_FLAGS["tide"], "true")
    with caplog.at_level("INFO", logger=pause.__name__):
        assert pause.check_paused("tide") is True
        assert pause.check_paused("tide") is True
        assert pause.check_paused("tide") is True
    assert len([r for r in caplog.records if "PAUSED" in r.getMessage()]) == 1

    caplog.clear()
    monkeypatch.delenv(pause.PAUSE_FLAGS["tide"])
    with caplog.at_level("INFO", logger=pause.__name__):
        assert pause.check_paused("tide") is False
    assert len([r for r in caplog.records if "RUNNING" in r.getMessage()]) == 1


def test_pause_status_reports_both_and_any(monkeypatch):
    """/health reads this; it must name every poller, not only the paused ones."""
    monkeypatch.setenv(pause.PAUSE_FLAGS["darkpool"], "true")
    st = pause.pause_status()
    assert set(st["pollers"]) == set(pause.PAUSE_FLAGS)
    assert st["pollers"]["darkpool"] is True
    assert st["pollers"]["tide"] is False
    assert st["any_paused"] is True


def test_pause_status_any_false_when_all_running():
    st = pause.pause_status()
    assert st["any_paused"] is False
    assert all(v is False for v in st["pollers"].values())
