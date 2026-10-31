"""R-IV.1469(e)1: write-once must never lock a PARTIAL session.

A Polygon or yfinance session that comes back short is marked partial and retried the next
night, not frozen. COMPLETE = every regular-hours minute has a bar (09:30-15:59 ET, 390 bars;
09:30-12:59 ET, 210, on an early close). A short copy is written as `<file>.partial` -- outside
the `*.parquet` globs TRITON and QUERY read -- and a later complete copy is written once as the
normal file, removing the .partial.

Also R-IV.1469: the nightly "held" line compared a FILE count with a DATE count (88 vs 11) and
printed INTERNAL INCONSISTENCY every night; it now compares files with files.
"""
import glob
import importlib.util
import os
import sys
import types
from datetime import date, datetime, timedelta

import pandas as pd
import pytest

pytest.importorskip("pyarrow")

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
F_EXPORT = os.path.join(REPO, "scripts", "f_export.py")
BARS_JOB = os.path.join(REPO, "scripts", "f_export_bars.py")
D1, D2 = date(2026, 10, 20), date(2026, 10, 21)
HALF = date(2026, 11, 27)


@pytest.fixture
def fx(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("_f_export_r1469", F_EXPORT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "ROOT", str(tmp_path))
    monkeypatch.setattr(mod, "CENSUS", ["SPY"])
    return mod


def _bars(d, n=390, start="09:30", pre=0):
    """n bars from `start` ET, plus `pre` pre-market bars from 04:00 ET."""
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    idx = pd.date_range("%s %s" % (d.isoformat(), start), periods=n, freq="min", tz=et)
    if pre:
        idx = pd.date_range("%s 04:00" % d.isoformat(), periods=pre, freq="min", tz=et).append(idx)
    px = [100.0 + i * 0.01 for i in range(len(idx))]
    return pd.DataFrame({"Open": px, "High": px, "Low": px, "Close": px, "Volume": [1000.0] * len(idx),
                         "Dividends": 0.0, "Stock Splits": 0.0}, index=idx.rename("Datetime"))


class _FakeYF:
    def __init__(self, frame):
        self.frame = frame

    def Ticker(self, t):
        frame = self.frame

        class _T:
            def history(self, **kw):
                return frame.copy()
        return _T()


def _path(fx, d, t="SPY"):
    return os.path.join(fx.ROOT, "bars1m", d.isoformat(), "%s.parquet" % t)


def _session_files(fx):
    """What a reader's glob sees -- the same pattern TRITON/QUERY use."""
    return sorted(glob.glob(os.path.join(fx.ROOT, "bars1m", "*", "*.parquet")))


# ── the completeness rule ─────────────────────────────────────────────────────────────────

def test_rth_count_ignores_extended_hours_and_other_days(fx):
    df = pd.concat([_bars(D1, n=390, pre=30), _bars(D1, n=20, start="16:00"), _bars(D2, n=5)])
    assert fx.rth_bar_count(df.index, D1) == 390
    assert fx.rth_bar_count(df.index, D2) == 5
    # UTC-naive stamps are read as UTC (Polygon's timestamp_utc)
    naive = df.index.tz_convert("UTC").tz_localize(None)
    assert fx.rth_bar_count(naive, D1) == 390


def test_an_early_close_is_complete_at_210(fx):
    assert fx.expected_rth_bars(HALF) == 210 and fx.expected_rth_bars(D1) == 390
    assert fx.rth_bar_count(_bars(HALF, n=210).index, HALF) == 210
    # bars after 13:00 on an early close are not regular hours
    assert fx.rth_bar_count(_bars(HALF, n=300).index, HALF) == 210


# ── yfinance ──────────────────────────────────────────────────────────────────────────────

def test_a_SHORT_yfinance_session_is_written_as_partial_and_not_as_the_session_file(fx, monkeypatch):
    monkeypatch.setattr(fx, "yf", _FakeYF(pd.concat([_bars(D1, n=389), _bars(D2)])))
    s = fx.export_bars1m()
    assert not os.path.exists(_path(fx, D1)), "a short session was frozen as the session file"
    assert os.path.exists(_path(fx, D1) + ".partial")
    assert _session_files(fx) == [_path(fx, D2)], "a reader's *.parquet glob saw the partial"
    assert s["partial"] == ["%s SPY 389/390" % D1.isoformat()]
    assert s["sessions_written"] == [D2.isoformat()] and s["files_written"] == 1


def test_the_next_night_a_COMPLETE_copy_replaces_the_partial(fx, monkeypatch):
    monkeypatch.setattr(fx, "yf", _FakeYF(_bars(D1, n=380)))
    fx.export_bars1m()
    monkeypatch.setattr(fx, "yf", _FakeYF(_bars(D1, n=390, pre=10)))
    s = fx.export_bars1m()
    assert os.path.exists(_path(fx, D1)) and not os.path.exists(_path(fx, D1) + ".partial")
    assert s["partials_completed"] == ["%s SPY" % D1.isoformat()] and s["partial"] == []
    assert len(pd.read_parquet(_path(fx, D1))) == 400
    # ...and from then on it is write-once like any other session file
    monkeypatch.setattr(fx, "yf", _FakeYF(_bars(D1, n=389)))
    s3 = fx.export_bars1m()
    assert s3["files_kept"] == 1 and s3["partial"] == []
    assert len(pd.read_parquet(_path(fx, D1))) == 400


def test_a_longer_short_copy_replaces_the_partial_and_a_shorter_one_does_not(fx, monkeypatch):
    for n in (300, 350, 320):
        monkeypatch.setattr(fx, "yf", _FakeYF(_bars(D1, n=n)))
        s = fx.export_bars1m()
        assert s["partial"] == ["%s SPY %d/390" % (D1.isoformat(), n)]
    assert len(pd.read_parquet(_path(fx, D1) + ".partial")) == 350


def test_an_EXISTING_session_file_is_still_never_rewritten(fx, monkeypatch):
    """Files written before this change are kept as they are, short or not (QUERY measured
    10-16 -> 10-29 at 390 each, so none is short)."""
    old = _bars(D1, n=389)
    fx.write_parquet(old, _path(fx, D1))
    monkeypatch.setattr(fx, "yf", _FakeYF(_bars(D1, n=390)))
    s = fx.export_bars1m()
    assert s["files_kept"] == 1 and s["files_written"] == 0
    assert len(pd.read_parquet(_path(fx, D1))) == 389


# ── Polygon ───────────────────────────────────────────────────────────────────────────────

class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


def _poly(d, n=390):
    from zoneinfo import ZoneInfo
    out = []
    for i, ts in enumerate(pd.date_range("%s 09:30" % d.isoformat(), periods=n, freq="min",
                                         tz=ZoneInfo("America/New_York"))):
        p = 100.0 + i * 0.01
        out.append({"t": int(ts.timestamp() * 1000), "o": p, "h": p, "l": p, "c": p,
                    "v": 1000, "vw": p, "n": 12})
    return out


def _now(d):
    from zoneinfo import ZoneInfo
    return datetime(d.year, d.month, d.day, 20, 45, tzinfo=ZoneInfo("America/New_York"))


def _seed(fx, d, n=390, partial=False):
    df = _bars(d, n=n)
    df["source"] = "yfinance"
    fx.write_parquet(df, _path(fx, d) + (".partial" if partial else ""))


def test_a_SHORT_polygon_session_is_partial_retried_and_completed(fx):
    _seed(fx, D1)
    pp = fx.poly_path(fx.ROOT, D1, "SPY")
    calls = []

    def short(url, params=None, timeout=None):
        calls.append(url)
        return _Resp(200, {"results": _poly(D1, n=388)})
    out = fx.export_polygon_bars1m(key="k", now_et=_now(D2), sleep=lambda s: None, get=short)
    assert not os.path.exists(pp) and os.path.exists(pp + ".partial")
    assert out["partial"] == ["%s SPY 388/390" % D1] and out["files_written"] == 0
    assert not glob.glob(os.path.join(fx.ROOT, "bars1m_polygon_daily", "*", "*_adjusted_false.parquet"))

    def full(url, params=None, timeout=None):
        calls.append(url)
        return _Resp(200, {"results": _poly(D1)})
    out2 = fx.export_polygon_bars1m(key="k", now_et=_now(D2 + timedelta(days=1)),
                                    sleep=lambda s: None, get=full)
    assert len(calls) == 2, "the partial session was not asked for again"
    assert os.path.exists(pp) and not os.path.exists(pp + ".partial")
    assert out2["partials_completed"] == ["%s SPY" % D1] and out2["files_written"] == 1


def test_a_polygon_partial_is_not_asked_for_after_its_retry_window(fx):
    _seed(fx, D1)
    fx.export_polygon_bars1m(key="k", now_et=_now(D2), sleep=lambda s: None,
                             get=lambda *a, **k: _Resp(200, {"results": _poly(D1, n=10)}))
    late = D1 + timedelta(days=fx.POLY_RETRY_DAYS + 1)
    calls = []
    out = fx.export_polygon_bars1m(key="k", now_et=_now(late), sleep=lambda s: None,
                                   get=lambda *a, **k: calls.append(1) or _Resp(200, {"results": []}))
    assert calls == [] and out["calls"] == 0
    assert os.path.exists(fx.poly_path(fx.ROOT, D1, "SPY") + ".partial"), "kept, listed, not deleted"


def test_polygon_still_copies_a_session_whose_yfinance_file_is_partial(fx):
    _seed(fx, D1, n=300, partial=True)
    out = fx.export_polygon_bars1m(key="k", now_et=_now(D2), sleep=lambda s: None,
                                   get=lambda *a, **k: _Resp(200, {"results": _poly(D1)}))
    assert out["files_written"] == 1 and out["compared"] == 1


# ── the manifest and the nightly line ─────────────────────────────────────────────────────

def test_the_manifest_labels_a_partial_copy(fx, monkeypatch):
    monkeypatch.setattr(fx, "yf", _FakeYF(_bars(D1, n=200)))
    fx.export_bars1m()
    fx._manifest_rows.clear()
    rows = [r for r in fx._archive_rows() if r["path"].endswith(".partial")]
    assert len(rows) == 1 and rows[0]["note"].startswith("PARTIAL session copy")
    assert rows[0]["rows_read_back"] == 200


def _run_job(monkeypatch, summary, poly=None):
    spec = importlib.util.spec_from_file_location("_f_export_bars_r1469", BARS_JOB)
    job = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(job)
    said, recorded = [], []
    monkeypatch.setattr(job, "_say", said.append)
    monkeypatch.setattr(job, "_record", lambda status, **kw: recorded.append((status, kw)))
    real_isdir = os.path.isdir
    monkeypatch.setattr(os.path, "isdir",
                        lambda p: True if p in ("F:\\", job.F_ROOT) else real_isdir(p))
    fake = types.ModuleType("f_export")
    fake.R1378C_HOLD_ACTIVE = True
    fake.export_bars1m = lambda: summary
    fake.export_bars1d = lambda: None
    fake.export_polygon_bars1m = lambda: poly or {"status": "ok", "files_written": 0, "calls": 0}
    monkeypatch.setitem(sys.modules, "f_export", fake)
    assert job.main() == job.EXIT_OK
    return said, recorded


def _summary(**kw):
    held_dates = ["2026-10-%02d" % d for d in (2, 5, 6, 7, 8, 9, 12, 13, 14, 15)] + ["2026-10-01"]
    s = {"files_written": 8, "sessions_written": ["2026-10-30"], "tickers_empty": [],
         "files_kept": 80, "revised_sessions": [], "revisions_logged": 0,
         "window_start": "2026-10-02", "window_end": "2026-10-31",
         "sessions_held": 88, "held_dates": sorted(held_dates),
         "held_files": [(d, t) for d in held_dates for t in "ABCDEFGH"],
         "partial": [], "partials_completed": []}
    s.update(kw)
    return s


def test_the_held_line_counts_files_against_files_and_names_both(monkeypatch):
    said, recorded = _run_job(monkeypatch, _summary())
    assert not [m for m in said if "INTERNAL INCONSISTENCY" in m]
    line = [m for m in said if m.startswith("HELD ")][0]
    assert line.startswith("HELD 88 files across 11 sessions (2026-10-01..2026-10-15)")
    assert "88 files (11 sessions) held" in recorded[-1][1]["skip_reason"]


def test_a_real_held_mismatch_is_still_reported(monkeypatch):
    said, _ = _run_job(monkeypatch, _summary(sessions_held=87))
    assert [m for m in said if "INTERNAL INCONSISTENCY: held count 87 but 88 held files" in m]


def test_the_nightly_line_names_partials_and_completions(monkeypatch):
    said, recorded = _run_job(monkeypatch, _summary(
        partial=["2026-10-30 SMH 389/390"], partials_completed=["2026-10-29 SPY"]))
    line = [m for m in said if m.startswith("HELD ")][0]
    assert "PARTIAL 1 (retried next night): 2026-10-30 SMH 389/390" in line
    assert "partials completed: 2026-10-29 SPY" in line
    assert "1 partial (retried next night)" in recorded[-1][1]["skip_reason"]
