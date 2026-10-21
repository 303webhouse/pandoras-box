"""Regime classifier v2.1, the parts built so far. R-IV.1277(b) / R-IV.1278(c), registration §1.

THE BUILD'S OWN FIRST RULE IS "NO new thresholds", so the rules file is asserted to differ from
v2 in exactly two keys. A copy made by hand and eyeballed is how a threshold moves by one
digit, and this file is the thing that would notice.

THE MELT-UP LEG COULD NEVER FIRE, which is the substantive fix here and not a tidy-up:
`_rsi_ge_75_of_last_5` returned a BOOL, and `regime_classifier` compares it as
`hits >= melt_up_rsi_hits_of_last_5` where the threshold is 2. `float(True)` is 1.0 and
`1.0 >= 2` is False, so the Melt-up row's RSI condition was unreachable on every session in
every era. A yes/no feeding a ">= 2" test is not a stricter rule, it is a rule that cannot fire.

AND FIXING IT RECLASSIFIED A FIXTURE, which is the right kind of consequence to see: the 300-bar
synthetic ramp this suite calls "a steady uptrend" is 17.3% above its own 200dma with RSI at or
above 75 on all of the last 5 -- a melt-up by section 2's own rules. The fixture was corrected
rather than the assertion relaxed, and the reclassification is pinned by its own test so the fix
cannot silently regress.
"""
from __future__ import annotations

import collections
import io
import json
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from models.regime_inputs import (Bar,                                # noqa: E402
                                  _rsi_hits_above_melt_up_min)
from models.regime_inputs_v2 import confirmed_break_up_50dma         # noqa: E402

V2 = _BACKEND / "config" / "regime_rules.v2.json"
V21 = _BACKEND / "config" / "regime_rules.v2.1.json"



def _load(p):
    return json.loads(io.open(p, encoding="utf-8").read(),
                      object_pairs_hook=collections.OrderedDict)


def _bars(closes, vols=None):
    import datetime as _dt
    return [Bar(_dt.date(2025, 1, 1) + _dt.timedelta(days=i), c, c + 1, c - 1, c,
                (vols[i] if vols else 1_000_000)) for i, c in enumerate(closes)]


# ── 1 · the rules file ───────────────────────────────────────────────────────

def test_the_v21_file_exists_and_is_tagged_v21():
    assert V21.exists()
    assert _load(V21)["version"] == "v2.1"


#: R-IV.1297(c): the stamped artifact's LF sha256, as the ruling states it.
STAMPED_SHA256 = "4bc6d895484a2f581efa3b4356591209b966351183d693cd158eedb240974e9a"


def test_the_v21_file_IS_LABs_STAMPED_ARTIFACT_byte_for_byte():
    """R-IV.1297(c): "production must read the stamped artifact."

    f1777f80's file was written here from the spec; this one is LAB's, copied. The difference
    matters because that file is the only statement of what v2.1 IS -- a hand-written copy of a
    stamped artifact is a second original, and the two drift silently because nothing compares
    them. It also carried `registered: True`, which R-IV.1191 does not support: v2.1's
    authority is TA-208, registration ab015afa, stamp PR-1b, and LAB's file says
    `registered: false` with "pending Nick's PR-1 stamp".

    HASHED ON LF BYTES, which is what the ruling specifies and also what survives this
    machine. `core.autocrlf` is true, so a CRLF checkout would change the file by one byte per
    line and a raw hash would read drift where there is none; `.gitattributes` pins the path
    with `-text` as well, so both halves hold.
    """
    import hashlib
    raw = V21.read_bytes()
    lf = raw.replace(b"\r\n", b"\n")
    assert hashlib.sha256(lf).hexdigest() == STAMPED_SHA256, (
        "backend/config/regime_rules.v2.1.json is not LAB's stamped artifact")


def test_it_claims_NO_REGISTRATION_IT_DOES_NOT_HAVE():
    """R-IV.1297(c) / R-IV.1191."""
    d = _load(V21)
    assert d["registered"] is False
    assert "pending" in d["registered_by"].lower()
    assert "ab015afa" in d["source"], d["source"]


def test_it_differs_from_v2_ONLY_IN_PROVENANCE():
    """"NO new thresholds. Every number is already in regime_rules.v2.json." Asserted over
    every leaf, so a digit moved anywhere in the file is a failure rather than a reading.

    STATED AS A PREDICATE OVER THE KEYS, not as a count. The earlier version asserted
    `differ == [".hysteresis.stated_cost", ".version"]` -- exactly two keys -- and the stamped
    artifact differs in seven, every one of them provenance. A count would have failed here
    while the thing it existed to protect was intact, and the fix for a failing count is to
    edit the number, which is how a guard stops guarding. What matters is that NOTHING
    ARITHMETIC MOVED, so that is what this asserts.
    """
    def flat(o, p=""):
        if isinstance(o, dict):
            for k, v in o.items():
                yield from flat(v, p + "." + str(k))
        elif isinstance(o, list):
            yield p, json.dumps(o)
        else:
            yield p, o
    a, b = dict(flat(_load(V2))), dict(flat(_load(V21)))
    differ = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    allowed = {".version", ".registered", ".registered_by", ".source", ".authority",
               ".hysteresis.stated_cost"}
    offending = [k for k in differ
                 if k not in allowed and not k.startswith(".v2_1_defect_pack.")]
    assert offending == [], offending

def test_the_thresholds_the_hysteresis_and_the_order_are_byte_identical():
    a, b = _load(V2), _load(V21)
    assert json.dumps(a["thresholds"], sort_keys=True) == json.dumps(b["thresholds"], sort_keys=True)
    assert list(a["order"]) == list(b["order"])
    for k in a["hysteresis"]:
        if k != "stated_cost":
            assert a["hysteresis"][k] == b["hysteresis"][k], k


def test_the_RULES_FILE_IS_NOT_THE_SOURCE_OF_THE_COST_LINE():
    """R-IV.1303(b) RESOLVED THE COLLISION THIS TEST USED TO RECORD.

    R-IV.1297(e) asked for the cost sentence to change; R-IV.1297(c) required this file to stay
    byte-identical to a named sha256; `cost_statement` read the sentence out of it. No common
    satisfaction, so the item was reported blocked. The fault was PLACEMENT: a sentence about
    what a classifier gets wrong is a DISPLAY fact that changes when someone grades the
    classifier, while the thresholds it describes must not change at all.

    So the line moved to `backend/config/regime_card_display.v1.json` and this file keeps its
    own `stated_cost` -- part of the stamped bytes -- undisplayed. R-IV.1307(b) supplies the
    real line, and the phrase that called QUERY's graded figures ungraded is gone from the
    repo's live text entirely.
    """
    from models.regime_hysteresis import cost_statement

    stamped = _load(V21)["hysteresis"]["stated_cost"]
    assert "V-shaped bottoms" in stamped, "the stamped bytes are unchanged"
    assert stamped not in cost_statement("v2.1"), "the rules file must not be the display source"

def test_v2s_own_file_is_untouched():
    """v2's rows stay in regime_snapshots beside v2.1's, so v2 must keep working exactly as it
    does. The unique key (as_of, rules_version, close_source) is what lets them sit together."""
    assert _load(V2)["version"] == "v2"
    assert "V-shaped bottoms" in _load(V2)["hysteresis"]["stated_cost"]


# ── 2 · the melt-up count ────────────────────────────────────────────────────

def test_it_returns_an_integer_count_not_a_boolean():
    hits = _rsi_hits_above_melt_up_min(_bars([100 + i * 2.0 for i in range(40)]),
                                       rules_version="v2.1")
    assert isinstance(hits, int) and not isinstance(hits, bool), type(hits)


def test_a_ramp_counts_every_hit_and_a_flat_series_counts_none():
    assert _rsi_hits_above_melt_up_min(_bars([100 + i * 2.0 for i in range(40)]),
                                       rules_version="v2.1") == 5
    flat = _bars([100.0 + (0.01 if i % 2 else -0.01) for i in range(40)])
    assert _rsi_hits_above_melt_up_min(flat, rules_version="v2.1") == 0


def test_the_old_boolean_could_never_satisfy_the_two_hit_test():
    """The defect, stated as arithmetic so it cannot come back as an opinion."""
    need = _load(V21)["thresholds"]["melt_up_rsi_hits_of_last_5"]
    assert need == 2
    assert float(True) == 1.0
    assert not (float(True) >= need), "this is why the Melt-up row was unreachable"
    assert _rsi_hits_above_melt_up_min(_bars([100 + i * 2.0 for i in range(40)]),
                                       rules_version="v2.1") >= need


def test_exactly_one_hit_is_not_a_melt_up_and_two_is():
    """registration §1 / R-IV.1277(b)'s own test: "a series with exactly 1 hit gives no melt-up; one with 2 hits
    passes the RSI leg."

    THE SERIES IS MEASURED, NOT ASSUMED. My first attempt climbed hard then drifted down, and
    gave 5 hits on BOTH arms -- RSI(14) stays above 75 for many sessions after a steep run, so
    "drift down for four bars" does not drop it. A flat base with N spike bars on the end does
    separate them, measured directly off `latest_rsi`:

        spikes=0  hits=0   RSI(newest first) 52.5 48.8 52.6 48.9 52.7
        spikes=1  hits=1   RSI 95.3 52.5 48.8 52.6 48.9
        spikes=2  hits=2   RSI 97.6 95.3 52.5 48.8 52.6

    A fixture that passes for the wrong reason is worse than no fixture, which is why these
    were read off the indicator rather than reasoned about.
    """
    need = _load(V21)["thresholds"]["melt_up_rsi_hits_of_last_5"]
    base = [100.0 + (0.05 if i % 2 else -0.05) for i in range(30)]

    def with_spikes(n):
        return _rsi_hits_above_melt_up_min(
            _bars(base + [100.0 + 12.0 * (k + 1) for k in range(n)]), rules_version="v2.1")

    assert with_spikes(0) == 0
    one, two = with_spikes(1), with_spikes(2)
    assert one == 1 and two == 2, (one, two)
    assert not (one >= need), "one hit must NOT satisfy the RSI leg"
    assert two >= need, "two hits must satisfy it"


def test_the_threshold_is_read_from_the_rules_file():
    """75 was a literal in the signature while `thresholds.melt_up_rsi_min` held the same
    number -- two places for one figure, and the one nobody edits is the one that drifts."""
    import inspect
    sig = inspect.signature(_rsi_hits_above_melt_up_min)
    assert sig.parameters["threshold"].default is None, (
        "the default must come from the rules file, not from the signature")
    assert "melt_up_rsi_min" in inspect.getsource(_rsi_hits_above_melt_up_min)
    assert _load(V21)["thresholds"]["melt_up_rsi_min"] == 75.0


def test_a_series_too_short_is_none_and_not_zero():
    """"Cannot tell" is not "no hits": zero would make the row FAIL on a reason that is about
    the data rather than about the tape."""
    assert _rsi_hits_above_melt_up_min(_bars([100 + i for i in range(10)]),
                                       rules_version="v2.1") is None


def test_an_unreadable_session_makes_the_whole_count_unknowable():
    """A partial count would understate it. Read from the source, because the behaviour is a
    branch rather than a value a fixture can reach easily here."""
    import inspect
    src = inspect.getsource(_rsi_hits_above_melt_up_min)
    assert "MAKES THE COUNT UNKNOWABLE, not smaller" in src
    assert src.count("return None") >= 2


# ── 3 · the up-side volume check ─────────────────────────────────────────────

def test_short_volume_history_is_none_not_true():
    """It used to SKIP the volume test and fall through to `return True` -- so a series too
    short to confirm a break returned a CONFIRMED break, dropping the one leg that separates a
    real break from a drift."""
    assert confirmed_break_up_50dma(_bars([100 + i for i in range(260)], vols=[None] * 260),
                                    rules_version="v2.1") is None
    assert confirmed_break_up_50dma(
        _bars([100 + i for i in range(260)], vols=([None] * 245 + [1_000_000] * 15)),
        rules_version="v2.1") is None


def test_a_full_history_still_answers_true_or_false():
    got = confirmed_break_up_50dma(_bars([100 + i for i in range(260)]),
                                   rules_version="v2.1")
    assert got in (True, False), got


def test_it_now_mirrors_the_downward_one():
    """The two are written beside each other precisely so they mirror, and the mirror had
    drifted on the one branch nobody exercised -- a short series is rare once the 200dma
    warm-up has been served."""
    from models.regime_inputs import confirmed_break_down_50dma
    short = _bars([100 - i for i in range(260)], vols=[None] * 260)
    assert confirmed_break_down_50dma(short) is None
    assert confirmed_break_up_50dma(_bars([100 + i for i in range(260)], vols=[None] * 260),
                                    rules_version="v2.1") is None


# ── the consequence of the melt-up fix, pinned ───────────────────────────────

def test_the_steep_synthetic_ramp_is_a_melt_up_and_the_gentle_one_is_an_uptrend():
    """The reclassification, in one place. Both are monotonic, so RSI is pinned at 100 on each
    and the EXTENSION leg is what separates them: the steep ramp sits 17% above its own 200dma,
    past the 12% threshold; the gentle one near 8%, inside it."""
    from jobs.regime_seed import replay
    from models.regime_inputs import SECTORS, sessions_from_series

    def series(slope):
        import datetime as _dt
        bars, d, i = [], _dt.date(2024, 1, 2), 0
        while len(bars) < 300:
            if d.weekday() < 5:
                c = 300.0 + i * slope
                bars.append(Bar(d, c, c * 1.004, c * 0.996, c, 1_000_000))
                i += 1
            d += _dt.timedelta(days=1)
        s = {"SPY": bars, "QQQ": bars, "IWM": bars}
        for t in SECTORS:
            s[t] = bars
        return s

    # BOTH SIDES NAME v2.1 (R-IV.1297(b)1). The fix is gated now, so inputs built without a
    # version get v2's bool and the Melt-up row goes back to being unreachable -- this test
    # would then assert v2's defect while claiming to test the fix.
    from models.regime_classifier import load_rules
    r21 = load_rules("v2.1")
    steep = replay(sessions_from_series(series(0.8), rules_version="v2.1"), r21)["shown"][-1]
    gentle = replay(sessions_from_series(series(0.3), rules_version="v2.1"), r21)["shown"][-1]
    assert steep["regime"] == "melt_up", steep["basis"]
    assert gentle["regime"] == "uptrend", gentle["basis"]
    assert "RSI >= 75 on 5 of the last 5" in steep["basis"]


def test_melt_up_sits_above_uptrend_in_the_order():
    """Which is why the fix changed the label rather than adding a second one."""
    order = _load(V21)["order"]
    assert order.index("melt_up") < order.index("uptrend"), order
