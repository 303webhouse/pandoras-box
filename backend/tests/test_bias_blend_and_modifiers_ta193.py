"""TA-193 R1 — the blend, the sub-scores with their weights, and every modifier by name.

THE TICKET: a served composite of -0.105 against a recompute of -0.080, with no way to account
for the difference. Four stages move the score and only the first is the weighted blend:

    raw_score  = SUM(factor.score x weight / active_weight_sum)      <- the recompute
    x velocity_multiplier      1.3 when >= 3 bearish shifts in 24h
    x rvol_modifier            1.10 bullish / 1.20 bearish; forced 1.0 inside the
                               |score| <= 0.10 dead zone, or when confidence is LOW
    x circuit_breaker          bearish trigger on an already-bearish score multiplies by
                               2.0 - scoring_modifier, so 0.7 IS a 1.3x
    = composite_score                                                <- the served figure

-0.0808 x 1.3 = -0.105. TWO STAGES PRODUCE 1.3x, they fire at different points for different
reasons, and neither was named in the payload. The final number cannot tell them apart — a test
below asserts exactly that, because it is the reason naming them was the fix. TA suspected RVOL,
which is the one stage that provably did not fire: at a blend of -0.080 it sits in its own dead
zone and is forced to 1.0.

Two surfaces also lied about what they held, and both are pinned here:

  * `frontend/v2.js` captioned `composite_score` as "Raw score". It is the FULLY MODIFIED
    score. That caption is what sent a reader to recompute the blend and report the engine as
    broken.
  * `hub_get_positions`' sibling, `hub_get_bias_composite`, assigns ONE snapshot to all three
    of swing/daily/intraday, so their agreement is by construction and carries no information.
"""
from __future__ import annotations

import io
import os
import re

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(os.path.dirname(BACKEND), "frontend")


def _read(path: str) -> str:
    return io.open(path, encoding="utf-8", errors="replace").read()


def _js() -> str:
    return _read(os.path.join(FRONTEND, "v2.js"))


def _code(js: str) -> str:
    """JS with `//` comments stripped — a comment explaining a forbidden pattern contains it."""
    out = []
    for line in js.split("\n"):
        i = line.find("//")
        if i > 0:
            before = line[:i]
            if before.count("'") % 2 or before.count('"') % 2 or before.count("`") % 2:
                i = -1
        out.append(line if i < 0 else line[:i])
    return "\n".join(out)


# ── the model carries the blend and the trail ────────────────────────────────

def test_the_result_carries_the_blend_separately_from_the_final_score():
    from bias_engine.composite import CompositeResult

    assert "raw_score" in CompositeResult.model_fields
    assert "score_modifiers" in CompositeResult.model_fields


def test_an_unknown_blend_is_None_and_never_a_zero():
    """A cached pre-fix payload has no `raw_score`. Defaulting it to 0.0 would publish a blend
    of exactly zero — a real measurement — for a reading that simply predates the field."""
    from bias_engine.composite import CompositeResult

    assert CompositeResult.model_fields["raw_score"].default is None


def test_the_trail_defaults_to_empty_not_to_None():
    """A list a caller can iterate without a None check, because every consumer of it is a
    display loop and `for m in None` is the kind of break that takes a panel down."""
    from bias_engine.composite import CompositeResult

    f = CompositeResult.model_fields["score_modifiers"]
    assert f.default_factory is list


# ── every stage is named, and naming is the whole point ──────────────────────

def _stage_names() -> list:
    from tests._srcscan import read_source

    src = read_source(os.path.join(BACKEND, "bias_engine", "composite.py"))
    return re.findall(r'_stage\(\s*"([a-z_]+)"', src)


@pytest.mark.parametrize("name", ["velocity_multiplier", "rvol_modifier", "circuit_breaker"])
def test_every_post_weighting_stage_is_recorded_by_name(name):
    assert name in _stage_names()


def test_the_stage_recorder_keeps_the_score_either_side():
    """Without both, a reader can see that a stage exists but not what it did — and the ticket
    was about accounting for a difference, which needs the before and the after."""
    from tests._srcscan import function_code

    import bias_engine.composite as comp

    code = function_code(comp.__file__, "_stage")
    for key in ("score_before", "score_after", "applied", "reason", "name", "value"):
        assert key in code, key


def test_applied_distinguishes_RAN_AND_DID_NOTHING_from_DID_NOT_RUN():
    """A modifier of 1.0 ran and declined. That is not the same as a stage that never
    executed, and the difference is the whole diagnostic value: `rvol_modifier 1.0
    reason=dead_zone` says RVOL was asked and said no."""
    from tests._srcscan import function_code

    import bias_engine.composite as comp

    code = function_code(comp.__file__, "_stage")
    assert "round(before, 4) != round(after, 4)" in code


def test_an_ACTIVE_breaker_with_a_1_point_0_modifier_is_still_recorded():
    """An active breaker whose modifier has faded to 1.0 is a different state from no breaker,
    and leaving it out of the trail makes a live breaker invisible exactly when someone is
    asking what moved the score."""
    src = _read(os.path.join(BACKEND, "bias_engine", "composite.py"))
    assert "active but scoring_modifier is 1.0" in src


# ── the arithmetic the trail describes ───────────────────────────────────────

def _walk(raw, stages):
    return stages[-1]["score_after"] if stages else raw


def _build(raw, velocity=1.0, rvol=1.0, rvol_reason="dead_zone", cb_mod=None):
    """The trail's shape as composite.py builds it, so the walk is testable without Redis,
    Postgres or a live factor set."""
    stages, score = [], raw

    def stage(name, value, before, after, reason):
        stages.append({"name": name, "value": value, "score_before": round(before, 4),
                       "score_after": round(after, 4),
                       "applied": round(before, 4) != round(after, 4), "reason": reason})

    after_v = round(raw * velocity, 4)
    stage("velocity_multiplier", velocity, score, after_v, "3+ bearish shifts in 24h")
    score = after_v
    after_r = round(score * rvol, 4)
    stage("rvol_modifier", rvol, score, after_r, rvol_reason)
    score = after_r
    if cb_mod is not None and cb_mod != 1.0:
        amp = 2.0 - cb_mod if score <= 0 else cb_mod
        after_c = round(score * amp, 4)
        stage("circuit_breaker", cb_mod, score, after_c, "amplified by 2.0 - scoring_modifier")
        score = after_c
    return stages, score


def test_the_blend_times_the_applied_stages_lands_on_the_served_score():
    """THE TICKET'S ARITHMETIC. -0.0808 x 1.3 = -0.105, which is what was served."""
    stages, final = _build(-0.0808, velocity=1.3)
    assert final == pytest.approx(-0.105, abs=0.0005)
    assert _walk(-0.0808, stages) == final


def test_THE_AMBIGUITY_two_different_stages_produce_the_same_final_number():
    """THE REASON NAMING THEM IS THE FIX. A 1.3 velocity multiplier and a circuit-breaker
    scoring_modifier of 0.7 (amplifier 2.0 - 0.7) take the same blend to the same score. The
    final figure cannot distinguish them; only `name` in the trail can."""
    _, by_velocity = _build(-0.0808, velocity=1.3)
    _, by_breaker = _build(-0.0808, cb_mod=0.7)
    assert by_velocity == by_breaker
    assert by_velocity == pytest.approx(-0.105, abs=0.0005)


def test_both_firing_is_distinguishable_from_either_one():
    """If a reader sees -0.105 they know exactly one 1.3x fired, because both give -0.137."""
    _, both = _build(-0.0808, velocity=1.3, cb_mod=0.7)
    assert both == pytest.approx(-0.1365, abs=0.0005)
    assert both != pytest.approx(-0.105, abs=0.0005)


def test_RVOL_is_the_one_stage_that_CANNOT_have_caused_it():
    """TA suspected RVOL. Its own dead zone forbids it: `abs(adjusted_score) <= 0.10` forces
    1.0, and the blend in question is -0.080. Asserted against the real guard, not a copy."""
    from tests._srcscan import function_code

    import bias_engine.composite as comp

    # `0.1`, not `0.10`: ast.unparse NORMALISES NUMERIC LITERALS, the same way it normalises
    # string quotes to single. The source reads `<= 0.10` and the unparsed tree reads `<= 0.1`,
    # so matching the source spelling fails on a guard that is present and correct. Noted
    # because it is the numeric sibling of a trap already recorded for quotes.
    code = function_code(comp.__file__, "compute_rvol_modifier")
    assert "abs(adjusted_score) <= 0.1" in code
    assert "dead_zone" in code
    # And the threshold really is a tenth in the source, not a hundredth misread by unparse.
    from tests._srcscan import read_source

    assert "abs(adjusted_score) <= 0.10" in read_source(comp.__file__)


# ── the sub-scores: weights in, labels out ───────────────────────────────────

def test_a_sub_score_carries_its_active_weight():
    """A sub-score of -0.4 resting on 8% of the factor weight and one resting on 40% are not
    comparable, and nothing said which it was."""
    src = _read(os.path.join(BACKEND, "bias_engine", "composite.py"))
    i = src.index("timeframe_scores[tf_name] = {")
    block = src[i:src.index("}", i)]
    assert '"active_weight"' in block
    assert '"active_factor_count"' in block
    assert '"sub_score"' in block


def test_a_sub_score_carries_NO_bias_label():
    """R-IV.1152(d): numbers only. `bias_level` and `bias_numeric` were a second and third
    rendering of one number, and a labelled sub-score reads as a call in its own right — which
    it is not, because the call is the composite's."""
    src = _read(os.path.join(BACKEND, "bias_engine", "composite.py"))
    i = src.index("timeframe_scores[tf_name] = {")
    block = src[i:src.index("}", i)]
    assert "bias_level" not in block
    assert "bias_numeric" not in block


def test_the_weight_is_defined_even_when_a_timeframe_has_no_active_factors():
    """`tf_weight_sum` used to be bound only inside the `if tf_active:` branch, so reading it
    on the empty path would raise. An empty timeframe reports a weight of 0.0 — which here is a
    measurement, not a stand-in: no active factors IS zero active weight."""
    src = _read(os.path.join(BACKEND, "bias_engine", "composite.py"))
    i = src.index('for tf_name in ("intraday", "swing", "macro")')
    block = src[i:i + 1400]
    assert "tf_weight_sum = 0.0" in block
    assert block.index("tf_weight_sum = 0.0") < block.index("if tf_active:")


def test_the_frontend_row_shows_numbers_and_weight_not_a_label():
    js = _code(_js())
    i = js.index("const tfRow")
    body = js[i:js.index("};", i)]
    assert "active_weight" in body
    assert "levelWords" not in body, "a sub-score must not be labelled"
    assert "bias_level" not in body


# ── the caption that caused the ticket ───────────────────────────────────────

def test_composite_score_is_NO_LONGER_captioned_raw():
    """`composite_score` is the score AFTER velocity, RVOL and the breaker. Captioning it
    "Raw score" is what sent a reader to recompute the blend, get -0.080 against a displayed
    -0.105, and conclude the arithmetic was broken. The arithmetic was right."""
    js = _code(_js())
    assert "kv('Raw score', c.composite_score" not in js
    assert "kv('Weighted blend', c.raw_score" in js
    assert "kv('Score after modifiers', c.composite_score" in js


def test_the_panel_lists_the_stages_between_the_two_figures():
    js = _code(_js())
    i = js.index("kv('Weighted blend'")
    block = js[i:i + 900]
    assert "score_modifiers" in block
    assert "m.applied" in block, "only the stages that moved the score are listed"
    assert "m.name" in block and "m.value" in block


# ── the MCP payload ──────────────────────────────────────────────────────────

def test_the_tool_serves_the_blend_the_trail_and_the_sub_scores():
    src = _read(os.path.join(BACKEND, "hub_mcp", "tools", "bias_composite.py"))
    for key in ('"raw_score"', '"score_modifiers"', '"sub_scores"'):
        assert key in src, key


def test_the_tool_serves_each_factors_weight():
    """It was hard-coded `None`, so a reader had a list of scores with no way to see which the
    blend rests on."""
    src = _read(os.path.join(BACKEND, "hub_mcp", "tools", "bias_composite.py"))
    assert '"weight": None' not in src
    assert '"weight": _FACTOR_WEIGHTS.get(name)' in src


def test_the_weights_come_from_the_engines_own_config():
    """One author. A copy pasted into the tool would be a second place for a weight to drift,
    and weights are what convention #42's original defect was about."""
    src = _read(os.path.join(BACKEND, "hub_mcp", "tools", "bias_composite.py"))
    assert "from bias_engine.composite import FACTOR_CONFIG" in src


def test_an_unreadable_weight_is_None_never_zero():
    """A zero weight asserts the factor does not count. That is a different claim from "I could
    not read it", and #42's whole subject is not confusing provenance with value."""
    src = _read(os.path.join(BACKEND, "hub_mcp", "tools", "bias_composite.py"))
    i = src.index("_FACTOR_WEIGHTS = {}")
    assert "never as 0.0" in src[max(0, i - 400):i]


def test_the_three_identical_timeframe_slots_SAY_SO_in_the_payload():
    """One snapshot is assigned to swing, daily and intraday, so their agreement is by
    construction. That was stated only in a code comment, which no reader receives."""
    src = _read(os.path.join(BACKEND, "hub_mcp", "tools", "bias_composite.py"))
    assert '"timeframes_basis"' in src
    assert "THE THREE SLOTS ARE ONE READING" in src
    assert "sub_scores" in src


def test_the_summary_prints_one_label_once():
    """It printed the same label and score three times — three identical clauses reading as
    three independent horizons agreeing, which is the emptiest claim the tool could make."""
    from tests._srcscan import function_code

    import hub_mcp.tools.bias_composite as t

    code = function_code(t.__file__, "_summary")
    assert 'for tf in ("swing", "daily", "intraday")' not in code or "blocks[0]" in code
    assert "one reading across" in code


def test_the_summary_names_the_stages_that_moved_the_score():
    from tests._srcscan import function_code

    import hub_mcp.tools.bias_composite as t

    code = function_code(t.__file__, "_summary")
    assert "score_modifiers" in code
    assert "blend" in code


# ── nothing about the arithmetic itself moved ────────────────────────────────

def test_no_weight_and_no_cut_off_changed():
    """R-IV.1152(d): numbers only, no weight or cut-off changes. The trail is observation
    bolted onto arithmetic that must be byte-for-byte what it was — so the four lines that DO
    the arithmetic are pinned here."""
    src = _read(os.path.join(BACKEND, "bias_engine", "composite.py"))
    assert "raw_score = sum(active[f].score * normalized_weights[f] for f in active)" in src
    assert "adjusted_score = _clamp_score(raw_score * velocity_multiplier)" in src
    assert "adjusted_score = _clamp_score(adjusted_score * rvol_modifier)" in src
    assert "amplifier = 2.0 - scoring_mod" in src


def test_the_velocity_threshold_is_untouched():
    src = _read(os.path.join(BACKEND, "bias_engine", "composite.py"))
    assert "if bearish_shifts_24h >= 3:" in src
    assert "velocity_multiplier = 1.3" in src


def test_the_rvol_thresholds_are_untouched():
    src = _read(os.path.join(BACKEND, "bias_engine", "composite.py"))
    assert "RVOL_ACTIVATE_THRESHOLD = 1.5" in src
    assert "RVOL_DEACTIVATE_THRESHOLD = 1.2" in src
    assert "RVOL_LOW_THRESHOLD = 0.5" in src


def test_the_v2_pin_moved_because_v2_js_changed():
    """CLAUDE.md: a changed asset behind an unchanged pin is a fix that never reaches the
    browser. The regime drawer's rows changed, so the pin has to move."""
    m = re.search(r"v2\.js\?v=(\d+)", _read(os.path.join(FRONTEND, "v2.html")))
    assert m and int(m.group(1)) >= 61
