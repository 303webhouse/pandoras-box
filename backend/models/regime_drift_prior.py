"""LAB's stamped drift-prior table, as data. R-IV.1284(c).

SOURCE, VERIFIED BEFORE ANYTHING WAS COPIED OUT OF IT:

    C:\\temp\\cc-query-handoff\\lab\\regime-scorecard\\step0-v3\\
        DRIFT-PRIOR-TABLE-v1-LAB-STAMPED-R-IV.1279.md
    sha256 c9a00aab7d04faa8a759eab5128e6bb067797711adaeace0b7ca6b35a101d98e   2,326 bytes

sha256sum and PowerShell Get-FileHash agree. LAB stamped it after a measured 2026-10-21
17:11:58 UTC, from REGIME-SCORECARD v1 (`b6a6abd9`), v2-C0 shown labels (`3250061e`), classifier
v2 at `999aae43`, SPY yfinance fully adjusted closes (`14bb3e32`), over 1999-01-04 to 2026-10-16
with the last 20 sessions excluded because their outcome is not yet known.

IT FORECASTS NOTHING AND NOTHING GATES ON IT (#42). It is a description of what followed each
label historically, and the table says of itself that it "sits beside the scorecard's verdict,
NOT CREDIBLE (T2), and does not change it" -- which is carried onto the card rather than left in
the file, because a figure shown without that standing reads as a forecast.

THE WINDOWS OVERLAP, and that is the single most important thing about every n below: a
20-session window starting on each of 2,496 uptrend sessions is not 2,496 independent
observations. The table's own words are kept verbatim on the card: "overlapping windows; about
n / 20 independent."

TYPED OUT RATHER THAN PARSED, deliberately. The file is a ferry artefact under `C:\\temp`, and
R-IV.1043(c) makes a ferried file immutable once handed over -- but it is not in the repo, so a
reader of this module cannot see it and a deploy cannot depend on it being present. The numbers
live here with their hash beside them, and a test re-verifies the hash whenever the file IS
present. Transcription is the risk that buys; the test below compares every figure against the
file when it can be read.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

TABLE_FILE = "DRIFT-PRIOR-TABLE-v1-LAB-STAMPED-R-IV.1279.md"
TABLE_SHA256 = "c9a00aab7d04faa8a759eab5128e6bb067797711adaeace0b7ca6b35a101d98e"
TABLE_PATH = (r"C:\temp\cc-query-handoff\lab\regime-scorecard\step0-v3\%s" % TABLE_FILE)

#: The data file LAB's own stamp names, recorded so the chain is followable.
DATA_FILE_SHA256 = "e0d48657657b2edbe980a6a00c2ff2ce1feb009254cd238c112db92e46dab750"
LAB_CODE = "claude/lab-regime-scorecard-v2 @ cdb8362 (regime_v3_step0.py)"
LAB_STAMPED_AT = "2026-10-21T17:11:58Z"

SPAN = "1999-01-04 to 2026-10-16, last 20 sessions excluded"
HORIZON_SESSIONS = 20

#: R-IV.1284(c): the overall row. "typical worst dip" is the MEDIAN of the largest drop from the
#: running high over the 20 sessions -- a median, not a worst case, and the card says so.
OVERALL = {"n": 6970, "higher_pct": 64.4, "worst_dip_pct": 3.1, "median_return_pct": 1.33,
           "note": "includes 27 unlabelled sessions"}

#: Per label, as stamped. `None` where the table prints a dash: v2 has never shown melt_up or
#: crash_liquidation, so there is NO prior for them -- which is not a prior of zero.
BY_LABEL: Dict[str, Optional[Dict[str, Any]]] = {
    "uptrend":           {"n": 2496, "higher_pct": 68.7, "worst_dip_pct": 2.5, "median_return_pct": 1.26},
    "narrow_uptrend":    {"n": 423,  "higher_pct": 65.7, "worst_dip_pct": 2.9, "median_return_pct": 1.31},
    "recovery":          {"n": 126,  "higher_pct": 81.0, "worst_dip_pct": 1.6, "median_return_pct": 3.04},
    "range_chop":        {"n": 329,  "higher_pct": 56.8, "worst_dip_pct": 2.1, "median_return_pct": 0.61},
    "correction":        {"n": 1577, "higher_pct": 67.1, "worst_dip_pct": 2.9, "median_return_pct": 1.67},
    "breakdown":         {"n": 532,  "higher_pct": 65.4, "worst_dip_pct": 4.6, "median_return_pct": 2.48},
    "bear_market":       {"n": 1425, "higher_pct": 54.3, "worst_dip_pct": 5.1, "median_return_pct": 0.78},
    "bear_market_rally": {"n": 35,   "higher_pct": 54.3, "worst_dip_pct": 6.2, "median_return_pct": 0.23},
    "melt_up":           None,
    "crash_liquidation": None,
}

#: The table's own sentence about independence, VERBATIM in substance and in the ruling's own
#: wording. Shown on the card beside every n.
INDEPENDENCE_NOTE = "overlapping windows; about n \u00f7 20 independent"

#: Cells the table itself says to read as a handful of episodes rather than as a rate.
SMALL_CELL_MAX = 150

STANDING = ("descriptive, not a forecast; nothing gates on it (#42), and it sits beside the "
            "scorecard's verdict NOT CREDIBLE (T2) without changing it")


def for_label(label: Optional[str]) -> Dict[str, Any]:
    """The prior line for one shown label, ready to render, or an explained absence.

    A LABEL WITH NO PRIOR IS NOT A PRIOR OF ZERO. v2 has never shown melt_up or
    crash_liquidation, so the table prints a dash for them; this returns `available: False` with
    that reason rather than a 0% a reader would take as a measurement.
    """
    key = str(label or "").strip().lower().replace("/", "_").replace(" ", "_")
    out: Dict[str, Any] = {
        "label": key or None,
        "overall": dict(OVERALL),
        "independence": INDEPENDENCE_NOTE,
        "horizon_sessions": HORIZON_SESSIONS,
        "span": SPAN,
        "source": "LAB %s (%s), stamped %s" % (TABLE_FILE, TABLE_SHA256[:8], LAB_STAMPED_AT),
        "standing": STANDING,
    }
    if key not in BY_LABEL:
        return dict(out, available=False,
                    reason="%r is not a label in LAB's stamped table" % label)
    row = BY_LABEL[key]
    if row is None:
        return dict(out, available=False,
                    reason="v2 has never shown %s, so the table has no prior for it -- which "
                           "is not a prior of zero" % key)
    small = row["n"] <= SMALL_CELL_MAX
    return dict(out, available=True, **row,
                small_cell=small,
                small_cell_note=("n = %d is a handful of episodes, not a rate" % row["n"])
                if small else None,
                # CONVENTION #37: source, universe and as-of in the same sentence as the figure.
                text=("SPY higher %s sessions later on %.1f%% of %s sessions, typical worst dip "
                      "%.1f%% (median) -- LAB's stamped table, SPY 1999-2026, %s"
                      % (HORIZON_SESSIONS, row["higher_pct"], row["n"],
                         row["worst_dip_pct"], INDEPENDENCE_NOTE)))
