"""R-IV.1095(b) — every `feed_health` field names its SCOPE.

THE DEFECT WAS TWO CORRECT FIELDS IMPLYING SOMETHING FALSE. On 2026-10-15 a read of
`hub_get_market_profile(SPY)` returned:

    data         SPY's own newest row, 2026-10-14T14:38Z, status stale, sessions_behind 1
    feed_health  flowing, last_accepted_at 2026-10-15T16:34:49Z, rejected 0

Both figures were right. Together they said SPY had just reported, and it had not: 31 events
landed that day across 28 tickers and **none were core-8**. The newest row belonged to `SRE`.

`data` is PER-TICKER; `feed_health` is FEED-WIDE by design (R-IV.1037(c)2 created it to catch
65 consecutive 401s that the per-ticker freshness verdict called `ok`). That scope is correct
and is kept. The bug was serving it UNLABELLED next to per-ticker levels.

So the fix is not a different number -- it is the scope of each number, stated. And
`last_accepted_ticker` alone would have prevented the misreading: the field would have said
`SRE` beside a SPY request.

Not a mapping bug and not a selection bug: the events carry levels, `script_version` is
`v2.6`, and the read's SQL is `WHERE ticker = $1 ORDER BY timestamp DESC LIMIT 1` with no
filter that could skip v2.6. Those were hypotheses (b)1 and (b)3 and both were falsified
before anything was changed.
"""
from __future__ import annotations

import inspect
import re

import pytest

from services.read_only import market_profile as mp
from tests._srcscan import code_of


# ── 1. the scope-naming fields exist ────────────────────────────────────────

def test_feed_health_takes_the_ticker():
    """It cannot label a per-ticker figure without knowing which ticker it is serving."""
    sig = inspect.signature(mp._feed_health)
    assert "tkr" in sig.parameters


def test_the_caller_passes_the_ticker():
    """A parameter nothing passes is decoration. This is the line that was wrong."""
    code = code_of(mp.get_market_profile)
    assert "_feed_health(tkr)" in code, code[:400]


@pytest.mark.parametrize("field", [
    "feed_health_scope",
    "last_accepted_ticker",
    "this_ticker_last_accepted_at",
    "this_ticker_rejections_since",
])
def test_the_scope_fields_are_served(field):
    code = code_of(mp._feed_health)
    assert field in code, field


def test_the_scope_string_says_FEED_WIDE_explicitly():
    """A reader must not have to infer it. The whole defect was an unstated scope."""
    code = code_of(mp._feed_health)
    assert "FEED-WIDE" in code
    assert "not this one" in code


# ── 2. the per-ticker count is per-ticker ───────────────────────────────────

def test_the_ticker_count_filters_by_ticker():
    """THE SUBSTANCE. `_feed_counts` is MAX(timestamp) across every row; the new helper must
    be scoped, or the 'this ticker' field repeats the feed-wide one under a new name."""
    code = code_of(mp._ticker_feed_counts)
    assert "WHERE ticker = $1" in code
    assert "MAX(timestamp)" in code


def test_the_ticker_count_excludes_observe_rows_too():
    """Consistent with `_feed_counts`: an allowed-but-invalid payload was not REFUSED, so it
    must not be counted as a refusal here either. Two refusal counts with different rules
    would be worse than one wrong one."""
    code = code_of(mp._ticker_feed_counts)
    assert "OBSERVE:%" in code


def test_the_feed_wide_count_is_still_feed_wide():
    """THE PAIR. Narrowing `_feed_counts` to the ticker would have destroyed the signal
    R-IV.1037(c)2 built: a ticker that simply has not fired would read as a refused feed."""
    code = code_of(mp._feed_counts)
    assert "WHERE ticker" not in code
    assert "MAX(timestamp) FROM pythia_events" in code


def test_last_accepted_ticker_reads_the_newest_rows_ticker():
    code = code_of(mp._last_accepted_ticker)
    assert "ORDER BY timestamp DESC" in code
    assert "LIMIT 1" in code


# ── 3. unreadable is not zero, and never raises ─────────────────────────────

@pytest.mark.parametrize("fn", ["_ticker_feed_counts", "_last_accepted_ticker"])
def test_the_new_helpers_never_raise(fn):
    """They run inside a read path that must degrade rather than fail; and an unreadable
    count must return None, because "I could not check" is not "no rejections"."""
    code = code_of(getattr(mp, fn))
    assert "except Exception" in code


def test_an_unreadable_ticker_count_returns_None_not_zero():
    code = code_of(mp._ticker_feed_counts)
    # `ast.unparse` renders a bare tuple return with parentheses, so match the parsed form
    # rather than the source spelling.
    assert "return (None, None)" in code


# ── 4. first boot: the new reads touch only startup-migrated tables ─────────

def test_the_new_queries_read_only_tables_created_at_startup():
    """R-IV.1052(b). Both tables are migrated in main.py's startup path, so these reads do
    not wait on a writer. Asserted here as well as in the first-boot guard, because the guard
    scans READ_DIRS and this module is one -- if that ever changes, this still holds."""
    import os

    # THE STARTUP SET COMES FROM THE GUARD, not from a second list here. My first version
    # scanned main.py alone and "found" that `pythia_events` is not created at startup -- it
    # is, in database/postgres_client.py, which is the guard's SECOND startup file. A narrower
    # copy of someone else's definition produces a false finding, which is the failure mode
    # this whole register is about.
    from tests.test_first_boot_reads_r1052 import STARTUP_FILES

    backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    startup = ""
    for f in STARTUP_FILES:
        with open(os.path.join(backend, f), encoding="utf-8-sig") as fh:
            startup += fh.read() + chr(10)
    created = {t.lower() for t in re.findall(
        r"CREATE TABLE IF NOT EXISTS\s+([a-z_][a-z0-9_]*)", startup, re.I)}
    for tbl in ("pythia_events", "pythia_webhook_rejections"):
        assert tbl in created, "%s is not created at startup" % tbl


def test_the_two_tables_are_the_only_ones_the_new_helpers_touch():
    code = code_of(mp._ticker_feed_counts) + code_of(mp._last_accepted_ticker)
    tables = set(re.findall(r"\bFROM\s+([a-z_][a-z0-9_]*)", code, re.I))
    assert tables <= {"pythia_events", "pythia_webhook_rejections"}, tables

