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
