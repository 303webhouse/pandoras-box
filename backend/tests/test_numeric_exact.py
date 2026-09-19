"""R-IV.463(e), first finding -- a float written into NUMERIC is the number, not its binary expansion.

FAIL-FIRST against the pre-2026-09-19 tree: the pool used asyncpg's default numeric encoder, which
writes a Python float by its exact binary expansion (34.81 -> 34.81000000000000227373675443232059
478759765625). Verified read-only against production before the fix: the default gives that text,
and the codec here gives 34.81, for scalars and for numeric[].
"""
from __future__ import annotations

import asyncio
import inspect
import sys
from decimal import Decimal

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from database import postgres_client as PC  # noqa: E402


def test_a_float_is_written_as_the_number_the_writer_meant():
    assert PC._numeric_text(34.81) == "34.81"
    assert PC._numeric_text(0.015) == "0.015"
    assert PC._numeric_text(15.35049) == "15.35049"


def test_other_values_pass_as_written():
    assert PC._numeric_text(Decimal("46.10")) == "46.10"
    assert PC._numeric_text(5) == "5"
    assert PC._numeric_text("1.5") == "1.5"
    assert PC._numeric_text(True) == "1" and PC._numeric_text(False) == "0"
    assert PC._numeric_text(float("nan")) == "nan"


def test_a_numpy_float_is_written_as_its_number_not_its_repr():
    np = __import__("pytest").importorskip("numpy")
    assert PC._numeric_text(np.float64(34.81)) == "34.81"


def test_every_pooled_connection_gets_the_codec():
    calls = []

    class Conn:
        async def set_type_codec(self, name, **kw):
            calls.append((name, kw))

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(PC._init_connection(Conn()))
    finally:
        loop.close()
    name, kw = calls[0]
    assert name == "numeric" and kw["format"] == "text" and kw["schema"] == "pg_catalog"
    assert kw["encoder"] is PC._numeric_text and kw["decoder"] is Decimal
    src = inspect.getsource(PC.get_postgres_client)
    assert "init=_init_connection" in src


def test_an_equity_mark_is_the_quoted_price_not_the_vendors_float32():
    """Measured 2026-09-19 16:51 UTC: six equity marks written through the codec still read
    45.709999084472656 -- the vendor's float32 for 45.71, stored exactly as received."""
    import numpy as np
    assert round(float(np.float32(45.71)), 4) == 45.71
    from api import unified_positions as U
    src = inspect.getsource(U.run_mark_to_market)
    assert "current_price = round(float(info.last_price), 4)" in src
