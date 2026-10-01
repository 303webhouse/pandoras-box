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

# ── The display name, served rather than inferred (R-IV.632(c), R-IV.633) ───────────────────
#
# ABACUS must label, sort and filter by account WITHOUT inferring, so the name travels with
# every row instead of being reconstructed from the key at each surface. A key is not a label:
# `FIDELITY_401A.replace("_"," ").title()` gives "Fidelity 401A", which is not what the account
# is called, and every surface would get it subtly differently.
#
# FIDELITY_401A's name is PROVISIONAL — R-IV.632(c)1 says Trade Analysis may rename it. It is
# one string in one dict, so a rename is one edit and no surface disagrees in the meantime.
DISPLAY_NAMES = {
    ROBINHOOD: "Robinhood",
    FIDELITY_ROTH: "Fidelity Roth",
    FIDELITY_401A: "Fidelity 401(a)",
}

# Provisional names, declared so a rename is a known operation rather than a discovery.
PROVISIONAL_NAMES = (FIDELITY_401A,)

# ── IDENTITY BY NUMBER — R-IV.638(b)1 ───────────────────────────────────────────────────────
#
# A NAME CANNOT TELL THE TWO FIDELITY ACCOUNTS APART, AND IT NEVER COULD.
# Both are Fidelity BrokerageLink accounts. "Fidelity", "BrokerageLink", "401k", "Brokerage"
# describe both of them equally, and the 09-22 rule that every Fidelity name means the Roth
# was only ever true while there was one. It is retired.
#
# It is worse than ambiguous. The scope normaliser lowercases and turns underscores into
# spaces, so `'Fidelity 401A'` -- the PARKED mutual-fund history, 90 snapshot rows up to
# $11,075.62 -- and `'FIDELITY_401A'`, the tradeable account, collapse to the SAME key. No
# name-based rule can separate them, which is ABACUS's catch (R-IV.638(b)2): bringing the
# 401(a) into scope by NAME would have pulled the parked history in with it.
#
# So the account number is the identity. POSITIONS read both from the principal's files.
ACCOUNT_NUMBERS = {
    FIDELITY_ROTH: "652303158",
    FIDELITY_401A: "653641836",
}
ACCOUNT_BY_NUMBER = {num: key for key, num in ACCOUNT_NUMBERS.items()}

# Names that USED to route to FIDELITY_ROTH and no longer route anywhere. Kept as a declared
# set so the refusal can name them, rather than a caller guessing why its string stopped
# working. Rows already stored under these spellings are LEFT ALONE (R-IV.638(b)3): this
# governs resolution for a new write, not a rewrite of history.
# ── Spellings a RECONCILIATION READ must still look under ───────────────────────────────────
# Separate from ALIASES on purpose. ALIASES feeds `normalize_account`, which is the WRITE path,
# and (b)3 closes that to Fidelity names. But the reconciliation doctrine below is explicit
# that an account-scoped READ missing a row reports ABSENCE where there is DUPLICATION, and
# then writes the row it believes is missing. Closing the write path must not blind the read.
#
# FIDELITY_401A HAS NONE, DELIBERATELY. It is new, so no row was ever written under a historical
# spelling FOR it -- and `'Fidelity 401A'` names the PARKED mutual-fund money (90 snapshot rows
# to 2026-07-23), which is a different pot. Giving it that spelling is exactly ABACUS's catch.
HISTORICAL_SPELLINGS = {
    FIDELITY_ROTH: ("FIDELITY", "FIDELITY - INDIVIDUAL", "FID", "FIDELITY ROTH"),
    ROBINHOOD: ("ROBINHOOD ",),
    FIDELITY_401A: (),
}

RETIRED_FIDELITY_NAMES = frozenset({
    "FIDELITY", "FIDELITY - INDIVIDUAL", "FID", "FIDELITY ROTH", "FIDELITY 401A",
    "BROKERAGELINK", "BROKERAGE LINK", "BROKERAGE", "401K", "403B",
    "FIDELITY BROKERAGELINK", "FIDELITY 401K", "FIDELITY 403B",
})


def describe_accounts() -> str:
    """One sentence naming every account a committee tool may ask for — R-IV.638(b)4.

    GENERATED, because both MCP tools had it typed as prose: they offered a fixed list and
    described "401k BrokerageLink", so the committee could not ask for the new account at all
    while it COULD reach the retired parked snapshot under a name that now sounds like the
    traded one. A description is a vocabulary surface like any other.
    """
    parts = []
    for key in CANONICAL_ACCOUNTS:
        name = DISPLAY_NAMES[key]
        num = ACCOUNT_NUMBERS.get(key)
        parts.append(f"{name} ({key}{', #' + num if num else ''})")
    return ", ".join(parts)


def account_choices() -> list:
    """The account values a tool may accept, lowercase, canonical only.

    The retired snapshot is NOT here: `brokerage_link_401k` is the merged parked
    401(a)+403(b) under a disputed label, and offering it beside the traded accounts is how a
    committee member sizes off $11,642.35 that is in neither of them (R-IV.638(b)2/4).
    """
    return [k.lower() for k in CANONICAL_ACCOUNTS]


def account_for_number(number) -> Optional[str]:
    """The canonical key for an account NUMBER, or None if it is not one we track.

    Digits only, so '653641836', 'X653641836' and '...1836' do not accidentally agree: a
    partial match on an account number is how money lands in the wrong account.
    """
    if number is None:
        return None
    digits = "".join(ch for ch in str(number) if ch.isdigit())
    return ACCOUNT_BY_NUMBER.get(digits)


def is_fidelity_name(value: Optional[str]) -> bool:
    """True when `value` is a Fidelity-ish NAME that can no longer resolve on its own."""
    if value is None:
        return False
    key = " ".join(str(value).strip().upper().split())
    if key in RETIRED_FIDELITY_NAMES:
        return True
    return "FIDELITY" in key or "BROKERAGE" in key

# Spellings that have meant a canonical account and are normalised on the way in. `FIDELITY`
# resolves to FIDELITY_ROTH: that is what the alias has meant since the remap, and it is the
# label the five rows written under it on 2026-09-16 belong to.
# R-IV.638(b)3: THE FIDELITY NAME ALIASES ARE GONE. Every one of them resolved a name to an
# account, and with two Fidelity accounts a name is not an identity. `RETIRED_FIDELITY_NAMES`
# below records them so a refusal can say what happened. Robinhood keeps its alias: there is
# one Robinhood account and no number is needed to tell it from another.
ALIASES = {
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
    # An ACCOUNT NUMBER is the identity (R-IV.638(b)1), so it resolves on its own -- the
    # refusal below tells a caller to send one, and it would be a poor instruction if the
    # number were then rejected.
    by_number = account_for_number(key)
    if by_number:
        return by_number
    return ALIASES.get(key)


def canonical_account(value: Optional[str], *, field: str = "account") -> str:
    """The canonical spelling, or a 400 naming the vocabulary and what arrived.

    The refusal quotes the received value because the whole failure mode here is a label that
    looked plausible: a caller told only "invalid account" will send the same string again.
    """
    resolved = normalize_account(value)
    if resolved:
        return resolved

    # R-IV.638(b)3: a Fidelity NAME is refused with its reason, never defaulted to the Roth.
    # Defaulting is what the 09-22 rule did, and it was right while there was one Fidelity
    # account. There are two, and a silent default would file the new account's money in the
    # old one -- the single worst outcome available here, and an invisible one.
    bare = " ".join(str(value or "").strip().upper().split())
    if bare in DISPUTED:
        # Checked BEFORE the Fidelity-name branch: this label has its own, more specific
        # reason, and it is also the retired June snapshot ($11,642.35, 2026-06-09) that
        # must never be reachable as either tradeable account (R-IV.638(b)2).
        raise HTTPException(
            status_code=400,
            detail=(f"{field}: '{value}' is the RETIRED merged snapshot of the parked "
                    f"401(a) + 403(b), under a label disputed as to which plan it names "
                    f"(DEF-ACCOUNT-LABEL-DUP). It is not a write target, and it is not the "
                    f"traded 401(a): that is {FIDELITY_401A} "
                    f"({ACCOUNT_NUMBERS[FIDELITY_401A]})."))

    if is_fidelity_name(value):
        pairs = ", ".join(f"{k} ({ACCOUNT_NUMBERS[k]})" for k in ACCOUNT_NUMBERS)
        raise HTTPException(
            status_code=400,
            detail=(f"{field}: '{value}' names Fidelity without saying WHICH Fidelity "
                    f"account, and there are now two: {pairs}. A name cannot tell them "
                    f"apart -- both are BrokerageLink accounts -- so this is refused rather "
                    f"than defaulted to the Roth, which is what it used to do (retired "
                    f"R-IV.638(b)3). Send the account number, or the key itself. For a "
                    f"combined view, ask for both keys explicitly."))

    disputed = " ".join(str(value or "").strip().upper().split()) in DISPUTED
    detail = (f"{field} must be one of {list(CANONICAL_ACCOUNTS)} (case-insensitive); "
              f"got '{value}'")
    if disputed:
        detail += (" — that label is under an unresolved dispute about which plan it names "
                   "and is not a write target")
    raise HTTPException(status_code=400, detail=detail)


def display_name(value: Optional[str]) -> Optional[str]:
    """The account's human name, or None when `value` is not a canonical account.

    None rather than the raw string: a surface that prints whatever arrived would show
    `BROKERAGE_LINK_401K` to the principal as though it were a name, and that label is
    under dispute about which plan it even denotes.
    """
    resolved = normalize_account(value)
    return DISPLAY_NAMES.get(resolved) if resolved else None


def account_envelope(value: Optional[str]) -> dict:
    """`{"account": <key>, "account_display": <name>}` — what every row carries.

    One shape, so a consumer never has to ask which of the two it was given. Both keys are
    present even when the row has no account, because a missing key and a null read
    differently in JSON and only one of them is honest about an unlabelled row.
    """
    resolved = normalize_account(value)
    return {"account": resolved, "account_display": DISPLAY_NAMES.get(resolved) if resolved else None}


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
    # HISTORICAL_SPELLINGS, not ALIASES: the write path no longer resolves Fidelity names
    # (R-IV.638(b)3), and a read that followed it would stop seeing rows filed under the old
    # vocabulary -- the label half of the rule below, reintroduced by the fix to a different
    # half. Measured before shipping: scope_for(FIDELITY_ROTH) had silently narrowed to one
    # spelling.
    spellings = sorted(set(HISTORICAL_SPELLINGS.get(canonical, ()))
                       | {sp for sp, t in ALIASES.items() if t == canonical})
    return [canonical] + [sp for sp in spellings if sp != canonical]


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

    THE NULL-PREDICATE RULE (R-IV.454(b)). A date predicate on a NULLABLE column silently
    excludes every NULL: `exit_date >= X` means "closed on or after X AND has a recorded close
    date", never the first alone. Both date predicates here carry their `IS NULL OR` branch, so
    a terminal row with no exit date -- every undated expiry, every status-only close -- is IN
    the scope rather than silently out of it. Such a row cannot be placed inside the window, so
    it appears in every window it could belong to; that is the safe direction, because a row
    shown twice is visible and a row shown never is the false absence this rule exists to stop.

    THIRD SCOPE INSTANCE, recorded because the count is the argument: the label scope, the
    status scope, and now the NULL predicate each produced a false absence, and two of the
    three produced a write.
    """
    spellings = [s.upper() for s in scope_for(account)]
    clause = (f"UPPER({table}.account) = ANY($1::text[]) "
              f"AND ({table}.entry_date IS NULL OR {table}.entry_date <= $3) "
              f"AND ({table}.exit_date IS NULL OR {table}.exit_date >= $2)")
    return clause, [spellings, start, end]
