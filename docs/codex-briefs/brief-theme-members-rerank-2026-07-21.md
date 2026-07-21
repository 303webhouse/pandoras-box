# Brief: Theme Members Re-Rank After Live Overlay (Inversion Bug)

**Date:** 2026-07-21
**Priority:** P1 — panel is actively misleading during market hours
**Scope:** 1 backend function, 1 tool description, 1 frontend label, 1 regression test
**Lanes:** ATLAS (data provenance), HELIOS (label copy only — NO layout change, mockup gate does NOT apply)
**Author:** Coordination lane (Claude.ai), anchors verified against live repo `main` @ c2aea5f

---

## Incident (evidence, 2026-07-21 ~09:50 MT)

`hub_get_stable_theme_members("Software Infrastructure")` during RTH returned:

- **TOP** slice containing FROG at **-6.3% ret_1d** (the WORST 1d return in the entire returned set)
- **BOTTOM** slice containing NET at **+0.7% ret_1d** (the BEST 1d return in the entire returned set)

The dashboard theme drawer rendered this faithfully under an "AS OF LIVE · 0S OLD" chip. Root cause is server-side. The UI is innocent but compounds it by claiming one freshness for two data vintages.

## Root cause (confirmed in source)

`backend/services/read_only/stable.py` → `get_theme_members()`:

1. Members are ranked on **nightly** `ret_1d` (last close) — correct per AEGIS slice-then-fetch cost bound (Brief 3, Task 5).
2. The top+bottom slice gets a **live price overlay** during RTH; `ret_1d` and `last_price` are recomputed from live prices.
3. The code then re-sorts `slice_members` and — per its own comment — intends to "re-derive top/bottom from it." **It doesn't.** The two list comprehensions map the ORIGINAL `top_slice` / `bottom_slice` membership through `by_ticker`, which only swaps in the value-refreshed objects. Membership and ordering stay frozen at last-close ranking while displayed numbers go live. On any reversal day the lists invert.

## Task 1 (MANDATORY): actually re-derive top/bottom after overlay

File: `backend/services/read_only/stable.py`, inside `get_theme_members()`, in the `if live:` block.

**FIND (exact):**
```python
                # Re-sort just the (small) live-updated slice; re-derive top/bottom from it.
                slice_members.sort(key=lambda m: (m.get("ret_1d") is None, -(m.get("ret_1d") or 0.0)))
                by_ticker = {m["ticker"]: m for m in slice_members}
                top_slice = [by_ticker.get(m["ticker"], m) for m in top_slice]
                bottom_slice = [by_ticker.get(m["ticker"], m) for m in bottom_slice]
```

**REPLACE WITH:**
```python
                # Re-sort the (small) live-updated slice and ACTUALLY re-derive
                # top/bottom membership from the re-sorted order. The prior code
                # refreshed values but kept nightly membership -> top/bottom
                # inversion on reversal days (2026-07-21 Software Infrastructure
                # incident: best 1d name rendered in BOTTOM, worst in TOP).
                slice_members.sort(key=lambda m: (m.get("ret_1d") is None, -(m.get("ret_1d") or 0.0)))
                top_slice = slice_members[:top]
                bottom_slice = slice_members[-bottom:][::-1] if slice_members else []
```

Semantics preserved: `top_slice` best-first, `bottom_slice` worst-first, overlap allowed when roster < top+bottom (same as the pre-overlay path).

**Known residual limitation (accepted, document in the function docstring):** the CANDIDATE POOL is still selected from last-close ranking before the live fetch (AEGIS cost bound). A ticker that was mid-pack at close but is today's true extreme won't appear. Task 1 guarantees the returned lists are internally consistent (invariant below); it does not widen the pool. Pool widening is Task 4 (optional).

## Task 2 (MANDATORY): `ranking_basis` provenance field

Same function. Add a `ranking_basis` key to the returned envelope so the UI and THALES can state what the ranking means:

- Overlay succeeded (`live` truthy): `ranking_basis="live"`
- Overlay skipped/failed or outside RTH: `ranking_basis=f"close@{latest}"` (the `stable_metrics` MAX(date) already in scope as `latest`)

**FIND (exact):**
```python
            return _envelope(
                as_of, anchor, False,
                theme=theme, member_count=len(members),
                top=top_slice, bottom=bottom_slice,
            )
```

**REPLACE WITH:**
```python
            return _envelope(
                as_of, anchor, False,
                theme=theme, member_count=len(members),
                top=top_slice, bottom=bottom_slice,
                ranking_basis=("live" if live else f"close@{latest}"),
            )
```

Also update the degraded/empty early returns in the same function to include `ranking_basis=None` so the response shape is stable.

**Task 2b:** `backend/hub_mcp/tools/stable_theme_members.py` — append one sentence to `DESCRIPTION`: "The ranking_basis field states what the top/bottom ranking is computed on: 'live' (RTH overlay succeeded) or 'close@YYYY-MM-DD' (last close); when it is close-based, displayed prices may still be live — read the field before citing a name as a leader or laggard."

## Task 3 (MANDATORY): frontend provenance label

File: `frontend/v2.js`, theme member drawer render. **Label text only — no layout, spacing, or component changes. Mockup gate does NOT apply. Any change beyond the lines below requires HELIOS review first.**

**FIND (exact):**
```js
    const fresh = data.anchor === 'provisional' ? `live · ${ageLabel(data.data_age_seconds)} old`
      : data.anchor === 'close' ? `${String(data.as_of || '').slice(0, 10)} close` : 'unknown';
```

**REPLACE WITH:**
```js
    const rb = String(data.ranking_basis || '');
    const fresh = data.anchor === 'provisional'
      ? (rb && rb !== 'live'
          ? `ranked @ ${rb.replace('close@', '')} close · prices live`
          : `ranked live · ${ageLabel(data.data_age_seconds)} old`)
      : data.anchor === 'close' ? `${String(data.as_of || '').slice(0, 10)} close` : 'unknown';
```

After Task 1, RTH responses will normally read `ranked live · 0s old`. The `ranked @ ... close · prices live` branch is the honest fallback when the overlay fails mid-session (ranking stays close-based in that path).

## Task 4 (OPTIONAL, P2 — ship 1-3 without it if it stalls): widen candidate pool

In `get_theme_members()`, before slicing: widen the fetched pool to `min(len(members), 2 * (top + bottom), 40)` candidates taken symmetrically from both ends of the nightly ranking, overlay, re-sort, then trim to `top`/`bottom`. Preserves the AEGIS request-derived cost bound (never roster-derived, hard cap 40). The 60s in-process memo already caps call rate. If implemented, note the widened pool in the tool DESCRIPTION.

## Task 5 (MANDATORY): regression test

Add to the backend test suite (alongside existing hub_mcp/stable tests — CC locate, e.g. `backend/hub_mcp/tests/`):

- Seed a fake theme roster (>= 12 members) with nightly `ret_1d` ranking A.
- Monkeypatch `stable_engine.live.fetch_live_prices` to return prices that INVERT the ranking, and `stable_engine.job_status.is_market_hours` to return True.
- Call `get_theme_members` and assert the invariant that failed on 2026-07-21:
  - `min(m['ret_1d'] for m in top) >= max(m['ret_1d'] for m in bottom)`
  - `ranking_basis == 'live'`
- Second case: overlay raises → assert membership matches nightly ranking and `ranking_basis == 'close@...'`.

New tests must be green. Known-red baseline is 9 (3 scanner: footprint_long / session_sweep / pullback_entry; 6 environmental: envelope / trade_ideas / hermes) — do not add to it.

## Non-goals

- Robotics/LAZR score corruption root fix (separate orphaned P3 brief — still open).
- Theme score computation / DOMINANT thresholds (score 87.4 for Software Infra is honest-but-nightly; not this defect).
- Any dashboard layout change.

## Acceptance criteria

1. During RTH, `hub_get_stable_theme_members` returned payload satisfies: min(top ret_1d) >= max(bottom ret_1d). Always.
2. `ranking_basis` present in every response shape (including degraded).
3. Theme drawer chip reads `ranked live · Ns old` (overlay ok) or `ranked @ YYYY-MM-DD close · prices live` (overlay failed), never a bare `live · 0s old` over a close-based ranking.
4. Regression tests green; red baseline unchanged at 9.

## Post-deploy verification (coordination lane runs, not CC)

1. `mcp_ping`, then `hub_get_stable_theme_members("Software Infrastructure")` during RTH — assert invariant + `ranking_basis`.
2. Toggle the Pandora connector (tool schema changed: new field).
3. Screenshot the Software Infrastructure drawer and compare against the 2026-07-21 defect screenshot.
