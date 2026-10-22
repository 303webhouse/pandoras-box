"""FINRA short interest goes live. R-IV.1318(a)/(b).

WHAT THE ACCESS CHECK FOUND, measured against FINRA's own endpoints on 2026-10-21 rather than
read off a page. R-IV.1318(a) asked which path needs no paid credential. Three exist and only
one is usable:

    api.finra.org/data/group/otcMarket/name/EquityShortInterest
        no credential, HTTP 200 -- but OTC-ONLY (AAPL and SPY both 204) and it ENDS AT
        SETTLEMENT 2022-09-15. Bisected: `> 2022-09-01` returns rows, `> 2022-10-01` is 204.
    api.finra.org/data/group/Equity/name/consolidatedShortInterest
        HTTP 401. NOTE 401 AND NOT 404 -- the dataset is real and token-gated, needing an
        Individual Account. The control that makes that reading sound: OTCMarket/weeklysummary
        returns 200 with no credential, so the API does serve some datasets anonymously.
    cdn.finra.org/equity/otcmarket/biweekly/shrt<YYYYMMDD>.csv
        NO CREDENTIAL AND NO ACCOUNT. 200, 2.7MB, 22,581 rows, and it covers EXCHANGE-LISTED
        names -- AAPL (NNM), SPY (ARCA), GME (NYSE), TSLA (NNM).

So R-IV.1318(a)2's STOP condition never fired: nothing here needs Nick to create an account and
no credential exists to store.

TWO EARLIER FINDINGS WERE WRONG, and the row had been held back on them:

    "days to cover is not a documented field in FINRA's own file"  -- FALSE. The file carries
        `daysToCoverQuantity` AND `averageDailyVolumeQuantity`. Measured AAPL 2026-09-30: short
        120,763,539, ADV 39,858,260, days to cover 3.03.
    "short interest is not served by the API at all"  -- wrong in detail, and it did not matter:
        the route used is the file, not the API.

THESE TESTS DO NOT CALL FINRA. A suite that reaches the public internet fails for reasons that
have nothing to do with the code, and twice-monthly data would make a live assertion wrong for
about thirteen days in every fourteen. The parsing, the date handling and the row shape are
exercised against a fixture cut from the real file; the live reads above are recorded here and
in the module, where they belong.
"""
from __future__ import annotations

import pathlib
import sys
from datetime import date

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from integrations import finra_short_interest as fsi               # noqa: E402
from models import crowd_b6 as cb                                  # noqa: E402

from ._srcscan import read_source                                  # noqa: E402

#: Two real rows, copied from shrt20260930.csv, with FINRA's own header.
SAMPLE = (
    '"accountingYearMonthNumber"|"symbolCode"|"issueName"|"issuerServicesGroupExchangeCode"'
    '|"marketClassCode"|"currentShortPositionQuantity"|"previousShortPositionQuantity"'
    '|"stockSplitFlag"|"averageDailyVolumeQuantity"|"daysToCoverQuantity"|"revisionFlag"'
    '|"changePercent"|"changePreviousNumber"|"settlementDate"\n'
    '"20260930"|"SPY"|"State Street SPDR S&P 500 ETF"|"E"|"ARCA"|"98476070"|"99297854"|""'
    '|"48804519"|"2.02"|""|"-0.83"|"-821784"|"2026-09-30"\n'
    '"20260930"|"AAPL"|"Apple Inc. Common Stock"|"R"|"NNM"|"120763539"|"128753092"|""'
    '|"39858260"|"3.03"|""|"-6.21"|"-7989553"|"2026-09-30"\n'
)


# ── the file, parsed ────────────────────────────────────────────────────────

def test_the_file_is_PIPE_delimited_and_keyed_by_symbol():
    rows = fsi._parse(SAMPLE)
    assert set(rows) == {"SPY", "AAPL"}
    assert rows["SPY"]["marketClassCode"] == "ARCA"


def test_it_covers_EXCHANGE_LISTED_names_which_is_why_this_route_was_chosen():
    """The no-credential API route is OTC-only and returns 204 for both of these. A positioning
    tile about SPY cannot be built on a dataset that has no SPY."""
    rows = fsi._parse(SAMPLE)
    assert rows["SPY"]["issuerServicesGroupExchangeCode"] == "E"
    assert rows["AAPL"]["marketClassCode"] == "NNM"


def test_DAYS_TO_COVER_IS_FINRAS_OWN_FIELD_not_computed_here():
    """The finding that held this row back for two rulings was that FINRA's file documents no
    days-to-cover field, so the figure would have to be computed against an average daily volume
    from somewhere else -- at which point it is not from FINRA's file. The field is there."""
    rows = fsi._parse(SAMPLE)
    assert rows["AAPL"]["daysToCoverQuantity"] == "3.03"
    assert rows["AAPL"]["averageDailyVolumeQuantity"] == "39858260"
    src = read_source(str(_BACKEND / "integrations" / "finra_short_interest.py"))
    assert "daysToCoverQuantity" in src
    # nothing here divides short interest by a volume from another source
    assert "/ adv" not in src and "/ average" not in src


# ── both dates ──────────────────────────────────────────────────────────────

def test_the_publish_date_is_OBSERVED_from_Last_Modified():
    """FINRA publishes on about the 7th business day after settlement, and a rule-of-thumb date
    would be a guess printed as a fact. Measured: settlement 2026-09-30 -> Mon, 12 Oct 2026."""
    assert fsi._publish_date("Mon, 12 Oct 2026 10:00:21 GMT") == "2026-10-12"
    assert fsi._publish_date("Mon, 28 Sep 2026 10:01:36 GMT") == "2026-09-28"


def test_an_unreadable_publish_header_is_NONE_and_never_today():
    """A missing header must not quietly become the current date, which would present an old
    file as freshly published."""
    assert fsi._publish_date(None) is None
    assert fsi._publish_date("") is None
    assert fsi._publish_date("not a date") is None


def test_the_settlement_dates_tried_are_the_15th_and_month_end_newest_first():
    got = fsi.candidate_settlements(date(2026, 10, 21))
    assert got[0] == date(2026, 10, 15)
    assert got[1] == date(2026, 9, 30)
    assert got[2] == date(2026, 9, 15)
    assert all(d <= date(2026, 10, 21) for d in got), "never a future settlement"


def test_a_settlement_that_is_not_published_yet_is_SKIPPED_not_reported():
    """2026-10-15 answers 403 today because its file does not exist yet. That is routine, not an
    error, and the loop falls through to the newest published settlement."""
    src = read_source(str(_BACKEND / "integrations" / "finra_short_interest.py"))
    i = src.index("async def _fetch")
    block = src[i:src.index("async def load_latest", i)]
    assert "403" in block and "not published yet" in block
    assert "return None" in block


# ── no credential anywhere ──────────────────────────────────────────────────

def test_NO_CREDENTIAL_IS_READ_OR_STORED_because_the_route_needs_none():
    """R-IV.1318(a)2: never store a credential in code. There is nothing to store -- the file is
    public -- so the module must not read a key, a token or an env var at all."""
    src = read_source(str(_BACKEND / "integrations" / "finra_short_interest.py"))
    for needle in ("os.getenv", "environ", "API_KEY", "Authorization", "Bearer", "client_secret"):
        assert needle not in src, needle


def test_it_is_display_only_and_nothing_gates_on_it():
    """#42. The row is one line on a positioning tile."""
    hits = []
    for path in sorted(_BACKEND.rglob("*.py")):
        if "__pycache__" in str(path) or path.name.startswith("test_"):
            continue
        if "finra_short_interest" in path.read_text(encoding="utf-8"):
            hits.append(path.name)
    assert sorted(hits) == ["crowd.py", "finra_short_interest.py"], hits


# ── the row ─────────────────────────────────────────────────────────────────

def _live_si():
    rows = fsi._parse(SAMPLE)
    r = rows["SPY"]
    return {"available": True, "symbol": "SPY", "days_to_cover": 2.02,
            "current_short": 98476070.0, "average_daily_volume": 48804519.0,
            "settlement_date": r["settlementDate"], "publish_date": "2026-10-12",
            "attribution": fsi.ATTRIBUTION, "cadence": fsi.CADENCE_NOTE}


def test_the_live_row_carries_BOTH_DATES_and_the_attribution():
    row = cb.short_interest_row(_live_si())
    assert row["value"] == "2.02"
    assert row["settlement_date"] == "2026-09-30"
    assert row["publish_date"] == "2026-10-12"
    assert row["attribution"] == "Source: FINRA"
    assert "twice-monthly" in row["cadence"]
    assert "not real-time" in row["cadence"]


def test_the_row_is_NO_LONGER_A_MOCK():
    assert cb.short_interest_row(_live_si())["mock"] is False
    assert cb.short_interest_row(None)["mock"] is False, (
        "unavailable is not a mock either -- it is a stated absence")


def test_an_unavailable_read_gives_a_REASON_not_a_zero():
    row = cb.short_interest_row({"available": False, "reason": "no file read"})
    assert row["value"] == "—"
    assert row["days_to_cover"] if False else row.get("crowded_short") is None
    assert "unavailable this read" in row["source"] and "no file read" in row["source"]


def test_the_row_has_NO_PERCENTILE_and_therefore_never_votes():
    """A percentile needs a history and this route serves one settlement per 2.7MB file.
    `headline()` counts only rows that are live AND have a percentile, so the row displays a
    real figure and stays out of the market call -- which is the honest arrangement, not a
    limitation worked around."""
    row = cb.short_interest_row(_live_si())
    assert row["pct"] is None and row["thin"] is True
    word, lean, basis = cb.headline([row])
    assert word is None and "no live positioning row has a percentile" in basis


@pytest.mark.parametrize("dtc,expect", [(2.02, False), (4.99, False), (5.0, True), (9.1, True)])
def test_the_crowded_short_flag_is_the_rulings_threshold(dtc, expect):
    row = cb.short_interest_row(dict(_live_si(), days_to_cover=dtc))
    assert row["crowded_short"] is expect
    assert row["crowded_short_at"] == cb.CROWDED_SHORT_DTC == 5.0


def test_the_source_line_names_the_file_and_both_dates():
    """A reader who wants to check the number has to be able to find it."""
    src = cb.short_interest_row(_live_si())["source"]
    assert "cdn.finra.org" in src
    assert "2026-09-30" in src and "2026-10-12" in src


# ── the card ────────────────────────────────────────────────────────────────

def test_the_tile_renders_both_dates_and_names_FINRA():
    js = read_source(str(_BACKEND.parent / "frontend" / "v2.js"))
    i = js.index("function agDates(r)")
    block = js[i:i + 700]
    assert "settled " in block and "published " in block
    assert "r.settlement_date" in block and "r.publish_date" in block
    assert "ag-attrib" in js, "the panel must carry the attribution"
    j = js.index("ag-attrib")
    assert "f.attribution" in js[max(0, j - 400):j + 400], (
        "rendered from the row, so a panel without FINRA data stops claiming FINRA")


def test_the_dates_are_absent_rather_than_blank_when_there_is_no_settlement():
    js = read_source(str(_BACKEND.parent / "frontend" / "v2.js"))
    i = js.index("function agDates(r)")
    assert "if (!r.settlement_date) return" in js[i:i + 240]
