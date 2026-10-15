"""Shared helpers for source-scanning tests. ONE AUTHOR, because I keep re-deriving these.

A test that asserts "X must not appear in the code" has to strip comments AND docstrings first,
or it fails on the prose explaining why X is wrong -- and good comments name the defect they
replaced, so the better the comment the more certain the false failure.

**NINE INSTANCES** of that trap are on record, the last two in a single session: once where
`ast.unparse` was used alone (it drops comments but KEEPS docstrings), and once where I had
already written the docstring-stripping fix in a neighbouring test file and then wrote the
next file without it. Re-deriving a fix per file is how the tenth instance happens, so the
helper lives here and the test files import it.

Two facts that are easy to get wrong, both learned the hard way:

  * `ast.unparse` DROPS COMMENTS BUT KEEPS DOCSTRINGS. Stripping only comments is the trap
    one level up, and it reads as a code match.
  * Docstrings must be removed BY IDENTITY -- the first statement of a body -- never by
    comparing against `ast.get_docstring()`, which cleans indentation and therefore never
    matches the literal in the tree.

And one about files: some sources in this repo carry a BOM (`scheduler/bias_scheduler.py`
does), so a plain utf-8 read makes `ast.parse` die with `invalid non-printable character
U+FEFF` -- the PARSE fails rather than the assertion, which reads as a broken test.
`read_source` uses utf-8-sig.
"""
from __future__ import annotations

import ast
import inspect


def read_source(path: str) -> str:
    """A whole file's text, BOM-tolerant."""
    with open(path, encoding="utf-8-sig") as fh:
        return fh.read()


def strip_docstrings(tree: ast.AST) -> ast.AST:
    """Remove every docstring in the tree, by identity. Mutates and returns the tree."""
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
    return tree


def code_only(src: str) -> str:
    """`src` with comments and docstrings gone. Scan THIS, never the raw text."""
    return ast.unparse(strip_docstrings(ast.parse(src)))


def code_of(obj) -> str:
    """`code_only` for a function, class or module object."""
    return code_only(inspect.getsource(obj).lstrip())


def code_of_file(path: str) -> str:
    """`code_only` for a file path, BOM-tolerant."""
    return code_only(read_source(path))


def function_code(path: str, name: str) -> str:
    """One named function's code from a file, comments and docstring stripped.

    Useful when a module is too large to scan wholesale and the claim is about one function --
    scanning the whole module is how an assertion ends up matching an unrelated branch.
    """
    tree = ast.parse(read_source(path))
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name),
              None)
    if fn is None:
        raise AssertionError("%s not found in %s" % (name, path))
    return ast.unparse(strip_docstrings(ast.Module(body=[fn], type_ignores=[])))
