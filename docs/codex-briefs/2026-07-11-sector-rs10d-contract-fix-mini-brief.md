# MINI-BRIEF — sector RS 10d contract fix (hub_get_sector_strength)

**Date:** 2026-07-11 (Saturday — market closed, open push window, no blackout)
**Status:** ATLAS-approved in-context 2026-07-11 (no veto; amendments A1–A6 folded below). Fable-drafted from live diagnosis.
**Executor:** CC. ONE push, any time today. Confirm Railway deploy healthy + `/mcp/v1/health` new SHA after.
**ACK RULE:** reply with an explicit ACK line + ETA before starting (standing rule 2026-07-10).

## Root cause (verified live, not hypothesis)

- `hub_get_sector_strength` reads Redis `sector:rotation:current`, written by `backend/bias_filters/sector_momentum.py`.
- The writer COMPUTES `rs_10d` internally (acceleration calc) but never stores it — entries carry `rs_5d`/`rs_20d`/status/ranks(5d,20d) only.
- The reader (`backend/hub_mcp/tools/sector_strength.py`) does `entry.get(...) or 0.0` → every sector reports `rs_10d = 0.0`, 24/7, since the tool shipped (~2026-05-14).
- `rank_10d` is then assigned by stable-sorting eleven equal zeros → equals the writer's `SECTOR_ETFS` dict declaration order. Live payload 2026-07-11 23:23Z matches that order exactly (XLK, XLY, XLF, XLV, XLE, XLI, XLP, XLC, XLU, XLRE, XLB). Deterministic proof.
- Bonus defects, same file: `staleness_seconds=600` HARDCODED (fake-staleness anti-pattern; entries carry a real `updated_at` that is ignored), and the `or` chain would also eat a legitimate 0.0.
- Closes the 2026-05-22 `docs/build-backlog.md` diagnostic item with corrected root cause — it is NOT after-hours-only.
- Blast radius note: Achilles (`backend/scanners/sector_rs.py`) reads its OWN real 10d/20d cache (`sector_rs:{ETF}`) — healthy, OUT OF SCOPE, do not touch. Dual-pipeline consolidation = backlog note only, not this brief.

## Scope

Exactly two backend files + tests + two doc edits. No schema, no new endpoints, no UW calls, no frontend, no manifest change.

1. `backend/bias_filters/sector_momentum.py` — store `rs_10d` + `rank_10d` (already computed).
2. `backend/hub_mcp/tools/sector_strength.py` — honest-null + degraded + real staleness.
3. Tests in `backend/hub_mcp/tests/test_tools_smoke.py` (or sibling).
4. `docs/build-backlog.md` — close the 5/22 diagnostic entry with the corrected root cause.
5. `docs/workstreams.md` — CC updates its own section (ledger discipline).

## Change 1 — writer stores rs_10d + rank_10d (`backend/bias_filters/sector_momentum.py`)

**1a.** In the `entry = {` dict, FIND:
```python
            "rs_5d": round(rs_5d, 2),
            "rs_20d": round(rs_20d, 2),
```
REPLACE with:
```python
            "rs_5d": round(rs_5d, 2),
            "rs_10d": round(rs_10d, 2) if rs_10d is not None else None,
            "rs_20d": round(rs_20d, 2),
```
(`rs_10d` is already computed a few lines above for the acceleration calc; it may be None when the accel branch fell to "unknown" — preserve None, never coerce.)

**1b.** Immediately AFTER this existing block:
```python
    rank_data.sort(key=lambda x: x["rs_20d"], reverse=True)
    for i, entry in enumerate(rank_data):
        entry["rank_20d"] = i + 1
        entry["rank_change_5d"] = entry["rank_20d"] - entry["rank_5d"]
        # Positive rank_change = improved (moved up), negative = deteriorated
```
ADD:
```python
    # rank_10d — only over entries that actually have rs_10d (never fabricate)
    with_10d = [e for e in rank_data if e.get("rs_10d") is not None]
    with_10d.sort(key=lambda x: x["rs_10d"], reverse=True)
    for i, entry in enumerate(with_10d):
        entry["rank_10d"] = i + 1
```

**1c.** In the results-update loop, FIND:
```python
        results[sector]["rank_change_5d"] = entry["rank_change_5d"]
```
REPLACE with:
```python
        results[sector]["rank_change_5d"] = entry["rank_change_5d"]
        results[sector]["rank_10d"] = entry.get("rank_10d")
```

## Change 2 — reader honest-null + real staleness (`backend/hub_mcp/tools/sector_strength.py`)

**2a.** Add to imports: `from datetime import datetime, timezone`

**2b.** FIND the coercion (THE BUG):
```python
        rs_10d = entry.get("relative_strength_10d") or entry.get("rs_10d") or 0.0
        rs_20d = entry.get("relative_strength_20d") or entry.get("rs_20d") or 0.0
```
REPLACE with is-None chaining (an `or` chain also eats a legitimate 0.0):
```python
        rs_10d = entry.get("relative_strength_10d")
        if rs_10d is None:
            rs_10d = entry.get("rs_10d")
        rs_20d = entry.get("relative_strength_20d")
        if rs_20d is None:
            rs_20d = entry.get("rs_20d")
```

**2c.** `_map_status` None guard. FIND:
```python
def _map_status(status: str, rs_20d: float) -> str:
    s = (status or "").upper()
```
REPLACE with:
```python
def _map_status(status: str, rs_20d: "float | None") -> str:
    if rs_20d is None:
        return "NEUTRAL"
    s = (status or "").upper()
```

**2d.** Rank assignment must never sort None (TypeError) or fabricate. FIND:
```python
    by_rs_10d.sort(key=lambda s: s["rs_10d"], reverse=True)
    by_rs_20d.sort(key=lambda s: s["rs_20d"], reverse=True)
    for rank, s in enumerate(by_rs_10d, start=1):
        if s["rank_10d"] is None:
            s["rank_10d"] = rank
    for rank, s in enumerate(by_rs_20d, start=1):
        if s["rank_20d"] is None:
            s["rank_20d"] = rank
```
REPLACE with:
```python
    ranked_10 = [s for s in by_rs_10d if s["rs_10d"] is not None]
    ranked_10.sort(key=lambda s: s["rs_10d"], reverse=True)
    for rank, s in enumerate(ranked_10, start=1):
        if s["rank_10d"] is None:
            s["rank_10d"] = rank
    ranked_20 = [s for s in by_rs_20d if s["rs_20d"] is not None]
    ranked_20.sort(key=lambda s: s["rs_20d"], reverse=True)
    for rank, s in enumerate(ranked_20, start=1):
        if s["rank_20d"] is None:
            s["rank_20d"] = rank
```
(CC may instead simplify away the redundant `by_rs_10d`/`by_rs_20d` copies and build from `sectors` directly — allowed, as long as tests T1–T4 pass.)

**2e.** REPLACE the tail of `hub_get_sector_strength` — everything from `regime = _classify_regime(sectors)` through the final `return make_response(...)` — with:
```python
    # Real staleness from the writer's per-entry updated_at (never hardcoded)
    ages = []
    now = datetime.now(timezone.utc)
    for entry in raw.values():
        ts = entry.get("updated_at")
        if not ts:
            continue
        try:
            ages.append((now - datetime.fromisoformat(ts)).total_seconds())
        except (ValueError, TypeError):
            continue
    staleness = int(max(ages)) if ages else None

    missing = []
    for s in sectors:
        if s["rs_10d"] is None:
            missing.append(f"{s['etf']}:rs_10d")
        if s["rs_20d"] is None:
            missing.append(f"{s['etf']}:rs_20d")

    regime = _classify_regime(sectors)
    leaders_count = sum(1 for s in sectors if s["state"] in ("LEADING", "ROTATING_IN"))
    breadth_score = round(leaders_count / max(len(sectors), 1), 2)
    narrow = breadth_score < 0.35

    data = {
        "rotation_regime": regime,
        "sectors": sectors,
        "narrow_leadership_flag": narrow,
        "leadership_breadth_score": breadth_score,
    }
    if missing:
        data["warnings"] = [
            "missing (null, ranks omitted — cache predates field or writer skipped): "
            + ", ".join(missing)
        ]

    have_20 = [s for s in sectors if s["rs_20d"] is not None]
    top = sorted(have_20, key=lambda s: s["rs_20d"], reverse=True)[:3]
    bottom = sorted(have_20, key=lambda s: s["rs_20d"])[:2]
    top_str = ", ".join(f"{s['etf']} ({s['rs_20d']:+.1f}%)" for s in top) or "n/a"
    bot_str = ", ".join(f"{s['etf']} ({s['rs_20d']:+.1f}%)" for s in bottom) or "n/a"
    summary = (
        f"Sector regime: {regime}. Leading: {top_str}. Lagging: {bot_str}. "
        f"Leadership breadth {breadth_score}."
    )
    if missing:
        summary += f" DEGRADED: {len(missing)} field(s) missing."

    return make_response(
        status="degraded" if missing else "ok",
        data=data,
        summary=summary,
        staleness_seconds=staleness,
    )
```

## ATLAS amendments (folded)

- **A1** Reader MUST tolerate the old-schema cache post-deploy (up to one refresh cycle): degraded + null is the correct interim state, never a crash, never 0.0. This window is acceptance case T1, not a failure.
- **A2** `updated_at` parsing wrapped per-entry in `(ValueError, TypeError)`; staleness = max age across entries; None when nothing parses (envelope supports null — Hydra returns it live).
- **A3** Legitimate-zero regression guard: `rs_10d == 0.0` in cache must pass through as `0.0` with status ok (test T2).
- **A4** Pre-flight grep all consumers of `sector:rotation:current` / `get_cached_rotation` — confirm `.get()`-based access (additive key = non-breaking). Record findings in the commit message.
- **A5** NO Pandora connector toggle — tool name/description/params unchanged, manifest identical. Per 7/13 handoff: do not disconnect/re-add.
- **A6** Summary/sort None-safety (2c + 2d + `have_20` filter above).

## Pre-flight (CC)

1. `git fetch && git status` — main must include the brief commit for this file. Pathspec-only; do NOT stage TODO.md, docs/trading-memory.md, or any untracked noise.
2. Run the A4 grep; record results.
3. Read `make_response` signature in `backend/hub_mcp/envelope.py`; confirm `staleness_seconds=None` is accepted (expected — Hydra emits null).

## Tests

- **T1** old-schema cache (entries WITHOUT rs_10d) → rs_10d null, rank_10d null, status "degraded", warning names the ETFs+field. No exception.
- **T2** legit zero: rs_10d=0.0 in cache → 0.0 in output, status "ok" (guards the `or`-eats-zero pattern).
- **T3** staleness: entries with a known `updated_at` → staleness_seconds ≈ real age (tolerance ±5s); absent/garbage timestamps → staleness null, no exception.
- **T4** existing smoke case (rs_10d present: 2.4 / −1.8 / 0.6) still passes; rank_10d ordering follows VALUES, not dict declaration order.

## Acceptance (CC runs 1–3; Fable independently verifies 4 — builder never grades own pixels)

1. `py_compile` clean on both files; hub_mcp test suite green (the 3 pre-existing known failures — footprint_long, session_sweep, pullback_entry ceiling — remain excluded per chase item 5).
2. Local proof: run `refresh_sector_rotation()` then the tool → 11 sectors, rs_10d values NON-IDENTICAL across sectors, ≠ rs_20d, rank_10d ≠ SECTOR_ETFS declaration order, staleness ≈ real cache age.
3. ONE push. Railway deploy healthy; `/mcp/v1/health` shows the new SHA. `git diff --stat` on the push = exactly: 2 backend files, test file, docs/build-backlog.md, docs/workstreams.md, this brief (if step-0 committing it).
4. Post-deploy live (Fable, via MCP `hub_get_sector_strength`): EITHER real rs_10d values (happy path, after the scheduler's next refresh repopulates the cache) OR degraded+null with honest warning (correct interim state per A1). If the happy path hasn't printed by Monday pre-market, confirm it before the first committee pass of the day.

## Rollback

Single `git revert` of the fix commit. Reader tolerates both schemas, so partial rollback is also safe. No data migration; Redis self-heals within TTL (3600s).

## Out of scope

- `backend/scanners/sector_rs.py` (Achilles pipeline) — healthy, untouched.
- Dual sector-RS pipeline consolidation — add one line to `docs/build-backlog.md` under cleanup, do not build.
- Any other file. Any UW call. Any frontend surface.
