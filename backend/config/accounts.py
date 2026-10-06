"""T2 — THE account vocabulary. One module, read by every surface.

R-IV.394. The census at P0.1 of the ledger brief found FIVE surfaces disagreeing on
the third account's NAME, not merely its casing: `Fidelity 401A`/`Fidelity 403B` in
the seed, `BROKERAGE_LINK_401K` in the MCP map, `FIDELITY_401A` in two others,
`brokerage_link_401k` in a fifth.

AMENDED R-IV.632(c): Pandora tracks EXACTLY THREE accounts.

    FIDELITY_ROTH   the Roth 401k BrokerageLink -- traded
    ROBINHOOD       high-risk: options primarily, with crypto/ETFs/stocks at times
    FIDELITY_401A   the 401(a), CONVERTED to a second BrokerageLink and now traded

THE PREMISE CHANGED; THE MODULE WAS NOT WRONG WHEN IT WAS WRITTEN. R-IV.284(a) said two,
and `fidelity_401a` sat in _OUT_OF_SCOPE_LABELS below because it named PARKED MUTUAL-FUND
MONEY. The principal has since converted that 401(a) into a second BrokerageLink account
and started trading in it, so the classification is now factually false rather than merely
stale -- and this is precisely the distinction this module's own design note draws. A
scope class cannot be "refreshed"; it has to be re-decided, and a ruling has re-decided it.

IT WAS ALSO ALREADY CONTRADICTORY. `models/accounts.py` has had FIDELITY_401A in its
CANONICAL_ACCOUNTS since R-IV.445(a), so the account was a legal WRITE target for positions
while every money aggregate here classified it OUT_OF_SCOPE: writable and unsummable at the
same time. The canonical set is now IMPORTED from that module rather than retyped, so the
two cannot disagree again.

STILL OUT OF SCOPE, and for the unchanged reason: the 403(b), `BROKERAGE_LINK_401K` (the
parked SUM under a misleading name, now additionally wrong because the 401(a) half of it has
been converted away -- see DEF-ACCOUNT-LABEL-DUP, which is not this ruling's to settle), and
the retired IBKR.

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

# ── The canonical accounts — ONE AUTHOR, imported, never retyped ────────
# models/accounts.py is the registry (R-IV.445(a)); this module adds the scope CLASS and a
# never-raising normaliser on top of it. Retyping the set here is what let the two disagree
# about FIDELITY_401A for weeks.
from models.accounts import CANONICAL_ACCOUNTS as _CANONICAL_TUPLE
from models.accounts import DISPLAY_NAMES, FIDELITY_401A, FIDELITY_ROTH, ROBINHOOD

CANONICAL_ACCOUNTS = frozenset(_CANONICAL_TUPLE)

# ── Aliases. Free text that MEANS a canonical account. ──────────────────
# Keys are compared case-insensitively with underscores and spaces equivalent.
_ALIASES = {
    # R-IV.660(c)1: `"fidelity": FIDELITY_ROTH` STOOD HERE and is gone. `models/accounts.py`
    # has refused a bare `FIDELITY` since R-IV.638(b)3 -- with a 400 that names both keys and
    # both account numbers -- while this module went on resolving the same string to the Roth.
    # One question, two registries, opposite answers: whichever one a surface happened to ask
    # decided whether the principal's filter was refused or silently narrowed to one of two
    # Fidelity accounts. The refusal is the correct answer and it lives in the registry, so
    # this module stops answering. The specific spellings below are unaffected.
    "fidelity roth": FIDELITY_ROTH,
    "fidelity_roth": FIDELITY_ROTH,
    "robinhood": ROBINHOOD,
    "rh": ROBINHOOD,
    "robinhood - individual": ROBINHOOD,
    "robinhood individual": ROBINHOOD,
}

# ── ABACUS'S CATCH — R-IV.638(b)2 ───────────────────────────────────────────────────────────
# `_key()` lowercases and turns underscores into spaces, so the PARKED mutual-fund history
# `'Fidelity 401A'` (90 snapshot rows, 2026-03-20 to 2026-07-23, up to $11,075.62) and the
# TRADEABLE `'FIDELITY_401A'` collapse to the identical key "fidelity 401a".
#
# An earlier pass of R-IV.632(c) aliased that key to FIDELITY_401A. It would have brought the
# parked history into scope along with the account -- the tradeable 401(a) reading $11,075.62
# of money that is not in it. NO NAME-BASED RULE CAN SEPARATE THEM, which is exactly why
# R-IV.638(b)1 makes the ACCOUNT NUMBER the identity.
#
# R-IV.660(c)1 SETTLES IT, AND THE PREVIOUS ANSWER WAS THE WRONG KIND OF RULE.
#
# The remedy above was to match the canonical key EXACTLY, before normalisation, and leave
# every other spelling out of scope. That made the scope of an account depend on its
# CAPITALISATION: `is_in_scope("FIDELITY_401A")` was True and `is_in_scope("fidelity_401a")`
# was False, for the same account. Case is itself a name-based rule -- the very thing the
# comment above correctly says cannot separate these two pots -- and it is the most fragile
# one available, because every boundary that folds case (a URL, a form, a JSON key, a lower()
# on the way to a display label) silently flips the answer.
#
# It flipped one. `hub_get_portfolio_balances` lowercases the name for its own payload key and
# then asked this module: the traded 401(a) came back OUT OF SCOPE, was dropped from
# `total_balance`, and the tool reported 12,881.24 across "2 of 3 accounts" while naming the
# third as excluded parked money. Measured 2026-10-06.
#
# WHAT ACTUALLY SEPARATES THEM IS NOT A NAME AT ALL, and it is already in place: the parked
# history lives in `balance_snapshots` (90 rows as 'Fidelity 401A'), and the day-P&L reader
# selects `account_name = ANY(<the exact names in account_balances>) AND basis = 'derived'`.
# `account_balances` holds only the canonical `FIDELITY_401A`, so a parked snapshot row cannot
# match that filter whatever this module says about its spelling. Identity and an exact
# membership test do the work; the casing trick was never what held the parked money out.
#
# So the 401(a) spellings come OUT of the out-of-scope set below. The 403(b) and
# BROKERAGE_LINK_401K stay: that money is still parked, and it is not what was converted.
#
# (`_PARKED_FIDELITY_KEYS` stood here holding the same four strings and was read by nothing in
# the repo -- a second scope list that no caller consulted. Removed rather than amended: an
# unread vocabulary cannot be trusted to still mean what it says.)

# ── OUT OF SCOPE. NOT aliases of anything. ─────────────────────────────
# R-IV.284(c). Parked money and a retired broker. Rows carrying these names are
# tagged and preserved; they are never summed with the trading accounts and never
# resolved to one.
OUT_OF_SCOPE = "OUT_OF_SCOPE"
# R-IV.660(c)1: the 401(a) spellings are GONE from this set -- see the long note above. Every
# casing of the traded account now resolves to FIDELITY_401A, and the parked history is held
# out by the exact-name filter on `account_balances`, which is what was holding it out anyway.
_OUT_OF_SCOPE_LABELS = {
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
    # EXACT canonical key first, as a fast path. It no longer carries any distinction:
    # R-IV.660(c)1 removed the 401(a) spellings from the out-of-scope set, so this branch and
    # the normalised one below now agree on every casing of every canonical account. It is kept
    # only because a caller passing the canonical key should not pay for normalisation -- NOT,
    # as it was, because the answer differs.
    if name is not None and str(name).strip() in CANONICAL_ACCOUNTS:
        return str(name).strip()

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
    """True only for the THREE traded accounts, in any casing (R-IV.660(c)1).

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
