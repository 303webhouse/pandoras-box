"""R-IV.1456(g): F: 1-minute bars are WRITE-ONCE, and a Polygon reference copy sits beside them.

yfinance serves two alternating versions of settled 1-minute bars (measured 10-29/10-30), and the
nightly export rewrote every session file, so F: flipped between them under every reader.

  1. An existing session file is never overwritten. Tonight's vendor copy is compared with it
     and a difference is LOGGED (date, ticker, bars changed, largest price change, and both
     versions' fingerprints, so the alternation is visible), never written over.
  2. A session still trading (extended hours end 20:00 ET) is not written at all.
  3. Polygon's bars for the same sessions go to a SEPARATE folder, write-once, back-filled from
     09-25, with their differences from the yfinance file logged. The current session is withheld
     by the plan, so it lands the night after; a 403 on a past session stops the run.
"""

import importlib.util
import os
from datetime import date, datetime

import pandas as pd
import pytest

pytest.importorskip("pyarrow")

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
F_EXPORT = os.path.join(REPO, "scripts", "f_export.py")
BARS_JOB = os.path.join(REPO, "scripts", "f_export_bars.py")


@pytest.fixture
def fx(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("_f_export_r1456", F_EXPORT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "ROOT", str(tmp_path))
    monkeypatch.setattr(mod, "CENSUS", ["SPY"])
    return mod


def _bars(d: date, base: float, n: int = 5, bump_at: int = None, bump: float = 0.0):
    from zoneinfo import ZoneInfo
    idx = pd.date_range("%s 09:30" % d.isoformat(), periods=n, freq="min",
                        tz=ZoneInfo("America/New_York"), name="Datetime")
    px = [base + i * 0.1 for i in range(n)]
    if bump_at is not None:
        px[bump_at] += bump
    return pd.DataFrame({"Open": px, "High": [p + 0.05 for p in px],
                         "Low": [p - 0.05 for p in px], "Close": px,
                         "Volume": [1000.0] * n, "Dividends": 0.0, "Stock Splits": 0.0},
                        index=idx)


class _FakeYF:
    def __init__(self, frame):
        self.frame = frame

    def Ticker(self, t):
        frame = self.frame

        class _T:
            def history(self, **kw):
                return frame.copy()
        return _T()


D1, D2 = date(2026, 10, 20), date(2026, 10, 21)


def _path(fx, d, t="SPY", folder="bars1m"):
    return os.path.join(fx.ROOT, folder, d.isoformat(), "%s.parquet" % t)


def _sha(p):
    import hashlib
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


# ── 1. write-once ─────────────────────────────────────────────────────────────────────────

def test_an_EXISTING_session_file_is_never_overwritten_and_the_difference_is_LOGGED(fx,
                                                                                   monkeypatch):
    kept = _bars(D1, 100.0)
    kept["source"] = "yfinance"
    fx.write_parquet(kept, _path(fx, D1))
    before = _sha(_path(fx, D1))
    # Tonight the vendor serves ANOTHER version of D1 (one bar's price moved $9.01, one bar
    # added) and D2 for the first time.
    vendor = pd.concat([_bars(D1, 100.0, n=6, bump_at=2, bump=9.01), _bars(D2, 200.0)])
    monkeypatch.setattr(fx, "yf", _FakeYF(vendor))
    s = fx.export_bars1m()
    assert _sha(_path(fx, D1)) == before, "the kept file was written over"
    assert os.path.exists(_path(fx, D2)), "a NEW session was not written"
    assert s["files_written"] == 1 and s["files_kept"] == 1
    assert s["sessions_written"] == [D2.isoformat()]
    assert s["revisions_logged"] == 1 and s["revised_sessions"] == [D1.isoformat()]
    log = pd.read_csv(os.path.join(fx.ROOT, "bars1m-revisions.tsv"), sep="\t")
    assert list(log.columns) == list(fx.REVISIONS_HEADER)
    row = log.iloc[0]
    assert (row["session"], row["ticker"]) == (D1.isoformat(), "SPY")
    assert row["bars_changed"] == 1 and row["bars_added"] == 1 and row["bars_removed"] == 0
    assert abs(row["largest_price_change"] - 9.01) < 1e-6
    assert "09:32" in row["largest_at"]
    assert row["kept_fp"] != row["vendor_fp"]


def test_the_SAME_version_again_logs_nothing(fx, monkeypatch):
    v = _bars(D1, 100.0)
    monkeypatch.setattr(fx, "yf", _FakeYF(v))
    fx.export_bars1m()
    s = fx.export_bars1m()
    assert s["files_written"] == 0 and s["files_kept"] == 1 and s["revisions_logged"] == 0
    assert not os.path.exists(os.path.join(fx.ROOT, "bars1m-revisions.tsv"))


def test_two_alternating_versions_show_as_two_fingerprints(fx, monkeypatch):
    a, b = _bars(D1, 100.0), _bars(D1, 100.0, bump_at=0, bump=0.05)
    monkeypatch.setattr(fx, "yf", _FakeYF(a))
    fx.export_bars1m()
    for v in (b, a, b):
        monkeypatch.setattr(fx, "yf", _FakeYF(v))
        fx.export_bars1m()
    log = pd.read_csv(os.path.join(fx.ROOT, "bars1m-revisions.tsv"), sep="\t")
    assert len(log) == 2, "only the nights serving the OTHER version are logged"
    assert log["vendor_fp"].nunique() == 1 and (log["kept_fp"] != log["vendor_fp"]).all()


def test_a_session_still_TRADING_is_not_written(fx, monkeypatch):
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    assert fx.session_closed(D1, datetime(2026, 10, 21, 1, 0, tzinfo=et))
    assert not fx.session_closed(D1, datetime(2026, 10, 20, 19, 59, tzinfo=et))
    assert not fx.session_closed(D1, datetime(2026, 10, 20, 20, 4, tzinfo=et))
    assert fx.session_closed(D1, datetime(2026, 10, 20, 20, 5, tzinfo=et))
    monkeypatch.setattr(fx, "yf", _FakeYF(_bars(D1, 100.0)))
    monkeypatch.setattr(fx, "session_closed", lambda d, now: False)
    s = fx.export_bars1m()
    assert s["files_written"] == 0 and s["sessions_open"] == [D1.isoformat()]
    assert not os.path.exists(_path(fx, D1))


def test_the_hold_still_skips_before_anything_else(fx, monkeypatch):
    held = date(2026, 10, 1)
    monkeypatch.setattr(fx, "yf", _FakeYF(_bars(held, 100.0)))
    s = fx.export_bars1m()
    assert s["sessions_held"] == 1 and not os.path.exists(_path(fx, held))


def test_the_job_treats_a_night_with_NOTHING_NEW_as_healthy_and_nothing_KEPT_as_a_fault():
    code = open(BARS_JOB, encoding="utf-8").read()
    i = code.index("if written == 0:")
    j = code.index("return", i)
    branch = code[i:j]
    assert "if not kept or empty:" in branch and "STATUS_COMPLETED_DEFECTIVE" in branch
    assert "export_polygon_bars1m()" in code
    assert "KEPT" in code and "REVISED" in code


# ── 2. the Polygon reference copy ─────────────────────────────────────────────────────────

class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


def _poly_results(d: date, base: float, n: int = 5):
    from zoneinfo import ZoneInfo
    out = []
    for i, ts in enumerate(pd.date_range("%s 09:30" % d.isoformat(), periods=n, freq="min",
                                         tz=ZoneInfo("America/New_York"))):
        p = base + i * 0.1
        out.append({"t": int(ts.timestamp() * 1000), "o": p, "h": p + 0.05, "l": p - 0.05,
                    "c": p, "v": 1000, "vw": p, "n": 12})
    return out


def _seed_yf(fx, days):
    for d in days:
        df = _bars(d, 100.0)
        df["source"] = "yfinance"
        fx.write_parquet(df, _path(fx, d))


NOW = None


def _now():
    from zoneinfo import ZoneInfo
    return datetime(2026, 10, 30, 20, 45, tzinfo=ZoneInfo("America/New_York"))


def test_POLYGON_backfills_from_09_25_writes_once_and_logs_the_differences(fx, capsys):
    days = [date(2026, 9, 24), date(2026, 9, 25), D1, D2, date(2026, 10, 30)]
    _seed_yf(fx, days)
    calls, sleeps = [], []

    def get(url, params=None, timeout=None):
        calls.append((url, dict(params)))
        res = _poly_results(D1, 100.0) + _poly_results(D2, 100.0, n=4)
        res += _poly_results(date(2026, 9, 25), 100.2)
        return _Resp(200, {"results": res})
    out = fx.export_polygon_bars1m(key="TEST-KEY-NEVER-PRINTED", now_et=_now(),
                                   sleep=sleeps.append, get=get)
    assert out["status"] == "ok" and out["calls"] == 1
    # 09-24 is before the back-fill start; 10-30 is the CURRENT session, which the plan withholds.
    assert out["sessions_written"] == ["2026-09-25", D1.isoformat(), D2.isoformat()]
    url, params = calls[0]
    assert url.endswith("/SPY/range/1/minute/2026-09-25/2026-10-21")
    assert params["adjusted"] == "false"
    pol = pd.read_parquet(_path(fx, D1, folder="bars1m-polygon"))
    assert (pol["source"] == "polygon").all() and str(pol.index.tz) == "America/New_York"
    log = pd.read_csv(os.path.join(fx.ROOT, "bars1m-polygon-vs-yfinance.tsv"), sep="\t")
    assert list(log.columns) == list(fx.POLY_VS_YF_HEADER) and len(log) == 3
    d1 = log[log["session"] == D1.isoformat()].iloc[0]
    assert d1["bars_price_differ"] == 0 and d1["only_yfinance"] == 0
    d2 = log[log["session"] == D2.isoformat()].iloc[0]
    assert d2["only_yfinance"] == 1 and d2["only_polygon"] == 0
    s925 = log[log["session"] == "2026-09-25"].iloc[0]
    assert s925["bars_price_differ"] == 5 and abs(s925["largest_price_diff"] - 0.2) < 1e-6
    assert "TEST-KEY-NEVER-PRINTED" not in capsys.readouterr().out

    # Second night: nothing missing -> no call, nothing rewritten.
    before = _sha(_path(fx, D1, folder="bars1m-polygon"))
    out2 = fx.export_polygon_bars1m(key="k", now_et=_now(), sleep=sleeps.append, get=get)
    assert out2["calls"] == 0 and out2["files_written"] == 0
    assert _sha(_path(fx, D1, folder="bars1m-polygon")) == before


def test_POLYGON_paces_at_13s_and_waits_out_a_429(fx):
    from datetime import timedelta
    days = [date(2026, 9, 25) + timedelta(days=i) for i in range(30)]
    days = [d for d in days if d.weekday() < 5][:12]          # two calls' worth
    _seed_yf(fx, days)
    sleeps, statuses = [], [429, 200, 200]

    def get(url, params=None, timeout=None):
        return _Resp(statuses.pop(0), {"results": []})
    out = fx.export_polygon_bars1m(key="k", now_et=_now(), sleep=sleeps.append, get=get)
    assert out["calls"] == 2
    assert sleeps == [60, 13]


def test_POLYGON_stops_on_a_403_and_says_so(fx):
    _seed_yf(fx, [D1])
    out = fx.export_polygon_bars1m(key="k", now_et=_now(), sleep=lambda s: None,
                                   get=lambda *a, **k: _Resp(403, {"status": "NOT_AUTHORIZED"}))
    assert out["status"] == "stopped" and "403" in out["reason"]
    assert out["files_written"] == 0


def test_POLYGON_without_a_key_is_SKIPPED_not_an_error(fx, monkeypatch):
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    out = fx.export_polygon_bars1m(now_et=_now(), get=lambda *a, **k: 1 / 0)
    assert out["status"] == "skipped" and "POLYGON_API_KEY" in out["reason"]
