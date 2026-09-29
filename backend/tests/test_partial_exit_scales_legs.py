"""A partial exit shrinks the legs to the open remainder, in the same transaction.

R-IV.517(c) (98e32b5, 2026-09-23) made the database refuse a commit where a leg's qty
differs from SUM(position_lots.qty) on an OPEN row. Neither partial-exit path -- /close
with quantity < total, nor /reduce -- updated the legs, so every partial exit on a row
carrying both lots and legs failed at commit from that day on. First seen 2026-09-29:
HYG, close 2 of 5, two attempts, both rolled back, book left behind the broker.

Convention #30: every "it writes the legs" case has a case beside it that must NOT.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException


# --- harness -------------------------------------------------------------------------------
class _Acq:
    def __init__(self, conn): self._c = conn
    async def __aenter__(self): return self._c
    async def __aexit__(self, *a): return False
    def __call__(self): return self


class _Txn:
    async def __aenter__(self): return None
    async def __aexit__(self, *a): return False


OPEN_SPREAD = {
    "position_id": "p_hyg", "ticker": "HYG", "asset_type": "OPTION", "account": "ROBINHOOD",
    "status": "OPEN", "structure": "put_debit_spread", "direction": "LONG",
    "quantity": 5.0, "entry_price": 0.136, "cost_basis": 68.0,
    "long_strike": 76.0, "short_strike": 73.0, "expiry": "2026-11-20",
    "entry_date": datetime(2026, 8, 20, 12, tzinfo=timezone.utc), "signal_id": None,
}


def _close_pool(row, *, has_lots, lots_sum, legs_shape):
    """A conn that answers the close path's queries by their shape and records its writes."""
    conn = MagicMock()
    conn.executed = []

    async def fetchrow(sql, *args):
        s = " ".join(sql.split())
        if "INSERT INTO close_attempts" in s:
            return {"id": 1}
        if "INSERT INTO trades" in s:
            return {"id": 55}
        if "FROM position_legs WHERE position_id" in s:
            return legs_shape
        if "UPDATE unified_positions" in s:
            conn.executed.append((s, args))
            return row
        return row

    async def fetchval(sql, *args):
        s = " ".join(sql.split())
        if "SELECT 1 FROM position_lots" in s:
            return 1 if has_lots else None
        if "SUM(qty)" in s:
            return lots_sum
        return None

    async def fetch(sql, *args):
        return []

    async def execute(sql, *args):
        conn.executed.append((" ".join(sql.split()), args))

    conn.fetchrow, conn.fetchval, conn.fetch, conn.execute = fetchrow, fetchval, fetch, execute
    conn.transaction = lambda: _Txn()
    pool = MagicMock()
    pool.acquire = _Acq(conn)
    return pool, conn


def _close(monkeypatch, *, quantity, has_lots=True, lots_sum=3.0,
           legs_shape={"n": 2, "shapes": 1}, row=OPEN_SPREAD):
    from api import unified_positions as U
    pool, conn = _close_pool(row, has_lots=has_lots, lots_sum=lots_sum, legs_shape=legs_shape)
    monkeypatch.setattr(U, "get_postgres_client", AsyncMock(return_value=pool))
    monkeypatch.setattr(U, "name_actor", AsyncMock())
    monkeypatch.setattr(U, "_adjust_account_cash_with_conn", AsyncMock(return_value=True))
    monkeypatch.setattr(U.manager, "broadcast_position_update", AsyncMock())
    # Background work is scheduled after commit; the test loop closes before it runs.
    monkeypatch.setattr(U.asyncio, "ensure_future", lambda coro, *a, **k: coro.close())
    req = U.ClosePositionRequest(exit_price=0.40, quantity=quantity)
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(U.close_position("p_hyg", req)), conn
    finally:
        loop.close()


def _legs_updates(conn):
    return [e for e in conn.executed if e[0].startswith("UPDATE position_legs SET qty")]


# --- /close ---------------------------------------------------------------------------------
def test_a_partial_close_scales_the_legs_to_the_lots_remainder(monkeypatch):
    """HYG: 5 held as lots 3 + 2, legs 5/5, close 2. The legs must read 3 -- the LOTS'
    remainder, which is the figure the trigger compares against."""
    out, conn = _close(monkeypatch, quantity=2, has_lots=True, lots_sum=3.0)
    assert out["status"] == "partial_close" and out["remaining_qty"] == 3
    ups = _legs_updates(conn)
    assert len(ups) == 1, "exactly one legs update, in the same transaction"
    assert ups[0][1] == (3.0, "p_hyg")


def test_the_legs_update_follows_the_disposal_lot(monkeypatch):
    """Order inside the transaction: disposal lot first, then the legs read the new sum.
    (The trigger is deferred, so order is for the SUM read, not the trigger.)"""
    _, conn = _close(monkeypatch, quantity=2)
    kinds = [e[0][:30] for e in conn.executed]
    lot_at = next(i for i, k in enumerate(kinds) if k.startswith("INSERT INTO position_lots"))
    leg_at = next(i for i, k in enumerate(kinds) if k.startswith("UPDATE position_legs"))
    assert lot_at < leg_at


def test_a_partial_close_on_a_row_without_lots_still_shrinks_its_legs(monkeypatch):
    """No lots means no disposal and no trigger -- but the mark path still reads the legs,
    so they follow the row's own remainder rather than describing a size no longer held."""
    _, conn = _close(monkeypatch, quantity=2, has_lots=False)
    assert not [e for e in conn.executed if "INSERT INTO position_lots" in e[0]]
    ups = _legs_updates(conn)
    assert len(ups) == 1 and ups[0][1] == (3.0, "p_hyg")


def test_a_full_close_does_not_touch_the_legs(monkeypatch):
    """Negative control (#30). A CLOSED row is exempt from the trigger; its legs stay as
    the record of what was held."""
    out, conn = _close(monkeypatch, quantity=5)
    assert out["status"] == "closed"
    assert _legs_updates(conn) == []


def test_a_partial_close_on_a_row_with_no_legs_writes_no_legs(monkeypatch):
    """Negative control (#30): legs count 0 -> nothing to scale, nothing written."""
    _, conn = _close(monkeypatch, quantity=2, legs_shape={"n": 0, "shapes": 0})
    assert _legs_updates(conn) == []


def test_a_ratio_structure_is_refused_rather_than_scaled(monkeypatch):
    """Legs holding different quantities have no single uniform remainder. Refuse with
    both facts named -- the first ratio row should be met loudly, not guessed at."""
    with pytest.raises(HTTPException) as e:
        _close(monkeypatch, quantity=2, legs_shape={"n": 3, "shapes": 2})
    assert e.value.status_code == 409
    assert "ratio" in e.value.detail and "Nothing was written" in e.value.detail


# --- /reduce --------------------------------------------------------------------------------
def _reduce_pool(position, lots, legs_shape):
    conn = MagicMock()
    conn.executed = []

    async def fetchrow(sql, *args):
        s = " ".join(sql.split())
        if "FROM position_lots WHERE broker_ref" in s:
            return None
        if "FROM position_legs WHERE position_id" in s:
            return legs_shape
        return position

    async def fetch(sql, *args):
        return [dict(l) for l in lots]

    async def fetchval(sql, *args):
        conn.executed.append((" ".join(sql.split()), args))
        return 99

    async def execute(sql, *args):
        conn.executed.append((" ".join(sql.split()), args))

    conn.fetchrow, conn.fetch, conn.fetchval, conn.execute = fetchrow, fetch, fetchval, execute
    conn.transaction = lambda: _Txn()
    pool = MagicMock()
    pool.acquire = _Acq(conn)
    return pool, conn


def test_a_confirmed_reduction_scales_the_legs_to_the_lots_sum(monkeypatch):
    """The reduce path recomputes the aggregate from the lots it was handed; the legs
    take that same sum. (The fake conn returns the pre-disposal lot set on every read,
    so the sum here is the acquisitions' 5 -- the assertion is that the legs are set to
    whatever derive_aggregate said, not to a number computed a second way.)"""
    from api import unified_positions as U
    lots = [{"id": 1, "fill_time": datetime(2026, 8, 20, tzinfo=timezone.utc),
             "qty": 3.0, "price": 0.14, "fees": 0},
            {"id": 2, "fill_time": datetime(2026, 9, 16, tzinfo=timezone.utc),
             "qty": 2.0, "price": 0.13, "fees": 0}]
    pool, conn = _reduce_pool({**OPEN_SPREAD}, lots, {"n": 2, "shapes": 1})
    monkeypatch.setattr(U, "get_postgres_client", AsyncMock(return_value=pool))
    req = U.ReducePositionRequest(qty=2, price=0.40, confirm=True)
    loop = asyncio.new_event_loop()
    try:
        out = loop.run_until_complete(U.reduce_position("p_hyg", req))
    finally:
        loop.close()
    assert out["status"] == "reduced"
    ups = _legs_updates(conn)
    assert len(ups) == 1
    assert ups[0][1] == (float(out["quantity_after"]), "p_hyg")


def test_the_helper_is_shared_by_both_partial_paths():
    """One owner for the arithmetic: the two paths call the same function, so a fix to
    one cannot leave the other as the way back in."""
    import inspect
    from api import unified_positions as U
    assert "_scale_legs_to_remainder(" in inspect.getsource(U.close_position)
    assert "_scale_legs_to_remainder(" in inspect.getsource(U.reduce_position)


# --- adds: the combine branch of create, and /lots --------------------------------------------
# The combine branch rewrote quantity and basis on the row alone. With lots and legs on the
# row, that left the row holding more than its lots and the legs marking the old size, and
# nothing refused it -- the trigger watches lots and legs, not the row. Worse than the close
# bug, because it was silent.

HYG_LOTS = [{"qty": 3.0, "price": 0.14, "fees": 0}, {"qty": 2.0, "price": 0.13, "fees": 0}]


def _combine_pool(existing, *, has_lots, lots_after, legs_shape):
    conn = MagicMock()
    conn.executed = []

    async def fetchrow(sql, *args):
        s = " ".join(sql.split())
        if "FROM position_legs WHERE position_id" in s:
            return legs_shape
        if s.startswith("UPDATE unified_positions"):
            conn.executed.append((s, args))
            return {**existing, "quantity": args[1]}
        return existing

    async def fetchval(sql, *args):
        if "SELECT 1 FROM position_lots" in " ".join(sql.split()):
            return 1 if has_lots else None
        return None

    async def fetch(sql, *args):
        return [dict(l) for l in lots_after]

    async def execute(sql, *args):
        conn.executed.append((" ".join(sql.split()), args))

    conn.fetchrow, conn.fetchval, conn.fetch, conn.execute = fetchrow, fetchval, fetch, execute
    conn.transaction = lambda: _Txn()
    pool = MagicMock()
    pool.acquire = _Acq(conn)
    return pool, conn


def _combine(monkeypatch, *, qty=2, price=0.20, has_lots=True, lots_after=None,
             legs_shape={"n": 2, "shapes": 1}, entry_date=None):
    from api import unified_positions as U
    existing = {**OPEN_SPREAD, "max_loss": None, "max_profit": None, "breakeven": None}
    pool, conn = _combine_pool(existing, has_lots=has_lots,
                               lots_after=lots_after if lots_after is not None else HYG_LOTS,
                               legs_shape=legs_shape)
    monkeypatch.setattr(U, "get_postgres_client", AsyncMock(return_value=pool))
    monkeypatch.setattr(U, "name_actor", AsyncMock())
    monkeypatch.setattr(U, "_adjust_account_cash", AsyncMock(return_value=True))
    monkeypatch.setattr(U.manager, "broadcast_position_update", AsyncMock())
    req = U.CreatePositionRequest(ticker="HYG", structure="put_debit_spread",
                                  entry_price=price, quantity=qty, long_strike=76.0,
                                  short_strike=73.0, expiry="2026-11-20",
                                  entry_date=entry_date)
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(U.create_position(req)), conn
    finally:
        loop.close()


def test_an_add_to_a_lotted_row_is_written_as_its_own_lot(monkeypatch):
    after = HYG_LOTS + [{"qty": 2.0, "price": 0.20, "fees": 0}]
    out, conn = _combine(monkeypatch, lots_after=after)
    assert out["status"] == "combined"
    ins = [e for e in conn.executed if e[0].startswith("INSERT INTO position_lots")]
    assert len(ins) == 1
    assert ins[0][1][2] == 2.0 and ins[0][1][3] == pytest.approx(0.20)


def test_the_row_is_derived_from_the_lots_after_an_add(monkeypatch):
    """5 held (3 @ 0.14, 2 @ 0.13) + 2 @ 0.20 -> 7 @ 0.1543, basis 108.00."""
    after = HYG_LOTS + [{"qty": 2.0, "price": 0.20, "fees": 0}]
    _, conn = _combine(monkeypatch, lots_after=after)
    upd = next(e for e in conn.executed if e[0].startswith("UPDATE unified_positions"))
    _, qty, entry, basis = upd[1][:4]
    assert qty == pytest.approx(7.0)
    assert entry == pytest.approx(round(1.08 / 7, 4))
    assert basis == pytest.approx(108.0)


def test_an_add_scales_the_legs_up_to_the_new_size(monkeypatch):
    after = HYG_LOTS + [{"qty": 2.0, "price": 0.20, "fees": 0}]
    _, conn = _combine(monkeypatch, lots_after=after)
    ups = _legs_updates(conn)
    assert len(ups) == 1 and ups[0][1] == (7.0, "p_hyg")


def test_an_add_carries_the_fill_date_the_principal_gave(monkeypatch):
    after = HYG_LOTS + [{"qty": 2.0, "price": 0.20, "fees": 0}]
    _, conn = _combine(monkeypatch, lots_after=after, entry_date="2026-09-29")
    ins = next(e for e in conn.executed if e[0].startswith("INSERT INTO position_lots"))
    assert ins[1][1].date().isoformat() in ("2026-09-29", "2026-09-30")  # 00:00 Denver, in UTC
    assert ins[1][1].tzinfo is not None


def test_an_add_to_a_row_without_lots_writes_no_lot(monkeypatch):
    """Negative control (#30): one lot for the add alone would make the lots describe 2 of
    7, and the remainder would be wrong in the other direction."""
    _, conn = _combine(monkeypatch, has_lots=False)
    assert not [e for e in conn.executed if e[0].startswith("INSERT INTO position_lots")]
    ups = _legs_updates(conn)
    assert len(ups) == 1 and ups[0][1] == (7.0, "p_hyg")


def test_an_add_to_a_row_without_legs_writes_no_legs(monkeypatch):
    """Negative control (#30)."""
    _, conn = _combine(monkeypatch, legs_shape={"n": 0, "shapes": 0},
                       lots_after=HYG_LOTS + [{"qty": 2.0, "price": 0.20, "fees": 0}])
    assert _legs_updates(conn) == []


def test_the_lots_route_scales_the_legs_too():
    import inspect
    from api import unified_positions as U
    src = inspect.getsource(U.add_position_lot)
    assert "_scale_legs_to_remainder(conn, position_id, stored_qty)" in src
    assert src.index("derive_aggregate(") < src.index("_scale_legs_to_remainder(")
