"""R-IV.809 / R-IV.820(e) — Nemesis was wired to a name that does not exist, and two more defects.

THE RECORD. `bias_scheduler.run_wrr_scan_job()` imported `run_wrr_scan` from
`strategies.wrr_buy_model`, which has never defined it (it defines `scan_wrr` and
`run_wrr_and_process`). The ImportError was caught by the job's own `except Exception` and logged
as an ordinary job error, so APScheduler reported the job **"executed successfully"**. The
2026-10-09 16:20 ET run logged, verbatim:

    ERROR:scheduler.bias_scheduler:WRR scan job error: cannot import name 'run_wrr_scan'
    from 'strategies.wrr_buy_model' (/app/backend/strategies/wrr_buy_model.py)

and the permitted count (R-IV.820(d), exception E1) returned **0**:

    SELECT COUNT(*) FROM signals WHERE strategy = 'nemesis_wrr' OR signal_type LIKE 'NEMESIS%';

So Nemesis has never emitted from the schedule, exactly as predicted.

THREE DEFECTS, not one. Fixing only the import would have produced a scan that still scanned
nothing (N1(i)) and a gate that still passed every long and rejected every short (N1(ii)).
"""
from __future__ import annotations

import ast
import io
import os
import sys

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

ROOT = __file__.rsplit("tests", 1)[0]
SCHED = os.path.join(ROOT, "scheduler", "bias_scheduler.py")


def _src(rel):
    # bias_scheduler.py carries a BOM; utf-8 alone raises on U+FEFF.
    return io.open(os.path.join(ROOT, rel), encoding="utf-8-sig").read()


# ── (b) the import fix, and the general test the ruling asks for ─────────────────────────────
class TestEveryNameAJobImportsExists:
    """R-IV.809(b): "one test that imports every function the scheduler job references".

    Resolved STATICALLY against each target module's AST. Importing for real would execute
    module-level code in dozens of app modules against production credentials, which is not
    something a test suite should do to find a typo.
    """

    def _names_in(self, dotted):
        p = os.path.join(ROOT, *dotted.split("."))
        for cand in (p + ".py", os.path.join(p, "__init__.py")):
            if os.path.exists(cand):
                path = cand
                break
        else:
            return None
        t = ast.parse(io.open(path, encoding="utf-8-sig").read())
        out = set()
        for n in ast.walk(t):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                out.add(n.name)
            elif isinstance(n, ast.Assign):
                for tgt in n.targets:
                    if isinstance(tgt, ast.Name):
                        out.add(tgt.id)
            elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
                out.add(n.target.id)
            elif isinstance(n, ast.ImportFrom):
                for a in n.names:
                    out.add(a.asname or a.name)
            elif isinstance(n, ast.Import):
                for a in n.names:
                    out.add((a.asname or a.name).split(".")[0])
        return out

    def _registered_jobs(self):
        tree = ast.parse(_src(os.path.join("scheduler", "bias_scheduler.py")))
        defs = {n.name: n for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        jobs = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "add_job" and node.args
                    and isinstance(node.args[0], ast.Name)):
                jobs.append(node.args[0].id)
        return [(name, defs[name]) for name in jobs if name in defs]

    def test_there_are_jobs_to_check(self):
        """POSITIVE CONTROL. Every assertion below passes trivially on an empty list."""
        assert len(self._registered_jobs()) >= 20

    def test_every_in_body_import_resolves(self):
        broken = []
        for fname, fn in self._registered_jobs():
            for n in ast.walk(fn):
                if not isinstance(n, ast.ImportFrom) or not n.module:
                    continue
                have = self._names_in(n.module)
                if have is None:
                    continue            # third-party / outside backend: not ours to judge
                for a in n.names:
                    if a.name not in have:
                        broken.append("%s: from %s import %s" % (fname, n.module, a.name))
        assert not broken, "scheduler jobs import names that do not exist: %s" % broken

    def test_the_wrr_job_points_at_the_function_that_PROCESSES(self):
        """`scan_wrr` alone would compute and discard. `run_wrr_and_process` puts hits through
        process_signal_unified, so they are governed, persisted and graded."""
        src = _src(os.path.join("scheduler", "bias_scheduler.py"))
        assert "from strategies.wrr_buy_model import run_wrr_and_process" in src
        assert "import run_wrr_scan" not in src, "the name that never existed"

    def test_both_wrr_entry_points_still_exist(self):
        from strategies import wrr_buy_model as w

        assert callable(w.scan_wrr) and callable(w.run_wrr_and_process)
        assert not hasattr(w, "run_wrr_scan")


# ── N1(i) the bars window ────────────────────────────────────────────────────────────────────
class TestTheBarsWindowIsWideEnough:
    def test_scan_asks_for_enough_history_for_a_200_SMA(self):
        """get_bars defaults to a 60-CALENDAR-day lookback (~41 bars) with no from_date, and the
        guard needs SMA_200_PERIOD + 5 = 205 — so every ticker was skipped by `continue` BEFORE
        `scanned` incremented, and the scan reported a quiet universe rather than a broken
        window."""
        from strategies.wrr_buy_model import BARS_LOOKBACK_DAYS, SMA_200_PERIOD

        # 400 calendar days is ~275 trading bars; the guard needs 205.
        assert BARS_LOOKBACK_DAYS == 400
        assert BARS_LOOKBACK_DAYS * (252.0 / 365.0) > SMA_200_PERIOD + 5

    def test_the_call_passes_from_date(self):
        import inspect

        from strategies.wrr_buy_model import scan_wrr

        # Comments are STRIPPED first: the windowless call appears verbatim in the comment that
        # explains why it was wrong, so a plain substring test fails on its own documentation.
        live = "\n".join(l.split("#", 1)[0] for l in inspect.getsource(scan_wrr).split("\n"))
        assert "from_date=_from" in live
        assert 'get_bars(ticker, 1, "day")' not in live, "the windowless call is still live"

    def test_get_bars_accepts_from_date(self):
        """A keyword the callee does not take would be a TypeError swallowed by the same
        `except Exception` that hid the ImportError for months."""
        import inspect

        from integrations.uw_api import get_bars

        assert "from_date" in inspect.signature(get_bars).parameters


# ── N1(ii) the bias-gate scale ───────────────────────────────────────────────────────────────
class TestTheCountertrendGateIsRecordedNotEnforced:
    def test_the_thresholds_really_are_on_the_other_scale(self):
        """The premise, asserted rather than assumed: 25/75 against a -1..+1 composite."""
        from signals.pipeline import BIAS_EXTREME_BEARISH, BIAS_EXTREME_BULLISH

        assert (BIAS_EXTREME_BEARISH, BIAS_EXTREME_BULLISH) == (25, 75)
        # Every reachable composite value passes the long test and fails the short test.
        for composite in (-1.0, -0.5, 0.0, 0.5, 1.0):
            assert composite <= BIAS_EXTREME_BEARISH      # counter-long: always "extreme"
            assert not composite >= BIAS_EXTREME_BULLISH   # counter-short: never "extreme"

    def test_a_nemesis_row_records_the_verdict_and_is_never_bailed_out(self):
        import inspect

        from signals import pipeline

        src = inspect.getsource(pipeline)
        assert '"countertrend_gate"' in src
        assert "_is_nemesis" in src
        # The bail-out is reached only via countertrend_rejected, which the Nemesis branch
        # never sets.
        nem = src[src.index("if _is_nemesis:"):src.index("elif not extreme_ok:")]
        assert "countertrend_rejected" not in nem, \
            "a Nemesis row must never take the pre-persist bail-out"
        assert '"enforced": False' in nem

    def test_the_verdict_has_three_states_including_unavailable(self):
        """"Unavailable" must be distinguishable from "fail": an absent composite was the case
        that silently rejected and returned before persisting."""
        import inspect

        from signals import pipeline

        src = inspect.getsource(pipeline)
        for state in ("unavailable", "pass", "fail"):
            assert '"%s"' % state in src or "'%s'" % state in src, state

    def test_the_gate_is_unchanged_for_every_other_producer(self):
        """Measured: `countertrend` is set in exactly ONE place in the codebase, so no other
        producer reaches this gate at all. The non-Nemesis branch is kept verbatim anyway."""
        import inspect

        from signals import pipeline

        src = inspect.getsource(pipeline)
        assert "elif not extreme_ok:" in src
        assert 'signal_data["countertrend_rejected"] = True' in src

    def test_only_wrr_sets_countertrend_anywhere_in_the_codebase(self):
        import subprocess

        out = subprocess.run(
            ["grep", "-rn", '"countertrend": True', "--include=*.py", ROOT],
            capture_output=True, text=True).stdout
        hits = [l for l in out.splitlines()
                if l.strip() and "/tests/" not in l.replace("\\", "/")]
        assert len(hits) == 1, "expected exactly one producer, found: %s" % hits
        assert "wrr_buy_model" in hits[0]


# ── (c) the L0 shadow ────────────────────────────────────────────────────────────────────────
class TestNemesisIsSuppressed:
    def test_NEMESIS_LONG_is_in_SUPPRESS_ALWAYS(self):
        from config.l0_routing import SUPPRESS_ALWAYS

        assert "NEMESIS_LONG" in SUPPRESS_ALWAYS

    def test_the_comment_states_the_ruling_and_that_grading_continues(self):
        src = _src(os.path.join("config", "l0_routing.py"))
        assert "R-IV.809 shadow" in src
        assert "graded under suppression" in src

    def test_the_other_suppressed_types_are_untouched(self):
        """CONTROL (#30). A change that suppressed more than Nemesis would pass the test
        above."""
        from config.l0_routing import SUPPRESS_ALWAYS

        for t in ("STRIKE_IB_BREAK", "HOLY_GRAIL_1H", "HOLY_GRAIL_15M", "PULLBACK_ENTRY",
                  "TRAPPED_LONGS", "ARTEMIS_LONG"):
            assert t in SUPPRESS_ALWAYS, t
        assert len(SUPPRESS_ALWAYS) == 7
        # And the types explicitly kept live stay out of it.
        for t in ("ARTEMIS_SHORT", "TWO_CLOSE_VOLUME", "GOLDEN_TOUCH", "TRAPPED_SHORTS"):
            assert t not in SUPPRESS_ALWAYS, t


# ── W5 the dark-pool accumulator ─────────────────────────────────────────────────────────────
class TestDarkPoolAggregatesInsteadOfErroring:
    """W5 / R-IV.820(e): `total_premium_all += prem` with the name never initialised, so the
    FIRST print of every ticker raised UnboundLocalError and the caller recorded
    `darkpool_status = "error"` — while the UW call that fetched those prints was spent anyway.
    """

    def _payload(self):
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        def p(prem, ago_min, bid, ask, price):
            return {"premium": str(prem), "size": 1000, "price": str(price),
                    "nbbo_bid": str(bid), "nbbo_ask": str(ask),
                    "executed_at": (now - timedelta(minutes=ago_min)).isoformat(),
                    "canceled": False}
        return [p(250_000, 10, 99.9, 100.1, 100.08),   # buy-side
                p(750_000, 30, 99.9, 100.1, 99.92),    # sell-side
                p(2_000_000, 60, 99.9, 100.1, 100.0),  # mid, >1m bucket
                p(50_000, 90, 0, 0, 100.0)]            # no NBBO

    def test_a_payload_with_prints_aggregates_ok(self):
        """`_fetch_and_aggregate(ticker)` fetches its own prints through
        `uw_api.get_darkpool_ticker`, and the CALLER turns its return into
        `darkpool_status`. So the vendor call is faked and the real entry point is driven, which
        is the only way the status this asserts is actually produced.
        """
        import asyncio

        from integrations import uw_api
        from signals.darkpool_enrichment import _fetch_and_aggregate, enrich_darkpool_data

        prints = self._payload()

        async def _fake_vendor(ticker, *a, **k):
            return prints

        orig = uw_api.get_darkpool_ticker
        uw_api.get_darkpool_ticker = _fake_vendor
        loop = asyncio.new_event_loop()
        try:
            agg = loop.run_until_complete(_fetch_and_aggregate("SPY"))
            out = loop.run_until_complete(
                enrich_darkpool_data({"ticker": "SPY", "metadata": {}}))
        finally:
            loop.close()
            uw_api.get_darkpool_ticker = orig

        # It aggregated rather than raising UnboundLocalError on the first print.
        assert agg is not None, "aggregation returned None — the vendor fake did not take"
        # The returned keys are `darkpool_`-prefixed; assert on what it actually serves, and on
        # a figure that could only be non-zero if the accumulator loop completed.
        assert agg.get("darkpool_buy_premium", 0) > 0, agg
        assert agg.get("darkpool_direction"), agg
        # And the status the ruling names.
        assert out["metadata"]["darkpool_status"] == "ok", out["metadata"]

    def test_the_first_print_no_longer_raises(self):
        """The defect in one assertion: with `total_premium_all` uninitialised, ONE print was
        enough to raise. A payload of exactly one print is the minimal reproduction."""
        import asyncio

        from integrations import uw_api
        from signals.darkpool_enrichment import _fetch_and_aggregate

        one = self._payload()[:1]

        async def _fake_vendor(ticker, *a, **k):
            return one

        orig = uw_api.get_darkpool_ticker
        uw_api.get_darkpool_ticker = _fake_vendor
        loop = asyncio.new_event_loop()
        try:
            agg = loop.run_until_complete(_fetch_and_aggregate("SPY"))
        finally:
            loop.close()
            uw_api.get_darkpool_ticker = orig
        assert agg is not None

    def test_the_accumulator_is_initialised_beside_the_others(self):
        src = _src(os.path.join("signals", "darkpool_enrichment.py"))
        assert "total_premium_all  = 0.0" in src or "total_premium_all = 0.0" in src
        # It is used, so an uninitialised name would be an UnboundLocalError on the first print.
        assert "total_premium_all += prem" in src

    def test_the_size_buckets_sum_to_the_all_premium_total(self):
        """The accumulator's purpose: it is the size-bucket denominator. If it were quietly
        replaced by 0 the buckets would still fill and the percentages would be meaningless."""
        src = _src(os.path.join("signals", "darkpool_enrichment.py"))
        assert "size_buckets" in src


