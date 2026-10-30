"""R-IV.1461(b): main.py's startup reads attributes off job modules; every one must exist.

864c4f16 renamed option_quote_capture.SESSION_CALL_CEILING to session_ceiling(), and main.py's
start-up log line kept the old name. The task had already been created, so the capture ran
every day -- but every boot logged "option_quote_capture did NOT start", a false alarm at
ERROR on the one job TRITON-R2 Stage B reads. This test reads each `alias.attr` main.py uses
for an `from jobs import X as alias` import and checks the module really has it.
"""

import ast
import importlib
import os

MAIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")


def _aliases(tree):
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "jobs":
            for a in node.names:
                out[a.asname or a.name] = "jobs." + a.name
    return out


def test_every_job_attribute_main_reads_exists():
    tree = ast.parse(open(MAIN, encoding="utf-8").read())
    aliases = _aliases(tree)
    assert "_oqc" in aliases, "the capture import moved; update this test"
    missing = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id in aliases):
            mod = importlib.import_module(aliases[node.value.id])
            if not hasattr(mod, node.attr):
                missing.append("%s.%s (line %d)" % (aliases[node.value.id], node.attr, node.lineno))
    assert not missing, "main.py reads attributes its job modules do not have: %s" % missing
