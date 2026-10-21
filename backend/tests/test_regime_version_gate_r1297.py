"""v2.1's fixes must reach v2.1's rows and no others. R-IV.1297(b) and (d).

WHAT QUERY CAUGHT (M1), and why it mattered more than it looked. The two v2.1 defect fixes --
the melt-up count and the up-side volume guard -- went into the SHARED builder, unconditionally,
while `RULES_VERSION` was still "v2". Had 0e301ea8 deployed as written, every row stamped
`rules_version = 'v2'` from that moment on would have carried v2.1 ARITHMETIC: the label would
name one version and the numbers behind it would belong to another, and the 304 rows already in
`regime_snapshots` would no longer be reproducible from the version they name. R-IV.1265(a)
froze the v2 classifier -- "any change is v3 with a ruling" -- and an unconditional fix in a
shared builder is exactly that change, arriving without one.

MEASURED, on the stored series at 2026-10-21 (R-IV.1297(b)3):

    rows 928 / 929      computed with the fixes ON (both landed in 35d42637, before the repair)
    gated v2 path       reproduces them EXACTLY -- correction/range_chop, held 4 and 5,
                        pending correction, pending_closes 2 and 3
    all 304 sessions    0 label differences between the arms; 12 INPUT differences, where v2's
                        `True` becomes a count of 2, 3 or 4
    why no label moves  melt_up is row 8 and uptrend row 9, so the row IS reached and the RSI
                        leg now passes -- but `pct_above_200dma` is 8.35% to 10.75% on those 12
                        against a 12.0% threshold, so the row still declines. The nearest miss
                        is 1.25 points.

So no superseding rows were needed. THE GATE IS STILL NECESSARY: the inputs differ on 12 rows,
and a stored row whose `inputs_json` cannot be rebuilt from the version it names is the fault
this whole module exists to prevent. "No label changed" is a fact about this history, not a
property of the fix.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from models.regime_classifier import load_rules                    # noqa: E402
from models.regime_inputs import (Bar, _rsi_hits_above_melt_up_min,  # noqa: E402
                                  v21_fixes_apply)
from models.regime_inputs_v2 import confirmed_break_up_50dma       # noqa: E402

from ._srcscan import read_source                                  # noqa: E402

V2 = load_rules("v2")
V21 = load_rules("v2.1")

#: A monotonic ramp: RSI(14) is pinned high, so every one of the last 5 closes is a hit.
RAMP = [100 + i * 2.0 for i in range(40)]


def _bars(closes, vols=None):
    return [Bar(date="2026-01-%02d" % ((i % 28) + 1), c=closes[i], h=closes[i] * 1.01,
                l=closes[i] * 0.99, v=(vols[i] if vols is not None else 1e6))
            for i in range(len(closes))]


# ── the predicate itself ────────────────────────────────────────────────────

@pytest.mark.parametrize("arg,expect", [("v2.1", True), ("v2", False), ("v1", False),
                                        ("v3", False), ("", False), (None, False)])
def test_the_gate_opens_for_v21_ALONE(arg, expect):
    assert v21_fixes_apply(arg) is expect


def test_an_unknown_version_gets_the_FROZEN_behaviour_not_the_new_one():
    """The direction of the default is the whole safety property. Defaulting the other way
    would mean a version nobody has declared silently receives arithmetic nobody ratified."""
    assert v21_fixes_apply("v4.7") is False
    assert v21_fixes_apply(rules={"version": "something else"}) is False
    assert v21_fixes_apply(rules={}) is False


def test_the_rules_file_can_answer_when_no_version_is_passed():
    """`confirmed_break_up_50dma` is handed rules, not a version string, so the file's own
    `version` has to be a valid source -- otherwise that call site could not be gated."""
    assert v21_fixes_apply(rules=V21) is True
    assert v21_fixes_apply(rules=V2) is False


def test_an_explicit_version_OVERRIDES_the_rules_file():
    """Needed by the tests that drive one arm with the other's thresholds, and the precedence
    has to be stated or a reader cannot predict which wins."""
    assert v21_fixes_apply("v2", rules=V21) is False
    assert v21_fixes_apply("v2.1", rules=V2) is True


def test_there_is_ONE_predicate_and_both_call_sites_read_it():
    """A version test written twice is a version test that will disagree with itself. Both
    gated modules must call the same function rather than compare strings themselves."""
    for mod in ("regime_inputs.py", "regime_inputs_v2.py"):
        src = read_source(str(_BACKEND / "models" / mod))
        assert "v21_fixes_apply(" in src, mod
    v2src = read_source(str(_BACKEND / "models" / "regime_inputs_v2.py"))
    assert "from models.regime_inputs import" in v2src and "v21_fixes_apply" in v2src


# ── the melt-up count: two behaviours, one function ─────────────────────────

def test_v2_returns_999aae43s_BOOLEAN():
    got = _rsi_hits_above_melt_up_min(_bars(RAMP), rules_version="v2")
    assert got is True, got


def test_v21_returns_AN_INTEGER_COUNT():
    got = _rsi_hits_above_melt_up_min(_bars(RAMP), rules_version="v2.1")
    assert isinstance(got, int) and not isinstance(got, bool)
    assert got == 5, got


def test_no_version_means_v2s_behaviour():
    """The default has to be the frozen one: `build_inputs` is called from several places that
    pass no version, and every one of them is computing v2 today."""
    assert _rsi_hits_above_melt_up_min(_bars(RAMP)) is True


def test_a_series_with_no_hits_differs_the_same_way():
    """False vs 0 -- both falsy, and that is the point: the DEFECT is not that v2 said the
    wrong thing about a quiet tape, it is that `float(True) >= 2` could never hold on a loud
    one. The quiet case must still differ in TYPE so the two arms are distinguishable."""
    flat = _bars([100.0 + (0.01 if i % 2 else -0.01) for i in range(40)])
    assert _rsi_hits_above_melt_up_min(flat, rules_version="v2") is False
    assert _rsi_hits_above_melt_up_min(flat, rules_version="v2.1") == 0


def test_v2_CANNOT_pass_the_two_hit_test_and_v21_CAN():
    """The defect and its fix as arithmetic, so neither can come back as an opinion."""
    need = V21["thresholds"]["melt_up_rsi_hits_of_last_5"]
    assert need == 2
    v2_value = _rsi_hits_above_melt_up_min(_bars(RAMP), rules_version="v2")
    v21_value = _rsi_hits_above_melt_up_min(_bars(RAMP), rules_version="v2.1")
    assert not (float(v2_value) >= need), "v2's Melt-up RSI leg must stay unreachable"
    assert v21_value >= need, "v2.1's must be reachable"


def test_BOTH_arms_still_refuse_a_series_too_short():
    """"Cannot tell" is not "no hits", and that was never version-dependent."""
    short = _bars([100 + i for i in range(10)])
    assert _rsi_hits_above_melt_up_min(short, rules_version="v2") is None
    assert _rsi_hits_above_melt_up_min(short, rules_version="v2.1") is None


def test_v2_reads_its_threshold_from_the_SIGNATURE_and_v21_from_the_FILE():
    """999aae43 had 75.0 as a signature default. Keeping that on the v2 path matters: if v2
    started reading the file, a later edit to `melt_up_rsi_min` would retroactively change what
    v2 means, and v2's stored rows would stop being reproducible."""
    import inspect
    src = inspect.getsource(_rsi_hits_above_melt_up_min)
    assert "threshold = 75.0" in src, "v2's frozen literal must still be there"
    assert "melt_up_rsi_min" in src, "v2.1 must read the file"
    assert inspect.signature(_rsi_hits_above_melt_up_min).parameters["threshold"].default is None


def test_the_function_name_no_longer_states_the_threshold():
    """R-IV.1297(e): the 75 belongs to the rules file, and a name that repeats it is a second
    place for one figure. The DICT KEY is deliberately unchanged -- the classifier reads
    `spy.rsi_ge_75_of_last_5` by name and every stored `inputs_json` already carries it."""
    from models import regime_inputs as ri
    assert not hasattr(ri, "_rsi_ge_75_of_last_5")
    assert hasattr(ri, "_rsi_hits_above_melt_up_min")
    assert "rsi_ge_75_of_last_5" in read_source(str(_BACKEND / "models" / "regime_inputs.py"))


# ── the volume guard: LAB's order, and the case it changes ──────────────────

#: >=200 closes, a bearish stack, and the last two closes still through the 50dma. Found by
#: sweeping spike size and length against `latest_moving_averages` rather than reasoned about:
#: at spike 1.60 over 4 bars the stack reads `transitioning` and the fixture would prove
#: nothing. 1.25 over 2 bars is bearish AND clears the 50dma on both closes.
_DECLINE = [200.0 - (100.0 * i / 250.0) for i in range(250)]
_BOUNCE = _DECLINE + [_DECLINE[-1] * 1.25] * 2


def _few_volumes(n_usable=5):
    """The same series with only `n_usable` non-None volumes -- a LONG series whose VOLUMES are
    few, which is the distinction R-IV.1297(d) asks the comment to get right."""
    n = len(_BOUNCE)
    return _bars(_BOUNCE, vols=[(1e6 if i >= n - n_usable else None) for i in range(n)])


def test_the_divergent_case_returns_NONE_under_v21():
    """R-IV.1297(d)'s named case: >=200 closes, fewer than 21 non-None volumes, bearish stack.

    THIS IS WHY THE ORDER MATTERS. My version put the guard after the stack test, so the stack
    test answered first and the function returned False -- "not a confirmed break" -- about a
    series that cannot answer the question at all. LAB's order asks "can I check?" before
    "what is the answer?", and returns None.
    """
    assert confirmed_break_up_50dma(_few_volumes(), V21) is None


def test_the_same_case_is_FALSE_under_v2_which_is_the_divergence():
    """Both halves of the differential. A None that no arm contradicts proves nothing about
    the gate; this says the gate is what produced it."""
    assert confirmed_break_up_50dma(_few_volumes(), V2) is False


def test_the_CONTROL_with_enough_volumes_both_arms_agree():
    """CONVENTION #30. If the arms disagreed on this series for some reason other than the
    volume count, the two tests above would still pass and would still be measuring the wrong
    thing. With the guard not triggered they must agree."""
    plenty = _few_volumes(n_usable=60)
    assert confirmed_break_up_50dma(plenty, V2) is False
    assert confirmed_break_up_50dma(plenty, V21) is False


def test_the_fixture_really_has_a_bearish_stack_and_really_clears_the_50dma():
    """Otherwise the divergence above could come from the closes-through test short-circuiting
    before either the stack test or the guard, and the case would not be the one (d) named."""
    from indicators.moving_averages import latest_moving_averages
    from models.regime_inputs import _closes
    cs = _closes(_few_volumes())
    assert len(cs) >= 200
    assert latest_moving_averages(cs)["sma"]["stack_state"] == "bearish"
    for k in range(V21["confirmed_break"]["closes_through_50dma"]):
        upto = cs[:len(cs) - k]
        assert upto[-1] > latest_moving_averages(upto)["sma"]["50"]
    assert V21["confirmed_break"]["stack_must_turn"] is True


def test_the_guard_runs_BEFORE_the_original_body():
    """Read from the source, because the ORDER is the thing (d) corrects and a value test
    cannot see it: both orders return None on a series with no bearish stack."""
    src = read_source(str(_BACKEND / "models" / "regime_inputs_v2.py"))
    i = src.index("def confirmed_break_up_50dma")
    block = src[i:src.index("def ma20_crossed_above_ma50", i)]
    guard = block.index("if len(vols) < 21:")
    stack = block.index('if cb.get("stack_must_turn")')
    closes = block.index("for k in range(need):")
    assert guard < closes < stack, (guard, closes, stack)


def test_the_rationale_says_VOLUMES_not_series_length():
    """R-IV.1297(d). The old comment said "a series too short to confirm a break", which is
    wrong: the bar count can be 250 while `b.v` is None on all but a handful -- the fixture
    above is exactly that."""
    src = read_source(str(_BACKEND / "models" / "regime_inputs_v2.py"))
    i = src.index("def confirmed_break_up_50dma")
    block = src[i:src.index("def ma20_crossed_above_ma50", i)]
    # A NEGATIVE SUBSTRING SCAN IS UNUSABLE HERE, and failing it is how I found that out for
    # the ninth time in this repo: the corrected docstring QUOTES the wrong wording in order to
    # say it was wrong, so `"a series too short..." not in block` fails on the explanation
    # itself. `ast.unparse` does not help -- it drops comments but KEEPS docstrings, and this
    # text is a docstring. So the assertion is positive and specific instead: the block must
    # state the distinction, in terms a wrong version could not accidentally satisfy.
    assert "VOLUME VALUES, NOT SERIES LENGTH" in block
    assert "bar count can be 250" in block, "the distinction must be made concretely"
    assert "count of USABLE volumes" in block


def test_a_full_history_still_answers_on_both_arms():
    rising = _bars([100 + i for i in range(260)])
    assert confirmed_break_up_50dma(rising, V2) in (True, False)
    assert confirmed_break_up_50dma(rising, V21) in (True, False)


# ── the builders thread the version through ─────────────────────────────────

def test_sessions_from_series_takes_a_version_and_forwards_it_BOTH_ways():
    """Two paths need it: the shared block (the melt-up count) and `_fill_v2` (the volume
    guard, via the rules it loads). Forwarding one and not the other would compute a third
    thing that is neither version."""
    import inspect

    from models.regime_inputs import build_inputs, sessions_from_series
    assert "rules_version" in inspect.signature(sessions_from_series).parameters
    assert "rules_version" in inspect.signature(build_inputs).parameters
    src = inspect.getsource(sessions_from_series)
    assert "rules_version=rules_version" in src, "the shared block"
    assert "load_rules(rules_version or RULES_VERSION)" in src, "_fill_v2's rules"


def test_build_sessions_passes_the_rules_files_OWN_version():
    """The job holds `rules`, so the version it computes and the file it computes from cannot
    disagree -- which they would if the caller passed a version separately."""
    src = read_source(str(_BACKEND / "jobs" / "regime_job.py"))
    i = src.index("async def build_sessions")
    block = src[i:src.index("_GROUP_MEMBERS", i)]
    assert "rules_version=version" in block
    assert 'version = rules.get("version")' in block


def test_RULES_VERSION_IS_NOW_v21_BECAUSE_THIS_IS_THE_CUTOVER():
    """THE PIN FIRED AND THIS IS THE COMMIT IT WAS WAITING FOR. R-IV.1303(c) / R-IV.1307(c).

    The previous form asserted `RULES_VERSION == "v2"` and said in its own message: "if this is
    intentionally v2.1, this is the cutover commit and this test should be updated in it,
    together with the card and QUERY's review." All three happened -- QUERY cleared c7261e90
    under R-IV.1301(b) -- so the assertion inverts here rather than being deleted. A pin that is
    removed when it fires teaches nothing; one that flips records WHEN the flip happened and
    keeps guarding the other direction.
    """
    from models.regime_classifier import RULES_VERSION
    assert RULES_VERSION == "v2.1", (
        "the cutover is this branch; a change away from v2.1 needs its own ruling")


def test_the_served_rules_file_IS_the_stamped_v21_artifact():
    """The flip is only real if `load_rules()` with no argument now resolves to v2.1 -- which
    is the call every default path makes, and the one that raised FileNotFoundError until
    R-IV.1297(c) renamed the file."""
    assert load_rules()["version"] == "v2.1"

# ── the loader ──────────────────────────────────────────────────────────────

def test_the_loader_accepts_the_stamped_filename():
    """`load_rules` builds `regime_rules.%s.json`, so "v2.1" asks for `regime_rules.v2.1.json`.
    f1777f80's file was `regime_rules.v2_1.json`, which that name NEVER resolved to --
    `load_rules("v2.1")` raised FileNotFoundError, so the cutover would have crashed on its
    first call. R-IV.1297(c)'s filename is what fixes it; nothing in the loader changed."""
    assert load_rules("v2.1")["version"] == "v2.1"
    assert not (_BACKEND / "config" / "regime_rules.v2_1.json").exists(), (
        "f1777f80's file is retired")
