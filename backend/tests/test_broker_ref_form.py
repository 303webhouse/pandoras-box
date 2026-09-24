"""`position_lots.broker_ref` form — POSITIONS' SPEC.md, sha256 1edbc39c… (R-IV.512(c)1).

TWO forms are admitted, and admitting only the first would silently invalidate
seven live lots:

    <sha12>:L<a>-L<b>            span — only when EVERY record in it is the lot's
    <sha12>:L<a>,L<b>,…          record list (R-IV.504(b)) — the normal roll case
    <sha12>:L<a>-L<b>#<i>-<j>    contract slice (R-IV.507(c)), FIFO ordinals
    NNNNN-XXXXXX                 Fidelity confirmation — the broker's own document
                                 reference, which is STRONGER evidence than a CSV line

Measured live 2026-09-24: 417 lots, **114 carry a ref, 114 distinct** (uniqueness
holds), 107 export form + 7 confirmation form, **0 malformed**. The constraint was
added with no backfill because every existing row already satisfied it.

SPEC's own caution, kept in view: the form makes a ref unique and RESOLVABLE. It
does not make it TRUE. What makes it true is that the records it names reproduce
the lot's qty and price — a re-derivation from the export files, which is a
separate check and not this one.
"""

import re

import pytest

# The regex the constraint carries, verbatim.
EXPORT = re.compile(r'^[0-9a-f]{12}:L[0-9]+(-L[0-9]+|(,L[0-9]+)*)(#[0-9]+-[0-9]+)?$')
FIDELITY = re.compile(r'^[0-9]{5}-[A-Z0-9]{6}$')


def accepted(ref: str) -> bool:
    return bool(EXPORT.match(ref) or FIDELITY.match(ref))


@pytest.mark.parametrize("ref,label", [
    ("b7fce7073c1d:L426-L426", "single-record order writes first == last"),
    ("b7fce7073c1d:L38-L41", "span, every record in it belongs to the lot"),
    ("b7fce7073c1d:L38,L39,L41", "record list — non-contiguous, the roll case"),
    ("1f84bb337019:L5,L7", "two-record list"),
    ("b7fce7073c1d:L38-L41#1-3", "contract slice, FIFO ordinals"),
    ("339ab550832d:L100-L100#2-2", "single-contract slice"),
])
def test_export_record_forms_are_accepted(ref, label):
    assert accepted(ref), label


@pytest.mark.parametrize("ref", [
    "26261-MP7GJ7", "26264-QBM25Q", "26261-N7WG83", "26259-MCQG7Y",
    "26258-Q4ZDR8", "26259-PM8MYF", "26259-QKPYQL",
])
def test_the_seven_live_fidelity_confirmations_are_accepted(ref):
    """THE LOAD-BEARING CASE. A check that admits only the CSV form invalidates
    these seven, which are all FIDELITY_ROTH / IMPORTED and are the broker's own
    document references."""
    assert accepted(ref)


@pytest.mark.parametrize("ref,why", [
    ("not-a-valid-ref", "free text"),
    ("B7FCE7073C1D:L426-L426", "sha must be lowercase hex"),
    ("b7fce7073c1d:426-430", "records need the L prefix"),
    ("b7fce707:L426-L426", "sha must be exactly 12 hex"),
    ("b7fce7073c1dd:L426-L426", "sha must be exactly 12 hex"),
    ("b7fce7073c1d:L426-L430#1", "a slice needs both ordinals"),
    ("26261-mp7gj7", "confirmation suffix is uppercase"),
    ("2626-MP7GJ7", "confirmation prefix is five digits"),
    ("262611-MP7GJ7", "confirmation prefix is five digits"),
    ("", "empty is not a reference"),
    ("b7fce7073c1d:L38-L41,L44", "span and list are not mixed"),
])
def test_malformed_references_are_rejected(ref, why):
    assert not accepted(ref), why


def test_a_null_ref_is_not_a_malformed_ref():
    """The constraint is `broker_ref IS NULL OR …` — a lot may carry no reference
    at all, and that is a different condition from carrying a broken one."""
    assert not accepted("")          # empty string is malformed
    # NULL is handled by the constraint's own IS NULL arm, not by these patterns.


def test_the_two_forms_do_not_overlap():
    """If a string matched both, a reader could not say which evidence it is."""
    for ref in ("b7fce7073c1d:L426-L426", "26261-MP7GJ7"):
        assert bool(EXPORT.match(ref)) != bool(FIDELITY.match(ref))
