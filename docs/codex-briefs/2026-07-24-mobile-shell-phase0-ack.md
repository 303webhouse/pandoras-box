# PHASE 0 ACK — Pandora Mobile Shell (P0.1–P0.6)

**Author:** CC-SHELL (Claude Code) · **Filed:** 2026-07-24
**Brief:** `docs/codex-briefs/2026-07-24-brief-pandora-mobile-shell.md`
**Status:** Phase 0 complete. STOP-GATE fired and surfaced; resolved in brief v1.2.
**Standing:** This ACK is the *detailed spec*. Where it and the brief conflict, **the brief governs**; where the brief is silent, this ACK governs.

**origin/main HEAD at execution:** `74aa47f` · **SHELL design-read base:** `868ff3e` · **Read-only: confirmed.** No files written, nothing staged, no branch touched. Verification included live read-only checks (production HTTP, postgres MCP, Redis) — no writes anywhere. The `ssh-vps` bridge is still down, so one absence claim is repo-verified only (flagged below).

## STOP-GATE VERDICT: **FIRES.** P0.1, P0.2, and P0.3 each produced surprises.

Per §3, that means stop and surface. Below is what I found, including three corrections to my own draft that adversarial verification caught.

---

## The headline: a live data-loss path that exists *today*, before any Phase 1 code

GridStack 11.1.2 defaults `alwaysShowResizeHandle: "mobile"`, which resolves to `true` on any touch device. `frontend/v2.js:406-407` doesn't override it and requests `handles: 'e, se, s, sw, w'`. Consequence, read from the pinned bundle plus the pinned CDN CSS:

- **55 permanently-visible resize handles** (5 × 11 tiles) on a phone. The `e`/`w` handles are `width:10px` running the full tile height minus 30px.
- They carry `touch-action:none` and inline `z-index:100`, and `preventDefault()` on `touchstart` — so at 390px the leftmost and rightmost ~10px of the screen are **non-scrolling resize strips**, exactly where a thumb lands.
- Drag threshold is `Math.abs(dx)+Math.abs(dy) > 2` — 3px, no long-press delay.
- resize `stop` → `_triggerChangeEvent()` → `frontend/v2.js:415-418` 800ms debounce → POST `/api/layout` → `backend/api/layout.py:65-70` unconditional `ON CONFLICT DO UPDATE`.

The store is **one row, `layout_key='default'`, PRIMARY KEY, no history, no versioning, no backup.** Live row confirmed: 11 tiles, `updated_at 2026-07-24T18:17:20.897Z`.

So a stray thumb-swipe on Nick's phone today scrambles his desktop board, unrecoverably. This is derived from source, not observed on his device — it wants a real-device confirmation before anyone acts on it — but if it holds, it's independent of this build and arguably wants a same-week fix rather than waiting for Phase 1.

---

## P0.1 — `/api/layout` handler + storage · **surprises present**

Handler is `backend/api/layout.py`, mounted `prefix="/api"` at `backend/main.py:1534-1535`. Table `v2_dashboard_layout(layout_key TEXT PK, layout JSONB, updated_at TIMESTAMPTZ)` — verified against the **live** database via `information_schema`: one PK constraint, no indexes, no FKs, no triggers.

| Finding | Consequence |
|---|---|
| One row, hardcoded `_LAYOUT_KEY = "default"` (`:21`). No user/device/deck dimension. | The brief's premise is correct and worse than stated. |
| POST upsert is **unconditional** — no WHERE, no version guard, no last-writer check. `[]` passes the `is None` check and would blank the row. | T1.2's guard must be in `saveLayout()` itself. |
| `_ensure_table()` is `CREATE TABLE IF NOT EXISTS` and is the **sole** creation site — not in `init_database()`, not in any migration. | **Editing that CREATE to add a column is a silent no-op on the live DB.** It'd pass local testing and throw `column does not exist` on the first production POST. |
| The PK is on `layout_key` alone. | **The zero-migration fix is a second row** (`layout_key='mobile'`), not a schema change. This is the cheapest correct answer to the whole clobber problem and I'd make it Phase 1's default. |
| No seed row exists. | Not a `def-seed-resurrection` repeat — different failure mode (live-traffic clobber, not startup clobber). |
| GET `/api/layout` is **fully public** — no cookie, no middleware gate. Proven: unauthenticated production fetch returned 200 with the full tile JSON. | Low sensitivity (tile ids + coords), but auth is asymmetric with POST. A read-only mobile shell needs no session. One-line AEGIS note. |

Two corrections to my draft: the repo **does** have an established migration convention (22 files under `migrations/`, mirrored into `init_database()` with "keep in sync" comments) — that's where any ALTER belongs; and the "no VPS writer" claim is repo-verified only, since the ssh bridge is down. Mitigating: a VPS caller would use `X-API-Key`, not the `pivot_session` cookie, so it would 401. Don't carry it as a verified absence.

Also missed by everyone until the adversary caught it: POST has **no CSRF check**. `v2.js:424` sends `X-Requested-With` but the handler never reads it. The only barrier is `SameSite=lax` on the cookie. Fine today; relevant if Phase 2 ever adds a cross-origin mobile host.

---

## P0.2 — Route map · **the brief's stated belief is wrong**

**`/` does not serve Agora v2.** `backend/main.py:1147` `async def root()` returns `{"status":"online","service":"Pandora's Box","version":"1.0.0"}` — a JSON health payload. Confirmed by live production GET.

| Route | Serves |
|---|---|
| `/` | JSON health blob |
| `/app` | `v2.html` (the real dashboard, flipped 2026-07-13) |
| `/app/v2` | `v2.html` (alias) |
| `/app/stater` | `stater.html` |
| `/app/{mode}` | `index.html` (legacy) — catch-all at `:1864` |

**The PWA defect is the opposite shape from what §1 describes.** The brief says manifest exists but v2.html doesn't link it, and implies the fix is scoping `start_url`. Actually:

- `/app` (v2.html — the page Nick uses) links **no manifest at all**. Installing from there yields no name, no icons, no standalone display, no start_url.
- The bad `start_url: "/"` only bites installs initiated from a legacy `index.html` page.
- **Zero `apple-touch-icon` / `apple-mobile-web-app-*` tags in any HTML file** — required for iOS Add-to-Home-Screen, which is the Done-Definition item.
- **No service worker anywhere** — no `sw.js`, no `register()` call. Android Chrome will not offer a real install prompt without one; iOS will. Ruling 4 defers SW to Phase 2, which means **Phase 1's "Add to Home Screen opens standalone with the Pandora icon" is achievable on iPhone only.** That's fine — Nick's device is an iPhone — but the Done Definition should say so.

If the brief scopes T1.5 as "change start_url from `/` to `/app`," it fixes a page Nick doesn't use and leaves the actual dashboard uninstallable.

**The verified Abacus href is `/app/analytics`** — single segment, hardcoded. Do not derive it from `window.location`: `frontend/app.js:583-595` `buildModePath` emits two-segment paths from `/app/legacy`, and `/app/legacy/analytics` returns **404 in production** (confirmed by live curl). Worse than a click hazard — `initRouting()` on `DOMContentLoaded` does a `replaceState` that can land the address bar on a 404-on-reload URL with no interaction at all.

Also: `backend/main.py:1864`'s catch-all will **swallow a new `/app/mobile` route and silently serve the legacy dashboard** — 200 OK, wrong page. It must be declared above that line, next to `/app/stater`. (Root-level asset routes like `/v2.js` are *not* affected — those sit below the catch-all and work fine. The real adjacent trap is relative asset URLs.) There's also a stale `backend/main.py.backup.20260128_130239` in the tree that poisons "only one hit" absence greps.

---

## P0.3 — GridStack 11.1.2 · **surprises present; my draft framing was wrong**

Read from a bundle sha256-matched to the exact pinned CDN URL. Nothing here is from newer docs.

**Correction to my own draft:** I had the clobber vector as *"merely loading the page on a phone would POST a collapsed layout."* That's **wrong on two independent grounds**, and I'm glad it didn't reach SHELL as-is:

1. `checkDynamicColumn()` returns `false` immediately when `columnOpts` is absent — and `v2.js:406` passes none. Today there is **no auto-collapse and no ResizeObserver at all** (`cellHeight:46` is numeric, so `_isAutoCellHeight` is false). The column-switch hazard is **latent**, armed only when T1.1 adds `columnOpts` or calls `column(1)`.
2. Even after collapse, `engine.save()` **merges the cached widest-column layout over live positions** — GridStack's own built-in anti-clobber. A collapsed grid does not emit collapsed `x/y/w`. And `nodeBoundFix` auto-populates `_layouts[12]` even with no persisted row, so the fresh-install path is covered too.

**T1.2 is still required — for different and better reasons.** Three residual leaks survive the merge:

- **`h` is not in the layout cache.** Any mobile height change writes straight into the desktop slot. This is the direct hazard for T1.1's S/M/L height presets.
- **`layoutsNodesChange()` mutates the cached desktop layout on mobile drags** — cached `y` shifted by the mobile drag delta — and `save()` then writes that corrupted cache. `makeWidget()` sets `_ignoreLayoutsNodeChange` when `column===1`; the drag path does **not**. That asymmetry is the single strongest argument for `setStatic(true)` on mobile, over and above guarding `saveLayout()`.
- If a collapsed layout ever gets stored, the `o>s` re-cache branch stops firing and the protection quietly stops applying.

Confirmed mechanics for the build:

- `columnOpts.breakpoints` **is** supported in 11.1.2. Matching is `width <= bp.w` after a descending sort, so `{c:1,w:768}` aligns exactly with `@media (max-width:768px)`.
- **`breakpointForWindow: true` is required.** Default `_widthOrContainer` uses `el.clientWidth`, not `window.innerWidth` — without it the JS and CSS breakpoints fire at different viewport widths.
- **`columnOpts.layout` has no default** — omitting it yields `'moveScale'`, not `'list'`. Must be set explicitly.
- `'list'` sorts by **position** (`y` then `x`), not DOM order — so it follows Nick's *saved* arrangement, not `v2.html`.
- `setStatic()`, `enableMove()`, `enableResize()` all exist — but **`enableMove`/`enableResize` are unconditional no-ops once `staticGrid` is truthy.** Pick one mechanism; belt-and-braces silently won't work.
- **Boot-time `change` events DO fire** (twice — constructor auto-parse and `load()`). They're unobserved only because `v2.js:414-419` wires the handler in `.finally()` *after* `grid.load()` at `:411`. **That ordering is load-bearing, undocumented, and one refactor away from re-arming a cold-load clobber.** It should become a pinned invariant with an acceptance check.

**Separately shipping defect, higher probability of biting this build than the clobber:** `v2.js:411` calls `grid.load(d.layout)` with no second argument. `addRemove` defaults to `true`, and the removal branch deletes every engine node whose `gs-id` is absent from the loaded array. All 11 tiles carry `gs-id`. **So any new tile added to `v2.html` silently vanishes from the DOM for anyone holding a saved layout row — i.e. Nick.** This needs its own task.

---

## P0.4 — Book endpoints · usable, with two real holes

Four endpoints, confirmed at `v2.js:660-663`: `/api/portfolio/balances`, `/api/portfolio/pnl`, `/api/v2/positions/greeks`, `/api/v2/positions?status=OPEN`. Drawer adds `/api/chronos/next-earnings-batch`.

**Of the six fields T2.4 specifies, the score is 3 present / 1 derivable / 2 not deliverable:**

| Field | Status |
|---|---|
| structure, DTE, opened date | Present |
| P/L% | Derivable client-side (`unrealized_pnl` / `cost_basis`) |
| **bucket** | **No column exists.** Write-only input flattened into free-text `notes` as `"Bucket: X"` and never parsed back. Live: 0 of 304 rows contain the text. `v2.js:747`'s Bucket row has **always** rendered `—`. |
| **stop** | Real column, **NULL on 20 of 20 live open positions** (also `target_1` 0/20, `tags` 0/20). |

**`/api/v2/positions/greeks` always returns zero totals** — a branch bug at `backend/api/unified_positions.py:1152-1165`: the accumulators sit in the `else:` (result is None) path where `.get()` raises. The Book tile renders `Δ 0 / Γ 0.0 / Θ 0 / V 0` — not `--` — so it reads as a measured flat-delta book rather than a broken feed. The live response also carries `stale: true`, which `v2.js:672-674` ignores. **This is an existing fake-healthy on the surface the mobile deck derives from.** Fix the branch, or render the staleness flag that's already on the wire — don't carry the greeks row forward as-is.

"Closed today" has **no server-side date or limit filter** on either path. The two sources also disagree (260 rows vs 144 in the deprecated `closed_positions`), 11 CLOSED rows have NULL `exit_date`, and partial closes never set `status='CLOSED'` at all. T2.4 needs a `since`/`limit` param or a descope — a gate decision, not a build decision. (My draft's "235 KB, not viable on cellular" was wrong: GZip is on, real wire cost is 28 KB.)

One free win: the Book tile double-fetches the open-positions payload every cycle (`v2.js:1132` and `:663`). Hoist it — no backend change.

Note for Phase 2: fixed paths under `/v2/positions` must go above the `/{position_id}` param route at `:1203`.

---

## P0.5 — Truthful sources · **verdict: OMIT both bucket chips; CB chip needs a relabel and a fourth state**

| Chip | Verdict |
|---|---|
| B2 open count | **OMIT** — no source |
| B3 count today | **OMIT** — no source |
| Circuit breaker | **Source exists**, but not safe to ship as specified |

The B1/B2/B3 caps are **real and specific** — `skills/_shared/COMMITTEE_RULES.md:149`: *"B2 $200–300 max with max 2 open; B3 $100 cap … max 2 concurrent, max 3/day, same-day close."* But they live **exclusively in the prompt/prose layer and never in runtime data.** No column, no Redis key, no analytics endpoint, and zero signal in 304 historical rows — so there's no degraded path either, and no backfill is possible. Record it as a specified future work package, not a dead end: the honest enablement is a real `bucket` column on `unified_positions` with a CHECK constraint, wired on create *and* update.

**The sharpest risk in the chip set is semantic.** Three different things in this repo are called a "circuit breaker," and the one that's implemented is not the one Nick would read:

1. **Market-risk CB** (SPY/VIX) — implemented, exposed at `/webhook/circuit_breaker/status` and `/api/board/kill-switch`.
2. **UW vendor CB** — internal, unrelated.
3. **B3 trading-discipline CB** — `COMMITTEE_RULES.md:151`: *"Two consecutive B3 losses in a single session … no further B3 entries that day."* **Not implemented as enforcement.** (Correction to my draft: a loss-streak *advisory* does exist, on the VPS at `scripts/committee_context.py:1367-1377`, injected into prompts — it's prompt-layer, not state a chip could read.)

Those two are defined **two lines apart in the same file**. A chip reading "Circuit breaker: CLEAR" next to bucket chips is a semantic fake-healthy — Nick reads his discipline stop; the system is reporting SPY/VIX. **Mandatory: label by trigger domain ("Market CB" / "SPY-VIX"), and do not group it with bucket chips.** That belongs in the brief as a named constraint, not left to the implementer.

Two more, both real: the Redis key `bias:circuit_breaker` **does not currently exist**, so today's "all clear" is the module default, not a restored value — and nothing in either response distinguishes those. And **the existing kill-switch UI fails open**: `v2.js:160-164` swallows fetch errors into `kill=null`, and `:208-211` collapses both a failed fetch and the backend's honest `{kill_switch: null}` into "CLEAR / normal", with no health dot on that cell. **Do not reuse that logic verbatim** — it needs a fourth UNKNOWN state first. It's the exact failure class the brief exists to prevent, sitting in the surface the mobile shell derives from.

---

## P0.6 (Amendment 1) — **PASS**

Zero change to all five targets between `868ff3e` and `74aa47f`. Nine commits from four lanes, none touching them. Working tree clean on all five.

**One addition:** `frontend/styles.css` is a **de-facto sixth Phase 1 target** — T1.4's deck bar needs a `padding-bottom` reserve on `.container` (`styles.css:70`) or the last tile sits permanently under a fixed bar. I checked it too: **also unchanged** across the same range. Recommend adding it to the tracked target list for future gate checks.

**Expected s6 divergence before SG-3:** yes, from unbuilt Amendment A6 / T-D1 (`/api/crypto/discipline`, currently uncommitted in the working tree) and from any SG-3 veto remediation. All of it lands in `stater.*` and `backend/main.py`. **None of it touches the five (or six) targets.** The defer-on-overlap clause does not fire. Noted without adjudicating: the committed ledger records SG-0 as Option A *descope* of the discipline endpoint, while the uncommitted amendment puts it back in scope — an S-6 lane matter, but it's why divergence is likely.

---

## What I'd change in the brief before Phase 1 is ordered

1. **T1.1's default order is unachievable as specified.** `columnChanged` touches only `x` and `w` — `y` is never modified — so collapse order is a function of **Nick's saved arrangement**, not of anything in the repo. Actual collapse yields Regime, Movers, **Index, Curve, USD**, Kairos, Book, Divergence, River, Themes, Breadth. T1.1 needs an explicit per-`gs-id` order map that overrides persisted `y`. **And the brief lists 10 modules — there are 11.** `gs-id="river"` (`v2.html:201`) is missing, which collides with Ruling 6.
2. **T1.2's justification is wrong; the guard is right.** Reframe around `h` bypassing the cache, `layoutsNodesChange` corrupting it on drag, and the always-armed touch-resize path — not around wholesale x/y/w collapse. Add `setStatic(true)` as a required mitigation alongside the `saveLayout()` guard. **Strongly consider the second-row fix** (`layout_key='mobile'`) — no DDL, and it makes the whole class of failure structurally impossible rather than guarded against.
3. **T1.3 is under-scoped.** Collapse preserves `h`, so heights stay desktop-sized while widths shrink — ~2,900px of stack with **two nested scroll containers per tile** (CDN rule + `v2.css:116`). And fixed internal grids break at 390px: `.regime-band` is 6 columns (`v2.css:122`) → ~32px of content width for 22px type. That's restructuring, not typography. `.mem-row` and `.th-row` are also under-width. Separately, `.v2-topbar` min-contents to ~420–430px with no `flex-wrap` and no `overflow-x` guard on body — the one element that forces document-level horizontal scroll.
4. **T1.4's design authority models the bar as a flex child of a fixed-height `overflow:hidden` shell**; both target pages document-scroll. The `position:fixed` reality is unmodeled — needs content-occlusion reserve, and **zero `safe-area`/`viewport-fit=cover` exist anywhere in `frontend/`**, so the bar will sit under the iPhone home indicator.
5. **T1.5 needs the larger fix set** (manifest link on v2.html + apple tags + `start_url`), and the Done Definition should say iOS-only for standalone install, since Android needs the deferred SW.
6. **Two pre-existing defects should be decided on, not inherited:** the `grid.load()` tile-deletion behavior, and the all-zero greeks endpoint.

---

**Hard stops honored.** No code written. Phase 2 untouched. Freeze law (08-04 → 08-15) unchallenged.

---

## Verification provenance

Findings were produced by an initial read, then independently re-derived and adversarially attacked by a multi-agent verification pass (11 agents: 5 independent verifiers, 5 refuters, 1 completeness critic; 0 errors). Three of my draft claims were corrected by that pass and are marked inline above. Live read-only checks included production HTTP, postgres MCP, and Redis; the pinned GridStack 11.1.2 bundle was sha256-matched to its CDN URL rather than read from newer documentation.
