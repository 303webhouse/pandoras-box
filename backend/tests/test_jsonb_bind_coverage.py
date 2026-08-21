"""CI fence for DEF-SIGNAL-PERSISTENCE-COLLAPSE.

Every JSONB bind in backend/ must serialize through utils.json_sanitize.dumps_jsonb,
never through a bare json.dumps(). A bare json.dumps emits the tokens NaN /
Infinity / -Infinity, which Postgres rejects -- the mechanism that silently cost
459 signals on 2026-08-18/19.

Two assertions:
  1. no bare json.dumps at a JSONB bind site, INCLUDING values held in a variable
     and values passed via *params star-unpack
  2. no dumps_jsonb(sanitize_for_json(...)) composition, INCLUDING multi-line forms

Both blind spots are load-bearing history, not hypotheticals. The v1 fence was
line-scoped and lexical-args-only; it printed VIOLATIONS: 0 COMPOSITIONS: 0 while
5 live binds and 1 composition survived in the tree.

Run standalone for a report:  python backend/tests/test_jsonb_bind_coverage.py
"""
from __future__ import annotations

import ast
import pathlib
import re
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[1]

EXEC_CALLS = {"execute", "executemany", "fetch", "fetchval", "fetchrow", "fetchall"}

# public-schema json/jsonb columns: 48 live columns across 30 tables (live schema
# 2026-08-20), PLUS committee_recommendations.raw_json, declared JSONB at
# postgres_client.py:2432 but absent from the live DB. That omission was a real
# inventory gap -- it hid a live bare-json.dumps bind from this fence entirely.
JSONB_COLUMNS = {
    "bias_composite_history.factor_scores", "bias_history.supporting_data",
    "catalyst_events.correlated_tickers", "catalyst_events.sector_velocity",
    "catalyst_events.trip_wire_status", "committee_passes.agent_reads",
    "crypto_cycle_config.config", "crypto_cycle_log.cells",
    "crypto_dual_write_shadow.l0_shadow_decision",
    "crypto_dual_write_shadow.l1_shadow_decision",
    "crypto_dual_write_shadow.raw_shadow_signal_data", "crypto_gate_config.config",
    "earnings_calendar.position_overlap_details", "factor_history.data",
    "factor_readings.metadata", "health_alerts.metadata",
    "lightning_cards.confirmations", "options_positions.bias_at_open",
    "options_positions.breakeven", "options_positions.legs",
    "pending_trades.options_legs", "portfolio_snapshots.direction_exposure",
    "portfolio_snapshots.sector_exposure", "position_sync_audit.after_state",
    "position_sync_audit.before_state", "positions.bias_at_close",
    "positions.bias_at_open", "pythia_events.raw_payload",
    "regime_overrides.sectors_avoided", "regime_overrides.sectors_favored",
    "regime_overrides.theme_keywords", "signals.bias_at_signal",
    "signals.committee_data", "signals.context_factors", "signals.enrichment_data",
    "signals.outcome_options_metrics", "signals.score_v2_factors",
    "signals.triggering_factors", "strategy_health.regime_breakdown",
    "system_config.value", "trades.full_context", "triton_flow_shadow.raw",
    "unified_positions.legs", "uw_snapshots.extracted_data",
    "v2_dashboard_layout.layout", "watchlist_config.tickers",
    "weekly_reports.lessons", "weekly_reports.report_json",
    "committee_recommendations.raw_json",
}
JSONB_COLNAMES = {c.split(".", 1)[1] for c in JSONB_COLUMNS}
JSONB_TABLES = {c.split(".", 1)[0] for c in JSONB_COLUMNS}

# dumps_jsonb(sanitize_for_json(x)) is a COMPOSITION DEFECT: the inner call nulls
# non-finite values into a throwaway list, so the chokepoint sees clean data and
# emits no warning and no _degraded_nonfinite marker. The row lands and the
# degradation is silent -- passing "row landed" while defeating never-silent.
# re.S so \s* crosses newlines: the one composition that survived the first sweep
# was the one written multi-line, and a per-line scan can never match it.
_COMPOSITION = re.compile(r"dumps_jsonb\(\s*_?sanitize_for_json\(", re.S)


def _sql_touches_jsonb(sql: str) -> bool:
    low = " ".join(sql.lower().split())
    if not any(k in low for k in ("insert into", "update ")):
        return False
    if not any(t in low for t in JSONB_TABLES):
        return False
    return any(c in low for c in JSONB_COLNAMES) or "::jsonb" in low


def _strings_in(node: ast.AST) -> list[str]:
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            out.append(n.value)
        elif isinstance(n, ast.JoinedStr):
            out.append("".join(
                p.value for p in n.values
                if isinstance(p, ast.Constant) and isinstance(p.value, str)))
    return out


def _is_bare_json_dumps(node: ast.AST) -> bool:
    """True for json.dumps(...) / _json.dumps(...) -- NOT dumps_jsonb(...)."""
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    if isinstance(f, ast.Attribute) and f.attr == "dumps":
        return True
    if isinstance(f, ast.Name) and f.id == "dumps":
        return True
    return False


def find_violations() -> list[tuple[str, int, str]]:
    violations = []
    for path in sorted(BACKEND.rglob("*.py")):
        if "tests" in path.parts or "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue

        assigned: dict[str, str] = {}          # name -> SQL string
        dumps_vars: set[str] = set()           # name = json.dumps(...)
        list_vars: dict[str, ast.AST] = {}     # name = [...]  for conn.fetch(q, *name)
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Assign) and len(n.targets) == 1
                    and isinstance(n.targets[0], ast.Name)):
                continue
            tgt = n.targets[0].id
            for text in _strings_in(n.value):
                if _sql_touches_jsonb(text):
                    assigned[tgt] = text
            if _is_bare_json_dumps(n.value):
                dumps_vars.add(tgt)
            if isinstance(n.value, (ast.List, ast.Tuple)):
                list_vars[tgt] = n.value

        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)):
                continue
            if n.func.attr not in EXEC_CALLS or not n.args:
                continue
            sqls = _strings_in(n.args[0])
            if isinstance(n.args[0], ast.Name) and n.args[0].id in assigned:
                sqls.append(assigned[n.args[0].id])
            if not any(_sql_touches_jsonb(s) for s in sqls):
                continue

            bind_args = list(n.args[1:]) + [k.value for k in n.keywords]
            # conn.fetch(query, *params) -- follow the star to its list literal
            for a in list(bind_args):
                if isinstance(a, ast.Starred) and isinstance(a.value, ast.Name):
                    lit = list_vars.get(a.value.id)
                    if lit is not None:
                        bind_args.extend(lit.elts)

            rel = str(path.relative_to(BACKEND))
            for arg in bind_args:
                for sub in ast.walk(arg):
                    if _is_bare_json_dumps(sub):
                        violations.append((
                            rel, getattr(sub, "lineno", n.lineno),
                            "bare json.dumps into a JSONB bind -- use dumps_jsonb()"))
                    elif isinstance(sub, ast.Name) and sub.id in dumps_vars:
                        violations.append((
                            rel, getattr(sub, "lineno", n.lineno),
                            f"variable {sub.id!r} holds a bare json.dumps result and is "
                            "bound to a JSONB column -- use dumps_jsonb()"))
    return violations


def find_compositions() -> list[tuple[str, int]]:
    hits = []
    for path in sorted(BACKEND.rglob("*.py")):
        if "tests" in path.parts or "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in _COMPOSITION.finditer(text):
            hits.append((str(path.relative_to(BACKEND)), text.count("\n", 0, m.start()) + 1))
    return hits


def test_all_jsonb_binds_use_dumps_jsonb():
    v = find_violations()
    detail = "\n".join(f"  {f}:{ln} -- {m}" for f, ln, m in v)
    assert not v, "JSONB binds not routed through dumps_jsonb():\n" + detail


def test_no_double_sanitize_composition():
    hits = find_compositions()
    detail = "\n".join(f"  {f}:{ln}" for f, ln in hits)
    assert not hits, (
        "dumps_jsonb(sanitize_for_json(...)) composition -- the inner call "
        "destroys degraded-path capture:\n" + detail)


if __name__ == "__main__":
    vs = find_violations()
    cs = find_compositions()
    print(f"VIOLATIONS: {len(vs)}   COMPOSITIONS: {len(cs)}")
    for f, ln, m in vs:
        print(f"  bind  {f}:{ln} -- {m}")
    for f, ln in cs:
        print(f"  compo {f}:{ln}")
    sys.exit(1 if (vs or cs) else 0)
