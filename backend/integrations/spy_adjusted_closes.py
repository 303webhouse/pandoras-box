"""SPY fully adjusted daily closes, for the report card's forward-20 figures. R-IV.1327(b).

THE SOURCE IS MATCHED TO LAB'S, NOT CHOSEN. The report card's "higher 20 sessions later" and
"worst dip" are printed BESIDE base rates from LAB's stamped drift-prior table, and a live figure
on a different series is not comparable with the history next to it -- which is the whole of
spec section 1.2's warning. So the question was never "which price series is best", it was "which
one did LAB use", and the answer is read out of the provenance rather than assumed.

PROVENANCE, FOLLOWED TO THE FILE AND VERIFIED:

    DRIFT-PRIOR-TABLE-v1-LAB-STAMPED-R-IV.1279.md   sha256 c9a00aab...  (re-verified)
      -> says: "SPY, yfinance fully adjusted daily closes (`14bb3e32...`)"
    RS-BARS-20261019.parquet                        sha256 14bb3e325a15...  (re-verified)
      -> its own meta.json says: "yfinance 1.7.0 daily, auto_adjust=False,
         pulled 2026-10-19 19:38 UTC"

THOSE TWO SENTENCES LOOK LIKE A CONTRADICTION AND ARE NOT. `auto_adjust=False` makes yfinance
return BOTH columns: `Close`, which is split-adjusted and dividend-UNADJUSTED, and `Adj Close`,
which is adjusted for splits AND dividends. The parquet carries both (`close` and `adj_close`),
so ONE pull supplies both of section 1.2's bases, and "fully adjusted" names the `Adj Close`
column rather than a different download. Measured on the stamped file: 7,728 of 7,749 SPY rows
have `close != adj_close`, and at 1996-01-02 the ratio is 0.5894 -- thirty years of dividends
compounding backwards. They are emphatically not the same series.

SO THIS MODULE PULLS `auto_adjust=False` AND READS `Adj Close`, which is what LAB did, parameter
for parameter.

THE MATCH IS MEASURED, NOT ASSERTED. Fetched here and compared against the stamped parquet over
every overlapping row:

    overlapping rows   7,749 (the full span, 1996-01-02 to 2026-10-16)
    close              max abs diff 0.000000
    adj_close          max abs diff 0.000183, 124 rows above 1e-4

The residual on `adj_close` is expected and is not drift: yfinance recomputes the dividend
adjustment at pull time, LAB pulled on 2026-10-19 and this pulls later, and a dividend paid
between the two shifts the entire back-history by a hair. 0.000183 against prices of $36-$770 is
about 5e-7 relative. `close` matching to the cent in all 7,749 rows is what shows the pull
parameters are identical.

NO CREDENTIAL AND NO COST. yfinance needs no key and is already pinned in both requirements files
(`yfinance>=0.2.36`), so R-IV.1327(b)'s stop condition does not apply. Nothing here reads an env
var or a token.

#42, AND NARROWER THAN THE USUAL FORM. R-IV.1327(b) names the readers: the report card and
nothing else. The classifier, the input builders AND THE 200-DAY ROW never import it -- the
200-day row keeps `regime_daily_bars` (Polygon, split-adjusted, dividend-unadjusted), which is
the basis R2/R3/R4 define it on. That is why this module exposes ONLY the adjusted series: it
could serve the split-only basis too, and exposing it would invite exactly the import the ruling
forbids.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("spy_adjusted_closes")

TICKER = "SPY"

#: LAB's pull parameters, matched exactly. `auto_adjust=False` is what makes `Adj Close`
#: available beside `Close`; with it True there is one column and no way to tell which basis a
#: figure came from.
AUTO_ADJUST = False
ADJ_COLUMN = "Adj Close"

#: Carried on every figure derived from this series (Convention #37, spec section 1.2).
BASIS = "SPY fully adjusted closes (splits and dividends), yfinance Adj Close"

#: The provenance this series is matched to, so a reader can check the match rather than take it.
MATCHED_TO = {
    "table": "DRIFT-PRIOR-TABLE-v1-LAB-STAMPED-R-IV.1279.md",
    "table_sha256": "c9a00aab7d04faa8a759eab5128e6bb067797711adaeace0b7ca6b35a101d98e",
    "bars": "RS-BARS-20261019.parquet",
    "bars_sha256": "14bb3e325a1574138d217a17b69d1f0922c6d1d5bd35be326740831b55edfb4a",
    "pull": "yfinance daily, auto_adjust=False, Adj Close",
}

#: The series is static history plus one bar a day, so an hour is already far tighter than it
#: needs to be. It exists to bound a bad fetch, not to chase freshness.
TTL_SECONDS = 3600

_CACHE: Dict[str, Any] = {"at": 0.0, "rows": []}


def _rows_from_frame(df: Any) -> List[Dict[str, Any]]:
    """`[{date, adj_close}]`, oldest-first. Only the adjusted column leaves this module."""
    import pandas as pd

    if df is None or len(df) == 0:
        return []
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    if ADJ_COLUMN not in df.columns:
        # A yfinance change that dropped Adj Close would otherwise leave this silently reading
        # the WRONG BASIS from `Close`, which is the one failure mode section 1.2 names.
        logger.error("[spy_adj] no %r column; refusing to fall back to Close", ADJ_COLUMN)
        return []
    out: List[Dict[str, Any]] = []
    for idx, val in zip(df.index, df[ADJ_COLUMN]):
        try:
            v = float(val)
        except (TypeError, ValueError):
            continue
        if v != v:                                   # NaN
            continue
        out.append({"date": str(idx)[:10], "adj_close": v})
    return out


def fetch(start: str = "1996-01-01", end: Optional[str] = None) -> List[Dict[str, Any]]:
    """The raw pull, uncached. Never raises; an empty list is a stated absence."""
    try:
        import yfinance as yf

        df = yf.download(TICKER, start=start, end=end, auto_adjust=AUTO_ADJUST,
                         progress=False, actions=False)
        return _rows_from_frame(df)
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("[spy_adj] %s: %s", type(exc).__name__, exc)
        return []


def closes(force: bool = False) -> Dict[str, Any]:
    """`{available, rows, first, last, n, basis, matched_to}`. Cached. Never raises.

    `available: False` with a reason rather than an empty series presented as data: a report
    card panel reading zero rows must say the series could not be read, not that nothing
    happened.
    """
    now = time.time()
    if not force and _CACHE["rows"] and (now - _CACHE["at"]) < TTL_SECONDS:
        rows = _CACHE["rows"]
    else:
        rows = fetch()
        if rows:
            _CACHE.update({"at": now, "rows": rows})

    if not rows:
        return {"available": False, "reason": "the SPY adjusted series could not be read",
                "rows": [], "n": 0, "basis": BASIS, "matched_to": dict(MATCHED_TO)}
    return {
        "available": True,
        "rows": rows,
        "n": len(rows),
        "first": rows[0]["date"],
        "last": rows[-1]["date"],
        "basis": BASIS,
        "matched_to": dict(MATCHED_TO),
        "display_only": True,
    }


def forward_outcome(rows: List[Dict[str, Any]], i: int,
                    horizon: int = 20) -> Optional[Dict[str, Any]]:
    """R5 and R6 for the session at index `i`, or None when the window is not complete.

    R5 "higher"  the close `horizon` sessions later is ABOVE this session's close.
    R6 "worst dip"  the largest drop from the RUNNING HIGH over those sessions, as a percentage.

    NONE RATHER THAN A PARTIAL WINDOW. A 20-session figure computed from 11 sessions is not a
    cautious estimate, it is a different quantity wearing the same name -- and it is exactly
    what the card's `pending` count exists to report instead.
    """
    if i < 0 or i + horizon >= len(rows):
        return None
    base = rows[i]["adj_close"]
    if not base:
        return None
    window = [r["adj_close"] for r in rows[i + 1:i + 1 + horizon]]
    if len(window) < horizon:
        return None
    run_high, worst = base, 0.0
    for px in window:
        run_high = max(run_high, px)
        worst = max(worst, (run_high - px) / run_high * 100.0)
    return {
        "higher": bool(window[-1] > base),
        "worst_dip_pct": round(worst, 2),
        "from_date": rows[i]["date"],
        "to_date": rows[i + horizon]["date"],
        "basis": BASIS,
    }
