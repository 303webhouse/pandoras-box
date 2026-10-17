"""The regime playbook: versioned texts, loaded and checked — R-IV.1186(b), v0.

WHAT THIS GUARDS. §1 of the double-pass record is the whole constraint: the module "is not a
signal. It never says 'buy X' or 'short Y', never ranks tickers, and nothing in the hub uses its
label to change caps, gates, the kill-switch or the journal (Convention #42)." A playbook is
prose, prose drifts, and the drift that matters is a context line turning into an instruction.
So the texts live in versioned files and a lint rejects instruction wording before the build
passes.

THE HARD PART, STATED HONESTLY. The source texts themselves contain the words. "short squeezes",
"a before-the-turn short", "sellers' market", "dips bought", "B1/B2 shorts only after a confirmed
downtrend" — all descriptive, and a lint on the bare word `short` would reject the ruled text
it exists to protect. Meanwhile "Don't buy new premium in the spike" and "re-arm tails only
once..." ARE directives, and the same lint must catch those.

So the rule is about GRAMMAR, not vocabulary:

    FAIL  a directive verb aimed at an instrument or ticker        "buy SPY", "short the rally"
    FAIL  a bare imperative opening a line                          "Buy the dip.", "Take 60-70%"
    FAIL  a ticker carrying a directive                             "SPY: enter on a reclaim"
    PASS  the same words as nouns or descriptions                    "short squeezes", "puts lose"
    PASS  a ticker named as a measurement or a level                 "QQQ back above its 50dma"

A word list cannot make that distinction and is not attempted. What is attempted is narrow and
auditable: an imperative at the head of a sentence, and a directive verb with an instrument
inside a short window after it. Anything this rule cannot judge it REJECTS, because a lint that
waves through what it does not understand is the thing it replaces.

WRITTEN BEFORE THE TEXTS WERE TRANSCRIBED, deliberately — a lint shaped to pass a particular
transcription tests the transcription, not the rule.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Iterable, List, Tuple

#: Where the versioned files live. Under `frontend/assets/` because CLAUDE.md serves only that
#: folder wholesale, so the browser and this module read THE SAME bytes -- a second copy for the
#: card would be a second place for a text to drift away from the one the lint checked.
ASSETS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "frontend", "assets", "regime")

PLAYBOOK_VERSION = "v1"
PLAYBOOK_FILE = "playbooks.%s.json" % PLAYBOOK_VERSION
MOCK_FILE = "regime_mock.json"

#: Verbs that place an order. `hold` is absent on purpose: "defensives hold" is a description of
#: the tape, and the overlap with "hold a position" is not resolvable by word.
ORDER_VERBS = (
    "buy", "sell", "short", "long", "enter", "exit", "add", "trim", "close", "open",
    "take", "harvest", "re-arm", "rearm", "roll", "hedge", "scale", "size", "allocate",
    "cut", "stop", "cover", "write", "sweep",
)

#: Things an order would be aimed at. A directive verb within range of one of these is an
#: instruction whatever the sentence around it claims to be.
INSTRUMENT_WORDS = (
    "premium", "tails", "tail", "calls", "call", "puts", "put", "spread", "spreads",
    "contract", "contracts", "shares", "position", "positions", "stock", "etf", "etfs",
    "strangle", "straddle", "condor", "butterfly", "fly", "leaps", "dte",
    # Not instruments, but the ordinary objects of a trade directive: "take profits",
    # "cut risk", "scale exposure". A directive aimed at one of these is still an order.
    "profit", "profits", "gains", "risk", "exposure", "size", "sizing", "leverage",
)

#: Tickers and instrument symbols the record names. Used for the "a ticker as an instruction"
#: half of the rule -- a ticker is fine as a MEASUREMENT ("QQQ back above its 50dma") and not as
#: an object of a directive.
TICKERS = (
    "SPY", "QQQ", "IWM", "SMH", "TSM", "XLF", "KRE", "RSP", "VIX", "VIX3M", "BZ",
    "AUDJPY", "MXNJPY", "USDJPY", "HYG", "TLT", "GLD", "XLE", "XLU", "VTI", "SHV",
    "GUSH", "SQQQ", "SOXS", "TSLQ", "SRTY", "PDBC", "GDXJ",
)

#: How far after a directive verb an instrument still counts as its object. Four words catches
#: "buy new premium" and "take 60-70% of the position" without reaching across a sentence.
_OBJECT_WINDOW = 4

#: What turns a directive word into a COMMAND when it opens a sentence: an object phrase.
#: "Short THE rally" commands; "short squeezes" is a compound noun and describes the tape.
#: Measured on the record's own text -- "short squeezes, with the most-beaten-down names
#: ripping hardest" was the one false positive of the first version of this rule, and
#: loosening the rule to let it through would also have let "Short the rally" through. The
#: grammar separates them; a word list cannot.
_OBJECT_OPENERS = frozenset({
    "the", "a", "an", "this", "that", "these", "those", "your", "my", "our", "their", "its",
    "his", "her", "some", "any", "all", "both", "each", "every", "half", "more", "less",
    "into", "on", "at", "in", "to", "from", "out", "up", "down", "back", "now", "here",
    "when", "once", "only", "before", "after", "under", "over", "per", "by", "against",
    "two", "three", "four", "five", "ten", "it", "them", "new",
})

#: NOUN PHRASES THAT ONLY LOOK LIKE COMMANDS, each written down because an exception that is
#: not stated is a hole. "Long premium bleeds fastest as vol deflates" has `long premium` as its
#: SUBJECT and `bleeds` as its verb -- it is a pricing fact, which is exactly what §4 line 3
#: asks the premium line to be.
#:
#: The head noun in every entry is a MASS noun (premium, vol, gamma, duration) which cannot be
#: the object of an order in that form. `short puts` and `long calls` are DELIBERATELY ABSENT:
#: those read as commands ("Short puts here.") and must keep failing.
#:
#: A false positive costs a rewording. A false negative ships an instruction. So the rule stays
#: strict and the exceptions are enumerated, never inferred.
DESCRIPTIVE_PHRASES = (
    "long premium", "short premium", "long vol", "short vol", "long gamma", "short gamma",
    "long duration", "short duration", "long dated", "short dated", "long end", "short end",
    "short interest", "short squeeze", "short squeezes", "short covering",
    # NOUN-SLOT USES, found by running this lint over the record's own section 3. "A
    # hyperscaler capex-guidance cut" has `cut` as a NOUN with a hyphenated modifier in front
    # of it, and the `call` four words later is an EARNINGS call, not a call option -- two
    # words misread in one clause. Holding a WATCH condition over that would gut the overlay,
    # so the phrase is exempted and the exemption is written down.
    "guidance cut", "capex-guidance cut", "rate cut", "rate cuts", "spending cut",
    "earnings call", "conference call", "margin call", "capital call",
    "stop level", "stop loss", "stop losses", "short side", "long side",
)

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9\-]*")
_SENTENCE = re.compile(r"(?<=[.;:!?])\s+|\n+")


class PlaybookLintError(AssertionError):
    """A playbook text that reads as an instruction. Raised so a build stops."""


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE.split(text or "") if s and s.strip()]


def _words(text: str) -> List[str]:
    return _WORD.findall(text or "")


def order_findings(text: str) -> List[str]:
    """Every reason `text` reads as an instruction. Empty list means it does not.

    Two tests, both about grammar:

    1. A BARE IMPERATIVE OPENING A SENTENCE. English puts the verb first in a command, so a
       sentence whose first word is a directive verb is a command almost regardless of what
       follows -- "Buy the dip", "Take 60-70% under 21 DTE", "Re-arm tails once...". A
       negated imperative counts: "Don't buy new premium" instructs just as firmly as "buy"
       does, and the module is not permitted to instruct in either direction.

    2. A DIRECTIVE VERB WITH AN INSTRUMENT OR TICKER JUST AFTER IT, anywhere in the sentence.
       This is what catches "...so buy spreads here" mid-clause, where the imperative test
       does not reach.

    A ticker alone is NOT a finding. The record is full of tickers used as measurements, and
    rejecting those would reject §2 wholesale.
    """
    findings: List[str] = []
    for sent in _sentences(text):
        words = _words(sent)
        if not words:
            continue
        lowered = [w.lower() for w in words]

        # 1 - the imperative head. "Don't buy" / "Do not short" put the directive second or
        # third, so the first three words are examined and a leading negation is skipped.
        # An enumerated noun phrase at the head is not a command. Checked FIRST and reported
        # nowhere: it is a stated exception, not a silent skip -- `describes()` below exposes
        # the same list so a test can assert what is exempt.
        opening = " ".join(lowered[:2])
        if opening in DESCRIPTIVE_PHRASES:
            continue

        head_idx = [i for i, w in enumerate(lowered[:3])
                    if w not in ("don", "t", "do", "not", "never", "no")]
        if head_idx and lowered[head_idx[0]] in ORDER_VERBS:
            verb = lowered[head_idx[0]]
            after = lowered[head_idx[0] + 1] if len(lowered) > head_idx[0] + 1 else ""
            # A COMMAND NEEDS AN OBJECT PHRASE. A determiner, a preposition, a number, an
            # instrument or a ticker after the verb makes it one. A bare noun does not:
            # "short squeezes" is a compound noun about the tape, and the first version of
            # this rule rejected it -- while any loosening that admitted it would also have
            # admitted "Short the rally".
            commands = (after in _OBJECT_OPENERS
                        or after in INSTRUMENT_WORDS
                        or (after[:1].isdigit() if after else False)
                        or (len(words) > head_idx[0] + 1
                            and words[head_idx[0] + 1].upper() in TICKERS
                            and words[head_idx[0] + 1].isupper()))
            if commands:
                findings.append("imperative %r opens: %r" % (verb, sent[:90]))
                continue

        # 2 - a directive verb with an object in range.
        for i, w in enumerate(lowered):
            if w not in ORDER_VERBS:
                continue
            # THE VERB MIGHT BE A NOUN. An enumerated phrase that CONTAINS this occurrence
            # exempts this occurrence only -- the scan continues, so a real command later in
            # the same sentence is still caught. Checked both ways round because the directive
            # word can head the phrase ("stop loss") or end it ("capex-guidance cut").
            pair_before = " ".join(lowered[i - 1:i + 1]) if i else ""
            pair_after = " ".join(lowered[i:i + 2])
            if pair_before in DESCRIPTIVE_PHRASES or pair_after in DESCRIPTIVE_PHRASES:
                continue
            window = lowered[i + 1:i + 1 + _OBJECT_WINDOW]
            window_raw = words[i + 1:i + 1 + _OBJECT_WINDOW]
            hit = next((x for x in window if x in INSTRUMENT_WORDS), None)
            tick = next((x for x in window_raw if x.upper() in TICKERS and x.isupper()), None)
            if hit:
                findings.append("directive %r on %r: %r" % (w, hit, sent[:90]))
                break
            if tick:
                findings.append("directive %r on ticker %r: %r" % (w, tick, sent[:90]))
                break
    return findings


def describes(opening: str) -> bool:
    """Whether a two-word opening is an enumerated noun phrase rather than a command.

    Exposed so a test can assert the exemption list rather than infer it from behaviour, and so
    a reader can see the whole of it in one place.
    """
    return " ".join(_words(opening)[:2]).lower() in DESCRIPTIVE_PHRASES


def lint_text(text: str, where: str) -> List[str]:
    """`order_findings`, with `where` prefixed so a failure names the field it came from."""
    return ["%s: %s" % (where, f) for f in order_findings(text)]


def walk_texts(obj: Any, path: str = "") -> Iterable[Tuple[str, str]]:
    """Every string in a nested structure, with a dotted path. The lint checks EVERYTHING the
    card could render, because a text is not made safe by living under a key nobody expects to
    be displayed."""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk_texts(v, "%s.%s" % (path, k) if path else str(k))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from walk_texts(v, "%s[%d]" % (path, i))


def load_playbooks(version: str = PLAYBOOK_VERSION) -> Dict[str, Any]:
    """The versioned playbook file. NOT editable from the UI, by construction: it is a file on
    disk with a version in its name, and nothing in the hub writes it."""
    with open(os.path.join(ASSETS, "playbooks.%s.json" % version), encoding="utf-8") as fh:
        return json.load(fh)


def load_mock() -> Dict[str, Any]:
    """The 10-16 fixture (§9). A fixture, not a reading: v0 wires to nothing."""
    with open(os.path.join(ASSETS, MOCK_FILE), encoding="utf-8") as fh:
        return json.load(fh)


def lint_playbooks(version: str = PLAYBOOK_VERSION) -> List[str]:
    """Every instruction-shaped text in the playbook file. Empty means clean."""
    out: List[str] = []
    for path, text in walk_texts(load_playbooks(version)):
        out.extend(lint_text(text, path))
    return out


def assert_no_orders(version: str = PLAYBOOK_VERSION) -> None:
    """Raise `PlaybookLintError` if any playbook text reads as an instruction."""
    findings = lint_playbooks(version)
    if findings:
        raise PlaybookLintError(
            "playbook %s contains %d instruction-shaped text(s):\n  %s"
            % (version, len(findings), "\n  ".join(findings)))
