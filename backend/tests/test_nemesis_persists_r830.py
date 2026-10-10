"""A Nemesis hit reaches the INSERT (R-IV.830, found during the R-IV.809(f) census).

314fc21 fixed the import, the bars window and the gate scale, and a Nemesis row still could not
land: `scan_wrr` built its dict with `target_price` and no `target_1`, and `log_signal` indexes
`signal_data['target_1']` directly. The KeyError is caught by the pipeline as "Failed to log
signal", so the scan would report hits while the table stayed empty, the same silent shape as
the import defect before it.

This drives a REAL hit out of `scan_wrr` (synthetic bars built to satisfy every rule) into the
REAL `log_signal`, with only the vendor, the calendar lookup, the bias snapshot and the pool
stubbed, and asserts the INSERT ran with the target in the `target_1` slot.
"""

import pytest

import database.postgres_client as pg


def _bars():
    """240 bars rising 50 → 115 (SMA200 far below), nine falling to 100.5, then a reversal bar
    that still closes lower (RSI(3) = 0), 14% under its close 10 bars back, on double volume,
    with close > open and a body over 60% of its range."""
    bars = []
    for i in range(240):
        c = 50 + 65 * i / 239
        bars.append({"o": c - 0.2, "h": c + 0.5, "l": c - 0.5, "c": c, "v": 1_000_000})
    for k in range(1, 10):
        c = 115 - 14.5 * k / 9
        bars.append({"o": c + 0.5, "h": c + 0.8, "l": c - 0.3, "c": c, "v": 1_000_000})
    bars.append({"o": 95.0, "h": 99.5, "l": 94.0, "c": 99.0, "v": 2_000_000})
    return bars


class _Conn:
    def __init__(self):
        self.executed = []

    async def execute(self, sql, *args):
        self.executed.append((" ".join(sql.split()), args))
        return "INSERT 0 1"


class _Acq:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class _Pool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Acq(self.conn)


@pytest.mark.asyncio
async def test_a_wrr_hit_is_written_with_its_target(monkeypatch):
    import integrations.uw_api as uw
    from strategies.wrr_buy_model import scan_wrr

    async def _get_bars(ticker, mult, span, from_date=None, **_):
        return _bars()

    monkeypatch.setattr(uw, "get_bars", _get_bars)
    res = await scan_wrr(["TEST"])
    assert len(res["signals"]) == 1, res
    signal = res["signals"][0]
    assert signal["signal_type"] == "NEMESIS_LONG"

    conn = _Conn()

    async def _pool():
        return _Pool(conn)

    async def _calendar(ts, ticker):
        return {}

    monkeypatch.setattr(pg, "get_postgres_client", _pool)
    monkeypatch.setattr(pg, "_build_calendar_metadata", _calendar)
    signal["bias_at_signal"] = {"stub": True}  # skip the live bias snapshot

    await pg.log_signal(signal)

    inserts = [a for s, a in conn.executed if s.startswith("INSERT INTO signals")]
    assert len(inserts) == 1
    args = inserts[0]
    # positional: signal_id, timestamp, strategy, ticker, asset_class, direction, signal_type,
    # entry_price, stop_loss, target_1 (postgres_client.log_signal's INSERT column order)
    assert args[6] == "NEMESIS_LONG"
    assert args[9] == signal["target_price"] and args[9] > args[7] > args[8]
