"""R-IV.1195(b) — v1 live: the nightly job, the two tables, health, the diff, and the CI check.

THE CI CHECK IS THE POINT OF THIS FILE. #42 says nothing gates on the regime label, and a rule
that lives only in a ruling gets broken by the next author who needs a regime-aware threshold
and finds a table sitting right there. So the readers of `regime_snapshots` are ENUMERATED: the
job that writes it, the one read service that serves the card, and tests. Anything else fails
this suite by name.

That is the same shape as the breach this lane already reported and did not act on --
`can_open_new` gating on `breakout_remaining_dd`, a DERIVED figure, which was in breach of #42
long before anyone noticed because no test was watching. This one is watched from the first day.

WHAT IS NOT TESTED HERE, and why. The seeded row count at deploy is not asserted: it depends on
how many bars `stable_daily_bars` holds, and a test that pinned 52 would fail the day the bar
history grows. `seed_depth_report` is tested on its arithmetic in
test_regime_classifier_v1_r1193.py; the executed count is reported from the deploy's own audit
row, which is the only honest source for it.
"""
from __future__ import annotations

import ast
import os
import re

import pytest

from ._srcscan import code_of_file, read_source

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(BACKEND)
MIGRATION = os.path.join(ROOT, "migrations", "053_regime_snapshots.sql")
CLIENT = os.path.join(BACKEND, "database", "postgres_client.py")

#: Every file permitted to name `regime_snapshots`, with the reason it is permitted.
ALLOWED_READERS = {
    "backend/jobs/regime_seed.py": "writes the snapshots (the only writer)",
    "backend/jobs/regime_job.py": "orchestrates the job; reads back for the diff and health",
    "backend/jobs/stable_jobs.py": "schedules the pass and asks whether history exists",
    "backend/services/read_only/regime_strategy.py": "serves the card (the only reader)",
    "backend/database/postgres_client.py": "owns the DDL",
    "backend/main.py": "runs the seed at startup behind an empty-table guard",
}


def _repo_py_files():
    for base, dirs, files in os.walk(ROOT):
        parts = base.split(os.sep)
        if any(p in parts for p in ("__pycache__", ".git", ".venv-test", "node_modules",
                                    "tests", "docs", "migrations")):
            continue
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(base, f)


# ── the CI check (R-IV.1195(b)) ─────────────────────────────────────────────

def test_NOTHING_BUT_THE_CARD_READS_THE_REGIME_TABLE():
    """THE RULED CHECK. Readers are enumerated; a new one has to be added here deliberately,
    which is the moment someone asks whether it is allowed to."""
    offenders = {}
    for path in _repo_py_files():
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        if rel in ALLOWED_READERS:
            continue
        try:
            code = code_of_file(path)
        except (SyntaxError, UnicodeDecodeError):
            continue
        if "regime_snapshots" in code or "regime_audit" in code:
            offenders[rel] = "names a regime table"
    assert offenders == {}, offenders


def test_the_allowlist_is_not_stale():
    """An allowlist entry for a file that no longer reads the table would quietly permit a
    future one. Checked so the list stays a statement about the code and not about history."""
    stale = []
    for rel in ALLOWED_READERS:
        path = os.path.join(ROOT, rel.replace("/", os.sep))
        if not os.path.exists(path):
            stale.append(rel + " (missing)")
            continue
        if "regime_snapshots" not in read_source(path):
            stale.append(rel + " (no longer reads it)")
    assert stale == [], stale


def test_NO_GATE_READS_THE_LABEL():
    """#42 in the form that matters. A gate is a decision: a cap, a kill-switch, a routing
    suppression, a Kairos input, a grade. None of them may see this label."""
    gate_files = []
    for path in _repo_py_files():
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        base = os.path.basename(path)
        if not any(k in rel for k in ("l0_routing", "circuit_breaker", "kill", "cap",
                                      "kairos", "grade", "score_signals",
                                      "outcome_resolver", "position_risk")):
            continue
        try:
            code = code_of_file(path)
        except (SyntaxError, UnicodeDecodeError):
            continue
        for needle in ("regime_snapshots", "regime_audit", "shown_regime",
                       "regime_strategy", "regime_classifier"):
            if needle in code:
                gate_files.append("%s names %s" % (rel, needle))
    assert gate_files == [], gate_files


def test_the_read_service_declares_display_only_and_the_card_shows_it():
    from services.read_only.regime_strategy import DISPLAY_ONLY, _unavailable
    assert DISPLAY_ONLY == "display only"
    # Even the unavailable payload carries it: the caption is a property of the card, not of
    # whether the read happened to work.
    assert _unavailable("x")["display_only"] == "display only"


# ── no mock fallback (the fake-healthy fault) ──────────────────────────────

def test_THE_READ_SERVICE_HAS_NO_MOCK_FALLBACK():
    """The `/api/crypto/market` fault in advance: a fallback that serves plausible numbers makes
    a broken feed look healthy, and nobody finds it because the screen is full."""
    code = code_of_file(os.path.join(BACKEND, "services", "read_only", "regime_strategy.py"))
    for banned in ("regime_mock", "_last_good", "fixture", "fallback"):
        assert banned not in code, banned


def test_an_unavailable_payload_CANNOT_place_a_marker():
    """`regime_key` is what the card positions the slider from. None, not a default, so a
    missing label renders as nothing rather than as crash_liquidation at position zero."""
    from services.read_only.regime_strategy import _unavailable
    p = _unavailable("the db is down")
    assert p["available"] is False
    assert p["regime_key"] is None and p["label"] is None
    assert p["tags"] == []
    assert "the db is down" in p["unavailable_reason"]
    # `health` is a STRING for the card's dot, which reads 'ok' or anything else. The
    # three-state block rides alongside as `health_detail`: collapsing stale into unconfirmed
    # on the wire would throw away the distinction the block exists to make.
    assert p["health"] == "unconfirmed"
    assert p["health_detail"]["state"] == "unavailable"
    assert "the db is down" in p["health_reason"]


# ── the job: settled only, append-only, audited ────────────────────────────

def test_the_nightly_pass_IS_GATED_ON_THE_NIGHTLY_COMPLETING():
    """It classifies from the bars the nightly writes. Run first and the newest bar is
    yesterday's, so the label gets yesterday's `as_of` and the run looks like a success."""
    code = code_of_file(os.path.join(BACKEND, "jobs", "stable_jobs.py"))
    i = code.index("_maybe_run_regime")
    body = code[i:i + 2600]
    assert "JOB_NIGHTLY" in body
    assert "has_completed" in body
    assert "is not True" in body, "UNKNOWN must not be read as YES"


def test_the_regime_job_runs_AFTER_the_nightly_on_the_clock():
    import jobs.stable_jobs as sj
    assert sj.REGIME_TIME > sj.NIGHTLY_TIME


def test_the_job_refuses_an_UNSETTLED_session_and_leaves_a_ROW():
    """A refusal that writes nothing is indistinguishable from a job that never ran, which is
    the R-IV.1175 fault. So the decline is audited."""
    code = code_of_file(os.path.join(BACKEND, "jobs", "regime_job.py"))
    i = code.index("async def run_nightly")
    body = code[i:]
    assert "is_session_settled" in body
    assert "settled is not True" in body, "three-state: None must not pass"
    assert 'action=\'refused\'' in body or 'action="refused"' in body


def test_the_writer_is_APPEND_ONLY_and_a_conflict_is_RECORDED():
    """Not just "does not UPDATE" -- a disagreement with a stored row is itself worth keeping,
    so the conflict path writes an audit entry saying what this run would have said."""
    code = code_of_file(os.path.join(BACKEND, "jobs", "regime_seed.py"))
    assert "ON CONFLICT (as_of, rules_version) DO NOTHING" in code
    assert not re.search(r"\bUPDATE\s+regime_snapshots", code, re.I)
    job = code_of_file(os.path.join(BACKEND, "jobs", "regime_job.py"))
    assert "would have said" in job


def test_a_session_with_no_label_is_still_WRITTEN():
    """A hole in the series is indistinguishable from a session the job never reached."""
    code = code_of_file(os.path.join(BACKEND, "jobs", "regime_seed.py"))
    i = code.index("async def seed")
    assert "_write_snapshot" in code[i:i + 1200]
    assert not re.search(r"if\s+row\.get\('shown_regime'\)\s+is\s+None:\s*continue", code)


def test_the_bars_are_read_OLDEST_FIRST():
    """The vendor-order landmine in this repo came from a descending series meeting a positional
    slice. The query orders DESC and the code reverses, so the function returns ascending --
    asserted because "it happens to be sorted" is how that bug survived."""
    code = code_of_file(os.path.join(BACKEND, "jobs", "regime_job.py"))
    i = code.index("async def load_series")
    body = code[i:i + 900]
    assert "ORDER BY date DESC" in body and "reversed(" in body


# ── the diff ────────────────────────────────────────────────────────────────

def test_the_diff_compares_the_PREVIOUS_STORED_SESSION_not_a_calendar_day():
    """`as_of - 1 day` before a Monday is a Sunday, which has no label, so every Monday would
    report as a change."""
    code = code_of_file(os.path.join(BACKEND, "jobs", "regime_job.py"))
    i = code.index("async def latest_with_diff")
    body = code[i:i + 1400]
    assert "ORDER BY as_of DESC" in body and "LIMIT 2" in body
    assert "INTERVAL" not in body


def test_the_diff_reports_NO_PREVIOUS_SESSION_as_its_own_state():
    """`changed: None` is not `changed: False`. The first stored session has nothing to differ
    from, and saying "no change" there is a claim about a comparison nobody made."""
    code = code_of_file(os.path.join(BACKEND, "jobs", "regime_job.py"))
    assert "'changed': None" in code, "ast.unparse renders string keys single-quoted"


# ── health: three states ───────────────────────────────────────────────────

def test_health_has_a_STALE_state_distinct_from_current_and_dead():
    """A label from eight sessions ago served as current is worse than no label: the reader
    cannot tell, and the screen looks healthy either way."""
    code = code_of_file(os.path.join(BACKEND, "jobs", "regime_job.py"))
    i = code.index("async def health")
    body = code[i:]
    # Single quotes: ast.unparse normalises every string literal to them. Asserting the
    # double-quoted form is how the first run of this test failed.
    for state in ("'current'", "'stale'", "'dead'", "'unavailable'"):
        assert state in body, state


def test_health_measures_lag_in_TRADING_days():
    """A Friday label read on Monday is ONE session behind, not three. A calendar-day threshold
    would call every ordinary Monday stale and every long weekend dead."""
    code = code_of_file(os.path.join(BACKEND, "jobs", "regime_job.py"))
    i = code.index("async def health")
    body = code[i:]
    assert "trading_days_between" in body
    assert "lag_sessions" in body


def test_health_treats_an_unreadable_table_as_UNAVAILABLE_not_healthy():
    code = code_of_file(os.path.join(BACKEND, "jobs", "regime_job.py"))
    i = code.index("async def health")
    body = code[i:]
    assert "except Exception" in body
    j = body.index("except Exception")
    assert "'unavailable'" in body[j:j + 400]


# ── the DDL exists in both places and matches ──────────────────────────────

@pytest.mark.parametrize("table", ["regime_snapshots", "regime_audit"])
def test_the_table_is_created_at_startup(table):
    code = code_of_file(CLIENT)
    assert "CREATE TABLE IF NOT EXISTS %s" % table in code


@pytest.mark.parametrize("table", ["regime_snapshots", "regime_audit"])
def test_the_migration_mirrors_the_startup_ddl(table):
    sql = read_source(MIGRATION)
    assert "CREATE TABLE IF NOT EXISTS %s" % table in sql


def test_the_unique_key_is_as_of_plus_rules_version_in_BOTH_copies():
    """The key is what makes the writer append-only. If the two copies disagreed, a hand-run
    migration would create a table the writer's ON CONFLICT clause does not match -- and
    asyncpg raises on that, so the job would fail every night."""
    for src in (code_of_file(CLIENT), read_source(MIGRATION)):
        assert "UNIQUE (as_of, rules_version)" in src


def test_the_ddl_columns_match_what_the_writer_inserts():
    """The insert names 16 columns. A column added to one copy and not the other is a nightly
    failure that only shows up at 21:30 ET."""
    # RAW source, not unparsed: ast.unparse renders the SQL string's newlines as literal
    # backslash-n, which `\s*` cannot match. The target is a string literal, never a comment,
    # so stripping prose buys nothing and costs the match.
    writer = read_source(os.path.join(BACKEND, "jobs", "regime_seed.py"))
    m = re.search(r"INSERT INTO regime_snapshots\s*\(([^)]*)\)", writer, re.S)
    assert m, "the insert statement moved"
    cols = [c.strip() for c in m.group(1).replace("\n", " ").split(",") if c.strip()]
    assert len(cols) == 16, cols
    ddl = code_of_file(CLIENT)
    i = ddl.index("CREATE TABLE IF NOT EXISTS regime_snapshots")
    block = ddl[i:i + 1400]
    for c in cols:
        assert c in block, c
    mig = read_source(MIGRATION)
    j = mig.index("CREATE TABLE IF NOT EXISTS regime_snapshots")
    for c in cols:
        assert c in mig[j:j + 2400], "%s missing from the migration copy" % c


# ── the inputs builder: no lookahead ───────────────────────────────────────

def test_the_inputs_builder_SLICES_and_never_sees_the_future():
    """Computing a 200dma over the whole window and reusing it would let October's prices decide
    a February label -- and the seed would look better than anything the live job could do."""
    code = code_of_file(os.path.join(BACKEND, "models", "regime_inputs.py"))
    assert "bars[:i + 1]" in code or "spy[:i + 1]" in code


def test_each_index_is_sliced_BY_DATE_not_by_index():
    """A ticker that missed a session would otherwise be read a day out of step -- the UW/Yahoo
    bar landmine in a different costume."""
    code = code_of_file(os.path.join(BACKEND, "models", "regime_inputs.py"))
    i = code.index("def build_inputs")
    assert "<= as_of" in code[i:i + 2000]


def test_market_state_comes_from_the_ONE_function_the_card_uses():
    """Reimplementing the ADX bands would give two answers to one question, and the one on the
    screen would be the untested one."""
    import models.regime_inputs as ri
    import services.read_only.chart_indicators as ci
    assert ri.market_state is ci.market_state


def test_the_family_definitions_are_FLAGGED_not_asserted():
    """R-IV.925(b): do not invent labels. §2 names five families but states no per-family test
    for the two v1 can measure, so these reuse the Correction row's own clauses and say so."""
    from models.regime_classifier import load_rules
    fam = load_rules()["families_v1"]
    # R-IV.1198(e) RATIFIED these as INTERIM, so "pending ratification" is no longer the
    # status -- the ruling moved it, not the code drifting. What the test is really about is
    # unchanged: the two measured families declare that their test is provisional, and the
    # three with no feed declare that they have none.
    assert fam["status"].startswith("INTERIM")
    assert "R-IV.1198(e)" in fam["status"]
    assert "no per-family test" in fam["status"]
    assert fam["credit"] is None and fam["vol"] is None and fam["carry"] is None
    assert "50dma" in fam["structure"] and "50dma" in fam["breadth"]
    assert "never inferred" in fam["absent_rule"]


def test_an_absent_family_is_absent_and_not_False():
    """False means measured-and-risk-on. A missing feed is neither."""
    from models.regime_inputs import Bar, build_inputs
    import datetime as _dt
    bars = [Bar(_dt.date(2025, 1, 1) + _dt.timedelta(days=n), 1.0, 1.0, 1.0, 100.0 + n, 1)
            for n in range(260)]
    got = build_inputs({"SPY": bars, "QQQ": bars, "IWM": bars}, 259, settled=True)
    assert got is not None
    assert "credit" not in got["families"]
    assert "vol" not in got["families"]
    assert got["families_absent_in_v1"]["vol"].startswith("no VIX")


def test_a_series_shorter_than_the_200dma_yields_NO_session():
    from models.regime_inputs import Bar, build_inputs
    import datetime as _dt
    bars = [Bar(_dt.date(2025, 1, 1) + _dt.timedelta(days=n), 1.0, 1.0, 1.0, 100.0, 1)
            for n in range(150)]
    assert build_inputs({"SPY": bars}, 149, settled=True) is None


def test_the_route_is_registered_and_distinct_from_the_theme_regime_read():
    """`/stable/regime` serves theme breadth and predates this. Two different reads must not
    share a path, and the card must not be pointed at the wrong one."""
    src = read_source(os.path.join(BACKEND, "api", "stable.py"))
    assert '@router.get("/regime-strategy")' in src
    assert '@router.get("/regime")' in src
    tree = ast.parse(src)
    paths = []
    for node in ast.walk(tree):
        # AsyncFunctionDef, which is NOT a subclass of FunctionDef -- the first run of this
        # test collected zero routes because every one of them is `async def`.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and dec.args and isinstance(dec.args[0], ast.Constant):
                    paths.append(dec.args[0].value)
    assert paths.count("/regime-strategy") == 1
    assert paths.count("/regime") == 1


# ── the two defects the end-to-end dry run found ───────────────────────────
#
# Both were invisible to every compile-and-unit check: the pieces all worked, and the seam
# between them was wrong. They are pinned here because a dry run proves a moment and a test
# proves every deploy after it.

def _synthetic(n=300, shape=None, start=None):
    """n synthetic weekday bars. Labelled synthetic: these prove plumbing, not markets."""
    import datetime as _dt
    from models.regime_inputs import Bar
    shape = shape or (lambda i: 300.0 + i * 0.8)
    bars, d, i = [], (start or _dt.date(2024, 1, 2)), 0
    while len(bars) < n:
        if d.weekday() < 5:
            c = shape(i)
            bars.append(Bar(d, c, c * 1.004, c * 0.996, c, 1_000_000))
            i += 1
        d += _dt.timedelta(days=1)
    return bars


def _full_series(bars):
    from models.regime_inputs import SECTORS
    s = {"SPY": bars, "QQQ": bars, "IWM": bars}
    for t in SECTORS:
        s[t] = bars
    return s


def test_DEFECT_an_index_with_no_bar_for_the_session_is_UNAVAILABLE():
    """FOUND BY THE DRY RUN. Slicing by date stops a FUTURE bar leaking in, but it still reused
    the newest bar BEFORE `as_of`. An IWM series that stopped 30 sessions early reported 483.20
    as current while SPY was at 539.20, and the breadth family came back False -- a number
    computed from nothing. That is the fake-healthy fault, and it is worse than a gap."""
    from models.regime_inputs import build_inputs
    full = _synthetic(260)
    s = _full_series(full)
    s["IWM"] = full[:-30]
    got = build_inputs(s, 259, settled=True)
    assert got is not None
    iwm = got["indices"]["IWM"]
    assert iwm["price"] is None and iwm["ma50"] is None
    assert "breadth" not in got["families"], "a family must not be computed from a stale price"


def test_POSITIVE_CONTROL_a_complete_index_set_DOES_produce_the_breadth_family():
    """Without this, a builder that always returned None would satisfy the test above."""
    from models.regime_inputs import build_inputs
    full = _synthetic(260)
    got = build_inputs(_full_series(full), 259, settled=True)
    assert got["indices"]["IWM"]["price"] is not None
    assert got["families"]["breadth"] is False, "all three are above their 50dma here"
    assert "3 indices" in got["families_basis"]["breadth"]


def test_DEFECT_a_steady_uptrend_PRODUCES_A_LABEL():
    """FOUND BY THE DRY RUN, and the worse of the two. A clean 300-session uptrend classified as
    NO LABEL, because Uptrend, Melt-up and Narrow-uptrend all need sector breadth and nothing
    computed it -- so the most common regime in the book was the one v1 could not name."""
    from jobs.regime_seed import replay
    from models.regime_inputs import sessions_from_series
    sessions = sessions_from_series(_full_series(_synthetic(300)))
    assert sessions, "300 bars must yield classifiable sessions"
    out = replay(sessions)
    last = out["shown"][-1]
    assert last["regime"] == "uptrend", last["basis"]
    assert last["shown_regime"] == "uptrend"
    assert "11 of 11 sectors" in last["basis"]


def test_only_the_VIX_ROW_is_unevaluable_on_a_complete_series():
    """The honest residue. With every bar input present, exactly one §2 row remains untestable
    in v1 -- row 1, which needs a VIX series. Any other row going NOT EVALUABLE on complete
    bars means an input nothing computes, which is what the dry run caught twice."""
    from jobs.regime_seed import replay
    from models.regime_inputs import sessions_from_series
    sessions = sessions_from_series(_full_series(_synthetic(300)))
    out = replay(sessions)
    assert out["raw"][-1]["not_evaluable_rows"] == ["crash_liquidation"]


def test_the_sector_count_REFUSES_A_PARTIAL_SET():
    """§2 compares the count against a total of 11. A count from seven usable series is not a
    smaller number -- it is a different measurement wearing the same units."""
    from models.regime_inputs import SECTORS, sectors_above_50dma
    full = _synthetic(260)
    s = _full_series(full)
    as_of = min(str(full[-1].date)[:10], str(full[-1].date)[:10])
    ok = sectors_above_50dma(s, as_of)
    assert ok["count"] == 11 and ok["missing"] == []
    s.pop(SECTORS[0])
    short = sectors_above_50dma(s, as_of)
    assert short["count"] is None
    assert SECTORS[0] in short["missing"]
    assert "partial count" in short["reason"]


def test_the_confirmed_break_test_uses_THE_RULES_FILE_numbers():
    """The 2 closes and the 1.2 rvol are in `confirmed_break`, not in the code."""
    from models.regime_classifier import load_rules
    cb = load_rules()["confirmed_break"]
    assert cb["closes_through_50dma"] == 2
    assert cb["rvol_min_on_break_day"] == 1.2
    assert cb["stack_must_turn"] is True
    code = code_of_file(os.path.join(BACKEND, "models", "regime_inputs.py"))
    i = code.index("def confirmed_break_down_50dma")
    body = code[i:i + 2200]
    assert "closes_through_50dma" in body and "rvol_min_on_break_day" in body


def test_the_confirmed_break_returns_NONE_not_FALSE_when_it_cannot_check():
    """"No confirmed break" and "I could not check" put the same word on the screen and mean
    opposite things."""
    from models.regime_inputs import confirmed_break_down_50dma
    assert confirmed_break_down_50dma(_synthetic(50)) is None
    assert confirmed_break_down_50dma(_synthetic(260)) is False, "a clean uptrend has not broken"


def test_the_high_beta_breadth_is_ABSENT_and_says_why():
    """§2's narrow-uptrend row compares it to 40%, but no ruling states which names make up the
    high-beta universe. Picking one would be inventing the measurement (R-IV.925(b))."""
    from models.regime_inputs import build_inputs
    got = build_inputs(_full_series(_synthetic(260)), 259, settled=True)
    b = got["breadth"]
    assert "high_beta_above_50dma_pct" not in b
    assert "not inferred" in b["high_beta_above_50dma_pct_absent_reason"]
    assert b["sectors_above_50dma"] == 11


def test_the_job_loads_THE_SECTORS_as_well_as_the_indices():
    """The dry run's first pass failed because the fixture held only the three indices. The job
    must not have the same gap."""
    import jobs.regime_job as rj
    from models.regime_inputs import INDICES, SECTORS
    assert set(INDICES) <= set(rj.LOAD_TICKERS)
    assert set(SECTORS) <= set(rj.LOAD_TICKERS)
    assert len(rj.LOAD_TICKERS) == len(INDICES) + len(SECTORS)


# ── the card actually reads the live route ─────────────────────────────────
#
# The R-IV.1178 lesson: I built a button in index.html/app.js and verified it against
# /app/legacy, while /app serves v2.html. Every check was correct and none was about the page
# Nick opens. So this reads main.py's route table for the file /app returns, and checks THAT
# file.

FRONTEND = os.path.join(ROOT, "frontend")


def _file_served_at_app() -> str:
    """Which file does `/app` return? Read from main.py, not assumed."""
    src = read_source(os.path.join(BACKEND, "main.py"))
    m = re.search(r'@app\.get\(\s*["\']/app["\'][^)]*\)\s*(?:async\s+)?def\s+\w+[^)]*\)'
                  r'[^{]*?FileResponse\(\s*[^)]*?["\']([A-Za-z0-9_./-]+\.html)["\']',
                  src, re.S)
    if not m:
        m = re.search(r'["\']/app["\'].{0,600}?([A-Za-z0-9_-]+\.html)', src, re.S)
    assert m, "could not read which html /app serves"
    return os.path.basename(m.group(1))


def test_the_page_app_serves_is_the_one_i_changed():
    assert _file_served_at_app() == "v2.html"


def test_THE_CARD_FETCHES_THE_LIVE_ROUTE_not_the_fixture():
    js = read_source(os.path.join(FRONTEND, "v2.js"))
    i = js.index("async function loadRegimeStrategy")
    body = js[i:i + 2600]
    assert "/api/stable/regime-strategy" in body
    assert "regime_mock.json" not in body, "the fixture must not be a fallback"


def test_the_mock_fixture_is_no_longer_fetched_ANYWHERE_in_the_card():
    """A fallback left in one branch is the /api/crypto/market fault: invisible until it fires,
    and then it serves plausible numbers on a screen that looks healthy."""
    js = read_source(os.path.join(FRONTEND, "v2.js"))
    assert "regime_mock.json" not in js


def test_an_unavailable_payload_renders_CANNOT_CONFIRM():
    js = read_source(os.path.join(FRONTEND, "v2.js"))
    assert "available === false" in js
    i = js.index("available === false")
    assert "cannot confirm" in js[i:i + 600]
    assert "unavailable_reason" in js[i:i + 600], "the reason is printed, not just the state"


def test_the_premium_marker_is_OMITTED_when_there_is_no_reading():
    """`position_pct || 0` put the marker at 0% -- hard against the bear end of the track --
    which renders as a confident extreme reading taken from nothing."""
    js = read_source(os.path.join(FRONTEND, "v2.js"))
    assert "const hasPrem" in js
    i = js.index("const hasPrem")
    body = js[i:i + 700]
    assert "position_pct || 0" not in body
    assert "hasPrem ?" in body


def test_the_since_yesterday_row_exists_and_distinguishes_FIRST_SESSION():
    js = read_source(os.path.join(FRONTEND, "v2.js"))
    assert "rs-diff" in js
    i = js.index("let diffRow")
    body = js[i:i + 1200]
    assert "changed === null" in body
    assert "nothing to compare" in body
    assert "since yesterday" in body


def test_the_diff_row_has_a_CSS_RULE():
    """A class with no rule renders as unstyled body text in the middle of a dense card."""
    css = read_source(os.path.join(FRONTEND, "v2.css"))
    assert ".rs-diff {" in css
    i = css.index(".rs-diff {")
    rule = css[i:css.index("}", i)]
    # Tokens, not hexes (R-IV.1190(b)).
    assert "var(--" in rule
    assert not re.search(r"#[0-9a-fA-F]{3,6}", rule)


def test_the_no_feed_blocks_CARRY_THEIR_REASON():
    """An em-dash with an empty tooltip tells a reader nothing about why it is empty."""
    js = read_source(os.path.join(FRONTEND, "v2.js"))
    assert "no_feed_in_v1" in js
    from services.read_only.regime_strategy import NO_FEED_IN_V1
    for k in ("lights", "tripwires", "overlays", "lens_split", "intraday"):
        assert NO_FEED_IN_V1[k], k
    assert "not read by this card" in NO_FEED_IN_V1["intraday"]


def test_the_cache_pins_MOVED_for_every_page_that_pins_a_changed_asset():
    """v2.css is pinned by THREE pages at independent values. The pages I miss keep serving
    whatever was cached under their unchanged pin."""
    pins = {}
    for page in ("v2.html", "stater.html", "abacus.html"):
        src = read_source(os.path.join(FRONTEND, page))
        m = re.search(r"/v2\.css\?v=(\d+)", src)
        assert m, page
        pins[page] = int(m.group(1))
    # Not equal to each other -- they diverged long ago and that is expected; what matters is
    # that each one is past the value it held before this change.
    assert pins["v2.html"] >= 52, pins
    assert pins["stater.html"] >= 48, pins
    assert pins["abacus.html"] >= 47, pins
    jm = re.search(r"/v2\.js\?v=(\d+)", read_source(os.path.join(FRONTEND, "v2.html")))
    assert jm and int(jm.group(1)) >= 65


def test_the_settled_line_STILL_SAYS_DISPLAY_ONLY():
    """R-IV.1193(b), carried forward through the live flip. The phrase must stay visible on the
    face of the card, and a rewrite of the data source is exactly when it would get lost."""
    js = read_source(os.path.join(FRONTEND, "v2.js"))
    assert "display only" in js
    # Both paths: the rendered card and the unavailable card.
    assert js.count("display only") >= 2, "the unavailable path needs it too"


# ── the seed runs at deploy, once (R-IV.1195(b)) ───────────────────────────

def test_THE_SEED_RUNS_AT_STARTUP_BEHIND_AN_EMPTY_TABLE_GUARD():
    """R-IV.1195(b) asks for "the seed count actually executed at deploy", and the nightly only
    fires on weekdays at 21:30 ET -- seeded at the nightly alone, a Friday deploy would leave the
    card saying "cannot confirm" until Monday night.

    THE GUARD IS THE POINT. An unguarded startup seed is DEF-SEED-RESURRECTION:
    init_database()'s account_balances seed re-created deliberately deleted rows on every
    deploy. This writes only into an empty table."""
    src = read_source(os.path.join(BACKEND, "main.py"))
    i = src.index("Regime v1 seed")
    # To the NEXT startup step, not a fixed width. A fixed 1800 characters stopped reaching the
    # handler as soon as R-IV.1198(c)/(e)'s audit calls were added between them.
    body = src[i:src.index("Initialize watchlist config table", i)]
    assert "SELECT COUNT(*) FROM regime_snapshots" in body
    assert "if _have:" in body and "seed skipped" in body
    assert "run_seed" in body
    assert "except Exception" in body, "a failed seed must not fail startup"
    assert "DEF-SEED-RESURRECTION" in body, "the guard names what it is guarding against"


def test_the_seed_is_BOUNDED_BY_THE_CALENDAR_not_by_the_bar_table():
    """Left unbounded, `sessions_from_series` marks every session settled -- including today's
    bar if a provisional snapshot wrote one -- so the seed would stamp an UNSETTLED close as
    settled. That is the R-IV.1176 fault committed by the thing meant to avoid it."""
    code = code_of_file(os.path.join(BACKEND, "jobs", "regime_job.py"))
    i = code.index("async def run_seed")
    body = code[i:code.index("async def run_nightly")]
    assert "last_settled_session" in body
    assert "settled_through=through" in body
    assert "CalendarHorizonError" in body, "the bounded walk can refuse; that is handled"


def test_the_seed_is_IDEMPOTENT_in_two_independent_ways():
    """The startup guard (empty table) and the unique key (ON CONFLICT DO NOTHING). Either alone
    would do; both means a race between a deploy and a nightly cannot double-write."""
    assert "SELECT COUNT(*) FROM regime_snapshots" in read_source(
        os.path.join(BACKEND, "main.py"))
    assert "ON CONFLICT (as_of, rules_version) DO NOTHING" in code_of_file(
        os.path.join(BACKEND, "jobs", "regime_seed.py"))


# ── the write boundary: a string is not a date ─────────────────────────────

def test_as_date_coerces_the_ISO_STRING_the_classifier_carries():
    """THE FIRST LIVE SEED WROTE NOTHING because of this. Every `as_of` inside the classifier is
    an ISO string, deliberately -- verdicts are compared, keyed and replayed as text. asyncpg
    wants a `date` for a DATE column and raises on a string:

        invalid input for query argument $1: '2025-07-10'
        ('str' object has no attribute 'toordinal')

    The exact mirror of the `cut_due` crash, where an already-stringified date met
    `.isoformat()`. Same seam, opposite direction."""
    import datetime as _dt
    from jobs.regime_seed import as_date
    assert as_date("2026-10-16") == _dt.date(2026, 10, 16)
    assert as_date("2026-10-16 00:00:00") == _dt.date(2026, 10, 16), "a timestamp is truncated"
    assert as_date(_dt.date(2026, 10, 16)) == _dt.date(2026, 10, 16), "a date passes through"
    assert as_date(None) is None, "None stays None, never today"
    assert as_date("not a date") is None, "unparseable is None, not an exception at the DB"


def test_BOTH_writers_coerce_as_of():
    """`regime_snapshots` and `regime_audit` both have a DATE column, and both were handed the
    string. Fixing one would have left the other to fail at 21:30 ET."""
    snap = code_of_file(os.path.join(BACKEND, "jobs", "regime_seed.py"))
    i = snap.index("INSERT INTO regime_snapshots")
    assert "as_date(row.get('as_of'))" in snap[i:i + 1500]
    job = code_of_file(os.path.join(BACKEND, "jobs", "regime_job.py"))
    j = job.index("INSERT INTO regime_audit")
    assert "as_date(as_of)" in job[j:j + 600]


def test_a_SEED_WRITE_FAILURE_is_audited_not_just_raised():
    """The reason finding this needed a log dig: only the REFUSAL paths audited, so a raised
    write left no row and the route could say "no snapshot" with nothing able to say why."""
    code = code_of_file(os.path.join(BACKEND, "jobs", "regime_job.py"))
    i = code.index("async def run_seed")
    body = code[i:code.index("async def run_nightly")]
    assert "seed write failed" in body
    assert "except Exception" in body


def test_the_unavailable_payload_SURFACES_THE_LAST_AUDIT_ROW():
    """"No snapshot" is a symptom. The run that declined recorded its reason, and surfacing it
    is the whole point of auditing refusals rather than letting them be an absence."""
    code = code_of_file(os.path.join(BACKEND, "jobs", "regime_job.py"))
    i = code.index("async def latest_with_diff")
    body = code[i:i + 1800]
    assert "FROM regime_audit" in body
    assert "last run:" in body


def test_a_REFUSAL_names_the_bar_counts():
    """When the seed declines, the per-ticker bar counts ARE the diagnosis, and nothing else in
    this lane can read that table."""
    code = code_of_file(os.path.join(BACKEND, "jobs", "regime_job.py"))
    i = code.index("async def run_seed")
    body = code[i:code.index("async def run_nightly")]
    assert "bars: %s" in body or "bar_counts" in body


# ── the read-back must ask for what it serves ──────────────────────────────

def test_THE_READBACK_SELECTS_INPUTS_JSON():
    """It did not, in the first live version. The column held the numbers; the query did not ask
    for them, so the index strip came back empty and every family reported "no feed in v1" --
    a caption asserting an absence that was not real, about two families that DO have a feed."""
    code = code_of_file(os.path.join(BACKEND, "jobs", "regime_job.py"))
    i = code.index("async def latest_with_diff")
    body = code[i:i + 1600]
    assert "inputs_json" in body


def test_the_readback_selects_EVERY_column_the_payload_publishes():
    """The general form of that defect: the SELECT and the payload are two lists that have to
    agree, and nothing was checking."""
    code = code_of_file(os.path.join(BACKEND, "jobs", "regime_job.py"))
    i = code.index("async def latest_with_diff")
    m = re.search(r"SELECT (.*?) FROM regime_snapshots", code[i:i + 1800], re.S)
    assert m, "the read-back query moved"
    # Identifiers by regex, not a comma split. `ast.unparse` renders the SQL string's newlines
    # as LITERAL backslash-n, so splitting on commas leaves tokens like "\\n   pending" that
    # match nothing -- and the test then fails on a column that is plainly in the query.
    selected = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", m.group(1)))
    for needed in ("as_of", "regime", "shown_regime", "label", "tags", "basis",
                   "not_evaluable", "pending", "pending_closes", "held_sessions",
                   "change", "blocked", "seeded", "inputs_json"):
        assert needed in selected, needed


def test_NO_FEED_IN_V1_is_claimed_ONLY_for_the_families_that_have_none():
    """A family that has a feed but no value for this session is a DIFFERENT fact from a family
    with no feed, and only the rules file gets to say which is which."""
    from services.read_only.regime_strategy import _families
    # Nothing recorded at all: structure and breadth must NOT claim "no feed".
    rows = {r["key"]: r for r in _families({})}
    assert rows["STRUCTURE"]["why"] == "not recorded for this session"
    assert rows["BREADTH"]["why"] == "not recorded for this session"
    # With the rules file's own absence reasons present, those ARE quoted.
    rows2 = {r["key"]: r for r in _families(
        {"families": {"structure": True},
         "families_basis": {"structure": "SPY below its 50dma"},
         "families_absent_in_v1": {"vol": "no VIX/VIX3M series in v1"}})}
    assert rows2["STRUCTURE"]["state"] == "risk_off"
    assert rows2["VOL"]["why"] == "no VIX/VIX3M series in v1"
    assert rows2["CREDIT"]["why"] == "not recorded for this session"


def test_a_measured_risk_ON_family_is_not_confused_with_an_absent_one():
    """False means measured-and-risk-on. None means nobody measured. Both render without a
    colour, so the distinction has to live in the data."""
    from services.read_only.regime_strategy import _families
    rows = {r["key"]: r for r in _families(
        {"families": {"structure": False}, "families_basis": {"structure": "SPY above 50dma"}})}
    assert rows["STRUCTURE"]["state"] == "risk_on"
    # The basis is still there; R-IV.1198(e)'s interim mark is APPENDED, not substituted.
    assert rows["STRUCTURE"]["why"].startswith("SPY above 50dma")
    assert "interim test" in rows["STRUCTURE"]["why"]


def test_THE_SEED_COUNT_IS_READABLE_FROM_THE_ROUTE():
    """R-IV.1195(b) asks for "the seed count actually executed at deploy". The first time I went
    looking, the answer was only in a deploy log that had already rolled off. A number a ruling
    asks to be reported has to be readable from the thing that produced it."""
    code = code_of_file(os.path.join(BACKEND, "jobs", "regime_job.py"))
    assert "async def seed_run" in code
    i = code.index("async def seed_run")
    body = code[i:i + 900]
    assert "action = 'seed'" in body
    assert "rows_written" in body
    svc = code_of_file(os.path.join(BACKEND, "services", "read_only", "regime_strategy.py"))
    assert "seed_run" in svc


# ── the families' field name is the RENDERER'S (R-IV.1198 pass) ────────────

def test_THE_FAMILY_FIELD_IS_KEY_BECAUSE_THAT_IS_WHAT_V2JS_READS():
    """A live defect found while wiring R-IV.1198(e). v2.js reads `f.key`; the service served
    `name`. `esc(undefined)` renders the literal word "undefined" rather than failing, so the
    card carried five dots labelled "undefined" and nothing errored.

    The server and the renderer are two ends of one contract, and only the renderer gets to
    name it -- so this test reads the NAME OUT OF v2.js rather than restating it."""
    js = read_source(os.path.join(ROOT, "frontend", "v2.js"))
    i = js.index("(m.evidence || {}).families")
    block = js[i:i + 600]
    field = re.search(r"esc\(f\.(\w+)\)", block)
    assert field, "could not read which field the renderer prints"
    from services.read_only.regime_strategy import _families
    served = _families({"families": {"structure": True},
                        "families_basis": {"structure": "x"}})[0]
    assert field.group(1) in served, (
        "the renderer prints f.%s and the service does not serve it" % field.group(1))


# ── (e) the interim mark ───────────────────────────────────────────────────

def test_THE_INTERIM_MARK_IS_ON_THE_TOOLTIP():
    """R-IV.1198(e): "Mark them interim ... on the family dot's tooltip." The tooltip is the
    `why` string, which is what v2.js puts in the title attribute."""
    from services.read_only.regime_strategy import _families
    rows = {r["key"]: r for r in _families(
        {"families": {"structure": True, "breadth": False},
         "families_basis": {"structure": "SPY below its 50dma", "breadth": "1 of 3 below"}})}
    for k in ("STRUCTURE", "BREADTH"):
        assert rows[k]["interim"] is True, k
        assert "interim test (R-IV.1198(e))" in rows[k]["why"], k
    # And the basis is still there -- the mark is added, not substituted.
    assert "SPY below its 50dma" in rows["STRUCTURE"]["why"]


def test_only_STRUCTURE_and_BREADTH_are_interim():
    """The three with no feed are not "interim tests" -- they are absent. Marking them interim
    would imply a test exists that someone merely has not ratified."""
    from services.read_only.regime_strategy import INTERIM_FAMILIES, _families
    assert set(INTERIM_FAMILIES) == {"structure", "breadth"}
    rows = {r["key"]: r for r in _families(
        {"families_absent_in_v1": {"credit": "no HY OAS feed in v1",
                                   "vol": "no VIX/VIX3M series in v1",
                                   "carry": "no carry strip in v1"}})}
    for k in ("CREDIT", "VOL", "CARRY"):
        assert rows[k]["interim"] is False, k
        assert "interim" not in rows[k]["why"], k


def test_the_rules_file_says_INTERIM_and_cites_the_ruling():
    from models.regime_classifier import load_rules
    f = load_rules()["families_v1"]
    assert f["status"].startswith("INTERIM")
    assert "R-IV.1198(e)" in f["status"]
    assert "flip rate" in f["status"] or "flip rate" in f.get("flip_rate_review", "")


def test_the_INTERIM_status_is_RECORDED_IN_THE_AUDIT():
    """R-IV.1198(e): "Mark them interim in regime_audit". On the record, not only in a ruling
    and a comment."""
    code = code_of_file(os.path.join(BACKEND, "jobs", "regime_job.py"))
    assert "async def record_interim_families" in code
    i = code.index("async def record_interim_families")
    body = code[i:i + 1400]
    assert "interim_families" in body
    assert "R-IV.1198(e)" in body
    assert "LIMIT 1" in body, "idempotent: one row, not one per deploy"
    main = read_source(os.path.join(BACKEND, "main.py"))
    assert "record_interim_families" in main


# ── (c) the flip list and the known gap ────────────────────────────────────

def test_THE_FLIP_LIST_IS_READABLE_and_says_whether_a_flip_is_CHATTER():
    """R-IV.1198(c) asks for the list so a reader can see whether the flips are real regime
    changes or chatter between two neighbouring labels. The count alone cannot tell those
    apart, so the FROM and TO are published with their positions in §2's bear-to-bull order:
    a Correction/Narrow-uptrend pair one step apart is a different fact from a Bear/Melt-up
    pair six apart."""
    code = code_of_file(os.path.join(BACKEND, "jobs", "regime_job.py"))
    assert "async def flip_history" in code
    i = code.index("async def flip_history")
    body = code[i:i + 2600]
    assert "change IS NOT NULL" in body
    assert "ORDER BY as_of ASC" in body, "oldest-first, so the series reads forward"
    for field in ("from_index", "to_index", "steps", "neighbours", "closes_held"):
        assert field in body, field


def test_the_flip_rate_is_computed_against_SECTION_2s_TARGET():
    import jobs.regime_job as rj
    assert rj.FLIPS_PER_YEAR_TARGET == 6
    assert rj.SESSIONS_PER_YEAR == 252


def test_NO_THRESHOLD_OR_HYSTERESIS_CHANGE_was_made_for_the_flip_rate():
    """R-IV.1198(c) rules this explicitly. Tuning on observed flips is a fitted parameter
    wearing a rule's name, so the gap is RECORDED and nothing adjusts itself to meet it."""
    from models.regime_classifier import load_rules
    h = load_rules()["hysteresis"]
    # The numbers §2 states, unchanged.
    assert h["enter_requires_settled_closes"] == 2
    assert h["min_sessions_before_change"] == 5
    assert h["range_requires_sessions"] == 10
    code = code_of_file(os.path.join(BACKEND, "jobs", "regime_job.py"))
    i = code.index("async def flip_history")
    body = code[i:i + 3000]
    # The rate is reported; it must not feed back into any threshold.
    assert "FLIPS_PER_YEAR_TARGET" in body
    for banned in ("enter_requires_settled_closes =", "min_sessions_before_change =",
                   "range_requires_sessions ="):
        assert banned not in code, banned


def test_the_KNOWN_GAP_is_recorded_once_and_names_both_numbers():
    code = code_of_file(os.path.join(BACKEND, "jobs", "regime_job.py"))
    assert "async def record_known_gap" in code
    i = code.index("async def record_known_gap")
    body = code[i:i + 1600]
    assert "action = 'known_gap'" in body
    assert "LIMIT 1" in body, "idempotent on the action, so a redeploy does not restate it"
    j = code.index("async def flip_history")
    gap = code[j:j + 3000]
    assert "design target" in gap and "fitted parameter" in gap
    main = read_source(os.path.join(BACKEND, "main.py"))
    assert "record_known_gap" in main


def test_the_gap_is_NONE_when_the_rate_is_within_target():
    """A "known gap" that is always present is not a finding. The field is None when the
    observed rate sits at or under §2's target."""
    code = code_of_file(os.path.join(BACKEND, "jobs", "regime_job.py"))
    i = code.index("async def flip_history")
    body = code[i:i + 3000]
    assert "rate <= FLIPS_PER_YEAR_TARGET" in body


def test_CLOSES_HELD_IS_NOT_VACUOUS():
    """A live reporting defect found by reading my own output: every one of the 14 flips said
    "0 closes". `pending_closes` is zeroed by the hysteresis on the session a change fires, so
    the stored value is 0 on EVERY flip -- a column that cannot vary, which is the
    vacuous-column fault (DEF-EDGE-SPEC-B2) in a new place. R-IV.1198(c) asks for the closes
    held per flip, and a field that cannot vary cannot answer it."""
    from jobs.regime_job import _closes_from_change
    assert _closes_from_change("first label after 2 closes") == 2
    assert _closes_from_change("correction -> uptrend after 2 closes (toward risk)") == 2
    assert _closes_from_change("uptrend -> range_chop after 10 closes") == 10
    assert _closes_from_change(None) is None
    assert _closes_from_change("no count in this sentence") is None, (
        "a changed wording must show as MISSING data, never as a plausible number")


def test_THE_PARSE_AGREES_WITH_THE_PURE_FIELD():
    """Convention #34 in miniature: two independent routes to one number must agree. The
    hysteresis now publishes `qualified_closes` directly, and `flip_history` parses the same
    value out of the `change` sentence it stored -- because the snapshots are append-only and a
    column added now could never be filled for the 321 rows already seeded."""
    from jobs.regime_job import _closes_from_change
    from models.regime_hysteresis import apply_hysteresis
    series = [{"as_of": "2026-01-%02d" % (i + 1), "regime": k, "settled": True}
              for i, k in enumerate(["correction"] * 2 + ["uptrend"] * 6)]
    out = apply_hysteresis(series)
    changed = [r for r in out if r.get("change")]
    assert changed, "the fixture must produce at least one change"
    for r in changed:
        assert r["qualified_closes"] is not None
        assert _closes_from_change(r["change"]) == r["qualified_closes"], r["change"]


def test_qualified_closes_is_NONE_on_a_session_with_no_change():
    """It is the count that EARNED a move, so it exists only where a move happened. A 0 would
    be the vacuous column again, one level up."""
    from models.regime_hysteresis import apply_hysteresis
    out = apply_hysteresis([{"as_of": "2026-01-%02d" % (i + 1), "regime": "correction",
                             "settled": True} for i in range(6)])
    assert [r["qualified_closes"] for r in out if not r.get("change")] == [None] * 5


def test_PAIR_IDENTITY_is_published_because_ORDER_DISTANCE_misleads():
    """THE FINDING THAT CHANGES THE ANSWER TO (c). §2's order puts range_chop and melt_up
    between correction and uptrend, so a correction/uptrend oscillation scores 3 "steps" and
    reads as a real regime change -- while being the same two labels trading places over and
    over, which is exactly the chatter the ruling asks about. The tape never passed through
    the labels in between, so the distance is an artefact of the ordering."""
    from models.regime_classifier import load_rules
    order = load_rules()["order"]
    assert abs(order.index("uptrend") - order.index("correction")) == 3
    assert order[order.index("correction") + 1] == "range_chop"
    code = code_of_file(os.path.join(BACKEND, "jobs", "regime_job.py"))
    i = code.index("async def flip_history")
    body = code[i:i + 3600]
    for field in ("pair", "pair_counts", "repeated_pairs", "repeated_pair_flips"):
        assert field in body, field


# ── (d) the close source is named until the designated one is wired ────────

def test_THE_SETTLED_LINE_NAMES_ITS_CLOSE_SOURCE():
    """R-IV.1198(d): "Until this is settled, the card's settled line names its close source."

    Three candidates disagreed on 2026-10-16 and only one matched the Polygon daily aggregate,
    so an unnamed close is the one a reader assumes is right."""
    js = read_source(os.path.join(ROOT, "frontend", "v2.js"))
    i = js.index("const st = $('rsSettled')")
    body = js[i:i + 900]
    assert "m.close_source" in body
    assert "close_source_note" in body, "the rest of the finding rides in the tooltip"
    assert "display only" in body, "R-IV.1193(b): the phrase stays on the face of the card"


def test_the_close_source_is_served_on_BOTH_payload_paths():
    """An unavailable card still shows the settled line, so it still has to name the source."""
    from services.read_only.regime_strategy import CLOSE_SOURCE, _unavailable
    assert CLOSE_SOURCE == "stable_daily_bars"
    assert _unavailable("x")["close_source"] == CLOSE_SOURCE
    svc = code_of_file(os.path.join(BACKEND, "services", "read_only", "regime_strategy.py"))
    assert svc.count("'close_source': CLOSE_SOURCE") == 2


def test_the_MEASURED_NUMBERS_are_recorded_with_the_designation():
    """All three per ticker, as the ruling asks, written where the next reader of this code
    will find them rather than only in a report."""
    svc = read_source(os.path.join(BACKEND, "services", "read_only", "regime_strategy.py"))
    i = svc.index("R-IV.1198(d)")
    block = svc[i:i + 1800]
    for n in ("763.25", "709.80", "270.44"):        # Polygon, and the UW chart close
        assert n in block, n
    for n in ("764.29", "712.57", "270.67"):        # stable_daily_bars
        assert n in block, n
    assert "Polygon" in block
    assert "designated source is the UW chart close" in block


def test_NO_SUBSTITUTION_was_made():
    """R-IV.1198(d): "If neither matches Polygon, stop and report: no substitution." One DID
    match, and the designated source is still not wired -- the classifier needs a bar SERIES and
    the chart route serves only the newest reading. So the card names what it shows and nothing
    quietly swaps a number."""
    svc = read_source(os.path.join(BACKEND, "services", "read_only", "regime_strategy.py"))
    assert "Not yet wired" in svc
    # The inputs builder still reads the one source it always read; nothing was spliced.
    inputs = code_of_file(os.path.join(BACKEND, "models", "regime_inputs.py"))
    assert "stable_daily_bars" not in inputs, "the builder takes bars as an argument"
    job = code_of_file(os.path.join(BACKEND, "jobs", "regime_job.py"))
    assert job.count("FROM stable_daily_bars") == 1, "exactly one bar source, still"
