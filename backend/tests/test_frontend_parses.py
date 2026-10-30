"""The shipped JS must PARSE. R-IV.1246's near miss.

A Python-side edit to `v2.js` put a literal newline inside a string literal, which is a syntax
error: the whole file fails to parse, every renderer on the page stops, and the dashboard goes
blank. The suite's other JS tests are SOURCE SCANS -- they read the text and never execute it --
so all of them passed on a file the browser could not load. It was caught by running node by
hand, minutes before a deploy timed for the market open.

So: parse the files, every run. Skipped (not passed) where node is unavailable, because a guard
that silently does nothing is worse than no guard -- this repo has the scar.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

FRONTEND = pathlib.Path(__file__).resolve().parents[2].joinpath("frontend")
# abacus.js was retired with the ?view=summary rollback (R-IV.1448(b)); the Abacus page's one script
# is now assets/abacus-pnl.js.
JS_FILES = ("v2.js", "app.js", "stater.js", "assets/abacus-pnl.js", "knowledgebase.js")


@pytest.mark.parametrize("name", JS_FILES)
def test_the_shipped_js_parses(name):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not on PATH here; the parse check cannot run")
    path = FRONTEND.joinpath(name)
    if not path.exists():
        pytest.skip("%s is not in this tree" % name)
    # `new Function(src)` parses without EXECUTING, so a file that touches `document` at load
    # is still checked. --check would also work but rejects top-level returns in some files.
    script = ("const fs=require('fs');"
              "try{new Function(fs.readFileSync(process.argv[1],'utf8'));}"
              "catch(e){console.error(e.message);process.exit(1);}")
    res = subprocess.run([node, "-e", script, str(path)], capture_output=True, text=True,
                         timeout=60)
    assert res.returncode == 0, "%s does not parse: %s" % (name, res.stderr.strip()[:400])
