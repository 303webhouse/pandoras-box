"""The Regime Report Card: skeleton only. R-IV.1318(c).

WHAT THIS IS AND IS NOT, because a report card is the single most dangerous shape of display on
this hub. It is a page that tells Nick how well the regime module has been calling the market.
A plausible number on it gets trusted immediately and questioned late, which is exactly backwards
for a figure nobody has agreed the definition of yet.

So: SKELETON ONLY, MOCK VALUES ONLY. QUERY is writing the scoring spec under R-IV.1316 and the
wiring waits for it. This module exists to hold the shape, the scope rule and the lint -- not to
compute a score.

THE SCOPE RULE IS THE PART THAT MATTERS MOST. When it is wired, its only reads are regime rows
AFTER the v2.1 cutover. Nothing is backfilled. A report card that graded the era before the
version it grades would be marking a different classifier's homework and reporting the result as
this one's -- and with 304 pre-cutover rows sitting in the same table behind nothing but a
`rules_version` column, that is one forgotten predicate away at all times.

#42, THE SAME IMPORT RULE AS `regime_ma200`. Nothing computes from the report card. The
classifier, both input builders, the hysteresis and the nightly must not import it; a test
asserts that, because a score is precisely what a later reader reaches for when they want to
gate something, and an import is the first step.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

FIXTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                       "frontend", "assets", "regime", "report_card_mock.v1.json")

#: The design the skeleton is built from, hashed. Raw and LF hashes agree -- the file is LF
#: already -- so one value pins it either way.
FERRY_SHA256 = "ffd15cc3bc775a70e94b26b68775a475b2556e4e7bb10e2e11405bd85ff4e51b"

#: The version whose rows may be scored, and the only one. R-IV.1318(c).
SCORED_VERSION = "v2.1"

#: Stated here so the wiring commit cannot quietly widen it.
SCOPE_RULE = ("regime rows with rules_version = '%s' and settled IS TRUE, from the cutover "
              "session forward. No backfill, no earlier era, no other version." % SCORED_VERSION)

#: The panels the card carries, in the order R-IV.1321(b) sets: flips and the 200-day row
#: LEAD, the worst-dip ORDER panel is added (P10), and the per-label table is last and
#: smallest. The order is the finding -- QUERY measured flips at ~1.3 years to a verdict and
#: the per-label share at ~14.6 POOLED, so the original mock gave the most space to the
#: slowest panel.
PANEL_ORDER = ("flips", "ma200", "dip_order", "warnings_held", "all_clears_held", "by_label")

#: Spec section 8, in INDEPENDENT windows (R7) except flips, whose threshold is in live
#: sessions because it comes from a Poisson power calculation.
MIN_SESSIONS_FLIPS = 333
MIN_SCORED_UPCROSSES = 10
MIN_INDEP_HELD = 10
MIN_INDEP_LABEL_SHARE = 20

#: P7c + P8.
VERDICT_STATES = ("EARLY", "CONSISTENT WITH HISTORY", "DEPARTS FROM HISTORY",
                  "NOT REACHABLE AT THIS RATE")

#: R9's gap, verbatim.
NO_BASE_RATE = "no base rate (never shown 1999-2026)"

def load_fixture(path: str = FIXTURE) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def lint_report_mock(obj: Any) -> List[str]:
    """Every problem found, as sentences. Empty means well-formed.

    Shape only. The NUMBERS are fake by design and asserting one would pin the fixture to
    itself. What it DOES check is the handful of shapes a half-written scorer produces first,
    and the three the spec forbids outright.
    """
    bad: List[str] = []
    if not isinstance(obj, dict):
        return ["the fixture is not an object"]
    if obj.get("_mock") is not True:
        bad.append("`_mock` must be true: a report card that does not announce itself as a "
                   "fixture is the most trustable-looking fake surface on the hub")
    for field in ("scope", "flips", "ma200", "dip_order", "by_label", "footer"):
        if field not in obj:
            bad.append("no `%s`" % field)

    scope = obj.get("scope") or {}
    if scope.get("rules_version") != SCORED_VERSION:
        bad.append("the scope must name %s and nothing else" % SCORED_VERSION)
    if scope.get("backfilled") is not False:
        bad.append("`backfilled` must be false: nothing is ever backfilled, "
                   "including to repair a gap")

    # P7, the spec's own highest-risk item.
    ma = obj.get("ma200") or {}
    for field in ("up_crosses", "scored", "pending"):
        if field not in ma:
            bad.append("the 200-day panel must print %s (P7), never a bare count" % field)
    if isinstance(ma.get("scored"), int) and ma.get("scored") == 0 and ma.get("whipsaws") == 0:
        bad.append("`whipsaws: 0` with nothing scored is the bare zero P7 forbids: it reads as "
                   "'none went wrong' when it means 'none has finished its window'")
    if isinstance(ma.get("scored"), int) and isinstance(ma.get("up_crosses"), int):
        if ma["scored"] > ma["up_crosses"]:
            bad.append("more scored up-crosses (%d) than up-crosses (%d)"
                       % (ma["scored"], ma["up_crosses"]))
    if isinstance(ma.get("whipsaws"), int) and isinstance(ma.get("scored"), int):
        if ma["whipsaws"] > ma["scored"]:
            bad.append("more whipsaws (%d) than scored up-crosses (%d), which cannot happen"
                       % (ma["whipsaws"], ma["scored"]))

    rows = obj.get("by_label")
    if not isinstance(rows, list):
        bad.append("`by_label` must be a list")
        rows = []
    for r in rows:
        if not isinstance(r, dict):
            bad.append("a by_label row is not an object")
            continue
        # R-IV.1321(b): DESCRIPTIVE ONLY. A verdict column that can never fill is worse than
        # no column.
        if "verdict" in r:
            bad.append("row %r has a verdict column; the per-label table is descriptive only"
                       % r.get("label"))
        for field in ("sessions", "checked", "pending", "indep", "history_available"):
            if field not in r:
                bad.append("row %r has no `%s`" % (r.get("label"), field))
        if isinstance(r.get("checked"), int) and isinstance(r.get("sessions"), int):
            if r["checked"] > r["sessions"]:
                bad.append("row %r reports more checked calls (%d) than sessions (%d)"
                           % (r.get("label"), r["checked"], r["sessions"]))
        if r.get("checked") == 0 and r.get("share_higher") is not None:
            bad.append("row %r has 0 checked calls but a share" % r.get("label"))
        # Spec section 11.4: no percentage from fewer than one independent window.
        if (r.get("indep") or 0) < 1 and r.get("share_higher") is not None:
            bad.append("row %r shows a share with no independent window" % r.get("label"))
        # R9's gap, said out loud rather than as 0, a blank, or the group's rate.
        if r.get("history_available") is False and r.get("history_note") != NO_BASE_RATE:
            bad.append("row %r has no base rate and must say so verbatim" % r.get("label"))
        if r.get("history_available") is False and r.get("history_share") is not None:
            bad.append("row %r claims a base rate it does not have" % r.get("label"))

    for key in ("flips", "ma200", "dip_order"):
        v = ((obj.get(key) or {}).get("verdict") or {}).get("state")
        if v is not None and v not in VERDICT_STATES:
            bad.append("%s has verdict state %r, which is not one of the four" % (key, v))

    foot = str(obj.get("footer") or "")
    if "#42" not in foot:
        bad.append("the footer must state #42: the scores change nothing")
    if "backfill" not in foot.lower():
        bad.append("the footer must say nothing is backfilled")
    return bad