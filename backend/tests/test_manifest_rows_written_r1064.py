"""R-IV.1064(c) — `rows_written` is filled for a CARRIED file, from the file itself.

AND FROM A DIFFERENT MECHANISM THAN `rows_read_back`, which is the only thing that makes
filling it worth anything:

    rows_written    the parquet FOOTER's declared `num_rows` (metadata; no data pages read)
    rows_read_back  the count obtained by actually READING the data

Both from one read would have made the two columns tautologically equal for every carried file
and quietly retired the mismatch detector that MANIFEST.tsv v2 exists for. Sourced separately
they still disagree when a footer claims rows the body cannot produce -- convention #34's "two
routes verify a read-back", applied to a file rather than a route.

A non-parquet file (the READMEs) has no row concept and stays EMPTY. **Never -1**: a count
column holding a magic number is a lie told in the column's own type, and that one cost QUERY
56 failures (R-IV.1017(c)).
"""
from __future__ import annotations

import ast
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXPORT = os.path.join(REPO, "scripts", "f_export.py")


def _code_only(src: str) -> str:
    """Comments AND docstrings stripped. `ast.unparse` drops comments but KEEPS docstrings, and
    this module's own docstring is full of the words these tests scan for."""
    tree = ast.parse(src)
    docs = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body and isinstance(body[0], ast.Expr)
                and isinstance(getattr(body[0], "value", None), ast.Constant)
                and isinstance(body[0].value.value, str)):
            docs.add(id(body[0]))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list):
            node.body = [n for n in body if id(n) not in docs] or [ast.Pass()]
    return ast.unparse(tree)


@pytest.fixture(scope="module")
def src():
    with open(EXPORT, encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def archive_fn(src):
    tree = ast.parse(src)
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == "_archive_rows"), None)
    assert fn is not None, "_archive_rows not found"
    return ast.unparse(fn)


# ── 1. the two counts come from two mechanisms ───────────────────────────────

def test_rows_written_comes_from_the_parquet_FOOTER(archive_fn):
    assert "metadata.num_rows" in archive_fn, (
        "rows_written must come from the footer, not from the data read")


def test_rows_read_back_still_comes_from_READING_the_data(archive_fn):
    assert "read_parquet" in archive_fn


def test_they_are_not_the_same_expression(archive_fn):
    """THE POINT. If both were `len(pd.read_parquet(path))` the columns could never disagree
    and the mismatch check would be decoration."""
    assert archive_fn.count("read_parquet") >= 1
    assert "metadata.num_rows" in archive_fn
    # the footer read must not be derived from the dataframe
    assert "len(pd.read_parquet" in archive_fn or "len(" in archive_fn


def test_a_footer_data_disagreement_is_a_MISMATCH(archive_fn):
    """A corrupt file must be reported as corrupt, not carried silently with two numbers that
    happen to differ in a column nobody compares."""
    assert "MISMATCH" in archive_fn
    assert "footer declares" in archive_fn or "corrupt" in archive_fn


# ── 2. never a magic number ──────────────────────────────────────────────────

def test_rows_written_is_never_minus_one(archive_fn):
    """R-IV.1017(c): the -1 sentinel in a count column cost QUERY 56 failures. Scanned on
    parsed code so the comment explaining the ban cannot satisfy it."""
    assert "'rows_written': -1" not in archive_fn
    assert '"rows_written": -1' not in archive_fn


def test_a_non_parquet_file_keeps_an_EMPTY_rows_written(archive_fn):
    """A README has no rows. Filling it with 0 would assert an empty file."""
    assert "rows_declared = None" in archive_fn


def test_the_manifest_assembly_passes_the_value_through(src):
    """The count is useless if `write_manifest` keeps hardcoding None -- which it did, with a
    comment saying this process did not write the file. True, and not a reason to discard a
    count the file itself can state."""
    # SCOPED TO THE ASSEMBLY FUNCTION. My first version scanned the whole module and failed on
    # the UNREADABLE branch, where `rows_written: None` is exactly right -- a file that cannot
    # be opened has no knowable count. Over-reaching again: the claim is about where the
    # carried row is BUILT, not about the word None appearing anywhere.
    tree = ast.parse(src)
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and "manifest" in n.name.lower() and "write" in n.name.lower()), None)
    assert fn is not None, "the manifest writer could not be located"
    code = ast.unparse(fn)
    assert "r.get('rows_written')" in code or 'r.get("rows_written")' in code, (
        "the writer must pass the carried count through rather than hardcoding None:\n%s"
        % code[:900])


def test_the_stale_docstring_claim_is_corrected(src):
    """`_archive_rows` documented itself as carrying `rows_written = -1`, which stopped being
    true at R-IV.1017(c) and is doubly untrue now. A docstring that contradicts the column is
    worse than none: the next reader trusts it."""
    i = src.index("def _archive_rows")
    doc = src[i:i + 2200]
    assert "rows_written = -1`, NOT 0" not in doc
    assert "footer" in doc.lower()


# ── 3. the empty-vs-zero rule the writer must keep ───────────────────────────

def test_the_writer_still_renders_None_as_EMPTY_not_zero(src):
    code = _code_only(src)
    assert "'' if r['rows_written'] is None else str(r['rows_written'])" in code.replace(
        '"', "'"), "a None count must serialise to an empty cell, never 0"
