"""Three taxonomies, three fields — TA-123, R-IV.794(b).

THE DEFECT. `unified_positions.strategy_tag` is one column carrying three INDEPENDENT
taxonomies, so each row shows whichever was written last and the other two are gone. That is not
a presentation nuisance: filtering it for the Roth's 20% tactical cap returned SOXS alone at
**8.26%**, against the truth of SOXS + TSLQ at **19.50%**, because TSLQ's `TACTICAL` had been
overwritten by its bucket `B2`. A cap read off that field is a cap read off the last edit, and it
under-reported by more than half.

So `strategy_tag` becomes a DISPLAY STRING with no authority, and the three live beside it:

    classification   STRATEGIC | TACTICAL      <- the hard cap depends on this one
    sleeve_tag       TAIL | CONVEXITY
    bucket           B1 | B2 | B3

NOTHING HERE GUESSES. `split_display_tag` returns a value only where the word names that
taxonomy unambiguously, and reports a REASON otherwise. R-IV.794(b)3 is explicit that ambiguous
rows are listed for TA and not filled in, so the ambiguity has to survive as data rather than be
resolved by whoever wrote the mapping.

MEASURED WHILE BUILDING THIS: `models/strategy_tag.py`, which calls itself "the one author of
the strategy_tag vocabulary", does not recognise `STRATEGIC`, `TACTICAL` or `B3` --
`is_known("STRATEGIC")` is False -- while nine live rows carry the first two. Its declared set is
(CORE, B1, B2, CONVEXITY, TAIL). The vocabularies below are the RULED ones and do not read from
it, because inheriting a list that is two labels behind the book is how this defect started.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

# ── the three ruled vocabularies. Independent: a row may carry all three, or none. ──
STRATEGIC = "STRATEGIC"
TACTICAL = "TACTICAL"
CLASSIFICATIONS: Tuple[str, ...] = (STRATEGIC, TACTICAL)

TAIL = "TAIL"
CONVEXITY = "CONVEXITY"
SLEEVE_TAGS: Tuple[str, ...] = (TAIL, CONVEXITY)

BUCKETS: Tuple[str, ...] = ("B1", "B2", "B3")

FIELDS: Tuple[str, ...] = ("classification", "sleeve_tag", "bucket")
VOCABULARIES: Dict[str, Tuple[str, ...]] = {
    "classification": CLASSIFICATIONS,
    "sleeve_tag": SLEEVE_TAGS,
    "bucket": BUCKETS,
}

# R-IV.797(c)3: legacy CONVEXITY maps to `sleeve_tag` on ANY row. I had withheld it on rows
# written before 2026-09-25, on the chance it had been meant as a classification then. SPINE
# ruled the open-date question belongs to TA-045's scope — whether X4 APPLIES — and not to what
# the tag means. The date constant and the `entry_date` parameter are therefore gone rather than
# accepted-and-ignored: a parameter that no longer affects the answer is a trap for the next
# caller who passes it expecting it to.

# R-IV.797(c)1: CORE IS A LOCATION, NOT A CLASSIFICATION — "the Roth core half, membership in
# the target mix". So legacy CORE is not ambiguous after all; it maps to STRATEGIC. I had it
# listed as unplaceable and SPINE ruled otherwise, applying TA-124's four axes.
LEGACY_CLASSIFICATION: Dict[str, str] = {"CORE": STRATEGIC}

# Still in no ruled vocabulary. HEDGE/MOMENTUM/OTHER were never adjudicated, and choosing for
# them here would be the guess the ruling forbids.
NOT_IN_ANY_VOCABULARY: Tuple[str, ...] = ("HEDGE", "MOMENTUM", "OTHER")

# ── R-IV.797(c)2: the 20% cap does not reach ROBINHOOD ──────────────────────────────────────
# Part 4 v2: that account is "governed by its sleeve ceiling instead". So a ROBINHOOD row's
# classification is NULL BY DESIGN, and the distinction matters enormously: a null that means
# "not applicable here" must not be counted as a gap to be filled, and a null that means "not
# recorded" must not be counted as a decision. Both are null in the column; only the reason
# tells them apart, so the reason is served.
CAP_ACCOUNTS: Tuple[str, ...] = ("FIDELITY_ROTH", "FIDELITY_401A")
NO_CLASSIFICATION_ACCOUNTS: Tuple[str, ...] = ("ROBINHOOD",)
NOT_APPLICABLE_REASON = "not applicable: ROBINHOOD"
NOT_RECORDED_REASON = "not recorded"


def in_cap_scope(account: Any) -> bool:
    """Does the 20% tactical cap reach this account.

    Exact-name identity, never a prefix or a spelling: the parked-money lesson
    ([[scope-must-not-depend-on-case]]) is that scope decided by how a name is written answers
    differently for `FIDELITY_401A` and `fidelity_401a`.
    """
    return (_norm(account) or "") in CAP_ACCOUNTS


# TA-126 / R-IV.804(b). A value with no recorded basis says so IN the field a reader is already
# looking at, rather than appearing as a confident verdict. Fail loud, not silent: a null here
# was indistinguishable from "this row is fine", which is how 11 citations went unnoticed.
NO_BASIS_RECORDED = "NO BASIS RECORDED — do not gate on this value"

# The columns that hold each axis's basis. Only two axes have one: `sleeve_tag` is derived
# wholly from the legacy tag and carries no separate ruling to cite, so inventing a third
# column would be a field with nothing to put in it.
REASON_COLUMNS: Dict[str, str] = {
    "classification": "classification_reason",
    "bucket": "bucket_reason",
}


def classification_reason(account: Any, classification: Any,
                          stored: Any = None) -> Optional[str]:
    """The served basis for this row's classification.

    THREE cases, and conflating any two of them is the defect:
      * classified, with a basis  -> that basis, as stored (the ruling it was written under);
      * classified, with none     -> NO_BASIS_RECORDED, loudly, never None;
      * not classified            -> WHY not: "not applicable: ROBINHOOD" (a decision, since the
                                     cap does not reach that account) or "not recorded" (a gap).

    R-IV.804(b) corrects my own version, which returned None for a classified row. The
    R-IV.797(c) backfill cited a rule on every write, so the audit log has them -- but the
    payload served null, and a citation only an auditor can reach is not served provenance.
    """
    if _norm(classification) in CLASSIFICATIONS:
        text = (str(stored).strip() if stored is not None else "")
        return text or NO_BASIS_RECORDED
    if (_norm(account) or "") in NO_CLASSIFICATION_ACCOUNTS:
        return NOT_APPLICABLE_REASON
    return NOT_RECORDED_REASON


def bucket_reason(bucket: Any, stored: Any = None) -> Optional[str]:
    """The served basis for this row's bucket — R-IV.804(c), fail-loud.

    FOUR cases, and R-IV.807(c) added the third:
      * bucketed, with a basis   -> that basis, as stored;
      * bucketed, with none      -> NO_BASIS_RECORDED, loudly;
      * NOT bucketed, with a recorded reason -> that reason: a DELIBERATE exclusion. TA-127
        removes PDBC's and WEAT's inherited B1 and leaves IWM unbucketed, each for a stated
        reason, and "deliberately unbucketed" must not read the same as "nobody looked";
      * not bucketed, no reason  -> "not recorded", a gap.

    I HAD WRITTEN THE THIRD CASE OUT. R-IV.804(c) said an absent bucket is "always a gap and
    never a decision" -- true until a ruling deliberately unbucketed three rows, which is the
    classification pattern ("not applicable: ROBINHOOD" is a decision) arriving one axis over.

    THE COST, NAMED: a reason that outlives its value now reads as deliberate. So a write that
    CLEARS a bucket must set or clear its reason in the SAME request, or a stale citation will
    describe an exclusion nobody decided. `bucket_coverage` is unaffected either way -- it
    counts only bucketed rows.
    """
    text = (str(stored).strip() if stored is not None else "")
    if _norm(bucket) in BUCKETS:
        return text or NO_BASIS_RECORDED
    return text or NOT_RECORDED_REASON


def has_basis(row: Mapping[str, Any], field: str) -> bool:
    """Does this row's value for `field` carry a recorded basis.

    False when the value itself is absent: there is nothing to have a basis FOR, and counting
    those as "missing a basis" would bury the real gaps among them.
    """
    if field not in REASON_COLUMNS:
        return False
    if _norm(row.get(field)) not in VOCABULARIES[field]:
        return False
    return bool((str(row.get(REASON_COLUMNS[field]) or "")).strip())


def bucket_coverage(rows: Any) -> dict:
    """R-IV.804(c): the bucket mirror of `cap_enforceable`, and it reports the same way.

    `safe_to_gate` is False until EVERY bucketed row carries a basis. It is deliberately not
    true-by-default: today's buckets were inherited from legacy display strings, and a gate
    computed from them would be a gate computed from whatever was typed last -- the TA-123
    defect, one axis over.
    """
    bucketed = [r for r in rows if _norm(r.get("bucket")) in BUCKETS]
    with_basis = [r for r in bucketed if has_basis(r, "bucket")]
    return {
        "rows_bucketed": len(bucketed),
        "rows_with_basis": len(with_basis),
        "rows_without_basis": len(bucketed) - len(with_basis),
        "position_ids_without_basis": [r.get("position_id") for r in bucketed
                                       if not has_basis(r, "bucket")],
        "safe_to_gate": bool(bucketed) and len(with_basis) == len(bucketed),
        "basis": ("bucket is NOT safe to gate on until every bucketed row carries a basis; "
                  "today's values were inherited from legacy display strings. TA's deliberate "
                  "32-row table (R-IV.803(b)) supplies them."),
    }


def _norm(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip().upper()
    return s or None


def split_display_tag(tag: Any) -> Tuple[Dict[str, Optional[str]], Optional[str]]:
    """`({classification, sleeve_tag, bucket}, reason)` for one display tag.

    Every field it cannot establish stays None, and `reason` says why. `reason` is None only
    when the tag mapped cleanly onto exactly one taxonomy.

    A tag names at most ONE of the three, which is the whole defect: the other two were never
    recorded anywhere. So a clean mapping still leaves two fields unknown, and that is correct —
    unknown is not a value to be filled in later by inference.
    """
    out: Dict[str, Optional[str]] = {f: None for f in FIELDS}
    t = _norm(tag)
    if t is None:
        return out, "no strategy_tag: nothing is recorded for any of the three"
    if t in CLASSIFICATIONS:
        out["classification"] = t
        return out, None
    if t in BUCKETS:
        out["bucket"] = t
        return out, None
    if t == TAIL:
        out["sleeve_tag"] = TAIL
        return out, None
    if t == CONVEXITY:
        # R-IV.797(c)3 settles what I had listed as ambiguous: legacy CONVEXITY maps to
        # sleeve_tag, on any row. The open-date question is real but it belongs to TA-045's
        # scope for whether X4 APPLIES, not to what the tag means — so the date no longer
        # withholds the mapping.
        out["sleeve_tag"] = CONVEXITY
        return out, None
    if t in LEGACY_CLASSIFICATION:
        # CORE is a location, not a classification (R-IV.797(c)1).
        out["classification"] = LEGACY_CLASSIFICATION[t]
        return out, None
    if t in NOT_IN_ANY_VOCABULARY:
        return out, "%s belongs to no ruled vocabulary (not STRATEGIC/TACTICAL)" % t
    return out, "unrecognised value %r" % t


def is_valid(field: str, value: Any) -> bool:
    """True when `value` is in `field`'s vocabulary. None is never valid — it is absence."""
    v = _norm(value)
    return v is not None and v in VOCABULARIES.get(field, ())


def cap_enforceable(rows: Any) -> bool:
    """Can the 20% tactical cap be computed for this selection — R-IV.797(c)2.

    EVERY Fidelity row must be classified, AND ONLY FIDELITY ROWS COUNT. My first version
    required every row in the book, which would have held the cap unenforceable forever: the 21
    ROBINHOOD rows are null BY DESIGN, since Part 4 v2 governs that account by its sleeve
    ceiling instead. A condition no reachable state can satisfy reports "cannot enforce" for
    good, which is indistinguishable from the engine being broken.

    False on an empty Fidelity selection: nothing to enforce against is not the same as a
    satisfied cap, and the safe reading is the one that does not claim compliance.
    """
    fidelity = [r for r in rows if in_cap_scope(r.get("account"))]
    if not fidelity:
        return False
    return all(cap_eligible(r) for r in fidelity)


def cap_eligible(row: Mapping[str, Any]) -> bool:
    """Can the 20% tactical cap be applied to this row at all.

    False when `classification` is absent, and the CALLER must treat that as "cannot enforce",
    never as "not tactical". Counting an unclassified row as out-of-scope is what produced
    8.26% against a true 19.50%.
    """
    return _norm(row.get("classification")) in CLASSIFICATIONS


def column_ddl() -> Tuple[str, ...]:
    """The ADD COLUMN statements, generated from the vocabularies above.

    Nullable and with no CHECK, matching `strategy_tag`'s precedent: NULL here means "not
    recorded", and until the backfill lands it means "not yet migrated" — which is why the
    payload carries `classification_backfilled` rather than letting a reader infer from a null.
    """
    return tuple(
        "ALTER TABLE unified_positions ADD COLUMN IF NOT EXISTS %s TEXT" % f for f in FIELDS
    )


def column_comments() -> Dict[str, str]:
    """Generated, never retyped — a vocabulary with two authors has no author."""
    return {
        f: "TA-123/R-IV.794(b): one of %s, or NULL for not recorded. Independent of "
           "strategy_tag, which is a display string only and may not be used for any cap, "
           "gate or filter." % " | ".join(VOCABULARIES[f])
        for f in FIELDS
    }
