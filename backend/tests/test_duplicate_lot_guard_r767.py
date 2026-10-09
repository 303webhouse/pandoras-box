"""R-IV.767(c) — the duplicate-lot guard, replayed against the entry that caused it.

THE RECORD. The principal's UI entry wrote SOXS 15 @ 32.99 twice, at 17:21:03.824810 and
17:21:13, identical in every field, putting 494.85 of basis on POS_SOXS_20261008_155324 that no
broker charged. `cash_flows` had a duplicate guard and refused the matching movement;
`position_lots` had none.

The figures below are the LIVE ONES, read back from the hub before anything was built:
lot 3842 = 15 @ 32.06 written 15:53:24.648988Z, lot 3851 = 15 @ 32.99 written 17:21:03.819142Z,
both `fill_time` 2026-10-08T06:00:00Z. That shared fill_time is the reason the window is measured
on `created_at`: the two lots of a GENUINE two-part entry carry the same reported fill instant, so
a window measured there could not tell them apart from a double-submit, and would refuse the
honest second buy six hours later.

Convention #30 — every refusal is paired with a case that must be ACCEPTED, because a guard that
refused everything would pass every "it refuses" test and make the book unwritable:
  refuses the replayed double          <-> accepts the real second buy at a different price
  refuses inside 60 seconds            <-> accepts the same entry 61 seconds later
  refuses a principal entry            <-> accepts an IMPORT's two identical fills
  refuses an unconfirmed re-submit     <-> accepts it when the principal confirms
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from models import lot_duplicate_guard as g  # noqa: E402

# --- the live record ------------------------------------------------------------------------
PID = "POS_SOXS_20261008_155324"
FIRST_WRITE = datetime(2026, 10, 8, 17, 21, 3, 819142, tzinfo=timezone.utc)
SECOND_CLICK = datetime(2026, 10, 8, 17, 21, 13, tzinfo=timezone.utc)
# `fill_time` on BOTH lots. Kept as a constant so the point it proves cannot be edited away.
REPORTED_FILL = datetime(2026, 10, 8, 6, 0, 0, tzinfo=timezone.utc)


def lot_3851(**over):
    """Lot 3851 as the hub serves it: NUMERIC columns arrive as Decimal."""
    row = {"id": 3851, "position_id": PID, "account": "fidelity_roth", "ticker": "SOXS",
           "side": "LONG", "qty": Decimal("15"), "price": Decimal("32.99"),
           "created_at": FIRST_WRITE, "fill_time": REPORTED_FILL,
           "source": "principal-entry@2026-10-08T17:21:03.824810+00:00"}
    row.update(over)
    return row


def second_submit(**over):
    """What the form sends on the second click: the account in caps, the price a FLOAT."""
    cand = {"account": "FIDELITY_ROTH", "ticker": "SOXS", "side": "LONG",
            "qty": 15, "price": 32.99}
    cand.update(over)
    return cand


# --- the decision ---------------------------------------------------------------------------
class TestTheReplay:
    def test_replaying_976s_double_entry_refuses_the_second(self):
        """The ruled control, with the recorded instants."""
        twin = g.find_twin(second_submit(), [lot_3851()], now=SECOND_CLICK)
        assert twin is not None and twin["id"] == 3851

    def test_the_refusal_names_the_entry_the_lot_and_what_was_not_written(self):
        twin = g.find_twin(second_submit(), [lot_3851()], now=SECOND_CLICK)
        msg = g.refusal_detail(twin, second_submit(), now=SECOND_CLICK)
        for must in ("15", "SOXS", "32.99", "FIDELITY_ROTH", "lot 3851", PID,
                     "Nothing was saved this time", "confirm_duplicate"):
            assert must in msg, must
        assert "9 seconds ago" in msg, "the elapsed time is from the real instants"

    def test_the_first_submit_is_not_refused_by_itself(self):
        """POSITIVE CONTROL. With no prior lot the window is empty and the entry proceeds —
        otherwise the guard would refuse the FIRST entry and nothing could ever be opened."""
        assert g.find_twin(second_submit(), [], now=SECOND_CLICK) is None


class TestWhatMustStillBeAccepted:
    def test_the_real_second_buy_at_a_different_price_is_accepted(self):
        """The row genuinely holds 15 @ 32.06 and 15 @ 32.99. Had the guard keyed on quantity
        alone it would have refused the trade that is actually on the record."""
        assert g.find_twin(second_submit(price=32.06), [lot_3851()], now=SECOND_CLICK) is None

    def test_a_different_quantity_is_accepted(self):
        assert g.find_twin(second_submit(qty=14), [lot_3851()], now=SECOND_CLICK) is None

    def test_another_account_is_accepted(self):
        assert g.find_twin(second_submit(account="ROBINHOOD"), [lot_3851()],
                           now=SECOND_CLICK) is None

    def test_another_ticker_is_accepted(self):
        assert g.find_twin(second_submit(ticker="SOXL"), [lot_3851()], now=SECOND_CLICK) is None

    def test_the_other_side_is_accepted(self):
        assert g.find_twin(second_submit(side="SHORT"), [lot_3851()], now=SECOND_CLICK) is None


class TestTheWindow:
    @pytest.mark.parametrize("secs", [0, 1, 9, 59, 60])
    def test_inside_the_minute_it_is_a_duplicate(self, secs):
        now = FIRST_WRITE + timedelta(seconds=secs)
        assert g.find_twin(second_submit(), [lot_3851()], now=now) is not None

    @pytest.mark.parametrize("secs", [61, 120, 3600, 86400])
    def test_past_the_minute_the_same_entry_is_accepted(self, secs):
        now = FIRST_WRITE + timedelta(seconds=secs)
        assert g.find_twin(second_submit(), [lot_3851()], now=now) is None

    def test_the_window_is_measured_on_created_at_not_on_fill_time(self):
        """THE DESIGN POINT. Both lots report fill_time 06:00:00Z, so a window measured there
        would call a buy made eight hours later a duplicate. Measured on created_at, the same
        pair is correctly two entries."""
        eight_hours_later = REPORTED_FILL + timedelta(hours=8)
        by_fill = g.within_window(lot_3851()["fill_time"], eight_hours_later)
        by_write = g.within_window(lot_3851()["created_at"], eight_hours_later)
        assert by_fill is False and by_write is False
        # ... and at the moment of the second click, only created_at puts it in the window.
        assert g.within_window(lot_3851()["created_at"], SECOND_CLICK) is True
        assert g.within_window(lot_3851()["fill_time"], SECOND_CLICK) is False

    def test_a_row_with_no_instant_is_not_in_the_window(self):
        """An absent fact must not read as a satisfied condition — it would refuse a good entry
        on the strength of a row nobody can place in time."""
        assert g.within_window(None, SECOND_CLICK) is False
        assert g.find_twin(second_submit(), [lot_3851(created_at=None)],
                           now=SECOND_CLICK) is None

    def test_a_naive_timestamp_refuses_to_be_compared_rather_than_guessing(self):
        naive = FIRST_WRITE.replace(tzinfo=None)
        assert g.within_window(naive, SECOND_CLICK) is False

    def test_a_row_written_after_now_is_not_in_the_window(self):
        """Counted backwards only. A future created_at is a clock problem, not a duplicate."""
        assert g.within_window(FIRST_WRITE, FIRST_WRITE - timedelta(seconds=5)) is False


class TestTheFloatTail:
    """#27, as a trap this guard would have fallen straight into."""

    def test_the_naive_comparison_would_never_have_matched(self):
        """Proof the care is necessary, not decorative: the form sends the float 32.99 and the
        column returns Decimal('32.99'). Built the wrong way the guard never fires — and a guard
        that never fires is worse than none, because it also reports that it is protecting you."""
        assert Decimal(32.99) != Decimal("32.99")
        assert g._same_num(32.99, Decimal("32.99")) is True

    def test_trailing_zeros_are_the_same_price(self):
        assert g._same_num(Decimal("32.990"), 32.99) is True

    def test_a_third_decimal_is_a_different_price(self):
        """Not quantized to the cent: 32.994 and 32.990 are two different trades."""
        assert g._same_num(Decimal("32.994"), 32.99) is False

    def test_an_unstated_price_matches_nothing(self):
        assert g._same_num(None, Decimal("32.99")) is False
        assert g._same_num(None, None) is False

    def test_the_account_comparison_does_not_depend_on_case(self):
        """The book stores `fidelity_roth`; the form sends `FIDELITY_ROTH`. Keying on the
        spelling would have made the guard a no-op for every entry the UI makes."""
        assert g.is_twin(second_submit(), lot_3851()) is True


class TestImportsAreOutOfScope:
    @pytest.mark.parametrize("source", ["IMPORT", "LEGACY-SINGLE-LOT", "", None])
    def test_an_import_is_not_guarded(self, source):
        """Two identical fills seconds apart are one broker order filled in two parts."""
        assert g.is_guarded_source(source) is False

    @pytest.mark.parametrize("source", ["MANUAL", "manual",
                                        "principal-entry@2026-10-08T17:21:03.824810+00:00"])
    def test_a_principal_entry_is_guarded(self, source):
        assert g.is_guarded_source(source) is True


class TestOneAuthorForTheWindow:
    def test_the_minute_is_stated_once(self):
        assert g.GUARD_WINDOW_SECONDS == 60

    def test_the_route_reads_the_window_from_this_module(self):
        """Two copies of a number is how the second one gets forgotten."""
        import inspect

        from api import unified_positions as up

        src = inspect.getsource(up._recent_duplicate_entry)
        assert "GUARD_WINDOW_SECONDS" in src
        assert "60" not in src.replace("R-IV.767", ""), "the minute must not be re-typed here"


# --- the lookup, against a conn that returns the real row ------------------------------------
class _FakeConn:
    """Returns the recorded lot, and the database's own NOW() as the route selects it."""

    def __init__(self, rows, now):
        self.rows = rows
        self.now = now
        self.queries = []

    async def fetch(self, sql, *args):
        self.queries.append((sql, args))
        return [dict(r, db_now=self.now) for r in self.rows]


class _Req:
    def __init__(self, **kw):
        self.entry_price = kw.get("entry_price", 32.99)
        self.quantity = kw.get("quantity", 15)
        self.source = kw.get("source", "MANUAL")
        self.confirm_duplicate = kw.get("confirm_duplicate", False)
        self.reason = kw.get("reason")
        self.actor = kw.get("actor")


def _lookup(rows, now, **req):
    from api.unified_positions import _recent_duplicate_entry

    conn = _FakeConn(rows, now)
    out = asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        _recent_duplicate_entry(conn, account="fidelity_roth", ticker="SOXS",
                                side="LONG", req=_Req(**req)))
    return out, conn


class TestTheLookup:
    def test_the_replay_comes_back_as_a_refusal_sentence(self):
        out, _ = _lookup([lot_3851()], SECOND_CLICK)
        assert out is not None and "same entry twice" in out and "lot 3851" in out

    def test_an_empty_window_returns_none(self):
        out, _ = _lookup([], SECOND_CLICK)
        assert out is None

    def test_an_import_never_reaches_the_query(self):
        out, conn = _lookup([lot_3851()], SECOND_CLICK, source="IMPORT")
        assert out is None and conn.queries == [], "an import must not even be looked up"

    def test_a_priceless_or_sizeless_entry_is_not_guarded(self):
        """No lot is written without both, so there is nothing to duplicate."""
        for kw in ({"entry_price": None}, {"quantity": 0}):
            out, conn = _lookup([lot_3851()], SECOND_CLICK, **kw)
            assert out is None and conn.queries == []

    def test_the_confirm_does_NOT_suppress_the_lookup(self):
        """A confirmed re-submit is still a known duplicate and must be RECORDED as one.
        Returning None here would let it through saying nothing — trading a wrong figure for a
        silence, which is the same bargain the defect made."""
        out, _ = _lookup([lot_3851()], SECOND_CLICK, confirm_duplicate=True)
        assert out is not None, "the helper reports it; the ROUTE decides what to do"

    def test_the_query_filters_on_created_at_and_on_acquisitions_only(self):
        _, conn = _lookup([lot_3851()], SECOND_CLICK)
        sql = conn.queries[0][0]
        assert "l.created_at >=" in sql, "the window is on created_at"
        assert "fill_time" not in sql, "fill_time must not bound the window"
        assert "l.qty > 0" in sql, "a disposal is not a duplicate acquisition"
        assert "NOW()" in sql, "one clock, the database's"

    def test_the_sql_window_is_a_net_and_python_makes_the_decision(self):
        """A row the SQL let through but which is not identical is still accepted. This is what
        keeps a sloppy predicate from silently widening the guard."""
        out, conn = _lookup([lot_3851(price=Decimal("31.00"))], SECOND_CLICK)
        assert conn.queries, "it did query"
        assert out is None, "the decision, not the query, is what refuses"


# --- the route ------------------------------------------------------------------------------
class _Acquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *a):
        return False


class _Pool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _Acquire(self._conn)


class ReachedTheWrite(Exception):
    """A sentinel, so "it got past the guard" is an OBSERVED event and not an absence.

    Without it the confirm test would be `except Exception: pass`, which passes whether the
    guard let the entry through or the route fell over on the line before — a test that cannot
    fail. The write path proper is not served by these fakes, so this is the furthest an
    honest in-process test can see.
    """


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _RouteConn:
    """Answers the reads create_position makes, then stops at the first write."""

    def __init__(self, rows, now):
        self.rows, self.now = rows, now

    async def fetchrow(self, sql, *a):
        return None          # no open position to combine with: the create branch

    async def fetch(self, sql, *a):
        return [dict(r, db_now=self.now) for r in self.rows]

    async def fetchval(self, sql, *a):
        return None

    def transaction(self):
        return _Tx()

    async def execute(self, sql, *a):
        raise ReachedTheWrite(sql.strip().split("\n")[0][:60])


def _req(**over):
    from api.unified_positions import CreatePositionRequest

    body = {"ticker": "SOXS", "asset_type": "EQUITY", "structure": "stock",
            "entry_price": 32.99, "quantity": 15, "source": "MANUAL",
            "account": "FIDELITY_ROTH", "entry_date": "2026-10-08"}
    body.update(over)
    return CreatePositionRequest(**body)


def _drive(req):
    """Run the real route against fakes that answer its reads and stop at its first write."""
    from api.unified_positions import create_position

    conn = _RouteConn([lot_3851()], SECOND_CLICK)
    loop = asyncio.get_event_loop_policy().new_event_loop()
    with patch("api.unified_positions.get_postgres_client", return_value=_Pool(conn)):
        try:
            return loop.run_until_complete(create_position(req))
        finally:
            loop.close()


def _post(**over):
    return _drive(_req(**over))


class TestTheRoute:
    def test_the_second_submit_is_refused_with_409_and_the_message(self):
        """Driven through the real route, not through the helper: the refusal has to be what
        the UI actually receives."""
        with pytest.raises(HTTPException) as e:
            _post()
        assert e.value.status_code == 409
        assert "same entry twice" in e.value.detail
        assert "lot 3851" in e.value.detail and "confirm" in e.value.detail

    def test_a_confirmed_second_entry_is_accepted(self):
        """The ruled control, and it asserts a POSITIVE event rather than the absence of one:
        the route must reach its first write, which is further than the refused submit ever
        gets."""
        with pytest.raises(ReachedTheWrite):
            _post(confirm_duplicate=True)

    def test_a_confirmed_entry_is_RECORDED_as_a_confirmed_duplicate(self):
        """Accepted is not the same as unremarked. Both branches hand `req.reason` to
        `name_actor`, so the annotation the guard writes reaches the audit trail."""
        req = _req(confirm_duplicate=True)
        with pytest.raises(ReachedTheWrite):
            _drive(req)
        assert req.reason is not None
        assert req.reason.startswith("CONFIRMED DUPLICATE (R-IV.767(c))")
        assert "lot 3851" in req.reason, "it records WHICH entry it duplicates"

    def test_an_ordinary_entry_is_not_labelled_a_confirmed_duplicate(self):
        """CONTROL (#30). The annotation must only appear when a twin was actually found —
        otherwise every confirmed write would carry a claim that may be false."""
        req = _req(confirm_duplicate=True, ticker="SOXL")   # no twin for this ticker
        with pytest.raises(ReachedTheWrite):
            _drive(req)
        assert req.reason is None or "CONFIRMED DUPLICATE" not in req.reason

    def test_the_other_lot_writers_are_deliberately_not_guarded(self):
        """SCOPE, stated so it is a decision and not an oversight. `/lots`, `/reduce` and the
        import paths write lots too; none is reachable from a form, and an import's two
        identical fills are legitimate. If one of them ever gets a UI, this test is the place
        that says the guard has to come with it."""
        import inspect

        from api import unified_positions as up

        for fn in (up.add_position_lot, up.reduce_position):
            assert "_recent_duplicate_entry" not in inspect.getsource(fn)
        # POSITIVE CONTROL: the route that IS guarded, so this is not just naming functions
        # that happen to lack a string.
        assert "_recent_duplicate_entry" in inspect.getsource(up.create_position)

    def test_the_guard_runs_before_either_branch_writes(self):
        """Placed once, above the add/create fork: the same entry submitted twice takes a
        DIFFERENT branch each time, because the first submit creates the row the second adds to.
        A guard wired per-branch would miss exactly that crossing."""
        import inspect

        from api import unified_positions as up

        src = inspect.getsource(up.create_position)
        at_guard = src.index("_recent_duplicate_entry")
        assert at_guard < src.index("ADD TO EXISTING POSITION")
        assert at_guard < src.index("INSERT INTO position_lots")
        assert at_guard < src.index("INSERT INTO unified_positions")


# --- the frontend half ----------------------------------------------------------------------
class TestTheFrontendHalf:
    """R-IV.767(c) also rules the submit button and the re-submit. Pinned by reading the files,
    which is this repo's idiom for a page with no test runner of its own.

    Worth saying plainly: of the two halves, the BUTTON would not have prevented the defect.
    The two SOXS writes were ten seconds apart, long after the first save returned. The button
    stops a double-click; the server guard stops a double-entry.
    """

    FRONTEND = __file__.rsplit("backend", 1)[0] + "frontend"

    def _read(self, name):
        import io as _io
        return _io.open(self.FRONTEND + "\\" + name, encoding="utf-8").read()

    def test_agora_disables_its_submit_for_the_whole_round_trip(self):
        js = self._read("v2.js")
        assert "btn.disabled = true" in js
        # Re-enabled in `finally`, or a failed save leaves a dead button and a stuck form.
        assert "finally { if (btn) { btn.disabled = false" in js

    def test_agora_shows_the_servers_own_sentence(self):
        """Not a paraphrase: a second wording is a second thing to keep true."""
        js = self._read("v2.js")
        assert "showDuplicateRefusal" in js
        assert "text.textContent = detail" in js

    def test_agora_requires_a_second_deliberate_action(self):
        js = self._read("v2.js")
        assert "addConfirmDuplicate = true; submitAdd();" in js
        # Spent on the submit it was given for, so a tick cannot sit armed for the next entry.
        assert "addConfirmDuplicate = false; }" in js

    def test_the_legacy_page_has_ONE_author_for_the_behaviour(self):
        """Three forms there POST this endpoint. Three copies is how one ends up a fix behind."""
        js = self._read("app.js")
        assert js.count("async function postPositionWithDuplicateGuard") == 1
        assert js.count("postPositionWithDuplicateGuard(") == 4      # 1 definition + 3 callers
        assert js.count("function lockSubmitButton") == 1
        assert js.count("lockSubmitButton(") == 4

    def test_every_legacy_caller_unlocks_in_finally(self):
        js = self._read("app.js")
        assert js.count("unlock();") == 3

    def test_the_legacy_page_sends_the_confirm_only_after_asking(self):
        js = self._read("app.js")
        assert "confirm(detail" in js
        assert "{ confirm_duplicate: true }" in js

    def test_the_consumed_body_bug_is_gone(self):
        """`response.json()` twice returns {} the second time, so the options form could only
        ever say 'Unknown error' and could never have displayed this refusal."""
        js = self._read("app.js")
        assert "const err = await response.json().catch(() => ({}));" not in js
        assert "alert('Error saving position: ' + (data.detail" in js

    def test_both_pages_still_pin_their_script(self):
        """A changed script behind an unchanged `?v=` is a fix that never reaches the browser.

        This asserted the literal `?v=177` / `?v=55` until R-IV.792, when the very next bump
        broke it. A hardcoded version here is the same defect R-IV.790(d) removed from
        CLAUDE.md: a second copy of a number that changes on every deploy. It could never have
        caught a MISSED bump either -- only a real one. So what is pinned here is that the pin
        EXISTS and is numeric; whether it was incremented is a review question, not a constant.
        """
        import re

        for page, script in (("index.html", "app.js"), ("v2.html", "v2.js")):
            m = re.search(r"/%s\?v=(\d+)" % re.escape(script), self._read(page))
            assert m, "%s must pin /%s with a ?v=" % (page, script)
            assert int(m.group(1)) > 0
