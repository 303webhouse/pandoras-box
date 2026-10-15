"""R-IV.1089(c) — footprint's SLO is 96h, chosen from its measured arrival distribution.

MEASURED 2026-10-15 over 60 days, 211 signals:

    median gap 0.75h | p75 3.25h | p90 19.0h | p95 23.5h | max 91.0h
    gaps breaching  6h: 40 of 210  (19.0%)   <- the old bound
    gaps breaching 24h: 10
    gaps breaching 72h:  1   (0.5%)
    gaps breaching 96h:  0   (0.0%)           <- the new bound

`footprint` is an INBOUND WEBHOOK, not a job: it fires only when a footprint condition
triggers, 2-10 times a day, in tight clusters with long quiet stretches between them. Judged
against 6 hours it breached on nearly one gap in five -- a false-flatline generator, and the
identical shape this module already records for `crypto_scanner`.

WHAT 96h DOES NOT BUY, stated so no later reader mistakes it for a liveness guarantee: the
crypto producers were fixed by judging whether the JOB RAN (`AGE_SOURCE_JOB_RUNS`), and
footprint has no job to run. A sender heartbeat is the only thing that could separate "no
condition fired" from "sender dead", and R-IV.1089(c) declined it because TRITON-R does not use
the footprint signal. So this bound detects TOTAL DEATH only, and takes up to four days.
"""
from __future__ import annotations

import os

import pytest

from stable_engine.signals_freshness import (
    AGE_SOURCES, DEFAULT_SLO_SECONDS, REGISTERED_CLASSES, RTH_ONLY_CLASSES, SLO_SECONDS,
)
#: The measured distribution the bound was chosen from, in hours.
MEASURED = {"median": 0.75, "p75": 3.25, "p90": 19.0, "p95": 23.5, "max": 91.0}
#: The gap that triggered the false flatline on 2026-10-15.
TODAYS_GAP_H = 25.3


def test_the_slo_is_96_hours():
    assert SLO_SECONDS["footprint"] == 96 * 3600


def test_the_bound_clears_the_whole_measured_distribution():
    """THE REASON FOR 96 AND NOT A ROUND NUMBER. Zero breaches in the 60-day sample, including
    the 91h maximum. 72h would have left one."""
    assert SLO_SECONDS["footprint"] > MEASURED["max"] * 3600
    assert SLO_SECONDS["footprint"] > 72 * 3600


def test_the_flatline_that_prompted_this_would_no_longer_fire():
    assert TODAYS_GAP_H * 3600 < SLO_SECONDS["footprint"]


def test_the_old_six_hour_bound_is_gone():
    """19% of its own gaps breached it. A bound a healthy producer cannot satisfy is not a
    bound, it is an alarm clock."""
    assert SLO_SECONDS["footprint"] != 6 * 3600
    assert SLO_SECONDS["footprint"] > MEASURED["p95"] * 3600


def test_it_is_not_silently_on_the_default():
    """The 4h default would be worse than the 6h it replaced. An explicit entry means a later
    reader sees a decision rather than an omission."""
    assert "footprint" in SLO_SECONDS
    assert SLO_SECONDS["footprint"] != DEFAULT_SLO_SECONDS


# ── the bound is still a bound: total death is still caught ──────────────────

def test_a_genuinely_dead_sender_is_STILL_detected():
    """THE PAIR. Raising an SLO until nothing ever fires is not a fix, it is a mute button.
    Five days of silence still flatlines."""
    assert 5 * 24 * 3600 > SLO_SECONDS["footprint"]


def test_the_class_keeps_its_supervision():
    """It stays REGISTERED, so it still moves /health's aggregate (R-IV.1059(b)) -- the bound
    changed, not the supervision."""
    assert "footprint" in REGISTERED_CLASSES


def test_it_stays_RTH_GATED():
    """Overnight and weekend quiet were already excused; that is independent of the bound and
    must not be lost in the edit."""
    assert "footprint" in RTH_ONLY_CLASSES


def test_it_was_NOT_moved_to_the_job_runs_source():
    """THE FIX THAT DOES NOT TRANSFER, asserted so nobody applies it later by analogy.
    `footprint` is an inbound webhook with no job_runs row; pointing it at job_runs would
    render `no_data` forever and disarm the sentinel -- the trap this file documents for the
    crypto producers."""
    assert AGE_SOURCES.get("footprint") is None


def test_the_measurement_and_its_LIMIT_are_both_recorded():
    """A bound chosen from data must carry the data, and a bound that cannot do what a reader
    will assume it does must say so."""
    # The evidence lives in a COMMENT, so this is the one place a raw read is correct --
    # `code_only` would strip exactly what is being asserted. Path built from the package
    # root rather than by string-replacing this file's own name, which breaks on either
    # separator.
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "stable_engine", "signals_freshness.py")
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()
    i = raw.index('"footprint": 96 * 3600')
    window = raw[max(0, i - 1600):i]
    assert "19.0%" in window or "40 of 210" in window, "the measurement is not recorded"
    assert "TOTAL DEATH" in window.upper(), "the bound's limit is not stated"
    assert "AGE_SOURCE_JOB_RUNS" in window, "why the crypto fix does not transfer is not stated"
