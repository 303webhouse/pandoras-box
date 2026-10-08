"""R-IV.429 — /api/abacus/summary, the Abacus v2 page's data contract (stub).

What these pin down:
  * the route is gated like every book read (R-IV.417), before it ever carries real data;
  * every block carries `source` and `computed_at`, and while mock the whole payload says so;
  * the fixture's computed_at is its AUTHORED instant, never the request time (a mock
    stamped "now" would read as fresh);
  * the range is echoed, and `range_applied` is False while the figures ignore it;
  * rates carry their n, and unknown is None, never 0;
  * the page and its assets are served, and /app/abacus is not swallowed by /app/{mode}.
"""
import pytest
from unittest.mock import AsyncMock, patch

PATH = "/api/abacus/summary"


def _get(client, test_api_key, qs=""):
    return client.get(PATH + qs, headers={"X-API-Key": test_api_key})


# R-IV.705(b): the rest of the arithmetic went live off the same census read.
LIVE_KEYS = {"net_profit", "win_rate", "expected_return", "expectancy", "profit_factor",
             "avg_win_loss", "loss_vs_risk"}
# Blocks that are still the fixture, and must keep saying so (R-IV.705(g)).
MOCK_BLOCK_KEYS = {"discipline"}
# R-IV.716(c): a live READ that found its own source untrustworthy. Not mock — nothing here is
# invented — and not a figure either: the reason stands where the number would.
WITHHELD_KEYS = {"loss_vs_risk"}


class _FakePool:
    """Records every query so a test can assert the predicate/window, not just the result.

    R-IV.705: the route now reads THREE tables -- the census, `balance_snapshots` and
    `cash_flows` -- so the stub routes by table instead of answering every query with the same
    rows. A pool that returned census rows to the snapshot query would have the equity curve
    reading a P&L as a balance.
    """

    def __init__(self, rows=None, snapshots=None, cash=None,
                 closures=None, fallback=None, dropped=None):
        self.rows = list(rows or [])
        self.snapshots = list(snapshots or [])
        self.cash = list(cash or [])
        # R-IV.761(b). `closures=None` means "derive them from the rows" (the book's norm);
        # `closures=[]` means "this row genuinely has none", which is a different fixture and
        # must stay expressible.
        self.closures = None if closures is None else list(closures)
        self.fallback = list(fallback or [])
        self.dropped = list(dropped or [])
        self.calls = []

    async def fetch(self, sql, *params):
        self.calls.append((sql, params))
        if "balance_snapshots" in sql:
            return self.snapshots
        if "cash_flows" in sql:
            return self.cash
        # R-IV.761(b): the realized TOTAL reads its own population -- the closures ledger, plus
        # the rows that ledger does not cover. Routed explicitly, because the fall-through below
        # would hand census rows to a query expecting `v`/`n` and the route would 500. That is
        # the same hazard this stub's docstring already names for the snapshot query.
        if "position_lot_closures" in sql:
            if "SUM(c.realized)" in sql:
                # Branch 1, modelled on the book's norm: 560 of 568 rows have closures that
                # agree with their `realized_pnl` exactly (measured 2026-10-08), so a row's
                # closures ARE its realized unless a test says otherwise.
                if self.closures is not None:
                    return self.closures
                by: dict = {}
                for r in self.rows:
                    if r.get("realized_pnl") is None:
                        continue
                    k = r.get("account")
                    agg = by.setdefault(k, {"account": k, "v": 0.0, "n": 0})
                    agg["v"] += float(r["realized_pnl"])
                    agg["n"] += 1
                return list(by.values())
            # Branch 2 (no closures, has exit_date) and the dropped read (no exit_date): empty
            # unless a test supplies them, which is the book's norm too -- eight and one row.
            return list(self.fallback if "p.exit_date IS NOT NULL" in sql else self.dropped)
        return self.rows


import datetime as _dt
_ENTRY = _dt.datetime(2026, 9, 1, 15, 0, tzinfo=_dt.timezone.utc)      # a Tuesday, in MT
_EXIT = _dt.datetime(2026, 9, 10, 20, 0, tzinfo=_dt.timezone.utc)      # 9 days held


def _row(pnl, basis=None, basis_incomplete_reason=None, account="ROBINHOOD", *,
         max_loss=None, structure="put_debit_spread", ticker="SPY", entry=_ENTRY, exit=_EXIT,
         strategy_tag=None, signal_id=None):
    # R-IV.650(b)3: the query selects `account`; R-IV.705(b) adds the columns the breakdowns and
    # the untagged count are grouped by. `None` is a real case for several of them -- a closed
    # trade the book never attributed, never bucketed, or never linked to a signal.
    return {"realized_pnl": pnl, "cost_basis": basis,
            "basis_incomplete_reason": basis_incomplete_reason, "account": account,
            "max_loss": max_loss, "structure": structure, "ticker": ticker,
            "entry_date": entry, "exit_date": exit, "strategy_tag": strategy_tag,
            "signal_id": signal_id}


def _snap(day, balance, name="ROBINHOOD"):
    return {"snapshot_date": _dt.datetime(*day, tzinfo=_dt.timezone.utc), "balance": balance,
            "account_name": name}


def _series(start_day, values, name="ROBINHOOD"):
    """One snapshot a day from `start_day`, so a test can reach the thirty returns R-IV.709(c)
    requires before a Sharpe ratio is served at all."""
    import datetime as dt
    d0 = _dt.date(*start_day)
    return [_snap((d.year, d.month, d.day), v, name)
            for d, v in ((d0 + dt.timedelta(days=i), v) for i, v in enumerate(values))]


def _cash(day, amount, kind="ACH", name="ROBINHOOD"):
    return {"activity_date": _dt.datetime(*day, tzinfo=_dt.timezone.utc), "amount": amount,
            "flow_type": kind, "account_name": name}


@pytest.fixture(autouse=True)
def book_pool():
    """R-IV.484(c) — net_profit/win_rate now read `unified_positions`. Default: an empty book,
    so every test not about the live book gets None/0 there rather than touching conftest's
    unconfigured mock pool. `patch_book(rows)` inside a test overrides this for the duration."""
    pool = _FakePool([])
    with patch("api.abacus.get_postgres_client", new=AsyncMock(return_value=pool)):
        yield pool


def _patch_book(rows, snapshots=None, cash=None, closures=None, fallback=None, dropped=None):
    pool = _FakePool(rows, snapshots, cash, closures, fallback, dropped)
    return pool, patch("api.abacus.get_postgres_client", new=AsyncMock(return_value=pool))


class TestAbacusSummaryGate:
    def test_no_credentials_is_401(self, client):
        assert client.get(PATH).status_code == 401

    def test_wrong_key_is_401(self, client):
        assert client.get(PATH, headers={"X-API-Key": "wrong"}).status_code == 401

    def test_machine_key_accepted(self, client, test_api_key):
        assert _get(client, test_api_key).status_code == 200

    def test_session_cookie_accepted(self, client):
        from utils.session import issue_session, COOKIE_NAME
        token = issue_session()
        assert token
        assert client.get(PATH, cookies={COOKIE_NAME: token}).status_code == 200


class TestAbacusSummaryContract:
    def test_mock_is_declared_on_every_block_that_is_still_the_fixture(self, client, test_api_key):
        """R-IV.705(g): what is still fixture data says so. The boundary moved -- scope, the
        equity curves and four of the five breakdowns went live -- and the test moved with it
        rather than being deleted: anything NOT in the live set must still declare itself mock."""
        d = _get(client, test_api_key).json()
        assert d["mock"] is True
        mock_blocks = [d["leaks"], d["strategies"],
                       *(s for s in d["stats"] if s["key"] not in LIVE_KEYS),
                       *(b for b in d["breakdowns"] if b["key"] in MOCK_BLOCK_KEYS)]
        assert mock_blocks, "no blocks to check"
        for b in mock_blocks:
            assert b["source"] == "mock", b.get("key") or b.get("label")
            assert b["computed_at"], b.get("key") or b.get("label")
        for b in [d["scope"], d["equity"],
                  *(b for b in d["breakdowns"] if b["key"] not in MOCK_BLOCK_KEYS)]:
            assert b["source"] == "live", b.get("key") or b.get("label")

    def test_net_profit_and_win_rate_are_live(self, client, test_api_key):
        from api.abacus import FIXTURE_AUTHORED_AT
        d = _get(client, test_api_key).json()
        for key in LIVE_KEYS:
            s = _stat(d, key)
            assert s["source"] == "live", key
            assert s["computed_at"] and s["computed_at"] != FIXTURE_AUTHORED_AT, key
            if key in WITHHELD_KEYS:
                # A withheld figure carries its reason instead of a coverage block: there is no
                # sample to describe, because the field it would be drawn from is wrong.
                assert s["value"] is None and s["unavailable"], key
                continue
            assert s["coverage"]["predicate"], key

    def test_computed_at_is_the_authored_instant_not_now(self, client, test_api_key):
        """A mock stamped "now" would read as fresh. Scope and the equity curves are live since
        R-IV.705 and are stamped with the read, so what is checked here is what is still fixture:
        its stamp must stay the instant it was AUTHORED."""
        from api.abacus import FIXTURE_AUTHORED_AT
        d = _get(client, test_api_key).json()
        stamps = {d["leaks"]["computed_at"], d["strategies"]["computed_at"],
                  *(s["computed_at"] for s in d["stats"] if s["key"] not in LIVE_KEYS),
                  *(b["computed_at"] for b in d["breakdowns"] if b["key"] in MOCK_BLOCK_KEYS)}
        assert stamps == {FIXTURE_AUTHORED_AT}

    def test_rates_carry_n(self, client, test_api_key):
        rows = [_row(10.0), _row(-4.0), _row(3.0)]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        win = next(s for s in d["stats"] if s["key"] == "win_rate")
        assert win["format"] == "pct" and win["n"] == 3

    def test_unknown_is_none_not_zero(self, client, test_api_key):
        d = _get(client, test_api_key).json()
        for row in d["strategies"]["rows"]:
            assert row[1:5] == [None, None, None, None], row

    def test_equity_is_one_curve_per_account_each_with_its_own_span(self, client, test_api_key):
        """R-IV.705(c): the single mock curve is gone. Each account carries its own points, its
        own first and last day, and its own day count -- the 401(a)'s curve cannot start where
        the Roth's does."""
        d = _get(client, test_api_key).json()
        accts = d["equity"]["accounts"]
        assert accts and "points" not in d["equity"]
        for a in accts:
            assert a["account"] and ("account_display" in a)
            assert a["days"] == len(a["points"])
            if a["points"]:
                assert a["from"] == a["points"][0]["d"] and a["to"] == a["points"][-1]["d"]

    def test_drawdown_and_sharpe_are_not_tiles(self, client, test_api_key):
        """R-IV.705(d): they are properties of a curve, and the curves have different spans and
        different cash coverage, so a single top-level figure has no denominator."""
        keys = {s["key"] for s in d_stats(client, test_api_key)}
        assert "max_drawdown" not in keys and "sharpe" not in keys, keys

    def test_breakdown_rows_match_columns(self, client, test_api_key):
        d = _get(client, test_api_key).json()
        for t in [*d["breakdowns"], d["strategies"]]:
            for row in t["rows"]:
                assert len(row) == len(t["columns"]), (t.get("key"), row)

    def test_fixture_is_not_mutated_across_requests(self, client, test_api_key):
        _get(client, test_api_key, "?from=2026-01-01&to=2026-02-01")
        d = _get(client, test_api_key).json()
        assert d["range"]["key"] == "90d"


class TestAbacusSummaryRange:
    @pytest.mark.parametrize("key", ["30d", "90d", "ytd", "all"])
    def test_preset_is_echoed(self, client, test_api_key, key):
        d = _get(client, test_api_key, f"?range={key}").json()
        assert d["range"]["key"] == key
        assert d["range_applied"] is True

    def test_all_has_no_start(self, client, test_api_key):
        assert _get(client, test_api_key, "?range=all").json()["range"]["from"] is None

    def test_explicit_dates_win(self, client, test_api_key):
        d = _get(client, test_api_key, "?range=30d&from=2026-06-18&to=2026-09-16").json()
        assert d["range"] == {"key": "custom", "from": "2026-06-18", "to": "2026-09-16"}

    def test_bad_range_is_rejected(self, client, test_api_key):
        assert _get(client, test_api_key, "?range=7y").status_code == 422

    def test_inverted_dates_are_rejected(self, client, test_api_key):
        assert _get(client, test_api_key, "?from=2026-09-16&to=2026-06-18").status_code == 422


def d_stats(client, test_api_key):
    return _get(client, test_api_key).json()["stats"]


def _stat(d, key):
    return next(s for s in d["stats"] if s["key"] == key)


QUERIES = ["?range=30d", "?range=90d", "?range=ytd", "?range=all",
           "?from=2026-09-10&to=2026-09-11", "?from=2020-01-01&to=2020-02-01",
           "?from=2025-01-01&to=2026-09-16"]


class TestAbacusSummaryScaling:
    """Charter D2: the range changes the figures, server-side, and every range stays coherent."""

    def test_the_window_reaches_the_live_query_at_every_range(self, client, test_api_key):
        """R-IV.705(b): the figures that used to SCALE now come from a windowed read, so what
        this pins is that the window reaches the query -- the thing the scaling rule stood in
        for while the page was a fixture."""
        for q in QUERIES[:4]:
            pool, p = _patch_book([])
            with p:
                _get(client, test_api_key, q)
            census = [c for c in pool.calls if "unified_positions" in c[0]]
            assert census, q
            # R-IV.726: the window compares the DAY the close DENOTES, not a bare `::date` cast. A
            # cast with no conversion reads a 9 PM Mountain close as the next day, which at a range
            # boundary moves a trade into the wrong window.
            sql = census[0][0]
            assert "AT TIME ZONE 'America/Denver'" in sql and "<= $1" in sql, q
            assert "exit_date::date <=" not in sql, q

    def test_a_range_with_no_closes_is_null_not_zero(self, client, test_api_key):
        """The sharpest case for a live page: a window the book has nothing in. Every figure is
        None -- "no trade here can be measured" is not "the result was nothing"."""
        pool, p = _patch_book([])
        with p:
            d = _get(client, test_api_key, "?from=2020-01-01&to=2020-02-01").json()
        for key in ("net_profit", "expectancy", "profit_factor", "avg_win_loss", "loss_vs_risk",
                    "win_rate", "expected_return"):
            assert _stat(d, key)["value"] is None, key
        assert d["scope"]["closed_positions"] == 0
        for b in d["breakdowns"]:
            if b["key"] not in MOCK_BLOCK_KEYS:
                assert b["rows"] == [], b["key"]

    @pytest.mark.parametrize("q", QUERIES)
    def test_every_range_is_self_consistent(self, client, test_api_key, q):
        d = _get(client, test_api_key, q).json()
        assert d["scope"]["closed_positions"] >= 0
        for a in d["equity"]["accounts"]:
            assert a["days"] == len(a["points"])

    @pytest.mark.parametrize("q", QUERIES)
    def test_rates_stay_rates_at_every_range(self, client, test_api_key, q):
        """A rate is a fraction of 0..1 whatever the window, and a null rate stays null."""
        d = _get(client, test_api_key, q).json()
        for key in ("win_rate", "loss_vs_risk"):
            v = _stat(d, key)["value"]
            assert v is None or 0.0 <= v <= 1.0, (key, v)
        for b in d["breakdowns"]:
            if b["key"] in MOCK_BLOCK_KEYS:
                continue
            wins = [r[2] for r in b["rows"]] if any(c[0] == "Win" for c in b["columns"]) else []
            assert all(w is None or 0.0 <= w <= 1.0 for w in wins), (b["key"], wins)

    @pytest.mark.parametrize("q", QUERIES)
    def test_counts_stay_whole_and_positive(self, client, test_api_key, q):
        d = _get(client, test_api_key, q).json()
        for it in d["leaks"]["items"]:
            # A LIVE count may legitimately be 0 -- nothing untagged since the cutoff in this
            # window -- and forcing it to 1 would be requiring a fiction. Mock items keep the
            # old floor, because a fixture with a zero in it is just a badly written fixture.
            floor = 0 if it.get("source") == "live" else 1
            assert isinstance(it["n"], int) and it["n"] >= floor, it["label"]
        for b in d["breakdowns"]:
            for i, (_, kind) in enumerate(b["columns"]):
                if kind == "int":
                    assert all(isinstance(r[i], int) and r[i] >= 1 for r in b["rows"]), (q, b["key"])

    @pytest.mark.parametrize("q", QUERIES)
    def test_a_drawdown_is_dated_inside_ITS_OWN_curve(self, client, test_api_key, q):
        """R-IV.705(c): each curve carries its own span, so a drawdown is bounded by the curve it
        was measured on -- not by the page's range, which no longer governs the snapshots."""
        for a in _get(client, test_api_key, q).json()["equity"]["accounts"]:
            dd = a.get("drawdown")
            if not dd:
                continue
            assert a["from"] <= dd["from"] <= dd["to"] <= a["to"], (a["account"], dd)
            assert 0 <= dd["from_index"] <= dd["to_index"] < len(a["points"]), (a["account"], dd)

    def test_unknown_stays_none_at_every_range(self, client, test_api_key):
        for q in QUERIES:
            for row in _get(client, test_api_key, q).json()["strategies"]["rows"]:
                assert row[1:5] == [None, None, None, None], (q, row)

    def test_version_is_declared(self, client, test_api_key):
        from api.abacus import SUMMARY_VERSION
        assert _get(client, test_api_key).json()["version"] == SUMMARY_VERSION == 1

    def test_leak_prose_carries_no_counts(self, client, test_api_key):
        """Counts live in `n` (R2); a count inside the prose would not scale with the range."""
        import re
        for it in _get(client, test_api_key, "?range=30d").json()["leaks"]["items"]:
            assert not re.search(r"\b\d+\s+(adds|bought|held past|with no)\b", it["detail"]), it["detail"]


class TestAbacusLiveBook:
    """R-IV.484(c): net_profit and win_rate read the book. Census predicate
    LOWER(status) IN ('closed','expired'), windowed on exit_date; basis-incomplete and
    sub -100%-of-basis rows are counted but never averaged in; a book that never recorded
    realized_pnl on a row is excluded the same way, never treated as a $0 trade."""

    def test_empty_book_is_null_not_zero(self, client, test_api_key):
        """The default fixture (no rows) -- unknown must read null, never 0.00 or 0%."""
        d = _get(client, test_api_key).json()
        net, win = _stat(d, "net_profit"), _stat(d, "win_rate")
        assert net["value"] is None and win["value"] is None
        assert win["n"] == 0
        assert net["coverage"] == win["coverage"] == {
            "predicate": "LOWER(status) IN ('closed','expired'), windowed on exit_date",
            # R-IV.761(b): the predicate governs the RATES, not net_profit, and says so.
            "predicate_scope": "win_rate and expected_return only; net_profit has its own",
            "total": 0, "counted": 0,
            "excluded": {"basis_incomplete": 0, "return_below_neg100pct": 0, "no_realized_pnl": 0},
        }

    def test_counted_rows_sum_and_win_rate(self, client, test_api_key):
        rows = [_row(100.0), _row(-40.0), _row(0.0), _row(25.0)]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        net, win = _stat(d, "net_profit"), _stat(d, "win_rate")
        assert net["value"] == 85.0
        assert win["n"] == 4 and win["value"] == 0.5  # 2 of 4 strictly positive
        assert net["coverage"]["total"] == net["coverage"]["counted"] == 4

    def test_basis_incomplete_rows_are_excluded_not_averaged_in(self, client, test_api_key):
        rows = [_row(100.0), _row(9999.0, basis_incomplete_reason="R-IV.456(a) third leg unrecorded")]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        net, win = _stat(d, "net_profit"), _stat(d, "win_rate")
        # R-IV.761(b) CHANGED THIS. The guard now protects the RATES, not the money.
        # net_profit reads the closures ledger -- actual per-lot proceeds less actual cost -- and
        # a row whose BASIS is incomplete still moved real money. Excluding it under-reported the
        # book, which is the family of bug R-IV.761(b) exists to fix.
        # The flagged row is still kept out of win_rate and expected_return, where an unmeasurable
        # return genuinely cannot be averaged, and `coverage.excluded` still counts it.
        assert net["value"] == 10099.0, "the money counts; the RATE is what excludes it"
        assert win["n"] == 1, "the flagged row is still out of the rate"
        assert net["coverage"]["total"] == 2
        assert net["coverage"]["counted"] == 1
        assert net["coverage"]["excluded"]["basis_incomplete"] == 1

    def test_return_below_neg100pct_is_excluded_not_averaged_in(self, client, test_api_key):
        # -150 on a 100 basis is a -150% return: past total loss, a data-integrity signal.
        rows = [_row(50.0, basis=200.0), _row(-150.0, basis=100.0)]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        net, win = _stat(d, "net_profit"), _stat(d, "win_rate")
        # R-IV.761(b) CHANGED THIS, and the live book is why: two rows return below -100% of
        # their basis, carrying -167.78 between them (measured 2026-10-08). A return past -100%
        # means the BASIS is understated, not that the loss is fictional -- and R-IV.761(b)'s
        # control of 3,607.73 counts those rows. Dropping real losses to protect a ratio would
        # make the book read better than it is.
        assert net["value"] == -100.0, "50 + (-150): the money counts"
        assert win["n"] == 1, "the impossible-return row is still out of the rate"
        assert net["coverage"]["excluded"]["return_below_neg100pct"] == 1

    def test_return_exactly_neg100pct_is_not_flagged(self, client, test_api_key):
        """A full loss of the stated basis is a real result, not a data-integrity signal --
        only a return that overshoots -100% is impossible and gets flagged."""
        rows = [_row(-100.0, basis=100.0)]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        net = _stat(d, "net_profit")
        assert net["value"] == -100.0
        assert net["coverage"]["excluded"]["return_below_neg100pct"] == 0

    def test_unrecorded_realized_pnl_is_excluded_not_zero(self, client, test_api_key):
        """A closed row with no realized_pnl at all is the book never having recorded it --
        excluded from both the sum and the win-rate denominator, never counted as a $0 loss."""
        rows = [_row(60.0), _row(None)]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        net, win = _stat(d, "net_profit"), _stat(d, "win_rate")
        assert net["value"] == 60.0
        assert win["n"] == 1
        assert net["coverage"]["excluded"]["no_realized_pnl"] == 1

    def test_return_check_is_skipped_without_a_basis(self, client, test_api_key):
        """A row with a real realized_pnl but no cost_basis to divide by can't have its return
        checked -- it must still count (nothing here says it's wrong), not be silently dropped."""
        rows = [_row(-9000.0, basis=None)]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        net = _stat(d, "net_profit")
        assert net["value"] == -9000.0
        assert net["coverage"]["counted"] == 1
        assert net["coverage"]["excluded"]["return_below_neg100pct"] == 0

    def test_predicate_and_window(self, client, test_api_key):
        pool, p = _patch_book([])
        with p:
            _get(client, test_api_key, "?from=2026-06-18&to=2026-09-16")
        # The route reads three tables now, so the census call is found by name rather than by
        # position. `calls[-1]` is the cash-event query.
        sql, params = next(c for c in pool.calls if "unified_positions" in c[0])
        assert "LOWER(status) IN ('closed', 'expired')" in sql, sql
        assert "exit_date" in sql
        from datetime import date
        assert params == (date(2026, 9, 16), date(2026, 6, 18))

    def test_all_range_has_no_lower_bound_on_the_query(self, client, test_api_key):
        """range=all must not clamp to the mock book's fake start date -- that's a fixture-only
        artifact and has no place gating a real query."""
        pool, p = _patch_book([])
        with p:
            _get(client, test_api_key, "?range=all")
        sql, params = next(c for c in pool.calls if "unified_positions" in c[0])
        assert len(params) == 1, "no lower-bound param when the range is open-ended"


class TestAbacusR705:
    """R-IV.705 — the figures that went live, and the three things that keep them honest:
    every figure carries its n and its span, every curve carries its own span, and a return is
    net of recorded cash before anything calls it performance."""

    def test_the_new_stats_are_live_with_their_n_and_their_span(self, client, test_api_key):
        rows = [_row(100.0, basis=200.0), _row(-40.0, basis=100.0), _row(60.0, basis=150.0)]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        for key in ("expectancy", "profit_factor", "avg_win_loss"):
            st = _stat(d, key)
            assert st["source"] == "live", key
            assert st["n"] is not None, key
            assert "span" in st, key
        assert _stat(d, "expectancy")["value"] == 40.0          # (100 - 40 + 60) / 3
        assert _stat(d, "profit_factor")["value"] == 4.0        # 160 won / 40 lost
        assert _stat(d, "avg_win_loss")["value"] == [80.0, -40.0]
        assert _stat(d, "expectancy")["span"] == {"from": "2026-09-10", "to": "2026-09-10"}

    def test_profit_factor_is_null_not_huge_when_nothing_lost(self, client, test_api_key):
        pool, p = _patch_book([_row(10.0), _row(5.0)])
        with p:
            d = _get(client, test_api_key).json()
        assert _stat(d, "profit_factor")["value"] is None
        assert _stat(d, "profit_factor")["n"] == 2

    def test_loss_vs_risk_is_withheld_while_max_loss_is_unreliable(self, client, test_api_key):
        """R-IV.716(c). The strong form: rows that WOULD produce a clean 0.5 still yield no figure.

        It was served under R-IV.705(g) with its own n, which answered how MANY rows carry a max
        loss and not whether the values are right. They are not: on the closed side this page reads,
        31 losing trades are recorded as having lost MORE than their own defined maximum, which
        cannot happen to a defined-risk trade. A rate whose denominator is wrong is not improved by
        publishing its n."""
        rows = [_row(-50.0, max_loss=100.0), _row(-30.0, max_loss=None), _row(20.0)]
        pool, p = _patch_book(rows)
        with p:
            st = _stat(_get(client, test_api_key).json(), "loss_vs_risk")
        assert st["value"] is None, "no figure from max_loss reaches the page"
        assert st["n"] is None, "and no n either: an n beside no figure invites one to be inferred"
        assert st["unavailable"] == "max loss not reliable yet"
        assert "R-IV.714(d)" in st["meaning"], "it says what has to land before it returns"
        assert "coverage" not in st, "there is no sample to describe"

    def test_no_other_stat_is_drawn_from_max_loss(self, client, test_api_key):
        """The field is quarantined, not just hidden on one tile."""
        # One distinctive max_loss, and nothing else in the payload that could produce it. The first
        # version of this check also forbade 0.5, which a two-trade win rate legitimately IS -- a
        # sentinel has to be a value no honest computation can reach.
        rows = [_row(-50.0, max_loss=31337.0), _row(20.0, max_loss=31337.0)]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        import json as _json
        for st in d["stats"]:
            if st["key"] == "loss_vs_risk":
                continue
            assert "31337" not in _json.dumps(st.get("value")), st["key"]

    def test_the_four_breakdowns_are_live_and_discipline_still_says_sample(self, client, test_api_key):
        import datetime as dt
        rows = [_row(10.0, structure="put_debit_spread", ticker="SPY",
                     entry=dt.datetime(2026, 9, 1, 15, tzinfo=dt.timezone.utc),
                     exit=dt.datetime(2026, 9, 1, 20, tzinfo=dt.timezone.utc)),
                _row(-5.0, structure="stock", ticker="XLE",
                     entry=dt.datetime(2026, 8, 3, 15, tzinfo=dt.timezone.utc),
                     exit=dt.datetime(2026, 9, 25, 20, tzinfo=dt.timezone.utc))]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        keys = [b["key"] for b in d["breakdowns"]]
        assert keys == ["structure", "ticker", "hold", "weekday", "discipline"], keys
        bd = {b["key"]: b for b in d["breakdowns"]}
        for k in ("structure", "ticker", "hold", "weekday"):
            assert bd[k]["source"] == "live", k
            assert bd[k]["rows"], k
        assert [r[0] for r in bd["ticker"]["rows"]] == ["SPY", "XLE"]
        # A same-day close and a 53-day hold land in their own buckets, in the declared order.
        held = {r[0]: r[1] for r in bd["hold"]["rows"]}
        assert held == {"Same day": 1, "Over 45 days": 1}, held
        # Opened Tuesday (2026-09-01) and Monday (2026-08-03), in Mountain Time.
        assert {r[0] for r in bd["weekday"]["rows"]} == {"Tuesday", "Monday"}
        assert bd["discipline"]["source"] == "mock"
        assert "Sample data" in bd["discipline"]["note"]

    def test_the_scope_line_names_the_accounts_and_never_a_key(self, client, test_api_key):
        from models.accounts import CANONICAL_ACCOUNTS
        d = _get(client, test_api_key).json()
        label = d["scope"]["label"]
        assert d["scope"]["accounts"] == len(CANONICAL_ACCOUNTS) == 3
        assert "Both accounts" not in label
        for key in CANONICAL_ACCOUNTS:
            assert key not in label, label

    def test_the_untagged_leak_counts_only_rows_opened_since_the_cutoff(self, client, test_api_key):
        """R-IV.705(f). Buckets began at TA-058's cutoff, so a row closed before it is untagged
        BY DESIGN -- counting it would indict the principal for a field that did not exist."""
        import datetime as dt
        from api.abacus import BUCKET_CUTOFF
        before = dt.datetime(2026, 9, 1, 15, tzinfo=dt.timezone.utc)
        after = dt.datetime(2026, 9, 26, 15, tzinfo=dt.timezone.utc)
        rows = [_row(1.0, entry=before, strategy_tag=None),      # pre-cutoff, untagged by design
                _row(1.0, entry=before, strategy_tag=None),
                _row(1.0, entry=after, strategy_tag=None),       # the only one that owes a bucket
                _row(1.0, entry=after, strategy_tag="B2")]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        it = next(i for i in d["leaks"]["items"] if "Untagged" in i["label"])
        assert it["n"] == 1, "only the post-cutoff untagged row counts"
        assert it["of_n"] == 2, "and it is counted against the post-cutoff population"
        assert it["source"] == "live"
        assert it["amount"] is None, "a missing tag has no dollar cost of its own"
        assert BUCKET_CUTOFF.isoformat() in it["detail"]
        assert "POSITIONS.md" in it["detail"], "the cutoff is cited, not asserted"

    def test_the_other_leaks_say_sample_data_on_their_face(self, client, test_api_key):
        d = _get(client, test_api_key).json()
        others = [i for i in d["leaks"]["items"] if "Untagged" not in i["label"]]
        assert len(others) == 5
        for it in others:
            assert it["source"] == "mock", it["label"]
            assert it["detail"].startswith("Sample data"), it["label"]

    def test_no_signal_outcome_figure_reaches_the_page(self, client, test_api_key):
        """R-IV.705(e): that table holds sealed-holdout and blind-window Triton rows, so no hit
        rate and no n from it appears here. The note names the real gap instead."""
        rows = [_row(1.0, signal_id="sig-1"), _row(1.0), _row(1.0)]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        note = d["strategies"]["note"]
        assert "not linked" in note and "signal id is recorded on 1 of the 3" in note, note
        assert "hit rate" not in note.lower()
        for row in d["strategies"]["rows"]:
            assert row[1:5] == [None, None, None, None], row
        assert not any("signal_outcomes" in c[0] for c in pool.calls), "this page never reads it"


class TestAbacusEquityCurve:
    """R-IV.705(c)/(d) — the spelling trap, and the deposit trap."""

    def test_the_roths_curve_reads_every_spelling_it_was_stored_under(self, client, test_api_key):
        """CONTROL (R-IV.705(c)1): `balance_snapshots.account_name` changed vocabulary on
        2026-08-27. Read on the canonical key alone, the Roth's curve is cut to its last weeks
        while looking complete. `scope_sql` matches every spelling it was stored under."""
        snaps = [_snap((2026, 3, 20), 8000.0, "Fidelity Roth"),
                 _snap((2026, 6, 15), 8500.0, "Fidelity Roth"),
                 _snap((2026, 8, 27), 8800.0, "FIDELITY_ROTH"),
                 _snap((2026, 9, 30), 9000.0, "FIDELITY_ROTH")]
        pool, p = _patch_book([], snapshots=snaps, cash=[_cash((2026, 3, 1), 500.0)])
        with p:
            d = _get(client, test_api_key).json()
        roth = next(a for a in d["equity"]["accounts"] if a["account"] == "FIDELITY_ROTH")
        assert roth["days"] == 4, "all four days, not the two under the new spelling"
        assert roth["from"] == "2026-03-20"
        assert set(roth["spellings_read"]) == {"Fidelity Roth", "FIDELITY_ROTH"}
        sql = next(c[0] for c in pool.calls if "balance_snapshots" in c[0])
        assert "UPPER(account_name) = ANY" in sql, sql

    def test_the_401a_reads_no_historical_spelling_at_all(self, client, test_api_key):
        """CONTROL (R-IV.705(c)2): 'Fidelity 401A' names the PARKED mutual-fund money, a
        different pot. FIDELITY_401A has no historical spellings by design, so those rows join
        no curve -- which is why `normalize_account` must not be used here: its key folding
        would resolve them into this account."""
        from models.accounts import scope_for
        assert scope_for("FIDELITY_401A") == ["FIDELITY_401A"]
        spellings = [s.upper() for s in scope_for("FIDELITY_401A")]
        assert "FIDELITY 401A" not in spellings, "the parked money must not be reachable"

    def test_a_partly_covered_curve_is_measured_over_the_part_the_ledger_covers(self, client, test_api_key):
        """R-IV.709(b). Refusing the figures outright threw away five months of the Roth's history
        to protect twenty-one days of it. The figures are now measured over the covered span, and
        the card says WHICH span and which days are left out."""
        snaps = [_snap((2026, 3, 20), 8000.0, "FIDELITY_ROTH"),      # before the ledger: excluded
                 _snap((2026, 3, 25), 8100.0, "FIDELITY_ROTH"),      # before the ledger: excluded
                 _snap((2026, 4, 20), 9000.0, "FIDELITY_ROTH"),      # the covered span starts here
                 _snap((2026, 5, 20), 8100.0, "FIDELITY_ROTH"),
                 _snap((2026, 6, 20), 8500.0, "FIDELITY_ROTH")]
        cash = [_cash((2026, 4, 10), 1000.0, "ACH", "FIDELITY_ROTH")]
        pool, p = _patch_book([], snapshots=snaps, cash=cash)
        with p:
            d = _get(client, test_api_key).json()
        a = next(x for x in d["equity"]["accounts"] if x["account"] == "FIDELITY_ROTH")
        assert a["off_reason"] is None, a["off_reason"]
        cov = a["covered"]
        assert cov["from"] == "2026-04-20" and cov["to"] == "2026-06-20"
        assert cov["days"] == 3 and cov["excluded_days"] == 2
        assert "2026-04-10" in cov["reason"]
        # The whole balance line is still drawn -- it is his money -- and the drawdown found inside
        # the covered span points at the right place ON THAT FULL LINE.
        assert a["days"] == 5 and len(a["points"]) == 5
        assert a["drawdown"]["from_index"] == 2 and a["drawdown"]["to_index"] == 3
        assert a["drawdown"]["from"] == "2026-04-20" and a["drawdown"]["to"] == "2026-05-20"
        assert a["cash"]["spans"] is False, "the ledger does not cover the whole curve, and says so"
        assert a["line_label"] == "balance — includes deposits/withdrawals"

    def test_the_excluded_days_are_never_in_a_return(self, client, test_api_key):
        """The point of the exclusion: the 8000 -> 8100 move before the ledger begins must not
        appear as a gain, because nothing says it was not a deposit."""
        snaps = [_snap((2026, 3, 20), 8000.0, "FIDELITY_ROTH"),
                 _snap((2026, 3, 25), 8100.0, "FIDELITY_ROTH"),
                 _snap((2026, 4, 20), 8100.0, "FIDELITY_ROTH"),
                 _snap((2026, 5, 20), 8100.0, "FIDELITY_ROTH")]
        cash = [_cash((2026, 4, 10), 50.0, "ACH", "FIDELITY_ROTH")]
        pool, p = _patch_book([], snapshots=snaps, cash=cash)
        with p:
            d = _get(client, test_api_key).json()
        a = next(x for x in d["equity"]["accounts"] if x["account"] == "FIDELITY_ROTH")
        assert a["drawdown"] is None, "flat across the covered span: no fall, and no pre-ledger gain"
        assert a["sharpe"]["n"] == 1, "one return inside the covered span, not three"

    def test_a_curve_with_no_snapshot_after_the_ledger_begins_still_says_so(self, client, test_api_key):
        snaps = [_snap((2026, 3, 20), 8000.0, "FIDELITY_ROTH"),
                 _snap((2026, 3, 25), 8100.0, "FIDELITY_ROTH")]
        cash = [_cash((2026, 4, 10), 50.0, "ACH", "FIDELITY_ROTH")]
        pool, p = _patch_book([], snapshots=snaps, cash=cash)
        with p:
            d = _get(client, test_api_key).json()
        a = next(x for x in d["equity"]["accounts"] if x["account"] == "FIDELITY_ROTH")
        assert a["sharpe"] is None and a["drawdown"] is None
        assert "no later balance snapshot" in a["off_reason"], a["off_reason"]

    def test_no_sharpe_under_thirty_returns(self, client, test_api_key):
        """R-IV.709(c): a hard floor on every account and every span. A Sharpe ratio from four
        points has the authority of a statistic and the content of noise."""
        from api.abacus import SHARPE_MIN_N
        assert SHARPE_MIN_N == 30
        short = _series((2026, 1, 2), [1000 + 10 * i for i in range(10)])
        pool, p = _patch_book([], snapshots=short, cash=[_cash((2026, 1, 1), 10.0)])
        with p:
            d = _get(client, test_api_key).json()
        a = next(x for x in d["equity"]["accounts"] if x["account"] == "ROBINHOOD")
        assert a["sharpe"]["value"] is None and a["sharpe"]["insufficient"] is True
        assert a["sharpe"]["n"] == 9, "the count stands in the figure's place"
        assert a["drawdown"] is None or a["drawdown"]["pct"] < 0, "a FALL is an observation, served at any length"

    def test_thirty_returns_is_enough(self, client, test_api_key):
        vals = [1000.0]
        for i in range(30):
            vals.append(vals[-1] * (1.002 if i % 3 else 0.999))
        pool, p = _patch_book([], snapshots=_series((2026, 1, 2), vals),
                              cash=[_cash((2026, 1, 1), 10.0)])
        with p:
            d = _get(client, test_api_key).json()
        a = next(x for x in d["equity"]["accounts"] if x["account"] == "ROBINHOOD")
        assert a["sharpe"]["n"] == 30 and a["sharpe"]["insufficient"] is False
        assert isinstance(a["sharpe"]["value"], float)

    def test_a_deposit_is_not_a_gain(self, client, test_api_key):
        """The whole point of (d), in one case: a flat account that receives a deposit shows no
        return for that day. Thirty-one snapshots, because the Sharpe floor (R-IV.709(c)) is where
        this is now provable: if the deposit counted as a gain the returns would have a spread and
        a positive ratio; netted out they are all zero, and there is nothing to divide by."""
        vals = [1000.0] + [2000.0] * 30           # a flat account, doubled by a deposit on day 2
        snaps = _series((2026, 1, 2), vals)
        cash = [_cash((2026, 1, 1), 1000.0), _cash((2026, 1, 3), 1000.0)]
        pool, p = _patch_book([], snapshots=snaps, cash=cash)
        with p:
            d = _get(client, test_api_key).json()
        rh = next(a for a in d["equity"]["accounts"] if a["account"] == "ROBINHOOD")
        assert rh["cash"]["spans"] is True, rh.get("off_reason")
        assert rh["drawdown"] is None, "the deposit day is not a 100% gain, and no fall followed"
        assert rh["sharpe"]["n"] == 30
        assert rh["sharpe"]["value"] is None, "every return is zero: no spread to divide a mean by"
        assert rh["sharpe"].get("no_spread") is True, rh["sharpe"]

    def test_an_unclassifiable_cash_event_fails_closed(self, client, test_api_key):
        """A flow type this page cannot call a deposit or an earning must not join a return
        series silently. It fails the coverage test BY NAME."""
        snaps = [_snap((2026, 1, 2), 1000.0), _snap((2026, 1, 3), 1100.0)]
        cash = [_cash((2026, 1, 1), 50.0, "ACH"), _cash((2026, 1, 3), 50.0, "MYSTERY_TYPE")]
        pool, p = _patch_book([], snapshots=snaps, cash=cash)
        with p:
            d = _get(client, test_api_key).json()
        rh = next(a for a in d["equity"]["accounts"] if a["account"] == "ROBINHOOD")
        assert rh["sharpe"] is None and rh["drawdown"] is None
        assert rh["covered"] is None, "a curve with no trustworthy ledger has no covered span either"
        assert "MYSTERY_TYPE" in rh["off_reason"]

    def test_a_dividend_is_not_netted_out(self, client, test_api_key):
        """Subtracting what the account EARNED would understate the return as surely as leaving a
        deposit in overstates it. A dividend stays in, and the SIGN of the Sharpe is what proves
        it: keeping the dividend makes the mean return positive, netting it out makes it
        negative."""
        # Flat but for one +10 day, which the ledger records as a DIVIDEND. Kept, the returns have a
        # spread and a positive ratio; netted out, every return is zero and there is nothing to
        # divide by -- so the two readings are told apart by whether a Sharpe exists at all.
        vals = [1000.0] + [1010.0] * 30
        snaps = _series((2026, 1, 2), vals)
        cash = [_cash((2026, 1, 1), 10.0, "ACH"), _cash((2026, 1, 3), 10.0, "DIVIDEND")]
        pool, p = _patch_book([], snapshots=snaps, cash=cash)
        with p:
            d = _get(client, test_api_key).json()
        rh = next(a for a in d["equity"]["accounts"] if a["account"] == "ROBINHOOD")
        assert rh["cash"]["spans"] is True, rh.get("off_reason")
        assert rh["sharpe"]["n"] == 30
        assert rh["sharpe"]["value"] > 0, "netting the dividend out would leave no spread at all"

    def test_an_account_with_no_snapshots_says_so(self, client, test_api_key):
        d = _get(client, test_api_key).json()
        for a in d["equity"]["accounts"]:
            assert a["points"] == [] and a["off_reason"]


class TestAbacusDayVsMoment:
    """R-IV.726 — `entry_date` and `exit_date` hold BOTH a day and a moment, so the rule is per
    value. WRTH (948) is the case that exposed it: stored `2026-10-01 00:00:00+00`, which the old
    rule converted to 6 PM on 09-30, and I reported 09-30 while both Fidelity exports and the row's
    own position_id said 10-01."""

    def test_a_day_at_midnight_utc_keeps_its_day(self, client, test_api_key):
        from api.abacus import _day_of
        import datetime as dt
        wrth = dt.datetime(2026, 10, 1, 0, 0, 0, tzinfo=dt.timezone.utc)
        assert _day_of(wrth) == dt.date(2026, 10, 1), "converting a day moves it backwards"

    def test_a_moment_is_the_principals_day_not_the_servers(self, client, test_api_key):
        from api.abacus import _day_of
        import datetime as dt
        # 01:30 UTC on the 2nd is 7:30 PM Mountain on the 1st: his day, not the server's.
        assert _day_of(dt.datetime(2026, 10, 2, 1, 30, tzinfo=dt.timezone.utc)) == dt.date(2026, 10, 1)
        # And an ordinary afternoon fill lands on the same day either way.
        assert _day_of(dt.datetime(2026, 10, 1, 17, 36, 47, tzinfo=dt.timezone.utc)) == dt.date(2026, 10, 1)

    def test_a_day_at_mountain_midnight_also_keeps_its_day(self, client, test_api_key):
        """`snapshot_date` and `activity_date` are stored at Mountain midnight (06:00/07:00Z). The
        one rule has to be right for them too, which is why it replaced both earlier helpers."""
        from api.abacus import _day_of
        import datetime as dt
        assert _day_of(dt.datetime(2026, 3, 20, 6, 0, tzinfo=dt.timezone.utc)) == dt.date(2026, 3, 20)
        assert _day_of(dt.datetime(2026, 1, 15, 7, 0, tzinfo=dt.timezone.utc)) == dt.date(2026, 1, 15)

    def test_the_weekday_is_the_day_the_row_denotes(self, client, test_api_key):
        """The breakdown this corrects. A Thursday stored at midnight UTC was being reported as a
        Wednesday, and 453 of 554 counted rows were in that shape."""
        import datetime as dt
        rows = [_row(10.0, entry=dt.datetime(2026, 10, 1, 0, 0, tzinfo=dt.timezone.utc),   # Thursday
                     exit=dt.datetime(2026, 10, 1, 0, 0, tzinfo=dt.timezone.utc))]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        wd = next(b for b in d["breakdowns"] if b["key"] == "weekday")
        assert [r[0] for r in wd["rows"]] == ["Thursday"], wd["rows"]
        hold = next(b for b in d["breakdowns"] if b["key"] == "hold")
        assert [r[0] for r in hold["rows"]] == ["Same day"], hold["rows"]

    def test_a_day_and_a_moment_in_one_row_still_measure_one_hold(self, client, test_api_key):
        """The mixed row is where the old rule did its worst: a day converted backwards against a
        moment converted correctly gave a hold a day too long — or negative."""
        import datetime as dt
        rows = [_row(10.0,
                     entry=dt.datetime(2026, 10, 1, 0, 0, tzinfo=dt.timezone.utc),        # a DAY
                     exit=dt.datetime(2026, 10, 1, 19, 45, tzinfo=dt.timezone.utc))]      # a MOMENT
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        hold = next(b for b in d["breakdowns"] if b["key"] == "hold")
        assert [r[0] for r in hold["rows"]] == ["Same day"], hold["rows"]

    def test_the_bucket_cutoff_is_decided_on_the_corrected_day(self, client, test_api_key):
        """R-IV.705(f)'s untagged count turns on which side of 2026-09-25 a row opened. A row stored
        at `2026-09-25 00:00Z` IS on the cutoff; the old rule read it as the 24th and left it out."""
        import datetime as dt
        rows = [_row(1.0, entry=dt.datetime(2026, 9, 25, 0, 0, tzinfo=dt.timezone.utc), strategy_tag=None)]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        it = next(i for i in d["leaks"]["items"] if "Untagged" in i["label"])
        assert it["of_n"] == 1, "the row opened ON the cutoff is in the population"
        assert it["n"] == 1

    def test_a_negative_hold_is_counted_rather_than_vanishing(self, client, test_api_key):
        """Two rows did this under the old reading and nothing said so: no bucket matched, so the
        row left the breakdown in silence."""
        import datetime as dt
        rows = [_row(10.0, entry=dt.datetime(2026, 10, 5, 18, 0, tzinfo=dt.timezone.utc),
                     exit=dt.datetime(2026, 10, 1, 18, 0, tzinfo=dt.timezone.utc)),
                _row(5.0, entry=dt.datetime(2026, 10, 1, 0, 0, tzinfo=dt.timezone.utc),
                     exit=dt.datetime(2026, 10, 1, 0, 0, tzinfo=dt.timezone.utc))]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        hold = next(b for b in d["breakdowns"] if b["key"] == "hold")
        assert [r[0] for r in hold["rows"]] == ["Same day"], hold["rows"]
        assert "could not be placed" in hold["note"], hold["note"]
        assert "1" in hold["note"]


class TestAbacusPageServed:
    @pytest.mark.parametrize("path,needle", [
        ("/app/abacus", b"abacus.js"),
        ("/abacus.css", b".ab-page"),
        ("/abacus.js", b"/api/abacus/summary"),
    ])
    def test_served(self, client, path, needle):
        r = client.get(path)
        assert r.status_code == 200, path
        assert needle in r.content, path

    def test_abacus_route_beats_the_catch_all(self, client):
        """/app/{mode} serves legacy index.html; /app/abacus must not be swallowed by it."""
        body = client.get("/app/abacus").content
        assert b"abacus.js" in body and b"/app.js" not in body

    def test_legacy_analytics_still_legacy(self, client):
        """R-IV.413(a): /app/analytics is not repointed until the replacement is live."""
        body = client.get("/app/analytics").content
        assert b"/app.js" in body



class TestAbacusPerAccount:
    """R-IV.650(b)3 — per account AND combined, with the combined row pooled."""

    def test_each_account_gets_its_own_block_with_its_served_name(self, client, test_api_key):
        rows = [_row(10.0, 100.0, account="ROBINHOOD"), _row(-4.0, 100.0, account="ROBINHOOD"),
                _row(20.0, 100.0, account="FIDELITY_ROTH")]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        by = {a["account"]: a for a in d["accounts"]}
        assert set(by) == {"ROBINHOOD", "FIDELITY_ROTH"}
        # the NAME is served, never inferred from the key by a reader
        assert by["FIDELITY_ROTH"]["account_display"] == "FID ROTH"
        assert by["ROBINHOOD"]["account_display"] == "Robinhood"

    def test_combined_is_pooled_not_an_average_of_the_rates(self, client, test_api_key):
        """Robinhood wins 1 of 2; the Roth wins 2 of 2. Averaging the RATES gives 0.75.
        Pooling the trades gives 3 of 4 = 0.75 here only by coincidence, so use counts that
        separate them: 1-of-3 and 2-of-2 average to 0.667 but pool to 3 of 5 = 0.6."""
        rows = [_row(10.0, 100.0, account="ROBINHOOD"), _row(-4.0, 100.0, account="ROBINHOOD"),
                _row(-5.0, 100.0, account="ROBINHOOD"),
                _row(20.0, 100.0, account="FIDELITY_ROTH"), _row(30.0, 100.0, account="FIDELITY_ROTH")]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        by = {a["account"]: a for a in d["accounts"]}
        assert by["ROBINHOOD"]["win_rate"] == 0.3333
        assert by["FIDELITY_ROTH"]["win_rate"] == 1.0
        combined = next(s for s in d["stats"] if s["key"] == "win_rate")
        assert combined["value"] == 0.6, "pooled over every trade, not the mean of the two rates"
        assert d["combined_is_pooled"] is True

    def test_every_rate_carries_its_own_n(self, client, test_api_key):
        # one trade has no basis: it has a P&L but no RETURN, so the two counts differ
        rows = [_row(10.0, 100.0), _row(-4.0, None), _row(6.0, 200.0)]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        wr = next(s for s in d["stats"] if s["key"] == "win_rate")
        er = next(s for s in d["stats"] if s["key"] == "expected_return")
        assert wr["n"] == 3
        assert er["n"] == 2, "a trade with no basis has no return and is not averaged in at zero"
        acct = d["accounts"][0]
        assert acct["win_rate_n"] == 3 and acct["expected_return_n"] == 2

    def test_expected_return_is_null_not_zero_when_nothing_has_a_basis(self, client, test_api_key):
        rows = [_row(10.0, None), _row(-4.0, None)]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        er = next(s for s in d["stats"] if s["key"] == "expected_return")
        assert er["value"] is None, "no trade can be measured is not an average of nothing"
        assert er["n"] == 0

    def test_a_trade_with_no_account_is_its_own_bucket_not_folded_in(self, client, test_api_key):
        rows = [_row(10.0, 100.0, account="ROBINHOOD"), _row(-4.0, 100.0, account=None)]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        by = {a["account"]: a for a in d["accounts"]}
        assert None in by, "an unattributed trade is not silently added to another account"
        assert by[None]["account_display"] is None, "and it is never given a name nobody served"

    def test_each_account_carries_its_own_coverage(self, client, test_api_key):
        rows = [_row(10.0, 100.0, account="ROBINHOOD"),
                _row(None, 100.0, account="FIDELITY_ROTH"),
                _row(-500.0, 100.0, account="FIDELITY_ROTH")]
        pool, p = _patch_book(rows)
        with p:
            d = _get(client, test_api_key).json()
        by = {a["account"]: a for a in d["accounts"]}
        roth = by["FIDELITY_ROTH"]["coverage"]
        assert roth["total"] == 2 and roth["counted"] == 0
        assert roth["excluded"]["no_realized_pnl"] == 1
        assert roth["excluded"]["return_below_neg100pct"] == 1
        assert by["ROBINHOOD"]["coverage"]["counted"] == 1

