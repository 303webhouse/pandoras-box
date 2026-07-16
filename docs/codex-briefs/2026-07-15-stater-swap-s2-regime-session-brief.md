# Brief S-2 — Stater Swap v2: Regime & Session Layer (R-1)

**Date:** 2026-07-15 | **Executor:** Claude Code | **Coordination:** Fable (Nick's coordination lane)
**Repo path for this brief:** `docs/codex-briefs/2026-07-15-stater-swap-s2-regime-session-brief.md`
**Predecessor:** S-1 (R-0 Foundation) — CLOSED, both sign-offs on record (`docs/strategy-reviews/stater-swap-redesign/s1-closure-note.md`; stamping the sign-offs is task D-1 of THIS brief)
**Sources (binding, in priority order):**
1. `docs/strategy-reviews/stater-swap-redesign/2026-07-12-stater-swap-v2-committee-brief.md` — Part 4 R-1 + Addendum A-2/A-3 (regime hierarchy, tiers)
2. Titans Review Record 2026-07-13 — S-2 carry-forward obligations (quoted verbatim in §1; the record file itself is a D-2 recovery target)
3. `PROJECT_RULES.md` — Data Source Hierarchy (crypto rows), Deployment Verification, Development Principles, Anti-Bloat Framework
4. `docs/strategy-reviews/stater-swap-redesign/symbol-capability-matrix.md` + `backend/config/crypto_symbol_matrix.py` — per-symbol data coverage
5. `docs/strategy-reviews/stater-swap-redesign/s1-closure-note.md` — S-1 shipped state (F-1..F-5), open threads

**Titans status:** Full Pass 1 / Pass 2 / ATHENA Overview completed 2026-07-13 (no vetoes, PROCEED, HIGH). This brief received its Titans **final review** in the coordination lane on 2026-07-15 — verdicts embedded in §12. No further review gate before CC execution.

---

## 0. What S-2 builds (one paragraph)

The R-1 "alpha decision" layer: a per-symbol crypto **regime classifier** (50-DMA + ADX + DMA slope → TREND_UP / CHOP / TREND_DOWN, BTC as master gate for all crypto risk) and a first-class **session engine** (continuous ASIA/LONDON/NY partition + the five event windows, IANA-anchored, dual-labeled UTC × America/Denver), both **shadow-logged** to Postgres, plus a **config-driven, hot-reloadable gate matrix** evaluated in shadow against every crypto signal flowing through `process_signal_unified`. Gating enforcement code ships **behind a flag that stays FALSE** — nothing in S-2 changes live signal behavior. The shadow logs are the validation dataset that later earns the flag-flip (validation bar in §10, not executed in S-2).

### Scope fences — S-2 is explicitly NOT:
- **Not a UI build.** Zero frontend changes. The MOCKUP GATE (HELIOS standing veto) governs S-6; the session "clock" ships here as a **data contract only** (API payload, §7). The parallel mockup track has its own charter: `docs/strategy-reviews/stater-swap-redesign/helios-mockup-track.md`.
- **Not the vendor-client parametrization.** The four `bias_filters/*_client.py` modules stay BTC-hardcoded (R-2/R-3 lift per the matrix doc's Cross-cutting note #1). S-2's only market-data dependency is **daily OHLCV bars via the existing per-symbol routing** (§4.2).
- **Not ticker-ingress normalization** (R-2). S-2 defensively canonicalizes its *own* keys via the existing `normalize_crypto_ticker()`.
- **Not the dominance / ETH-BTC / alt-breadth strip** (R-4 data). A-3 promoted it to a Tier-2/3 gating *input*; S-2 reserves the config slot and satisfies A-3's stated minimum bar ("at minimum BTC-regime-not-down") using the BTC master regime alone. The slot reads `NOT_AVAILABLE` — honestly — until R-4 ships the data.
- **Not new hub MCP tools.** No connector re-toggle, no committee re-test required this brief (standing carry-forward applies only to briefs that ship hub tools).
- **Not strategy retunes** (R-3). The gate matrix *classifies* existing strategies; it does not modify them.

---

## 1. Binding carry-forward obligations (Titans record, 2026-07-13 — verbatim)

| Brief | Obligation | Owner lane |
|---|---|---|
| S-2 | R-1 regime/session gates config-driven, hot-reloadable; regime states shadow-logged for validation before gating goes live | ATLAS |
| S-2 | Session clock Denver-localized or dual-labeled (UTC sessions × America/Denver user) | HELIOS |

How this brief discharges them: **hot-reloadable** = append-only Postgres config table + in-process loader with a ≤60s TTL cache — a config change is a SQL INSERT, takes effect within one TTL, **no redeploy** (§5.3, verified by Done item 8). **Shadow-logged before gating** = `crypto_regime_log` + `crypto_gate_shadow` populate from day one; `gating_enabled=false` in the seed config and stays false through S-2 closure (§5, §6, Done items 6/7/11). **Denver-localized/dual-labeled** = every session window and state object carries precomputed `utc` AND `america_denver` label strings, DST-safe via IANA `zoneinfo` (§6, §7 payload contract, Done item 9).

---

## 2. Hard rules for this brief

1. **Shadow-only.** `gating_enabled=false` at seed and at closure. No live signal may be blocked, dismissed, rescored, or altered by anything S-2 ships. Done item 11 proves it.
2. **Fail visible — never fake-neutral.** Missing/stale bars → `regime_state='UNKNOWN'` with `degraded=true` + `degrade_reason`. NEVER default to CHOP, never coerce nulls to values, never serve a regime computed from stale bars without labeling it. (House precedent: rs_10d fabricated-zero incident; matrix doc's "never fake-neutral, never silently blank.")
3. **IANA timezones only.** `zoneinfo` with `America/Denver`, `America/New_York`, `America/Chicago`, `Europe/London`, UTC. **No hardcoded UTC offsets anywhere** — DST is exactly the bug class this rule kills.
4. **Sanctioned bar routing only.** Daily bars per symbol via the existing S-1/F-2 routing (UW OHLC for BTC/ETH/SOL; Binance spot klines for ZEC; OKX candles for HYPE/FARTCOIN — PROJECT_RULES crypto rows). **No new yfinance-crypto call sites** (PROJECT_RULES explicit ban). No calls to the four BTC-hardcoded vendor clients.
5. **Non-blocking hook.** The shadow gate evaluator inside the unified signal path is wrapped so that ANY evaluator exception logs and continues — a shadow-logging failure must never break a signal write. Done item 10 includes a failure-injection proof.
6. **Migration discipline.** One migration (expected number **025** — confirm next free number in Phase 0), explicit `-- DOWN` block. Additive only: no changes to `signals`, `signal_outcomes`, `unified_positions`, or any existing table.
7. **Repo discipline.** `git fetch && git status` before work. Pathspec-only commits (never `git add .`). Commit messages via `C:\temp\commitmsg.txt` + `git commit -F`, `cmd` shell for git. Empty-safe env vars (`os.getenv("VAR") or default`).
8. **Deploy window.** Pushes to `main` redeploy Railway (~60–170s hub downtime). Prefer outside 09:30–16:00 ET / 07:30–14:00 MT on trading days. Nick may override explicitly (precedent: 2026-07-13); absent an override, hold pushes to outside the window.
9. **Deployment verification is 4 steps, every time** (PROJECT_RULES): (1) Railway deploy status SUCCESS; (2) deploy SHA == pushed SHA; (3) **empirical side effect of the new code observed on the running service** — `/health = OK` is NOT proof; (4) if silent >5 min, pull `railway logs` and check. A phase is not done until step 3 is confirmed.
10. **ACK contract.** Completion report (files, commits, evidence per Done item, deviations) is required. Silent completion is a contract violation.
11. **Bypass-retirement tracker check.** S-2 touches `bias_scheduler.py` (job registration). Per the S-1 closure note's standing instruction, run `scripts/crypto_dual_write_diff_report.py` first and record its output in the Phase-0 findings — whoever touches the Crypto Scanner's neighborhood checks the tracker.

---

## 3. Phase 0 — read-only reconnaissance (gate: findings committed before any Phase 1+ code)

Output: `docs/strategy-reviews/stater-swap-redesign/s2-phase0-findings.md`, file:line evidence for every claim, committed before Phase 1 begins. No code changes in Phase 0 except the D-tasks (§4), which are docs-only and may ride in the same commit window.

- **0.1 — Locate the equity regime classifier** the committee named as the mirror target ("mirroring the shipped equity regime classifier" — PYTHAGORAS, committee brief Part 2). Record module path, its state taxonomy, thresholds, and cadence. Also map ALL existing regime-adjacent crypto logic so S-2 doesn't create a competing truth: the CTA-zone classifier (`scanners/cta_scanner.py` — source of the CAPITULATION/WATERFALL reads), Brief-2E's regime pre-filter, and anything else that labels crypto regime. **Mandate:** S-2's classifier becomes the canonical crypto regime for gating; existing logic is documented, not modified.
- **0.2 — Daily-bars availability, live-checked per symbol.** Confirm the S-1/F-2 bar routing (`backend/jobs/crypto_bars.py` and neighbors) supports **daily (1d) interval for all six symbols**, then pull real counts from the running environment: require **≥120 daily bars** available per symbol from its sanctioned source (BTC/ETH/SOL via UW `/ohlc/1d`; **ZEC via Binance spot klines 1d — the known unverified edge**, S-1 verified 15m only; HYPE/FARTCOIN via OKX 1d candles). Record actual counts. Any symbol short of 120 → note it; short of 60 → that symbol launches in permanent-UNKNOWN until history accrues (fail visible, not fake-neutral).
- **0.3 — Scheduler pattern.** How jobs register in `bias_scheduler.py` (or wherever the crypto scan's every-5-min cadence lives); where an hourly job hooks in cleanly; how job-level disable flags are done today.
- **0.4 — Existing session windows.** Read the `/btc/sessions` route + backing implementation. Inventory the five windows (Asia Handoff, London Open, Peak Volume, ETF Fixing, Friday CME Close): exact boundaries, whether they're hardcoded UTC (expected), and what consumes them today. Record the route's **auth posture** — S-2's new read endpoints mirror it exactly.
- **0.5 — Config patterns.** Does a DB-backed hot-reload config pattern already exist anywhere in the codebase? (Known adjacent patterns: Redis watchdog flags, `backend/config/*.py` static configs.) If a reusable pattern exists, reuse it and say so; if not, §5.3's design stands.
- **0.6 — Strategy-name inventory.** The distinct crypto strategy identifiers currently flowing through `process_signal_unified`: from code (crypto_setups.py strategies, TV webhook strategies, Crypto Scanner strategies) AND from data (`SELECT DISTINCT` on recent crypto-class signals). The seed gate matrix (§6.3) is keyed on these — reconcile its keys to reality and note any mismatch (config is editable, so mismatches are a config fix, not a code fix).
- **0.7 — Hook point.** The exact file:line in `process_signal_unified`'s crypto branch (post-F-4 cutover, commit `47b4a79`) where the shadow gate evaluator will be called, and the exact mechanism the existing **conflict-dismissal** path uses to persist a dismissed signal (status value, reason field, feed exclusion) — §6.4's flag-off enforcement branch reuses that mechanism verbatim when it someday goes live.
- **0.8 — Docs recovery sweep** (feeds D-2): search the local working tree (`C:\trading-hub\docs\`, recursive) for `2026-07-13-stater-swap-s1-foundation-brief.md` and `2026-07-13-titans-review-stater-swap-v2.md`. Both are referenced by committed docs but **404 on origin/main** (verified 2026-07-15 — the Drogen-note failure mode, again). Record found/not-found with paths.
- **0.9 — Known-red test baseline.** Run the suite once, record the actual baseline. Expectation to verify, not gospel: **8 red** (2 scanner: `footprint_long`, `pullback_entry` — `session_sweep` was fixed in S-1; 6 environmental: envelope/trade_ideas/hermes). S-2's Done item 13 compares against THIS recorded baseline.
- **0.10 — Bypass-retirement tracker** output recorded (hard rule 11).

---

## 4. Docs tasks D-1..D-3 (D-1 is the FIRST task of this brief; all three are exact-anchor edits or bounded checks)

### D-1 — Stamp the S-1 closure note with both sign-offs (FIRST docs task)

File: `docs/strategy-reviews/stater-swap-redesign/s1-closure-note.md`

Find (exact, unique — the final sentence of the `## Sign-off` section):

```
Awaiting Nick/Fable's formal acknowledgment before R-1 work begins, per the brief's own gate ("Nothing in R-1+ may start until this brief's Done definition is met").
```

Replace with:

```
Both acknowledgments are now on record and the gate ("Nothing in R-1+ may start until this brief's Done definition is met") is cleared:

- **Nick — SIGNED, 2026-07-15 22:28Z (16:28 MDT).** Empirical connector check: Pandora connector re-toggled post-tool-ship; `hub_get_crypto_quote("BTC-USD")` returned live Bitcoin (fresh timestamp, clean v2.0 envelope, correct asset) through Nick's own Claude.ai connector — the Done-item-10 connector-visibility condition is satisfied.
- **Fable — COUNTERSIGNED, 2026-07-15.** The "pending one connector-visibility check" condition attached to the item-10 countersign is resolved by the same check. S-1 is formally closed.

R-1 work (Brief S-2, `docs/codex-briefs/2026-07-15-stater-swap-s2-regime-session-brief.md`) is cleared to begin.
```

### D-2 — Recover the two uncommitted 2026-07-13 artifacts (or record the gap)

Both files are cited by committed docs but do not exist on `origin/main` (verified 2026-07-15):
- `docs/codex-briefs/2026-07-13-stater-swap-s1-foundation-brief.md` — named as **Brief:** in the closure note header
- `2026-07-13-titans-review-stater-swap-v2.md` — the Titans review record (expected home: `docs/strategy-reviews/stater-swap-redesign/`)

Action: per the 0.8 sweep — if found in the local tree (untracked), commit each to its cited/expected path (pathspec-only). If not found locally, record NOT FOUND in the Phase-0 findings with the note: *"Fable can re-materialize both from the 2026-07-13 coordination-session record — same recovery path as the Drogen note."* Do NOT reconstruct their content yourself.

### D-3 — ZEC caveat touch-up in the capability matrix (closes the stale-caveat thread the closure note flagged)

File: `docs/strategy-reviews/stater-swap-redesign/symbol-capability-matrix.md` — two exact-anchor edits.

Edit 1 — summary table ZEC row. Find (exact, unique):

```
| ZEC | 3 | LIVE | UNAVAILABLE | GEO_BLOCKED → OKX LIVE | LIVE | LIVE (quote only) | UNAVAILABLE → fixed | Binance spot klines (deferred verify) — **not UW** |
```

Replace with:

```
| ZEC | 3 | LIVE | UNAVAILABLE | GEO_BLOCKED → OKX LIVE | LIVE | LIVE (quote only) | UNAVAILABLE → fixed | Binance spot klines (live-verified S-1 Phase 2) — **not UW** |
```

Edit 2 — Finding 3 closing sentence. Find (exact, unique):

```
ZEC's recommended bar-walk source is Binance spot klines (ZEC is confirmed listed on Binance spot, unlike HYPE/FARTCOIN) — the exact candle-history pull wasn't independently verified in this pass and is deferred to F-2 implementation, noted honestly as such rather than assumed.
```

Replace with:

```
ZEC's recommended bar-walk source is Binance spot klines (ZEC is confirmed listed on Binance spot, unlike HYPE/FARTCOIN). Update (S-2 docs pass, 2026-07-15): the candle-history pull WAS live-verified during S-1 Phase 2 — 5 real 15m candles pulled pre-wiring (`s1-phase2-findings.md`, "Pre-wiring verification") — this line originally deferred that verification and is corrected here rather than left stale. Note: 15m interval was what Phase 2 verified; the 1d interval S-2's regime classifier needs is live-checked in `s2-phase0-findings.md` §0.2.
```

---

## 5. Phase 1 — schema + config (migration 025)

One migration, three tables, explicit `-- DOWN`. Additive only. Expected number 025 (Phase 0 confirms next free).

### 5.1 `crypto_regime_log` (append-only shadow log; heartbeat rows every evaluation)

| column | type | notes |
|---|---|---|
| id | bigserial PK | |
| computed_at | timestamptz | evaluation wall-clock |
| symbol | text | canonical form via `normalize_crypto_ticker()` (e.g. `BTC-USD`) |
| tier | smallint | 1/2/3 from `crypto_symbol_matrix.py` |
| is_master | boolean | true on the BTC row only |
| regime_state | text | `TREND_UP` / `CHOP` / `TREND_DOWN` / `UNKNOWN` |
| price | numeric | close used for classification |
| dma50 | numeric | nullable — null only when UNKNOWN |
| price_vs_dma50_pct | numeric | nullable |
| adx14 | numeric | nullable |
| dma50_slope_pct | numeric | nullable — see §6.1 definition |
| bars_source | text | `UW_OHLC` / `BINANCE_SPOT` / `OKX` |
| bars_as_of | timestamptz | timestamp of latest bar used |
| bar_count | integer | bars available at compute time |
| data_age_seconds | integer | now − bars_as_of |
| degraded | boolean | |
| degrade_reason | text | nullable; REQUIRED non-null when degraded or UNKNOWN |
| session_partition | text | ASIA / LONDON / NY at computed_at |
| event_windows | text[] | active event windows at computed_at (may be empty) |
| weekend_holiday_flag | boolean | |
| config_version | integer | FK-by-convention to `crypto_gate_config.id` |
| changed | boolean | regime_state differs from this symbol's previous row |

Indexes: `(symbol, computed_at DESC)`; partial on `(changed) WHERE changed`.

### 5.2 `crypto_gate_shadow` (one row per gate evaluation of a signal)

| column | type | notes |
|---|---|---|
| id | bigserial PK | |
| evaluated_at | timestamptz | |
| signal_id | text | the signal's identifier as persisted by the unified path |
| symbol | text | canonical form |
| tier | smallint | |
| strategy | text | as emitted (also store `strategy_canonical` if 0.6 finds aliasing) |
| direction | text | LONG / SHORT / other-as-emitted |
| regime_master | text | BTC regime at eval |
| regime_symbol | text | per-symbol regime at eval |
| session_partition | text | |
| event_windows | text[] | |
| weekend_holiday_flag | boolean | |
| alt_gate | text | `NOT_AVAILABLE` in S-2 (R-4 slot) |
| verdict | text | `WOULD_PASS` / `WOULD_BLOCK` |
| reasons | text[] | e.g. `{BTC_TREND_DOWN_T3_BLOCK, SESSION_WINDOW}` — advisory notes included (e.g. `SIZE_REDUCE_WEEKEND`) |
| config_version | integer | |

Index: `(evaluated_at DESC)`; `(strategy, verdict)`.

### 5.3 `crypto_gate_config` (append-only versions = hot-reload + audit trail + rollback)

| column | type | notes |
|---|---|---|
| id | serial PK | **the config_version** |
| created_at | timestamptz default now() | |
| created_by | text | free-text: `SEED_S2` / `nick-sql` / etc. |
| note | text | one-line why |
| config | jsonb | the full payload (§6.3 seed) |

**Loader contract:** read the max-`id` row; in-process cache with TTL **60s**; every regime row and gate-shadow row stamps the `config_version` it used. Hot-reload = `INSERT` a new row (never UPDATE in place — prior versions are the audit trail; rollback = re-INSERT an older payload). No write endpoint ships in S-2 — config changes are SQL-only.

**Seed row (version 1):** the §6.3 JSON with `"gating_enabled": false`, `created_by='SEED_S2'`. Seed via idempotent `INSERT ... WHERE NOT EXISTS` in the migration, or a separate idempotent seed script — CC's call, state which in the findings.

---

## 6. Phase 2–4 — the three engines

### 6.1 Regime classifier (Phase 2) — suggested home `backend/jobs/crypto_regime.py` (pure classification logic importable; adjust placement only with Phase-0 rationale)

Per symbol, hourly (scheduler registration per 0.3; job-level disable flag per existing pattern):

1. Fetch daily bars via the existing per-symbol routing (0.2). Request ≥120; compute requires ≥60 (50-DMA + 10-bar slope lookback) — below 60 → `UNKNOWN`, `degraded=true`, `degrade_reason='INSUFFICIENT_HISTORY:<n>'`. 60–119 bars → compute, but `degraded=true`, `degrade_reason='THIN_HISTORY:<n>'` (ADX-14 Wilder smoothing is unstable on short history — be honest about it).
2. Compute: `dma50`; `price_vs_dma50_pct`; `adx14` on daily OHLC; `dma50_slope_pct = (dma50_now − dma50_10_bars_ago) / dma50_10_bars_ago × 100`.
3. Classify per config thresholds (seed: `slope_threshold_pct: 0.5`, `adx_trend_min: 20`):
   - `TREND_UP` — price > dma50 AND slope ≥ +threshold AND adx ≥ adx_trend_min
   - `TREND_DOWN` — price < dma50 AND slope ≤ −threshold AND adx ≥ adx_trend_min
   - `CHOP` — anything else with valid inputs
   - `UNKNOWN` — missing/insufficient/stale inputs (staleness seed: bars_as_of older than 48h → UNKNOWN with `degrade_reason='STALE_BARS:<age>'`). **UNKNOWN is never silently mapped to CHOP.**
4. Write a `crypto_regime_log` row every evaluation (heartbeat), `changed` computed vs. the symbol's prior row. BTC's row carries `is_master=true`.
5. Also stamp the row with session context (§6.2) at compute time.

All thresholds live in config (hot-reloadable) and are **shadow-window hypotheses** — the 14-day shadow exists to tune them without redeploys.

### 6.2 Session engine (Phase 3) — pure functions, suggested home `backend/utils/crypto_sessions.py`

Config-defined (all windows in the §6.3 JSON; Phase 0's inventory of the current `/btc/sessions` hardcoded windows seeds the values):

- **Continuous partition** (PYTHIA spec, fixed-UTC by crypto convention): ASIA 00:00–08:00, LONDON 08:00–16:00, NY 16:00–24:00 UTC. Every timestamp maps to exactly one.
- **Event windows** (flags, may overlap the partition): Asia Handoff, **London Open (anchored `Europe/London`)**, Peak Volume, **ETF Fixing (anchored `America/New_York`)**, **Friday CME Close (anchored `America/Chicago`)** — venue-tied windows are IANA-anchored so DST moves them correctly; convention-tied windows may stay fixed-UTC per the Phase-0 inventory. Config schema carries `anchor_tz` per window; **no hardcoded offsets in code**.
- **Weekend/holiday flag:** Saturday/Sunday in `America/New_York` terms, plus a config `holiday_dates` list (seed: 2026 US market holidays remaining: Sep 7, Nov 26, Dec 25). Flag semantics: thin-liquidity advisory → `SIZE_REDUCE_WEEKEND` reason in gate output; **never a block** in the seed.
- **`get_session_state(ts) →`** object per the §7 payload contract, with **dual labels** — every window/state carries `utc` and `america_denver` display strings, computed via `zoneinfo` (never string math).
- **Unit tests (required, part of Done item 9):** UK DST spring/fall boundary days (London Open moves in UTC), US DST boundaries (ETF Fixing / CME Close move in UTC), a Friday CME-close window, Denver dual-label correctness on both MDT and MST dates, partition edges at 08:00/16:00/00:00 UTC.

### 6.3 Gate config seed (version 1 — full JSON, committed as the seed row)

```json
{
  "gating_enabled": false,
  "regime": { "slope_threshold_pct": 0.5, "adx_trend_min": 20, "slope_lookback_bars": 10, "stale_bars_max_hours": 48, "min_bars_compute": 60, "thin_history_bars": 120, "recompute_minutes": 60 },
  "tiers": { "BTC-USD": 1, "ETH-USD": 1, "SOL-USD": 2, "HYPE-USD": 3, "ZEC-USD": 3, "FARTCOIN-USD": 3 },
  "master_rules": {
    "btc_trend_down_blocks_tier3_all_entries": true,
    "btc_trend_down_blocks_tier2_longs": true,
    "unknown_master_blocks_regime_dependent": true
  },
  "alt_gate": { "status": "NOT_AVAILABLE", "note": "R-4 dominance/ETH-BTC/alt-breadth strip; A-3 minimum bar (BTC-regime-not-down) enforced via master_rules until then" },
  "strategy_classes": {
    "momentum_continuation": { "strategies": ["holy_grail"], "long_allowed_in": ["TREND_UP"], "short_allowed_in": ["TREND_DOWN"] },
    "fade_mean_reversion": { "strategies": ["funding_rate_fade", "exhaustion"], "long_allowed_in": ["CHOP", "TREND_UP"], "short_allowed_in": ["CHOP", "TREND_DOWN"] },
    "sweep_reclaim": { "strategies": ["session_sweep"], "long_allowed_in": ["CHOP", "TREND_UP"], "short_allowed_in": ["CHOP", "TREND_DOWN"], "requires_event_window": true },
    "cascade_fade": { "strategies": ["liquidation_flush"], "long_allowed_in": ["CHOP", "TREND_UP"], "short_allowed_in": ["CHOP", "TREND_DOWN"] },
    "unclassified": { "strategies": ["*"], "policy": "WOULD_PASS_WITH_NOTE" }
  },
  "sessions": {
    "partition_utc": { "ASIA": [0, 8], "LONDON": [8, 16], "NY": [16, 24] },
    "event_windows": "SEED_FROM_PHASE0_INVENTORY — carry each window's boundaries + anchor_tz here",
    "holiday_dates": ["2026-09-07", "2026-11-26", "2026-12-25"]
  },
  "advisories": { "weekend_holiday_size_reduce": true }
}
```

Notes: strategy identifiers above are **expectations** — Phase 0.6 reconciles them to the real emitted names; unknown strategies fall to `unclassified` → `WOULD_PASS` with a `UNCLASSIFIED_STRATEGY` note (visible in shadow, never a silent gap). Classification of `exhaustion` as fade-class is a seed hypothesis — the shadow window exists to test exactly this kind of call. The `event_windows` placeholder MUST be replaced with the real Phase-0 inventory before the seed row is inserted.

### 6.4 Shadow gate evaluator (Phase 4) — suggested home `backend/bias_filters/crypto_gates.py`, hooked per 0.7

`evaluate_gates(signal_context)` runs inside `process_signal_unified`'s crypto branch, AFTER the signal is persisted, wrapped per hard rule 5 (exception → log → continue):

1. Canonicalize ticker (`normalize_crypto_ticker()`); resolve tier; read latest regime rows (master + symbol) and `get_session_state(now)`; load config (TTL cache).
2. Apply, in order: master rules → per-symbol strategy-class rule → session requirement (`requires_event_window`) → advisories. UNKNOWN regime on a regime-dependent evaluation → `WOULD_BLOCK`, reason `REGIME_UNKNOWN` (conservative and honest: a gate that can't see the regime can't pass — and frequent `REGIME_UNKNOWN` in shadow is itself a data-quality alarm).
3. Write one `crypto_gate_shadow` row. Never mutate the signal. Never write to `signals`.
4. **Flag-off enforcement branch (ships dormant):** `if config.gating_enabled and verdict == WOULD_BLOCK` → persist-then-dismiss via the **exact existing conflict-dismissal mechanism** (0.7), `dismiss_reason='REGIME_GATE:' + reasons` — rows always exist and are feed-excluded (Holy-Grail-treatment precedent); never a silent drop. Unit-tested behind the flag; **the flag stays false** — flipping it is §10's separately-gated act, not S-2's.

---

## 7. Phase 5 — read endpoints (data contracts for S-6; no UI ships here)

Auth posture: mirror the existing crypto read routes exactly (0.4). Payloads contain regime/session/config-version data ONLY — no positions, no account data, no credentials, no env values.

- **`GET /api/crypto/regime`** → `{ as_of, config_version, master: {symbol:"BTC-USD", regime_state, computed_at, data_age_seconds, degraded, degrade_reason}, symbols: [ per-symbol same shape + tier ] }` — served from the latest `crypto_regime_log` rows; `data_age_seconds` computed at request time (a frozen job must LOOK frozen — no caching that hides staleness).
- **`GET /api/crypto/clock`** → `{ as_of_utc, as_of_denver, partition, event_windows_active: [...], next_transitions: [ {window, at_utc, at_denver} ... ], weekend_holiday_flag }` — every timestamp field dual-labeled (HELIOS carry-forward lives in THIS contract).

`/btc/sessions` stays untouched in S-2 (legacy consumer safety); its retirement is an S-6 decision.

---

## 8. Done Definition (all items required; evidence = commit, committed doc, or live query captured in the completion report)

1. **Phase-0 findings** committed (`s2-phase0-findings.md`) with file:line evidence, per-symbol daily-bar counts (0.2), strategy-name inventory (0.6), hook point + dismissal mechanism (0.7), recorded red baseline (0.9), tracker output (0.10).
2. **D-1** stamp live on `main` — quote the final Sign-off section in the report.
3. **D-2** outcome recorded — both files committed (paths + SHAs) or NOT FOUND documented in the findings with the re-materialization note.
4. **D-3** both anchor edits live on `main`.
5. **Migration 025** applied with `-- DOWN`; all three tables exist (information_schema evidence from the deployed DB).
6. **Config seeded**, `gating_enabled=false` confirmed by querying the RUNNING service's DB (not the local copy); seed `event_windows` carries the real Phase-0 inventory, not the placeholder.
7. **Regime rows real:** ≥1 full hourly cycle post-deploy; all six symbols present; for covered symbols inputs are non-null AND values differ across symbols (anti-fake-healthy: six identical or zeroed rows = FAIL); any UNKNOWN row carries a non-null `degrade_reason`; BTC row `is_master=true`.
8. **Hot-reload proven:** INSERT a benign config change (e.g. `note` bump / threshold nudge) via SQL; next regime evaluation stamps the new `config_version` within one job cycle, **zero redeploys** — evidence: the two rows.
9. **Session engine proven:** DST unit tests green (all cases in §6.2); live `/api/crypto/clock` response captured showing dual labels + correct partition; one event-window boundary spot-checked against its anchor timezone.
10. **Shadow gate end-to-end:** one tagged synthetic signal (`S2_PHASE4_GATE_SHADOW_TEST_BTC_<date>`) through `process_signal_unified` produces a `crypto_gate_shadow` row with sane fields; PLUS failure-injection proof (force an evaluator exception in a test; the signal write survives and the error is logged).
11. **Zero-live-impact assertion:** no real signal blocked/dismissed/altered by S-2 code — evidence: `gating_enabled=false` in the deployed config row, zero `dismiss_reason LIKE 'REGIME_GATE%'` rows, and a before/after count sanity check across the deploy.
12. **Deployment verification** — all 4 steps (hard rule 9); the step-3 empirical side effect is items 7 + 9's live evidence.
13. **Known-red baseline unchanged** vs. the 0.9 recording. New reds → fix or root-cause-document before closure (S-1 precedent).
14. **Completion report + ACK** — files touched, commits, per-item evidence, deviations with rationale.

## 9. Rollback

Migration `-- DOWN` drops the three tables. Scheduler job behind a disable flag (0.3 pattern). Endpoints additive (removable). Evaluator hook = one call site (0.7). **No canonical table is written or altered** — `signals`, `signal_outcomes`, `unified_positions` untouched by S-2 (the dormant enforcement branch writes only via the existing dismissal mechanism, and only when a future config flip enables it).

## 10. Shadow validation bar — recorded here, NOT executed in S-2

Gating goes live only after ALL of: (a) **≥14 days** of shadow regime logs AND **n≥100** `crypto_gate_shadow` rows on real (non-synthetic) signals; (b) flip-flop sanity — regime `changed` transition rate reviewed, no thrash; (c) **anti-bloat subtractive test** (PROJECT_RULES): WOULD_BLOCK verdicts would have reduced weekly crypto signal count by **≥30% while holding or improving expectancy** (join shadow verdicts to `outcome_source='BAR_WALK'` outcomes); (d) explicit **Nick greenlight**. The flip itself is a config INSERT (`gating_enabled=true`) + a post-flip verification checklist (first real REGIME_GATE dismissal inspected end-to-end; Discord/feed exclusion confirmed; one-week review) — a micro-brief-sized act, deliberately outside S-2.

## 11. Olympus impact

**None this brief.** No hub MCP tools ship → no connector re-toggle, no BTC/SPY committee re-test mandated (standing carry-forward applies to hub-tool briefs only). No committee skill files touched; the seven `references/crypto.md` stubs stay stubbed until post-R-2 per PROJECT_RULES. Committee-facing exposure of regime state (a `hub_get_crypto_regime`-class tool) rides with R-2's PYTHIA-parity hub work, where the re-toggle + re-test obligations will apply.

---

## 12. Titans Final Review — 2026-07-15, coordination lane (Pass 1/Pass 2/Overview completed 2026-07-13; this is the brief-stage gate)

```
ATLAS — BRIEF FINAL REVIEW
BRIEF: docs/codex-briefs/2026-07-15-stater-swap-s2-regime-session-brief.md
CC-ACTIONABLE: YES — investigation-gated where code state is unknown (0.1–0.7), exact anchors where docs are known (D-1/D-3), schema + seed config fully specified.
GATES PRESENT: YES — Phase-0 commit gate, migration -- DOWN, 4-step deployment verification, failure-injection proof, zero-live-impact assertion.
SCOPE MATCHES PASS 2 AGREEMENT: YES — discharges both S-2 carry-forward rows; A-3 handled via master_rules + honest NOT_AVAILABLE alt_gate slot; vendor-client parametrization correctly fenced to R-2/R-3.
OLYMPUS IMPACT SECTION: Present + accurate (none; hub-tool obligations correctly deferred to R-2).
NOTES: (1) Canonical-table impact analysis present and clean — three new tables, zero writes to signals/signal_outcomes/unified_positions in shadow. (2) Append-only config-as-versions is the right hot-reload shape: audit trail and rollback come free. (3) Enforcement-branch-behind-flag is acceptable ONLY because the dismissal path reuses the existing conflict-dismissal mechanism verbatim (0.7) and Done 11 proves dormancy — a novel dismissal path behind a flag would have been a finding. (4) Bar-count Phase-0 check (0.2) correctly treats ZEC 1d as the unverified edge. Final-review constraint noted honestly: run from the coordination lane without a fresh local read of backend files — compensated by the hard Phase-0 gate, per house pattern.
APPROVE FOR CC: YES.

AEGIS — BRIEF FINAL REVIEW
BRIEF: docs/codex-briefs/2026-07-15-stater-swap-s2-regime-session-brief.md
CC-ACTIONABLE: YES.
SECRET HANDLING ADDRESSED: YES — no new credentials; bar routing reuses existing keys by env-var name only; brief prints no credential values; endpoint payloads exclude account/credential data by contract (§7).
AUDIT LOGGING ADDRESSED: YES — append-only crypto_gate_config is itself the config-change audit trail (who/when/why per row, SQL-only writes, no write endpoint); regime/gate logs stamp config_version.
ROTATION GUIDANCE ADDRESSED: YES (trivially) — nothing new to rotate; existing key handling unchanged.
OVERRIDE-ACCEPTED FINDINGS RECORDED: None — no override in play this brief.
NOTES: New read endpoints must mirror the existing route auth posture (0.4) — if Phase 0 finds those routes unauthenticated, that is pre-existing posture, not an S-2 regression; log it as an observation for the comprehensive security review backlog either way.
APPROVE FOR CC: YES.

HELIOS — BRIEF FINAL REVIEW
BRIEF: docs/codex-briefs/2026-07-15-stater-swap-s2-regime-session-brief.md
CC-ACTIONABLE: YES.
DESIGN SYSTEM COMPLIANCE ADDRESSED: Not applicable — zero frontend surfaces ship (mockup gate honored; charter opened at docs/strategy-reviews/stater-swap-redesign/helios-mockup-track.md).
ADHD-FRIENDLY HEURISTICS HONORED: YES at the contract layer — /api/crypto/regime and /clock return decisive state (a regime, a partition, a flag), not raw series to interpret.
STALENESS / REAL-TIME PATTERNS ADDRESSED: YES — data_age_seconds computed at request time, degraded/degrade_reason mandatory, UNKNOWN is a first-class visible state; "a frozen job must look frozen" is in the contract.
PERFORMANCE BUDGET ADDRESSED: Not applicable (no market-hours UI path; hourly backend job).
BACKEND DEPENDENCIES NOTED: YES — the S-2 carry-forward I own (Denver dual-label) is discharged in the §7 /clock contract: every timestamp field ships utc + america_denver precomputed, zoneinfo-derived. S-6 renders; it does not compute time. That is the correct division.
APPROVE FOR CC: YES.

ATHENA — BRIEF FINAL REVIEW
BRIEF: docs/codex-briefs/2026-07-15-stater-swap-s2-regime-session-brief.md
CC-ACTIONABLE: YES.
SCOPE MATCHES PASS 2 AGREEMENT: YES — R-1 as amended by A-2/A-3, both carry-forward rows discharged, five explicit scope fences hold the line against the two nearest creep vectors (vendor parametrization, R-4 strip data). The one judgment call — shipping the enforcement branch dormant behind gating_enabled — is within the carry-forward's own language ("before gating goes live" presumes a gate that can go live) and makes the eventual flip config-only; approved, with §10's bar as the binding gate.
OLYMPUS IMPACT SECTION: Present + accurate.
SEQUENCING REFLECTED IN BRIEF: YES — displacements were named in the 7/13 record (ZEUS Phase II defers L1/L2, Phase C, committee logging, Phase B get_bars); S-2 adds no new displacement. Standing post-R-2 checkpoint remains next in the sequence after S-3. D-2's recovery of the two uncommitted 7/13 artifacts closes a provenance gap before it compounds — good catch, correctly bounded (recover-or-record, never reconstruct).
APPROVE FOR CC: YES.
```

**Titans final review verdict: 4/4 APPROVE FOR CC. No vetoes. No conditions beyond the brief's own gates.**

---

## 13. Gate line

Nothing in R-2+ (Brief S-3 onward) may start until this brief's Done Definition (§8) is met and ACK'd. The §10 validation bar governs the gating flip separately and is NOT an S-2 exit criterion — S-2 closes with the flag false and the shadow dataset accruing.

*Authored in the coordination lane 2026-07-15 from the committee brief (R-1 + A-2/A-3), the 2026-07-13 Titans carry-forward table, PROJECT_RULES, the S-1 closure note, and the symbol capability matrix. Repo refs verified against `origin/main` at authoring time.*
