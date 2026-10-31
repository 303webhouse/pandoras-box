"""R-IV.1471: one earnings fetch per boot, not two.

4783239f added the loop's run-on-deploy but left the older "Chronos initial earnings load" in
main.py, so every deploy fetched the calendar twice (job_runs 10-31: 18:59:09Z and 19:00:09Z,
20:08:13Z and 20:09:13Z) -- ~36 UW calls each against a 100-a-day tag.

Read from the parsed code (comments and docstrings cannot satisfy it): every call to
run_chronos_earnings_ingest in main.py sits inside chronos_earnings_loop.
"""
import ast
import pathlib

MAIN = pathlib.Path(__file__).resolve().parents[1] / "main.py"


def _calls_by_enclosing_function():
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    found = []

    def walk(node, fn):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                walk(child, child.name)
                continue
            if isinstance(child, ast.Call):
                f = child.func
                name = f.id if isinstance(f, ast.Name) else getattr(f, "attr", None)
                if name == "run_chronos_earnings_ingest":
                    found.append(fn)
            walk(child, fn)
    walk(tree, None)
    return found


def test_every_earnings_fetch_in_main_is_inside_the_loop():
    fns = _calls_by_enclosing_function()
    assert fns, "main.py no longer starts the earnings fetch at all"
    assert set(fns) == {"chronos_earnings_loop"}, fns
    # once on deploy + once when the nightly slot is due
    assert len(fns) == 2, fns
