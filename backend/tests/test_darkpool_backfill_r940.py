"""The dark-pool backfill — R-IV.921(b), ordered to run by R-IV.940(b).

Nothing here touches the network. The properties that matter are the ORDER, the STOPS, the
QUARANTINE and the outcome-blindness, and all four are decidable without a vendor.

The hard-rule checks read the PARSED tree with docstrings removed, because the job's own
docstring necessarily discusses `triton_` tables, the ignored `page` parameter and the seal in
order to explain what it must not do.
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import sys
from datetime import date

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from jobs import darkpool_backfill as bf  # noqa: E402


def _live_strings(module) -> list:
    """Every string literal in the module EXCEPT docstrings.

    Docstring nodes are identified STRUCTURALLY -- the first statement of a module, function or
    class body -- and excluded by identity. NOT by comparing text against
    `ast.get_docstring()`, which CLEANS indentation and therefore never equals the raw Constant
    it is meant to exclude. That mistake made the first version of this helper pass the module
    docstring straight through, and the outcome-blindness check failed on the paragraph
    explaining the rule rather than on any code.
    """
    tree = ast.parse(inspect.getsource(module))
    doc_nodes = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(n, "body", None) or []
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                doc_nodes.add(id(body[0].value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in doc_nodes]


@pytest.mark.parametrize("prose", ["SEAL", "OUTCOME-BLIND", "triton_"])
def test_the_prose_stripper_actually_strips_prose(prose):
    """A positive control, because every hard-rule check below depends on this helper. Each
    probe is PRESENT in the job's docstring and absent from its code, so a leaking stripper
    fails here rather than making a later check fail on the explanation.

    `page` is deliberately NOT a probe: it is a substring of the legitimate column `page_no`.
    The real check next door tests exact list MEMBERSHIP (`"page" not in live`), which is the
    precise question -- is a parameter named exactly `page` ever sent -- and a substring search
    would answer a different one. My first version of this control got that wrong."""
    assert bf.__doc__ and prose in bf.__doc__, "the control's premise is stale"
    assert prose not in " ".join(_live_strings(bf))


# ── (b)2 ORDER: oldest session first, the 8 core names ───────────────────

def test_sessions_are_oldest_first():
    s = bf.trading_sessions(date(2026, 8, 28), date(2026, 9, 4))
    assert s == sorted(s), "the ruling says oldest first; a sorted list is the whole point"
    assert s[0] == date(2026, 8, 28)


def test_weekends_are_not_requested():
    s = bf.trading_sessions(date(2026, 8, 28), date(2026, 9, 7))
    assert all(d.weekday() < 5 for d in s)
    assert date(2026, 8, 29) not in s      # Saturday
    assert date(2026, 8, 30) not in s      # Sunday


def test_the_eight_core_names_exactly():
    assert bf.CORE_NAMES == ("SPY", "QQQ", "IWM", "SMH", "NVDA", "AAPL", "MSFT", "TSLA")
    assert len(bf.CORE_NAMES) == 8


def test_the_oldest_known_session_is_the_probed_one():
    assert bf.OLDEST_KNOWN_SESSION == date(2026, 8, 28)


# ── (b)4 QUARANTINE ──────────────────────────────────────────────────────

def test_the_two_quarantined_sessions():
    assert bf.QUARANTINED_SESSIONS == frozenset({date(2026, 8, 28), date(2026, 8, 31)})


def test_quarantine_is_stored_on_the_row_not_implied():
    """A flag a reader must infer from a date list is not a flag. Both tables carry it."""
    ddl = "\n".join(bf.DDL)
    assert ddl.count("quarantined BOOLEAN NOT NULL DEFAULT FALSE") == 2
    assert "quarantined" in bf.INSERT_PAGE and "quarantined" in bf.UPSERT_SESSION


# ── the three stops ──────────────────────────────────────────────────────

def test_the_budget_numbers_are_the_ruled_ones():
    assert bf.CALL_BUDGET_PER_UW_DAY == 2500
    assert bf.ACCOUNT_TOTAL_STOP == 30000
    assert bf.ALLOWANCE_THROUGH == date(2026, 10, 23)


def test_the_call_budget_actually_stops():
    b = bf.Budget(call_budget=3)
    for _ in range(3):
        b.spend()
    assert b.remaining == 0


def test_a_stop_reason_is_kept_and_not_overwritten():
    """The FIRST cause is the one worth reporting; a later stop must not rename it."""
    b = bf.Budget()
    b.stop("429 from the vendor")
    b.stop("call budget exhausted")
    assert b.stop_reason == "429 from the vendor"
    assert b.stopped is True


def test_the_allowance_refuses_to_run_after_it_lapses(monkeypatch):
    """Enforced by the job, not by remembering to stop calling it."""
    import datetime as _dt

    class _Late(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return _dt.datetime(2026, 10, 24, 1, 0, tzinfo=_dt.timezone.utc)

    monkeypatch.setattr(bf, "datetime", _Late)
    out = asyncio.run(bf.run())
    assert out["ok"] is False and "lapsed" in out["reason"]


def test_an_unreadable_account_total_fails_OPEN(monkeypatch):
    """Same disposition as the governor: an unmeasured account must not become an outage of its
    own. The call budget still bounds the run."""
    b = bf.Budget()

    async def boom():
        raise RuntimeError("no header")
    import integrations.uw_api as uw
    monkeypatch.setattr(uw, "account_quota", boom, raising=False)
    asyncio.run(b.check_account())
    assert b.stopped is False


def test_a_breached_account_total_stops(monkeypatch):
    b = bf.Budget()

    async def over():
        return {"used": 30001, "limit": 40000}
    import integrations.uw_api as uw
    monkeypatch.setattr(uw, "account_quota", over, raising=False)
    asyncio.run(b.check_account())
    assert b.stopped is True
    assert "30001" in b.stop_reason and "30000" in b.stop_reason


# ── (b)1 UNFLOORED, and the cursor that actually works ──────────────────

def test_no_floor_is_ever_sent():
    """R-IV.921(b)1: collect UNFLOORED. A size or premium floor would pre-decide the very
    definition the census exists to test."""
    live = _live_strings(bf)
    for floor in ("min_premium", "min_size"):
        assert floor not in live, "a floor reaches the vendor: %s" % floor


def test_the_cursor_is_older_than_and_NOT_page():
    """`page` is silently ignored by the vendor -- it returns page one again, which is why the
    first probe's "identical pages" reading was worthless until it was redone with a row
    fingerprint. `older_than` is the only cursor that moves."""
    live = _live_strings(bf)
    assert "older_than" in live
    assert "page" not in live, "the ignored `page` parameter must not be sent"


def test_the_oldest_cursor_is_the_minimum_timestamp():
    rows = [{"executed_at": "2026-08-28T19:00:00Z"},
            {"executed_at": "2026-08-28T16:24:40Z"},
            {"executed_at": "2026-08-28T18:00:00Z"}]
    assert bf._oldest_cursor(rows) == "2026-08-28T16:24:40Z"


def test_an_unusable_page_yields_no_cursor():
    assert bf._oldest_cursor([]) is None
    assert bf._oldest_cursor([{"nothing": 1}]) is None


def test_the_page_limit_is_the_vendors_hard_cap():
    assert bf.PAGE_LIMIT == 500


# ── OUTCOME-BLIND, and the SEAL satisfied by construction ───────────────

def test_it_reads_no_triton_table_and_no_outcome():
    """The job must not be steerable by what the collection would later show."""
    joined = " ".join(_live_strings(bf)).lower()
    for forbidden in ("triton_flow_shadow", "triton_", "signal_outcome", "outcome"):
        assert forbidden not in joined, "the backfill references %r" % forbidden


def test_it_writes_only_its_OWN_tables():
    """R-IV.912(c)2: darkpool_collector, its tables and its caller tag are SM7's registered
    instrument and must not be touched."""
    live = " ".join(_live_strings(bf))
    for own in ("darkpool_backfill_pages", "darkpool_backfill_sessions",
                "darkpool_backfill_runs"):
        assert own in live
    for stmt in (bf.INSERT_PAGE, bf.UPSERT_SESSION, *bf.DDL):
        for theirs in ("darkpool_pages", "darkpool_windows", "darkpool_depth_probes"):
            assert not (theirs in stmt and "darkpool_backfill" not in stmt), \
                "writes to the collector's table %s" % theirs


def test_the_caller_tag_is_its_own():
    assert bf.CALLER == "darkpool_backfill_triton"
    from integrations.uw_governor import FOREIGN_RESERVE_QUOTAS, quota_for
    assert bf.CALLER in FOREIGN_RESERVE_QUOTAS
    assert quota_for(bf.CALLER)[0] == 2500


def test_the_hubs_own_quota_table_is_untouched():
    """The 2,500 comes from the FOREIGN RESERVE. The hub's table still sums to exactly 26,000,
    which is the number the whole governor was measured around."""
    from integrations.uw_governor import DAILY_BUDGET, QUOTAS
    assert sum(q for q, _ in QUOTAS.values()) == 26000
    assert "darkpool_backfill_triton" not in QUOTAS
    assert DAILY_BUDGET == 28000


# ── resumability: a cut-short session must be retried ───────────────────

def test_only_EXHAUSTED_sessions_are_treated_as_done():
    """A session stopped by the budget must come back, or the night it was cut short becomes a
    permanent hole -- in a dataset whose whole problem is that holes cannot be refilled."""
    assert "exhausted = TRUE" in bf.DONE_SQL


def test_pages_are_idempotent_on_replay():
    assert "ON CONFLICT (ticker, session_date, page_no) DO UPDATE" in bf.INSERT_PAGE
    assert "ON CONFLICT (ticker, session_date) DO UPDATE" in bf.UPSERT_SESSION


def test_nothing_is_derived_from_the_payload():
    """Store raw, derive nothing (R-IV.921(b)). The only things computed are the cursor and the
    row count -- both needed to fetch and to report, neither a finding."""
    src = inspect.getsource(bf)
    for derived in ("premium_sum", "vwap", "notional", "classify"):
        assert derived not in src, "the backfill derives %s" % derived


# ── the ceiling, and resuming instead of re-walking ─────────────────────

def test_the_page_ceiling_is_a_runaway_guard_not_a_limit():
    """MEASURED on the first live run: SPY, QQQ and NVDA each hit a 60-page ceiling at 30,000
    prints WITHOUT exhausting 2026-08-28, while IWM finished in 20 pages and SMH in 15. The
    "~29 pages for SPY" figure the first ceiling was built on was a fire-WINDOW slice, not a
    whole unfloored session. A ceiling that truncates the three biggest names is a silent gap
    in exactly the names that matter."""
    assert bf.MAX_PAGES_PER_TICKER_SESSION >= 400


def test_a_cut_short_session_RESUMES_rather_than_restarting():
    """Without this the three biggest names could never finish: every run would spend its
    calls re-fetching the same first pages, forever, and `exhausted` would stay false. The
    cursor comes from the last stored page's own payload, which is exact because the raw
    payload is kept."""
    assert "RESUME_SQL" in dir(bf)
    assert "ORDER BY page_no DESC" in bf.RESUME_SQL
    src = inspect.getsource(bf.collect_one)
    assert "RESUME_SQL" in src, "collect_one does not consult the resume cursor"
    assert "first_page" in src


def test_the_session_row_reports_the_WHOLE_session_not_one_slice():
    """A resumed run must not make the stored totals shrink back to just its own slice: the
    page and print counts are re-read from the pages table before the upsert."""
    src = inspect.getsource(bf.collect_one)
    assert "FROM darkpool_backfill_pages WHERE ticker = $1" in src
