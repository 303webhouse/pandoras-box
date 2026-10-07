"""One route corrects a cash event to its export line — R-IV.667(b).

A UI-entered trade writes its cash BEFORE fees are known — the fee only arrives with the broker
export — and until R-IV.660(c)2 it also dated the movement on the day it was typed. CC-POSITIONS
holds the confirmed case: **event 144, BX, reads −38.00 on 2026-10-06 where the export says −38.18
on 2026-09-30.** Weekly cleanups will find more, because the fee is never knowable at entry.

R-IV.552(b) stands, which is the point of the route: nobody should need direct SQL. Note that
`cash_flow_corrections` already held 40 rows and NOTHING in the code wrote them — they went in by
hand. This is the writer.
"""

import ast
import io
import os
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException

from api.portfolio import CashFlowCorrection, correct_cash_flow
from services.cash_ledger import dedup_key

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EVENT_144 = {
    "id": 144, "account_name": "ROBINHOOD", "flow_type": "TRADE_DEBIT",
    "amount": Decimal("-38.00"), "description": "position opened",
    "activity_date": date(2026, 10, 6), "imported_from": "TRADE_ENTRY",
    "occurrence": 0, "source_ref": "POS_BX_20261006_183729",
    "dedup_key": "36304580017e7a4842376b705d4df748",
}


def _code(rel):
    src = io.open(os.path.join(BACKEND, rel), encoding="utf-8-sig").read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                src = src.replace(doc, "")
    return "".join(l for l in src.splitlines(keepends=True)
                   if not l.strip().startswith("#"))


class _Txn:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *a):
        return False


class _Conn:
    def __init__(self, row=None, clash=None, update_raises=False):
        self.row = row
        self.clash = clash
        self.update_raises = update_raises
        self.inserts = []
        self.updates = []

    def transaction(self):
        return _Txn()

    async def fetchrow(self, sql, *args):
        s = " ".join(sql.split())
        if "FROM cash_flows WHERE id" in s:
            return dict(self.row) if self.row else None
        if "AND dedup_key = $2" in s:
            return {"id": self.clash} if self.clash else None
        return None

    async def execute(self, sql, *args):
        s = " ".join(sql.split())
        if "INSERT INTO cash_flow_corrections" in s:
            self.inserts.append(args)
        elif "UPDATE cash_flows SET" in s:
            if self.update_raises:
                raise RuntimeError("UniqueViolationError")
            self.updates.append((s, args))


class _Acq:
    def __init__(self, conn):
        self._c = conn

    async def __aenter__(self):
        return self._c

    async def __aexit__(self, *a):
        return False

    def __call__(self):
        return self


def _pool(conn):
    class P:
        acquire = _Acq(conn)
    return P()


def _patch(monkeypatch, conn):
    import api.portfolio as portfolio

    async def _get():
        return _pool(conn)

    monkeypatch.setattr(portfolio, "get_postgres_client", _get)


def _body(**kw):
    base = dict(evidence_ref="RH export 2026-09-30 line 7", reason="fee arrived with the export",
                ruling="R-IV.667(b)", actor="CC-BUILD")
    base.update(kw)
    return CashFlowCorrection(**base)


class TestOnlyTwoFieldsAreCorrectable:
    def test_the_model_carries_no_other_mutable_field(self):
        """"Refuses any other change" is enforced by what a caller can EXPRESS, not by a check
        that might be forgotten. The account, type, source_ref and occurrence are the event's
        IDENTITY — correcting those would be a different event wearing this one's id."""
        fields = set(CashFlowCorrection.model_fields)
        assert fields == {"amount", "activity_date", "evidence_ref", "reason", "ruling", "actor"}
        for forbidden in ("account_name", "flow_type", "source_ref", "occurrence",
                          "description", "imported_from"):
            assert forbidden not in fields

    def test_the_update_statement_names_only_those_columns(self):
        src = _code("api/portfolio.py")
        i = src.index("async def correct_cash_flow")
        body = src[i:src.index("\n@router", i) if "\n@router" in src[i:] else len(src)]
        stmt = body[body.index("UPDATE cash_flows SET"):]
        stmt = stmt[:stmt.index('"', stmt.index("WHERE id = $1"))]
        assert "amount = $2" in stmt and "activity_date = $3" in stmt
        assert "dedup_key = $4" in stmt
        for forbidden in ("account_name", "flow_type", "source_ref", "occurrence =",
                          "description", "imported_from"):
            assert forbidden not in stmt


class TestTheEvidenceIsRequired:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("field", ["evidence_ref", "reason", "ruling", "actor"])
    async def test_each_is_refused_when_blank(self, monkeypatch, field):
        """An unevidenced correction to money is indistinguishable from a typo with a confident
        tone — and this route exists because the first figure was wrong."""
        _patch(monkeypatch, _Conn(EVENT_144))
        with pytest.raises(HTTPException) as exc:
            await correct_cash_flow(144, _body(amount=-38.18, **{field: "   "}))
        assert exc.value.status_code == 400
        assert field in str(exc.value.detail)

    @pytest.mark.asyncio
    async def test_the_evidence_ref_reaches_the_audit_row(self, monkeypatch):
        conn = _Conn(EVENT_144)
        _patch(monkeypatch, conn)
        await correct_cash_flow(144, _body(amount=-38.18))
        assert conn.inserts, "a correction with no audit row is not an audited correction"
        reasons = [a[4] for a in conn.inserts]
        assert all("RH export 2026-09-30 line 7" in r for r in reasons)
        assert all(a[5] == "R-IV.667(b)" for a in conn.inserts)
        assert all(a[6] == "CC-BUILD" for a in conn.inserts)


class TestEvent144TheRealCase:
    @pytest.mark.asyncio
    async def test_amount_and_date_are_both_corrected(self, monkeypatch):
        conn = _Conn(EVENT_144)
        _patch(monkeypatch, conn)
        out = await correct_cash_flow(144, _body(amount=-38.18, activity_date="2026-09-30"))
        assert out["status"] == "corrected"
        assert out["before"] == {"amount": -38.0, "activity_date": "2026-10-06"}
        assert out["after"] == {"amount": -38.18, "activity_date": "2026-09-30"}
        assert set(out["columns_changed"]) == {"amount", "activity_date", "dedup_key"}

    @pytest.mark.asyncio
    async def test_the_before_state_is_kept_one_row_per_column(self, monkeypatch):
        conn = _Conn(EVENT_144)
        _patch(monkeypatch, conn)
        await correct_cash_flow(144, _body(amount=-38.18, activity_date="2026-09-30"))
        by_col = {a[1]: (a[2], a[3]) for a in conn.inserts}
        assert by_col["amount"] == ("-38.00", "-38.18")
        assert by_col["activity_date"] == ("2026-10-06", "2026-09-30")
        assert "dedup_key" in by_col

    @pytest.mark.asyncio
    async def test_the_audit_rows_and_the_update_are_in_one_transaction(self, monkeypatch):
        """A correction whose audit row could be lost separately is not audited."""
        src = _code("api/portfolio.py")
        i = src.index("async def correct_cash_flow")
        # Bounded to the FUNCTION, not a char count: a fixed window cut off before the INSERT and
        # the assertion raised rather than failing on its subject -- the same truncation that bit
        # the tide-sink DDL test.
        j = src.find("\n@router", i)
        body = src[i:j if j != -1 else len(src)]
        assert "async with pool.acquire() as conn, conn.transaction():" in body
        assert body.index("INSERT INTO cash_flow_corrections") < body.index("UPDATE cash_flows SET")


class TestTheDedupKeyIsRecomputed:
    @pytest.mark.asyncio
    async def test_it_is_rebuilt_from_the_corrected_values(self, monkeypatch):
        """The key is DERIVED from account, type, amount, date, source_ref and occurrence.
        Leaving it stale would leave a row whose key describes values it no longer holds — so a
        genuinely new movement with the corrected values would dedup against it and be silently
        dropped. Same shape as a stored total that no longer matches its ledger."""
        conn = _Conn(EVENT_144)
        _patch(monkeypatch, conn)
        await correct_cash_flow(144, _body(amount=-38.18, activity_date="2026-09-30"))
        expected = dedup_key("ROBINHOOD", "TRADE_DEBIT", Decimal("-38.18"), date(2026, 9, 30),
                             "POS_BX_20261006_183729", 0)
        written = [a for a in conn.inserts if a[1] == "dedup_key"][0]
        assert written[3] == expected
        assert written[2] == EVENT_144["dedup_key"]
        # and the UPDATE carries it
        assert conn.updates[0][1][3] == expected

    @pytest.mark.asyncio
    async def test_a_row_with_no_key_is_left_without_one(self, monkeypatch):
        """POSITIVE CONTROL. An unattributed movement is stored WITHOUT a key on purpose (the
        partial unique index excludes nulls), so minting one here would quietly enrol it in
        deduplication it was deliberately kept out of."""
        conn = _Conn(dict(EVENT_144, dedup_key=None))
        _patch(monkeypatch, conn)
        await correct_cash_flow(144, _body(amount=-38.18))
        assert not any(a[1] == "dedup_key" for a in conn.inserts)
        assert conn.updates[0][1][3] is None

    @pytest.mark.asyncio
    async def test_a_key_collision_is_refused_not_written(self, monkeypatch):
        conn = _Conn(EVENT_144, clash=999)
        _patch(monkeypatch, conn)
        with pytest.raises(HTTPException) as exc:
            await correct_cash_flow(144, _body(amount=-38.18, activity_date="2026-09-30"))
        assert exc.value.status_code == 409
        assert "999" in str(exc.value.detail)
        assert conn.inserts == [] and conn.updates == []

    @pytest.mark.asyncio
    async def test_a_natural_key_collision_is_a_409_not_a_500(self, monkeypatch):
        """The wide natural-key index can collide too, and NULLS NOT DISTINCT means a null
        description does not excuse it."""
        conn = _Conn(EVENT_144, update_raises=True)
        _patch(monkeypatch, conn)
        with pytest.raises(HTTPException) as exc:
            await correct_cash_flow(144, _body(amount=-38.18))
        assert exc.value.status_code == 409
        assert "natural" in str(exc.value.detail)


class TestWhatItRefuses:
    @pytest.mark.asyncio
    async def test_a_missing_event_is_a_404(self, monkeypatch):
        _patch(monkeypatch, _Conn(None))
        with pytest.raises(HTTPException) as exc:
            await correct_cash_flow(9999, _body(amount=-1.0))
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_nothing_to_correct_is_refused(self, monkeypatch):
        _patch(monkeypatch, _Conn(EVENT_144))
        with pytest.raises(HTTPException) as exc:
            await correct_cash_flow(144, _body())
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_a_zero_amount_is_refused(self, monkeypatch):
        """A movement of zero is not a correction, it is a deletion wearing one."""
        _patch(monkeypatch, _Conn(EVENT_144))
        with pytest.raises(HTTPException) as exc:
            await correct_cash_flow(144, _body(amount=0))
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_a_future_date_is_refused(self, monkeypatch):
        """An export line describes something that already happened."""
        _patch(monkeypatch, _Conn(EVENT_144))
        future = (date.today() + timedelta(days=3)).isoformat()
        with pytest.raises(HTTPException) as exc:
            await correct_cash_flow(144, _body(activity_date=future))
        assert exc.value.status_code == 400
        assert "future" in str(exc.value.detail)

    @pytest.mark.asyncio
    async def test_a_malformed_date_is_refused(self, monkeypatch):
        _patch(monkeypatch, _Conn(EVENT_144))
        with pytest.raises(HTTPException) as exc:
            await correct_cash_flow(144, _body(activity_date="30/09/2026"))
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_resending_the_values_it_already_holds_writes_nothing(self, monkeypatch):
        """POSITIVE CONTROL, and the subtle one. Idempotent, and NOT an audit row: recording a
        no-op as a correction would put a change in the ledger that never happened."""
        conn = _Conn(EVENT_144)
        _patch(monkeypatch, conn)
        out = await correct_cash_flow(144, _body(amount=-38.00, activity_date="2026-10-06"))
        assert out["status"] == "unchanged"
        assert conn.inserts == [] and conn.updates == []
