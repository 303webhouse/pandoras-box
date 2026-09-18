"""The account vocabulary, in one place, with one spelling each (R-IV.445(a)).

An account label is not decoration: it decides which invariants apply to a row (the ETF-only
rule is account-scoped), which balance a position sizes against, and which export could ever
reconcile it. A row under a label nothing else uses is a row no rule reaches.

WHY THIS MODULE EXISTS RATHER THAN A CONSTANT NEXT TO EACH WRITE. The canonical set already
existed — inside one endpoint, checked inline. Every other write path took whatever string
arrived, so eleven days after the remap the manual-entry path was still minting rows under the
retired `FIDELITY` alias. A vocabulary enforced at one door is a vocabulary with one door.

ALIASES NORMALISE; UNKNOWNS ARE REFUSED. `FIDELITY` has meant FIDELITY_ROTH since the remap, so
it is accepted and rewritten rather than rejected — a caller that has been right for months
should not start failing. Anything outside the vocabulary is refused with the list, because the
alternative is a silent new label that reads like a real account forever afterwards.
"""

from __future__ import annotations

from typing import Iterable, Optional

from fastapi import HTTPException

ROBINHOOD = "ROBINHOOD"
FIDELITY_ROTH = "FIDELITY_ROTH"
FIDELITY_401A = "FIDELITY_401A"

# The only values a write may store.
CANONICAL_ACCOUNTS = (ROBINHOOD, FIDELITY_ROTH, FIDELITY_401A)

# Spellings that have meant a canonical account and are normalised on the way in. `FIDELITY`
# resolves to FIDELITY_ROTH: that is what the alias has meant since the remap, and it is the
# label the five rows written under it on 2026-09-16 belong to.
ALIASES = {
    "FIDELITY": FIDELITY_ROTH,
    "FIDELITY - INDIVIDUAL": FIDELITY_ROTH,
    "FID": FIDELITY_ROTH,
    "FIDELITY ROTH": FIDELITY_ROTH,
    "FIDELITY 401A": FIDELITY_401A,
    "ROBINHOOD ": ROBINHOOD,
}

# Deliberately NOT canonical and NOT an alias. The label is under a live factual dispute about
# which plan it names (DEF-ACCOUNT-LABEL-DUP) and is descoped from tradeable aggregates, so
# resolving it here would quietly take a side in an open question.
DISPUTED = ("BROKERAGE_LINK_401K",)


def normalize_account(value: Optional[str]) -> Optional[str]:
    """The canonical spelling of `value`, or None when it has none. Never raises."""
    if value is None:
        return None
    key = " ".join(str(value).strip().upper().split())
    if key in CANONICAL_ACCOUNTS:
        return key
    return ALIASES.get(key)


def canonical_account(value: Optional[str], *, field: str = "account") -> str:
    """The canonical spelling, or a 400 naming the vocabulary and what arrived.

    The refusal quotes the received value because the whole failure mode here is a label that
    looked plausible: a caller told only "invalid account" will send the same string again.
    """
    resolved = normalize_account(value)
    if resolved:
        return resolved
    disputed = " ".join(str(value or "").strip().upper().split()) in DISPUTED
    detail = (f"{field} must be one of {list(CANONICAL_ACCOUNTS)} (case-insensitive; "
              f"'FIDELITY' is accepted as {FIDELITY_ROTH}); got '{value}'")
    if disputed:
        detail += (" — that label is under an unresolved dispute about which plan it names "
                   "and is not a write target")
    raise HTTPException(status_code=400, detail=detail)


def non_canonical(values: Iterable[Optional[str]]) -> list:
    """Every value in `values` that no write should have stored. For reading a book."""
    return sorted({v for v in values if v is not None and normalize_account(v) != v})


# ── THE RECONCILIATION RULE (R-IV.449(b), AMENDED at R-IV.450(a)) ───────────────────────────
#
# A DUPLICATE AND AN ABSENCE PRESENT IDENTICALLY, AND THE REMEDIES ARE OPPOSITE. A row the
# read cannot see and a row that does not exist return the same empty result; one wants a
# write and the other wants nothing, so a scope that can miss a row is a scope that can order
# the wrong remedy.
#
# A RECONCILIATION OVER A DATE WINDOW READS EVERY ROW TOUCHING THAT WINDOW, IN ANY STATUS,
# UNDER THE CANONICAL LABEL PLUS EVERY ALIAS. All three halves, because each one alone has
# already produced a wrong answer:
#
#   the LABEL half  — an account-scoped read cannot see rows filed under another spelling, so
#                     a reconciliation asking only for the canonical one reports ABSENCE where
#                     there is DUPLICATION, and then writes the row it believes is missing;
#   the STATUS half — `status = 'OPEN'` cannot see a row that was opened and closed inside the
#                     window, which is the whole shape of a same-day round trip;
#   the WINDOW half — a row is IN the window if its life overlaps it, not if its entry date
#                     falls inside it; a position opened before and closed during is precisely
#                     the case a naive entry-date filter drops.
#
# CORRECTION, R-IV.450(a): this module previously said the BITX duplicate was caused by the
# retired alias hiding the row. That was WRONG and is recorded rather than quietly edited --
# the inventory matched `LIKE 'FIDELITY%'`, which matched both spellings. The proximate cause
# was the STATUS scope: the row had been opened and closed the same day, so an OPEN-scoped read
# could not see it, the trade was re-created from the confirmations, and the book carried one
# trade's money twice. The label half of the rule stands on its own reasoning; it was simply
# not what happened here.
#
# `scope_for` returns every spelling; `reconciliation_scope` returns the whole clause. They are
# the easy path on purpose: a rule that must be remembered is a rule that gets forgotten on the
# day it matters, which is the day a reconciliation is being written under time pressure.
def scope_for(account: Optional[str]) -> list:
    """Every spelling an inventory of `account` must read, canonical first.

    Raises on an unknown label rather than returning a one-element list, because silently
    scoping to exactly what was typed is the failure this exists to prevent.
    """
    canonical = canonical_account(account)
    aliases = sorted(spelling for spelling, target in ALIASES.items() if target == canonical)
    return [canonical] + aliases


def scope_sql(account: Optional[str], column: str = "account") -> tuple:
    """(clause, params) selecting every spelling of `account`, for a reconciliation read."""
    spellings = scope_for(account)
    return f"UPPER({column}) = ANY($1::text[])", [[s.upper() for s in spellings]]


def reconciliation_scope(account: Optional[str], start, end, *, table: str = "p") -> tuple:
    """(clause, params) for every row of `account` whose life TOUCHES [start, end].

    All three halves of the rule in one call: every spelling, every status, and overlap rather
    than containment. A reconciliation that builds its own WHERE clause has to remember three
    things; this one has to remember none.

    Deliberately takes no status argument. There is no correct reconciliation scope that
    filters by status -- a row opened and closed inside the window is exactly the row a status
    filter hides, and hiding it is what turns a duplicate into a reported absence.
    """
    spellings = [s.upper() for s in scope_for(account)]
    clause = (f"UPPER({table}.account) = ANY($1::text[]) "
              f"AND ({table}.entry_date IS NULL OR {table}.entry_date <= $3) "
              f"AND ({table}.exit_date IS NULL OR {table}.exit_date >= $2)")
    return clause, [spellings, start, end]
