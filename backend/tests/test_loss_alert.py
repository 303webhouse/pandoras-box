"""R-IV.517(d) + R-IV.526(c) -- the loss alert.

Convention #30: every group below carries POSITIVE controls -- cases that must
FIRE -- next to the cases that must stay silent. Four refusals in a row look like
a working guard and are equally consistent with a trigger that never fires at all.
"""

from datetime import datetime, timedelta, timezone

import pytest

from jobs import loss_alert as la


NOW = datetime(2026, 9, 24, 19, 30, tzinfo=timezone.utc)   # 15:30 ET, inside RTH
FRESH = NOW - timedelta(minutes=3)


def row(**kw):
    """An OPEN FIDELITY_ROTH equity with a fresh mark, 100 shares at $10, now $10."""
    base = {
        "id": 1, "position_id": "POS_T", "ticker": "T", "account": "FIDELITY_ROTH",
        "asset_type": "EQUITY", "structure": "stock", "direction": "LONG",
        "notes": None, "stop_loss": None,
        "current_price": 10.0, "mark_status": "OK", "mark_checked_at": FRESH,
        "remainder": 100.0, "lot_cost": 1000.0,
    }
    base.update(kw)
    return base


def triggers(rows, **kw):
    kw.setdefault("now", NOW)
    return [a["trigger"] for a in la.evaluate_rows(rows, **kw)]


# -- the columns this job may not read ---------------------------------------

def test_the_select_names_none_of_the_scope_broken_money_columns():
    """R-IV.526(c). The fault Trade Analysis found lives in these columns, so the
    alert must not be able to inherit it. Asserted against the SQL text itself."""
    sql = la.POSITION_SQL.lower()
    for col in la.FORBIDDEN_COLUMNS:
        assert col not in sql, f"{col} is read by the loss alert's SELECT"


def test_the_whole_module_never_reads_those_columns():
    """Not just the SELECT -- no string anywhere in live code names them.

    Walked as an AST rather than grepped, because the docstrings, the comments and
    FORBIDDEN_COLUMNS itself all name the columns deliberately, and a text scan
    cannot tell those apart from a read.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(la))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and \
                    isinstance(body[0].value, ast.Constant) and \
                    isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
        # The declaration of the forbidden list is not a read of those columns.
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "FORBIDDEN_COLUMNS"
                for t in node.targets):
            for sub in ast.walk(node.value):
                if isinstance(sub, ast.Constant):
                    docstrings.add(id(sub))

    live = [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docstrings]
    for col in la.FORBIDDEN_COLUMNS:
        offenders = [s for s in live if col in s]
        assert not offenders, f"{col} is named in live code: {offenders[:2]}"
    # The guard must be able to fail: a column the module DOES read is found.
    assert [s for s in live if "current_price" in s], \
        "the AST walk found no live column names at all -- it is not testing anything"


# -- T1, the unstopped loss --------------------------------------------------

def test_threshold_is_two_percent_of_the_account_value():
    """R-IV.539(c): the Roth total in the principal's positions file, 2026-09-24."""
    assert la.DEFAULT_ACCOUNT_VALUE_USD == 11_319.53
    assert la.loss_threshold_usd() == 226.39       # 2% of 11,319.53


def test_a_loss_past_two_percent_fires():
    """POSITIVE CONTROL. 100 shares cost $1,000, marked 7.70 -> -$230, past -$224."""
    assert la.TRIGGER_UNSTOPPED_LOSS in triggers([row(current_price=7.70)])


def test_a_loss_short_of_two_percent_does_not():
    assert la.TRIGGER_UNSTOPPED_LOSS not in triggers([row(current_price=7.80)])   # -$220


def test_the_loss_is_measured_at_the_open_remainder_not_the_size_opened():
    """The WEAT/ABNB fault, in the alert's own arithmetic. Half the position has been
    sold: 50 shares remain of the 100 opened, and the loss is HALF -- so the same
    mark that fires on a full position must NOT fire on a half-closed one."""
    half = row(remainder=50.0, lot_cost=500.0, current_price=7.70)   # -$115
    assert la.TRIGGER_UNSTOPPED_LOSS not in triggers([half])
    assert la.TRIGGER_UNSTOPPED_LOSS in triggers([row(current_price=7.70)])


def test_only_this_account_is_in_scope():
    assert la.TRIGGER_UNSTOPPED_LOSS not in triggers(
        [row(account="ROBINHOOD", current_price=7.70)])


def test_a_written_stop_does_not_count_as_a_live_broker_stop():
    """R-IV.517(d) says 'without a live broker stop'. The hub records no such thing,
    so a number in stop_loss must not silence the alert -- that would be the trigger
    reading a wish as an order."""
    assert la.has_live_broker_stop(row(stop_loss=9.0)) is None
    assert la.TRIGGER_UNSTOPPED_LOSS in triggers([row(current_price=7.70, stop_loss=9.0)])


# -- the mark gate -----------------------------------------------------------

def test_a_stale_mark_fires_nothing_and_says_so():
    stale = row(current_price=7.70, mark_checked_at=NOW - timedelta(hours=3))
    t = triggers([stale])
    assert la.TRIGGER_UNSTOPPED_LOSS not in t
    assert la.NOTICE_UNMEASURABLE in t


def test_a_refused_mark_fires_nothing_and_says_so():
    bad = row(current_price=7.70, mark_status="REJECTED")
    t = triggers([bad])
    assert la.TRIGGER_UNSTOPPED_LOSS not in t
    assert la.NOTICE_UNMEASURABLE in t


def test_a_fresh_ok_mark_is_live():
    ok, why = la.mark_is_live("OK", FRESH, NOW)
    assert ok and "ago" in why


# -- the lot-less row --------------------------------------------------------

def test_a_row_with_no_lots_is_reported_unmeasurable_not_guessed_at():
    """R-IV.526(b): no lots -> no open remainder. Nothing stands in for it, so the
    row produces a notice and no loss figure at all."""
    alerts = la.evaluate_rows([row(remainder=None, lot_cost=None, current_price=1.0)],
                              now=NOW)
    assert [a["trigger"] for a in alerts] == [la.NOTICE_UNMEASURABLE]
    assert "loss" not in alerts[0]


def test_a_lot_less_row_outside_the_account_is_silent():
    """The notice is about the account under alert, not a book-wide audit."""
    assert triggers([row(account="ROBINHOOD", remainder=None, lot_cost=None)]) == []


# -- T2, the written daily-close stop ----------------------------------------

@pytest.mark.parametrize("notes,level,side", [
    ("daily close below 43", 43.0, "below"),
    ("stop: close under $43.10", 43.10, "below"),
    ("daily-close stop 43", 43.0, "below"),
    ("exit on a daily close above 12.5", 12.5, "above"),
    ("closing below 7", 7.0, "below"),
])
def test_the_close_stop_grammar_reads_what_was_written(notes, level, side):
    assert la.parse_daily_close_stop(notes, "LONG") == (level, side)


@pytest.mark.parametrize("notes", [
    None, "", "stop 43", "hard stop at 43", "no stop written",
    "bought 43 shares", "closed half at 43",
])
def test_a_stop_that_is_not_a_close_stop_is_not_read_as_one(notes):
    """A bare 'stop 43' belongs to the stop_loss column. Reading it here would invent
    a daily-close instrument the principal never wrote."""
    assert la.parse_daily_close_stop(notes, "LONG") is None


def test_a_short_takes_the_other_side_when_no_word_is_written():
    assert la.parse_daily_close_stop("daily close 43", "SHORT") == (43.0, "above")


def test_an_explicit_word_beats_the_direction():
    assert la.parse_daily_close_stop("daily close below 43", "SHORT") == (43.0, "below")


def test_a_close_exactly_on_the_stop_is_a_breach():
    assert la.close_stop_breached(43.0, 43.0, "below") is True
    assert la.close_stop_breached(43.0, 43.0, "above") is True


def test_the_close_stop_fires_only_after_the_close():
    r = row(notes="daily close below 43", current_price=42.0)
    assert la.TRIGGER_CLOSE_STOP not in triggers([r], session_closes={"T": 42.0},
                                                 after_close=False)
    assert la.TRIGGER_CLOSE_STOP in triggers([r], session_closes={"T": 42.0},
                                             after_close=True)


def test_an_unbreached_close_stop_stays_silent():
    r = row(notes="daily close below 43", current_price=44.0)
    assert la.TRIGGER_CLOSE_STOP not in triggers([r], session_closes={"T": 44.0},
                                                 after_close=True)


def test_no_dated_close_means_no_close_stop_verdict():
    """R-IV.487: a bar that is not stamped with the session is not that session's
    close. An absent close produces silence, never a comparison against a stand-in."""
    r = row(notes="daily close below 43", current_price=42.0)
    assert la.TRIGGER_CLOSE_STOP not in triggers([r], session_closes={}, after_close=True)


# -- T3, cost recovery -------------------------------------------------------

def opt(**kw):
    base = dict(id=2, position_id="POS_O", ticker="O", account="ROBINHOOD",
                asset_type="OPTION", structure="call_debit_spread", direction="LONG",
                notes=None, stop_loss=None, current_price=0.40, mark_status="OK",
                mark_checked_at=FRESH, remainder=4.0, lot_cost=0.80)
    base.update(kw)
    return base


def test_two_times_cost_on_two_or_more_contracts_fires():
    """POSITIVE CONTROL. 4 contracts at 0.20 paid (lot_cost 0.80), marked 0.40 = 2x."""
    assert la.TRIGGER_COST_RECOVERY in triggers([opt()])


def test_just_under_the_multiple_does_not():
    assert la.TRIGGER_COST_RECOVERY not in triggers([opt(current_price=0.39)])


def test_one_contract_never_fires_cost_recovery():
    """There is no cost to sell back out of a single contract."""
    assert la.TRIGGER_COST_RECOVERY not in triggers(
        [opt(remainder=1.0, lot_cost=0.20, current_price=0.40)])


def test_the_multiple_is_per_contract_not_per_position():
    """lot_cost is the WHOLE position's cost; the multiple compares the mark to the
    cost of ONE contract. Getting that wrong scales the trigger by the size."""
    e = la.position_economics(4.0, 0.80, 0.40, is_option=True)
    assert e["unit_cost"] == pytest.approx(0.20)
    assert e["multiple"] == pytest.approx(2.0)
    assert e["cost"] == pytest.approx(80.0)
    assert e["value"] == pytest.approx(160.0)
    assert e["pnl"] == pytest.approx(80.0)


def test_cost_recovery_is_book_wide_not_roth_only():
    """FIDELITY_ROTH holds no options, so an account-scoped T3 would be dead code."""
    assert la.TRIGGER_COST_RECOVERY in triggers([opt(account="BREAKOUT_PROP")])


def test_an_equity_never_fires_cost_recovery():
    assert la.TRIGGER_COST_RECOVERY not in triggers([row(current_price=30.0)])


# -- the multiplier ----------------------------------------------------------

def test_an_option_carries_the_hundred_multiplier_and_a_share_does_not():
    assert la.position_economics(2.0, 0.50, 0.50, is_option=True)["cost"] == 50.0
    assert la.position_economics(2.0, 0.50, 0.50, is_option=False)["cost"] == 0.50


def test_a_zero_or_negative_remainder_produces_nothing():
    assert la.position_economics(0.0, 100.0, 1.0, is_option=False) is None
    assert la.position_economics(-2.0, 100.0, 1.0, is_option=False) is None


# -- the hours when a mark is due --------------------------------------------

def test_a_stale_mark_outside_market_hours_is_not_reported_as_a_fault():
    """At 02:00 ET the mark job has not run for hours because the market is shut.
    Saying so nightly would train the principal to ignore the channel."""
    stale = row(current_price=7.70, mark_checked_at=NOW - timedelta(hours=10))
    assert triggers([stale], expect_live_mark=False) == []
    assert la.NOTICE_UNMEASURABLE in triggers([stale], expect_live_mark=True)


def test_a_lot_less_row_is_reported_whatever_the_hour():
    """Missing lots is not a function of the clock, so this one is never suppressed."""
    blind = row(remainder=None, lot_cost=None)
    assert la.NOTICE_UNMEASURABLE in triggers([blind], expect_live_mark=False)


@pytest.mark.parametrize("hhmm,expected", [
    ((9, 29), False), ((9, 30), True), ((12, 0), True),
    ((17, 0), True), ((17, 1), False), ((2, 0), False),
])
def test_marks_are_due_from_the_open_to_an_hour_past_the_close(hhmm, expected):
    import pytz
    et = pytz.timezone("America/New_York").localize(
        datetime(2026, 9, 24, hhmm[0], hhmm[1]))       # a Thursday session
    assert la.marks_expected(et) is expected


def test_marks_are_never_due_on_a_non_session():
    import pytz
    sat = pytz.timezone("America/New_York").localize(datetime(2026, 9, 26, 12, 0))
    assert la.marks_expected(sat) is False


# -- the digest --------------------------------------------------------------

def test_the_blind_rows_go_out_as_one_message_naming_each():
    notices = [a for a in la.evaluate_rows(
        [row(id=1, position_id="A", ticker="AAA", remainder=None, lot_cost=None),
         row(id=2, position_id="B", ticker="BBB", remainder=None, lot_cost=None)],
        now=NOW)]
    title, body = la._digest_body(notices)
    assert "2" in title and la.ACCOUNT in title
    assert "AAA" in body and "BBB" in body


# -- the tick, end to end ----------------------------------------------------

class _Resp:
    def __init__(self, code):
        self.status_code = code


class _Client:
    """Stands in for httpx.AsyncClient and records what would have been posted."""
    posted = []

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None):
        _Client.posted.append((url, json))
        return _Resp(204)


@pytest.fixture
def no_redis(monkeypatch):
    """No dedupe store, so the tests exercise the in-process fallback -- and so the
    suite never reaches for a network Redis (12s of connect attempts when it tries)."""
    import database.redis_client as rc

    async def _none():
        return None

    monkeypatch.setattr(rc, "get_redis_client", _none)
    return rc


@pytest.fixture
def stub_webhook(monkeypatch, no_redis):
    import httpx
    _Client.posted = []
    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    monkeypatch.setenv("DISCORD_WEBHOOK_ALERTS", "https://example.invalid/hook")
    la._SENT_IN_PROCESS.clear()
    yield _Client
    la._SENT_IN_PROCESS.clear()


@pytest.mark.asyncio
async def test_a_firing_row_is_pushed_once_and_the_status_code_is_recorded(stub_webhook):
    """POSITIVE CONTROL for the whole tick: a real loss, a real post, 204 captured."""
    rows = [row(current_price=7.70)]
    r1 = await la.run_loss_alert(injected_rows=rows, now=NOW)
    assert r1["alerts"] == 1
    assert r1["pushed"] == 1
    assert r1["statuses"] == {"204": 1}
    assert len(stub_webhook.posted) == 1
    body = stub_webhook.posted[0][1]["embeds"][0]
    assert "Unstopped loss" in body["title"]
    assert "230.00" in body["description"]          # 100 shares, $1,000 cost, 7.70

    # Second pass, same session: claimed already, so nothing leaves.
    r2 = await la.run_loss_alert(injected_rows=rows, now=NOW)
    assert r2["pushed"] == 0 and r2["suppressed"] == 1
    assert len(stub_webhook.posted) == 1


@pytest.mark.asyncio
async def test_a_quiet_book_posts_nothing(stub_webhook):
    r = await la.run_loss_alert(injected_rows=[row()], now=NOW)
    assert r["alerts"] == 0 and r["pushed"] == 0
    assert stub_webhook.posted == []


@pytest.mark.asyncio
async def test_with_no_webhook_configured_nothing_is_sent_and_it_is_logged(monkeypatch, no_redis):
    monkeypatch.delenv("DISCORD_WEBHOOK_ALERTS", raising=False)
    monkeypatch.delenv("DISCORD_WEBHOOK_CB", raising=False)
    la._SENT_IN_PROCESS.clear()
    r = await la.run_loss_alert(injected_rows=[row(current_price=7.70)], now=NOW)
    assert r["alerts"] == 1 and r["pushed"] == 0
    assert r["statuses"] == {"None": 1}
    la._SENT_IN_PROCESS.clear()


@pytest.mark.asyncio
async def test_the_blind_rows_leave_as_a_single_post(stub_webhook):
    rows = [row(id=1, position_id="A", ticker="AAA", remainder=None, lot_cost=None),
            row(id=2, position_id="B", ticker="BBB", remainder=None, lot_cost=None),
            row(id=3, position_id="C", ticker="CCC", remainder=None, lot_cost=None)]
    r = await la.run_loss_alert(injected_rows=rows, now=NOW)
    assert r["alerts"] == 3
    assert len(stub_webhook.posted) == 1            # three rows, ONE message
    assert r["pushed"] == 1


@pytest.mark.asyncio
async def test_a_reachable_dedupe_store_is_what_claims_the_push(monkeypatch):
    """The claim survives a redeploy only if it lives in Redis, so the Redis path is
    tested on its own -- and a claim already held there stops the second push."""
    import database.redis_client as rc

    held = {}

    class _R:
        async def set(self, key, value, ex=None, nx=None):
            if nx and key in held:
                return None
            held[key] = value
            return True

    async def _get():
        return _R()

    monkeypatch.setattr(rc, "get_redis_client", _get)
    la._SENT_IN_PROCESS.clear()
    session = NOW.date()
    assert await la._claim(session, la.TRIGGER_UNSTOPPED_LOSS, "POS_T") is True
    assert len(held) == 1
    la._SENT_IN_PROCESS.clear()          # a fresh process, same session
    assert await la._claim(session, la.TRIGGER_UNSTOPPED_LOSS, "POS_T") is False
    la._SENT_IN_PROCESS.clear()
