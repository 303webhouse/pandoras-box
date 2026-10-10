"""FX capture through the Stable Engine (R-IV.823(i), Task 6).

- AUDJPY and MXNJPY join DXY and USDJPY in the strip's FX map.
- FX points are kept: the 7-day intraday prune spares them.
- The v2 FX tile's payload (`fx`) is unchanged; the carry pairs are served apart (`fx_capture`)
  until the principal approves a display.
The prune and the endpoint run for real here; only the database is stubbed.
"""

from datetime import datetime, timezone

import pytest

from stable_engine import strip


def test_the_carry_pairs_join_the_fx_map():
    assert strip.FX["AUDJPY=X"] == "AUDJPY" and strip.FX["MXNJPY=X"] == "MXNJPY"
    assert strip.FX["DX-Y.NYB"] == "DXY" and strip.FX["USDJPY=X"] == "USDJPY"
    assert set(strip.FX_KEEP) == {"DXY", "USDJPY", "AUDJPY", "MXNJPY"}
    assert strip.FX_DISPLAY == ("DXY", "USDJPY")


class _Cur:
    def __init__(self, log):
        self.log = log

    def execute(self, sql, params=None):
        self.log.append((sql, params))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Conn:
    def __init__(self, log):
        self.log = log

    def cursor(self):
        return _Cur(self.log)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_the_prune_spares_every_fx_symbol(monkeypatch):
    log, values = [], []
    monkeypatch.setattr(strip.db, "connect", lambda: _Conn(log))
    monkeypatch.setattr(strip, "execute_values", lambda cur, sql, rows: values.extend(rows))
    n = strip.append_intraday({"intraday": [("XLK", 0.4), ("AUDJPY", 110.5)],
                               "as_of": datetime(2026, 10, 9, 18, tzinfo=timezone.utc)})
    assert n == 2 and {v[0] for v in values} == {"XLK", "AUDJPY"}
    prunes = [p for _, p in log if p]
    assert len(prunes) == 1
    days, kept = prunes[0]
    assert days == strip.INTRADAY_RETENTION_DAYS
    assert set(kept) == {"DXY", "USDJPY", "AUDJPY", "MXNJPY"}


class _AConn:
    def __init__(self, latest, pts):
        self.latest, self.pts, self.calls = latest, pts, []

    async def fetch(self, sql, *args):
        self.calls.append(args)
        return self.latest if "stable_live_strip" in sql else self.pts


class _Acq:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


@pytest.mark.asyncio
async def test_the_tile_payload_is_unchanged_and_the_carry_pairs_are_served_apart(monkeypatch):
    import services.read_only.stable as svc

    now = datetime(2026, 10, 9, 20, tzinfo=timezone.utc)
    latest = [{"symbol": s, "day_change_pct": 0.1, "level": lvl, "as_of": now}
              for s, lvl in (("AUDJPY", 110.6), ("DXY", 102.2), ("MXNJPY", 8.59), ("USDJPY", 158.2))]
    pts = [{"symbol": "MXNJPY", "ts": now, "value": 8.59}, {"symbol": "DXY", "ts": now, "value": 102.2}]
    conn = _AConn(latest, pts)

    class _Pool:
        def acquire(self):
            return _Acq(conn)

    async def _pool():
        return _Pool()

    monkeypatch.setattr(svc, "get_postgres_client", _pool)
    out = await svc.get_fx()
    assert [f["symbol"] for f in out["fx"]] == ["DXY", "USDJPY"]          # what v2 renders
    assert out["count"] == 2
    assert [f["symbol"] for f in out["fx_capture"]] == ["AUDJPY", "MXNJPY"]
    assert out["fx_capture"][1]["series"][0]["value"] == 8.59
    assert set(conn.calls[1][0]) == set(strip.FX_KEEP)                    # series for all four


def test_the_strip_fetches_the_new_pairs(monkeypatch):
    """fetch_strip asks yfinance for every FX symbol (the map is the one list it reads)."""
    asked = {}

    def _download(syms, **kw):
        asked["syms"] = list(syms)
        raise RuntimeError("stop after the request")

    import yfinance as yf
    monkeypatch.setattr(yf, "download", _download)
    try:
        strip.fetch_strip()
    except Exception:
        pass
    assert {"AUDJPY=X", "MXNJPY=X", "DX-Y.NYB", "USDJPY=X"} <= set(asked.get("syms", []))
