"""SPY fully adjusted closes, matched to LAB's drift-prior pull. R-IV.1327(b).

WHY THE SOURCE WAS FOLLOWED RATHER THAN CHOSEN. The report card prints live "higher 20 sessions
later" and "worst dip" figures BESIDE base rates from LAB's stamped table. A live figure computed
on a different series is not comparable with the history next to it, which is the whole of spec
section 1.2. So the question was never which price series is best; it was which one LAB used.

THE PROVENANCE CHAIN, FOLLOWED TO THE FILE:

    DRIFT-PRIOR-TABLE-v1-LAB-STAMPED-R-IV.1279.md  c9a00aab...
      says "SPY, yfinance fully adjusted daily closes (`14bb3e32...`)"
    RS-BARS-20261019.parquet                       14bb3e325a15...
      its meta.json says "yfinance 1.7.0 daily, auto_adjust=False, pulled 2026-10-19 19:38 UTC"

THOSE LOOK CONTRADICTORY AND ARE NOT, and the reconciliation is the finding of this block.
`auto_adjust=False` makes yfinance return BOTH `Close` (split-adjusted, dividend-UNADJUSTED) and
`Adj Close` (splits AND dividends). The parquet carries both columns, so ONE pull supplies both
of section 1.2's bases and "fully adjusted" names the COLUMN, not a different download. Measured
on the stamped file: 7,728 of 7,749 SPY rows have `close != adj_close`, and at 1996-01-02 the
ratio is 0.5894 -- thirty years of dividends compounding backwards.

THE MATCH IS MEASURED. Fetched and compared against the stamped parquet over all 7,749
overlapping rows: `close` max abs diff 0.000000, `adj_close` max abs diff 0.000183 (124 rows
above 1e-4, about 5e-7 relative). The residual is yfinance recomputing the dividend adjustment
at pull time -- LAB pulled 2026-10-19, this pulled later, and a dividend in between shifts the
whole back-history slightly. `close` matching to the cent in every row is what shows the pull
parameters are identical.

NO NETWORK IN THIS FILE. A suite that reaches Yahoo fails for reasons that have nothing to do
with the code. The pure functions are exercised against fixtures; the live match above is
recorded in the module and in the report, where a measurement belongs.
"""
from __future__ import annotations

import hashlib
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from integrations import spy_adjusted_closes as sa                 # noqa: E402

from ._srcscan import read_source                                  # noqa: E402

STAMPED = pathlib.Path(
    r"C:\temp\cc-query-handoff\lab\regime-scorecard\RS-BARS-20261019.parquet")
TABLE = pathlib.Path(
    r"C:\temp\cc-query-handoff\lab\regime-scorecard\step0-v3"
    r"\DRIFT-PRIOR-TABLE-v1-LAB-STAMPED-R-IV.1279.md")


def _series(prices):
    return [{"date": "2026-01-%02d" % (i + 1), "adj_close": float(p)}
            for i, p in enumerate(prices)]


# ── the pull parameters are LAB's ───────────────────────────────────────────

def test_the_pull_matches_LABs_PARAMETER_FOR_PARAMETER():
    """`auto_adjust=False` plus the `Adj Close` column. With auto_adjust True there is ONE
    column and no way to tell from a figure which basis produced it."""
    assert sa.AUTO_ADJUST is False
    assert sa.ADJ_COLUMN == "Adj Close"
    src = read_source(str(_BACKEND / "integrations" / "spy_adjusted_closes.py"))
    assert "auto_adjust=AUTO_ADJUST" in src


def test_the_provenance_is_NAMED_not_described():
    """R-IV.1327(b) asks for the source to be named. A reader has to be able to check the match
    rather than take it, so both hashes travel with the series."""
    m = sa.MATCHED_TO
    assert m["table_sha256"] == (
        "c9a00aab7d04faa8a759eab5128e6bb067797711adaeace0b7ca6b35a101d98e")
    assert m["bars_sha256"] == (
        "14bb3e325a1574138d217a17b69d1f0922c6d1d5bd35be326740831b55edfb4a")
    assert "auto_adjust=False" in m["pull"] and "Adj Close" in m["pull"]


def test_the_basis_string_says_BOTH_adjustments():
    assert "splits and dividends" in sa.BASIS
    assert "Adj Close" in sa.BASIS


@pytest.mark.skipif(not TABLE.exists(), reason="the stamped table is not on this machine")
def test_the_stamped_TABLE_still_hashes_to_what_we_cite():
    assert hashlib.sha256(TABLE.read_bytes()).hexdigest() == sa.MATCHED_TO["table_sha256"]


@pytest.mark.skipif(not STAMPED.exists(), reason="the stamped parquet is not on this machine")
def test_the_stamped_PARQUET_still_hashes_to_what_we_cite():
    assert hashlib.sha256(STAMPED.read_bytes()).hexdigest() == sa.MATCHED_TO["bars_sha256"]


@pytest.mark.skipif(not STAMPED.exists(), reason="the stamped parquet is not on this machine")
def test_the_two_columns_in_the_stamped_file_are_GENUINELY_DIFFERENT_SERIES():
    """The reconciliation, re-measured rather than quoted. If `close` and `adj_close` were the
    same, "fully adjusted" would be a distinction without a difference and picking the wrong
    column would cost nothing -- which is exactly the reasoning that leads to picking it."""
    import pandas as pd

    df = pd.read_parquet(STAMPED)
    spy = df[df["ticker"] == "SPY"].sort_values("date")
    differ = int((spy["close"] - spy["adj_close"]).abs().gt(1e-6).sum())
    assert len(spy) == 7749
    assert differ > 7000, "the two columns must differ on nearly every row"
    oldest = spy.iloc[0]
    assert oldest["adj_close"] / oldest["close"] < 0.7, (
        "thirty years of dividends must compound backwards to well under the raw close")


# ── only the adjusted column leaves the module ──────────────────────────────

def test_only_the_ADJUSTED_column_is_exposed():
    """R-IV.1327(b) names the readers, and the 200-day row is NOT one. This module could serve
    the split-only basis too -- the same pull carries it -- and exposing it would invite exactly
    the import the ruling forbids."""
    rows = sa.closes.__doc__ or ""
    src = read_source(str(_BACKEND / "integrations" / "spy_adjusted_closes.py"))
    i = src.index("def _rows_from_frame")
    block = src[i:src.index("def fetch", i)]
    assert '"adj_close"' in block
    assert '"close"' not in block, "the unadjusted column must not be served from here"


def test_a_missing_Adj_Close_column_REFUSES_rather_than_falling_back_to_Close():
    """The one failure mode section 1.2 names. A yfinance change that dropped the column would
    otherwise leave this silently reading the WRONG BASIS, and every live figure would quietly
    stop being comparable with the history beside it."""
    import pandas as pd

    df = pd.DataFrame({"Close": [1.0, 2.0]}, index=pd.to_datetime(["2026-01-01", "2026-01-02"]))
    assert sa._rows_from_frame(df) == []
    src = read_source(str(_BACKEND / "integrations" / "spy_adjusted_closes.py"))
    assert "refusing to fall back to Close" in src


def test_rows_are_oldest_first_and_drop_unreadable_values():
    import numpy as np
    import pandas as pd

    df = pd.DataFrame({"Adj Close": [10.0, np.nan, 12.0]},
                      index=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]))
    got = sa._rows_from_frame(df)
    assert [r["date"] for r in got] == ["2026-01-01", "2026-01-03"]
    assert got[0]["adj_close"] == 10.0


# ── R5 and R6 ───────────────────────────────────────────────────────────────

def test_higher_is_the_close_20_SESSIONS_LATER_not_the_peak():
    """R5. A window that rose and gave it all back is NOT higher, however high it went."""
    rows = _series([100] + [150] * 19 + [90])
    out = sa.forward_outcome(rows, 0, horizon=20)
    assert out["higher"] is False
    assert out["from_date"] == "2026-01-01" and out["to_date"] == "2026-01-21"


def test_worst_dip_is_from_the_RUNNING_HIGH_not_from_the_start():
    """R6. A window that climbs 20% then falls 10% from that peak has a 10% worst dip, not 0 --
    measuring from the entry would report no drawdown at all on a profitable window."""
    rows = _series([100] + [120] * 10 + [108] * 9 + [115])
    out = sa.forward_outcome(rows, 0, horizon=20)
    assert out["worst_dip_pct"] == pytest.approx(10.0, abs=0.01)
    assert out["higher"] is True


def test_a_monotonic_rise_has_a_ZERO_worst_dip():
    rows = _series([100 + i for i in range(25)])
    assert sa.forward_outcome(rows, 0, horizon=20)["worst_dip_pct"] == 0.0


def test_an_INCOMPLETE_window_is_NONE_and_never_a_partial_figure():
    """A 20-session figure computed from 11 sessions is a different quantity under the same
    name -- and it is precisely what the card's `pending` count exists to report instead."""
    rows = _series([100 + i for i in range(15)])
    assert sa.forward_outcome(rows, 0, horizon=20) is None
    assert sa.forward_outcome(rows, len(rows) - 1, horizon=20) is None
    assert sa.forward_outcome(rows, -1, horizon=20) is None


def test_every_outcome_carries_its_BASIS():
    rows = _series([100 + i for i in range(25)])
    assert sa.forward_outcome(rows, 0)["basis"] == sa.BASIS


# ── no credential, no cost ──────────────────────────────────────────────────

def test_NO_CREDENTIAL_IS_READ_because_the_source_needs_none():
    """R-IV.1327(b): stop and report if the matching source needs a credential or a cost. It
    needs neither -- yfinance takes no key and is already pinned in both requirements files --
    so there is nothing to store and nothing to ask Nick for."""
    src = read_source(str(_BACKEND / "integrations" / "spy_adjusted_closes.py"))
    for needle in ("os.getenv", "environ", "API_KEY", "Authorization", "Bearer", "api_key"):
        assert needle not in src, needle


def test_yfinance_is_pinned_in_requirements():
    for name in ("requirements.txt",):
        txt = (_BACKEND.parent / name).read_text(encoding="utf-8")
        assert "yfinance" in txt, name


# ── #42, narrower than usual ────────────────────────────────────────────────

def test_the_ONLY_importer_is_the_report_card_path():
    """R-IV.1327(b) names them: the report card and nothing else. The classifier, the input
    builders AND THE 200-DAY ROW never import it -- the 200-day row keeps `regime_daily_bars`,
    which is the basis R2/R3/R4 define it on. Counted as imports from the parsed tree."""
    import ast

    importers = []
    for path in sorted(_BACKEND.rglob("*.py")):
        if "__pycache__" in str(path) or path.name.startswith("test_"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""] + [a.name for a in node.names]
            else:
                continue
            if any("spy_adjusted_closes" in (n or "") for n in names):
                importers.append(path.name)
                break
    assert sorted(set(importers)) == ["regime_report_scoring.py", "regime_strategy.py"], importers


def test_the_200_day_row_does_NOT_use_it():
    """Explicitly, because it is the import a later reader is most likely to add: the 200-day
    row is about SPY closes too, and the series is right there."""
    src = read_source(str(_BACKEND / "models" / "regime_ma200.py"))
    assert "spy_adjusted_closes" not in src
    assert "fully adjusted" not in src.lower() or "split" in src.lower()


def test_the_classifier_and_the_builders_do_not_know_it_exists():
    for mod in ("regime_classifier.py", "regime_inputs.py", "regime_inputs_v2.py",
                "regime_hysteresis.py"):
        assert "spy_adjusted_closes" not in read_source(str(_BACKEND / "models" / mod)), mod
    assert "spy_adjusted_closes" not in read_source(str(_BACKEND / "jobs" / "regime_job.py"))


# ── the scoring that consumes it ────────────────────────────────────────────

def test_a_session_is_CHECKED_only_when_its_whole_window_exists():
    """P1. The last 20 sessions of any live span are pending by construction, and reporting them
    as scored would mean grading a call before its horizon closed."""
    from models import regime_report_scoring as rs

    rows = _series([100 + i for i in range(40)])
    sessions = [{"as_of": r["date"], "shown_regime": "uptrend"} for r in rows]
    got = rs.score_sessions(sessions, rows, {"uptrend": "TREND-UP"})
    # 40 rows indexed 0..39: index 19 is the last with a complete window (rows[20..39]), so
    # TWENTY are checked and twenty pending. My first expectation said 19 -- an off-by-one in
    # the test, not in the code, and the kind that would have been written into the card as a
    # silently short count.
    assert got["checked_total"] == 20
    assert got["per_label"]["uptrend"]["sessions"] == 40
    assert got["per_label"]["uptrend"]["checked"] == 20
    assert got["per_label"]["uptrend"]["sessions"] - got["per_label"]["uptrend"]["checked"] == 20


def test_a_warning_HELD_is_measured_against_the_REGISTERED_median():
    """P5a: the 3.09% ALL-sessions median from R9, not a number chosen here."""
    from models import regime_report_scoring as rs

    assert rs.WARNING_DIP_PCT == 3.09
    rows = _series([100] + [100] * 10 + [80] * 10 + [100] * 10)
    sessions = [{"as_of": rows[0]["date"], "shown_regime": "breakdown"}]
    got = rs.score_sessions(sessions, rows, {"breakdown": "TREND-DOWN/STRESS"})
    assert got["warnings"]["checked"] == 1
    assert got["warnings"]["held"] == 1, "a 20% dip clears the 3.09% threshold"
