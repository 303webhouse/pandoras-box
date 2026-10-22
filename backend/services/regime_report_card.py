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

#: Every stat cell the design carries, by key. A cell missing from a payload is a hole on the
#: card, and a hole on a report card reads as a zero.
REQUIRED_STATS = ("CALLS CHECKED", "FLIPS PER YEAR", "WARNINGS THAT HELD", "ALL-CLEARS THAT HELD")

REQUIRED_COLUMNS = 6


def load_fixture(path: str = FIXTURE) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def lint_report_mock(obj: Any) -> List[str]:
    """Every problem found, as sentences. Empty means well-formed.

    Shape only. The NUMBERS are fake by design and asserting one would pin the fixture to
    itself -- the same reasoning as `regime_card_v21.lint_card_mock`.
    """
    bad: List[str] = []
    if not isinstance(obj, dict):
        return ["the fixture is not an object"]
    if obj.get("_mock") is not True:
        bad.append("`_mock` must be true: a report card that does not announce itself as a "
                   "fixture is the most trustable-looking fake surface on the hub")
    for field in ("headline", "sub", "badge", "stats", "table", "ma200", "footer"):
        if not obj.get(field):
            bad.append("no `%s`" % field)

    stats = obj.get("stats")
    if not isinstance(stats, list):
        bad.append("`stats` must be a list")
    else:
        keys = [s.get("key") for s in stats if isinstance(s, dict)]
        for want in REQUIRED_STATS:
            if want not in keys:
                bad.append("the %s cell is missing" % want)
        for s in stats:
            if isinstance(s, dict) and not s.get("note"):
                bad.append("the %r cell has no note; a bare score on a report card is a number "
                           "whose definition the reader has to guess" % s.get("key"))

    table = obj.get("table") or {}
    cols = table.get("columns") or []
    if len(cols) != REQUIRED_COLUMNS:
        bad.append("the table has %d columns; the design has %d" % (len(cols), REQUIRED_COLUMNS))
    rows = table.get("rows") or []
    if not rows:
        bad.append("the table has no rows")
    for r in rows:
        if not isinstance(r, dict):
            bad.append("a table row is not an object")
            continue
        for field in ("label", "sessions", "checked", "verdict"):
            if field not in r:
                bad.append("row %r has no `%s`" % (r.get("label"), field))
        # A CHECKED COUNT ABOVE THE SESSION COUNT IS IMPOSSIBLE, and it is the shape a
        # half-written scorer produces first.
        if isinstance(r.get("checked"), int) and isinstance(r.get("sessions"), int):
            if r["checked"] > r["sessions"]:
                bad.append("row %r reports more checked calls (%d) than sessions (%d)"
                           % (r.get("label"), r["checked"], r["sessions"]))
        # An unchecked row must not carry a live percentage: that is a score from nothing.
        if r.get("checked") == 0 and r.get("live_pct") is not None:
            bad.append("row %r has 0 checked calls but a live percentage" % r.get("label"))

    ma = obj.get("ma200") or {}
    for field in ("title", "up_crosses", "whipsaws", "history"):
        if field not in ma:
            bad.append("the 200-day block has no `%s`" % field)
    if isinstance(ma.get("whipsaws"), int) and isinstance(ma.get("up_crosses"), int):
        if ma["whipsaws"] > ma["up_crosses"]:
            bad.append("more whipsaws (%d) than up-crosses (%d), which cannot happen"
                       % (ma["whipsaws"], ma["up_crosses"]))

    foot = str(obj.get("footer") or "")
    if "#42" not in foot:
        bad.append("the footer must state #42: the scores change nothing")
    if "backfill" not in foot.lower():
        bad.append("the footer must say nothing is backfilled")
    return bad
