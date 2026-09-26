"""R-IV.462(b) -- every machine writer names itself, in the transaction that carries its write.

FAIL-FIRST against the pre-2026-09-19 tree: the mark job, the boot backfills, the PATCH recompute
and six scripts wrote unified_positions without naming an actor, so the audit trigger recorded
each as 'legacy-ui' -- 6,271 UPDATE rows from 2026-08-27, 3,239 of them the mark job.

The census below reads the source, so a writer added later that names no one fails here rather
than surfacing as another month of rows that cannot tell a person from a job.
"""
from __future__ import annotations

import ast
import asyncio
import pathlib
import re
import sys

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

ROOT = pathlib.Path(__file__).resolve().parents[2]
WRITE = re.compile(r"\b(UPDATE|DELETE\s+FROM|INSERT\s+INTO)\s+unified_positions\b", re.I)

# R-IV.463(e): the trigger records INSERT as well as UPDATE and DELETE, so every writer of either
# kind names itself. R-IV.463(b): the request-driven endpoints -- create, close, delete,
# reconcile, bulk, the two signal accepts -- take the optional actor PATCH already had and name
# the caller, legacy-ui only when the caller names no one. None is exempt any more.
REQUEST_DRIVEN: dict = {}
SCRIPT_EXEMPT = {
    "feat_position_lifecycle_phase1.py": "its two writes are a trigger probe rolled back to a "
                                         "savepoint and a no-op the trigger does not record",
}


def _parents(tree):
    out = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            out[child] = node
    return out


def _names_actor(node) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            if (isinstance(f, ast.Name) and f.id == "name_actor") or \
               (isinstance(f, ast.Attribute) and f.attr == "name_actor"):
                return True
            for a in n.args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str) and "app.actor" in a.value:
                    return True
    return False


def _is_txn(with_node) -> bool:
    return any(isinstance(i.context_expr, ast.Call) and isinstance(i.context_expr.func, ast.Attribute)
               and i.context_expr.func.attr == "transaction" for i in with_node.items)


def _unnamed_writes(path: pathlib.Path):
    src = path.read_text(encoding="utf-8-sig")        # three backend files carry a BOM
    tree = ast.parse(src)
    parent = _parents(tree)
    bad = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and WRITE.search(node.value)):
            continue
        if isinstance(parent.get(node), ast.Expr):          # a docstring, not a statement
            continue
        chain, cur = [], node
        while cur in parent:
            cur = parent[cur]
            chain.append(cur)
        func = next((c for c in chain if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef))), None)
        if func is not None and func.name in REQUEST_DRIVEN:
            continue
        ok = any(isinstance(c, ast.AsyncWith) and _is_txn(c) and _names_actor(c) for c in chain)
        if not ok:
            # a statement tuple a loop executes: the loop's own transaction must name the writer
            loop = next((c for c in chain if isinstance(c, ast.For)), None)
            ok = loop is not None and any(
                isinstance(w, ast.AsyncWith) and _is_txn(w) and _names_actor(w)
                for w in ast.walk(loop) if w not in chain)
        if not ok:
            bad.append(f"{path.relative_to(ROOT)}:{node.lineno} in "
                       f"{func.name if func else '<module>'}")
    return bad


def test_every_backend_writer_names_itself_in_its_transaction():
    files = [p for p in (ROOT / "backend").rglob("*.py") if "tests" not in p.parts]
    bad = [b for p in files for b in _unnamed_writes(p)]
    assert not bad, "writes the audit would record as legacy-ui:\n" + "\n".join(bad)


def test_every_script_that_updates_or_deletes_names_itself():
    bad = []
    for p in sorted((ROOT / "scripts").glob("*.py")):
        src = p.read_text(encoding="utf-8", errors="replace")
        dynamic = ('TABLE = "unified_positions"' in src
                   and re.search(r"(UPDATE|DELETE\s+FROM)\s+\{TABLE\}", src))
        if not (WRITE.search(src) or dynamic) or p.name in SCRIPT_EXEMPT:
            continue
        # Either the raw `set_config` OR a call to the canonical helper. The helper is the
        # BETTER form -- it is the one author for this (R-IV.462(b)) and it sets the reason as
        # well -- and a guard that only accepted the inlined string would push new scripts to
        # bypass it to satisfy a test. `test_name_actor_sets_both_settings_transaction_local`
        # below pins that the helper really does set `app.actor`, so the chain is complete.
        if "set_config('app.actor'" not in src and "name_actor(" not in src:
            bad.append(p.name)
    assert not bad, f"scripts writing unified_positions with no actor: {bad}"


def test_the_helper_is_an_accepted_form_because_it_does_the_same_thing():
    """POSITIVE CONTROL for the widened guard: a script naming no actor at all still fails."""
    import re as _re

    assert not ("set_config('app.actor'" in "UPDATE unified_positions SET x = 1"
                or "name_actor(" in "UPDATE unified_positions SET x = 1")
    # ...and the helper's own source contains the setting the guard used to demand textually.
    from utils import audit_actor
    import inspect
    assert "set_config('app.actor'" in inspect.getsource(audit_actor.name_actor)


def test_the_exemptions_are_still_true():
    """An exemption that stops being true must be removed, not left to excuse a new writer."""
    assert REQUEST_DRIVEN == {}, "R-IV.463(b): every request-driven writer names its caller"
    probe = (ROOT / "scripts" / "feat_position_lifecycle_phase1.py").read_text(encoding="utf-8")
    assert "ROLLBACK TO SAVEPOINT trigger_probe" in probe and "SET notes = notes" in probe


def test_name_actor_sets_both_settings_transaction_local():
    from utils.audit_actor import name_actor
    calls = []

    class Conn:
        async def execute(self, sql, *args):
            calls.append((sql, args))

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(name_actor(Conn(), "mark-to-market", "why"))
        loop.run_until_complete(name_actor(Conn(), "boot-migration"))
    finally:
        loop.close()
    assert calls[0] == ("SELECT set_config('app.actor', $1, true)", ("mark-to-market",))
    assert calls[1] == ("SELECT set_config('app.reason', $1, true)", ("why",))
    assert len(calls) == 3, "no reason, no reason setting"


def test_the_cutover_is_recorded_and_the_ambiguity_is_said():
    mig = (ROOT / "migrations" / "048_audit_actor_epoch.sql").read_text(encoding="utf-8")
    boot = (ROOT / "backend" / "database" / "postgres_client.py").read_text(encoding="utf-8")
    for text in (mig, boot):
        assert "CREATE TABLE IF NOT EXISTS audit_actor_epochs" in text
        assert "'machine-writers-named'" in text and "ON CONFLICT (epoch) DO NOTHING" in text
        assert "COMMENT ON COLUMN position_sync_audit.actor" in text
        assert "AMBIGUOUS" in text
    assert "UPDATE position_sync_audit" not in mig, "historical rows are not rewritten"


def test_inserts_are_audited_in_both_mirrors():
    mig = (ROOT / "migrations" / "050_audit_inserts.sql").read_text(encoding="utf-8")
    boot = (ROOT / "backend" / "database" / "postgres_client.py").read_text(encoding="utf-8")
    for text in (mig, boot):
        assert "IF (TG_OP = 'INSERT') THEN" in text
        assert "AFTER INSERT OR UPDATE OR DELETE ON unified_positions" in text
        assert "(tgtype & 4) = 4" in text, "re-created only when it does not already fire"


def test_the_four_endpoints_take_the_actor_patch_has():
    from api import unified_positions as U
    from api import positions as P
    for model in (U.CreatePositionRequest, U.ClosePositionRequest, U.BulkRequest,
                  U.ReconcileRequest, P.AcceptSignalRequest, P.AcceptSignalAsOptionsRequest):
        assert {"actor", "reason"} <= set(model.model_fields), model.__name__
    import inspect
    params = inspect.signature(U.delete_position).parameters
    assert "actor" in params and "reason" in params


def test_the_mark_job_and_the_patch_recompute_pass_t1():
    from api import unified_positions as U
    import inspect
    mtm = inspect.getsource(U.run_mark_to_market)
    assert mtm.count("evaluate_mark(") == 2, "both the legs path and the two-strike path"
    assert "above its width" in mtm
    patch = inspect.getsource(U.update_position)
    assert 'name_actor(conn, req.actor or "legacy-ui"' in patch
