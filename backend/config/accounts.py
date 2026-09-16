"""T2 — THE account vocabulary. One module, read by every surface.

R-IV.394. The census at P0.1 of the ledger brief found FIVE surfaces disagreeing on
the third account's NAME, not merely its casing: `Fidelity 401A`/`Fidelity 403B` in
the seed, `BROKERAGE_LINK_401K` in the MCP map, `FIDELITY_401A` in two others,
`brokerage_link_401k` in a fifth.

THE PRINCIPAL FACT (R-IV.284(a)): Pandora tracks EXACTLY TWO accounts.

    FIDELITY_ROTH   the Roth 401k BrokerageLink -- the account actually traded
    ROBINHOOD       high-risk: options primarily, with crypto/ETFs/stocks at times

Everything else is PARKED MUTUAL-FUND MONEY, untraded, OUT OF SCOPE.

WHY OUT_OF_SCOPE IS A CLASS AND NOT A STALENESS FLAG -- this is the whole design,
and R-IV.284 corrected an earlier ruling specifically to get it right:

    BROKERAGE_LINK_401K is NOT a stale vintage of the traded account. It is the
    PARKED SUM under a misleading name -- $11,642.35, exactly 401A + 403B. A
    DIFFERENT POT, not an older reading of the same pot.

    Same action, different reason, and the REASON is what this module encodes. A
    staleness-based exclusion would be "refreshed" by a diligent future maintainer
    who found an old row and updated it. A SCOPE-based one cannot be, because there
    is nothing to refresh it to.

RETENTION: out-of-scope rows are preserved -- never deleted, never summed, never
charted with the trading accounts.
"""

from __future__ import annotations

from typing import Optional

# ── The two canonical accounts ──────────────────────────────────────────
FIDELITY_ROTH = "FIDELITY_ROTH"
ROBINHOOD = "ROBINHOOD"
CANONICAL_ACCOUNTS = frozenset({FIDELITY_ROTH, ROBINHOOD})

# ── Aliases. Free text that MEANS a canonical account. ──────────────────
# Keys are compared case-insensitively with underscores and spaces equivalent.
_ALIASES = {
    "fidelity": FIDELITY_ROTH,
    "fidelity roth": FIDELITY_ROTH,
    "fidelity_roth": FIDELITY_ROTH,
    "robinhood": ROBINHOOD,
    "rh": ROBINHOOD,
    "robinhood - individual": ROBINHOOD,
    "robinhood individual": ROBINHOOD,
}

# ── OUT OF SCOPE. NOT aliases of anything. ─────────────────────────────
# R-IV.284(c). Parked money and a retired broker. Rows carrying these names are
# tagged and preserved; they are never summed with the trading accounts and never
# resolved to one.
OUT_OF_SCOPE = "OUT_OF_SCOPE"
_OUT_OF_SCOPE_LABELS = {
    "fidelity 401a", "fidelity_401a", "fidelity401a",
    "fidelity 403b", "fidelity_403b", "fidelity403b",
    "brokerage_link_401k", "brokerage link 401k",
    "interactive brokers", "interactive_brokers", "ibkr",
}

UNKNOWN = "UNKNOWN"


def _key(name: Optional[str]) -> str:
    """Case, underscores and surrounding space are settled HERE, once, at the
    boundary -- not defended at each call site (T2)."""
    return (name or "").strip().lower().replace("_", " ")


def normalize_account(name: Optional[str]) -> str:
    """Any account string -> a canonical name, OUT_OF_SCOPE, or UNKNOWN.

    NEVER raises and never guesses: a name this module does not know returns
    UNKNOWN rather than being resolved to the nearest thing. A wrong resolution on
    a money surface is worse than an unresolved one, because it is spendable.
    """
    k = _key(name)
    if not k:
        return UNKNOWN
    if k in _OUT_OF_SCOPE_LABELS:
        return OUT_OF_SCOPE
    hit = _ALIASES.get(k)
    if hit:
        return hit
    up = k.replace(" ", "_").upper()
    if up in CANONICAL_ACCOUNTS:
        return up
    return UNKNOWN


def is_in_scope(name: Optional[str]) -> bool:
    """True only for the two traded accounts.

    UNKNOWN is NOT in scope. An account nobody has classified must not be summed
    into a tradeable total on the strength of not having been recognised -- that
    is the absent-vs-real collapse, on money.
    """
    return normalize_account(name) in CANONICAL_ACCOUNTS


def accounts_match(account_filter: Optional[str], row_name: Optional[str]) -> bool:
    """Does `row_name` satisfy a request for `account_filter`?

    REPLACES THE `startswith` MATCH (`unified_positions._match_account_balance`),
    registered at P0.1 as its own defect: the legacy `FIDELITY` filter normalised
    to the prefix `fidelity` and matched `Fidelity Roth`, `Fidelity 401A` AND
    `Fidelity 403B` alike -- so a request for the traded account silently summed
    two parked ones with it.

    A PREFIX IS NOT A CLASSIFICATION. It answers "does this name begin with those
    letters", which is a question about spelling, on a surface where the question
    is about ownership of money. Membership is looked up, never inferred from the
    shape of a string.
    """
    want = normalize_account(account_filter)
    got = normalize_account(row_name)
    if want == UNKNOWN or got == UNKNOWN:
        return False
    return want == got
