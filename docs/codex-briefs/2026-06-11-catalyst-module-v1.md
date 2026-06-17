# CC Build Brief — Catalyst Module v1 (SPCX/AI Volatility)

**Date:** 2026-06-11
**Author:** Olympus + Titans (Fable planning lane), post code-level Pass 1/2
**Target:** Live for Monday 2026-06-15 pre-market
**Phase 0 source docs (READ FIRST):**
- `docs/phase0-catalyst-module-findings.md`
- `docs/phase0-global-webhook-hardening-findings.md`
- `docs/strategy-reviews/insights-feed-architecture-review-2026-04-24.md`

---

## Purpose

Build a reconfigurable catalyst-event module that exploits fast-moving market events (first
config: SPCX IPO + Nasdaq-100 rebalance / AI volatility, 6/12–6/22) and re-skins the four dead
Insights tabs onto live catalyst data. Phase 0 proved ~60% already exists: the `catalyst_events`
table, `lightning_cards` surface, WebSocket broadcast, and Hermes webhook hardening (in observe
mode) are all live. v1 EXTENDS these primitives — it does not build new infrastructure.

This is v1 (tactical). v2 (foundation: scoring integration into ranking, Signals-tab
consolidation, catalyst outcome logging, MCP tool) is sequenced AFTER v1 closure — separate brief.

---

## Pre-flight (CC runs these before any edit)

1. `cd /d C:\trading-hub && git fetch && git status` — confirm clean tree at `origin/main`
   (expected HEAD: `fe182bf` or later). If dirty, STOP and surface.
2. Confirm these files exist at the cited anchors (Phase 0 verified them):
   - `backend/webhooks/hermes.py` — `_hermes_observe()` line ~70, `hermes_webhook()` line ~91,
     `_store_catalyst_event()` line ~510.
   - `backend/database/postgres_client.py` — `catalyst_events` DDL line ~2131.
   - `frontend/app.js` — `switchFeedTab()` line ~4521, tier badge MAP line ~4199,
     `renderStalenessIndicator()` line ~13178.
   - `backend/integrations/uw_api.py` — canonical UW client (the ONLY client the poller may use).
3. **DEPLOY WINDOW GATE:** This build touches backend + triggers a Railway redeploy. Do NOT
   `git push origin main` during 09:30–16:00 ET Mon–Fri. CC may commit locally anytime; push only
   outside market hours. (PROJECT_RULES Deployment Rules.)

---

## Tasks (in strict order — Task 0 gates everything after it)

### TASK 0 — Hermes webhook fail-closed cutover (AEGIS veto condition — BLOCKS v1 go-live)

**Phase 0 finding:** the hardening CODE already exists and is deployed in OBSERVE mode.
`_hermes_observe()` (hermes.py:70-71) returns `True` (observe) unless env `WEBHOOK_HERMES_ENFORCE`
∈ {1,true,yes}. `validate_webhook_secret(...)` is already wired with `observe=_hermes_observe()`,
`strip_secret()` already strips before persist, content-length + payload caps already enforced.
**So Task 0 is a configuration cutover, not new code — but it must be sequenced and verified, not
flipped blind.**

0.1 — **Confirm the live TradingView Hermes alert sends `secret`.** The Hermes alert family is
Message-box class (no Pine in repo; JSON hand-authored in TV UI) — there are ~9 alert instances
(per webhook census §3). Nick must verify each Hermes alert's Message JSON includes
`"secret": "<HERMES_WEBHOOK_SECRET value>"`. CC cannot do this — it is a TV-UI action.
**Output a checklist** of the 9 Hermes alerts for Nick to tick off. Until all 9 carry the secret,
flipping enforce will 401 live catalyst alerts (feed goes dark).

0.2 — Confirm `HERMES_WEBHOOK_SECRET` is set in Railway env (it is read at hermes.py:112). If
unset, STOP — surface to Nick to set it (value is Nick's to generate; never echo it).

0.3 — **Only after 0.1 + 0.2 confirmed:** set Railway env `WEBHOOK_HERMES_ENFORCE=1`. This flips
`_hermes_observe()` to `False` → `validate_webhook_secret` goes fail-closed. No code change.

0.4 — **Empirical verification (PROJECT_RULES deploy-verification discipline — do NOT trust env
status):** POST a test payload to `/api/webhook/hermes` WITHOUT a secret → must return 401/403.
POST WITH the correct secret → must return 200 and write a `catalyst_events` row. Log both
results in the closure note. A bad-secret POST returning 200 = Task 0 FAILED, do not proceed.

**Gate:** No task below ships until 0.4 passes. This satisfies AEGIS's conditional veto ("no new
catalyst write path before Hermes is fail-closed").

---

### TASK 1 — Extend `catalyst_events` schema (ATLAS-gated: isolation invariant)

**ATLAS HARD GATE:** `catalyst_events` must NEVER write to or share semantics with `signals` /
`signal_outcomes`. v1 writes ZERO outcome rows. No `outcome_source` column in v1.

1.1 — In `backend/database/postgres_client.py`, extend the `CREATE TABLE IF NOT EXISTS
catalyst_events` block (line ~2131) with these columns (additive; `IF NOT EXISTS` table create
won't alter an existing table, so ALSO add idempotent ALTERs — see 1.2):
   - `catalyst_key TEXT` — which catalyst config produced this (e.g. `'SPCX_AI_INDEX'`)
   - `source TEXT DEFAULT 'unknown'` — emitter: `'uw_flow'` | `'tv_webhook'` | `'hermes'` | `'chain_listing'`
   - `scenario TEXT` — pre-written scenario label this event maps to (PIVOT requirement)
   - `direction TEXT` — `'bullish'` | `'bearish'` | `'neutral'`
   - `premium_usd NUMERIC(14,2)` — aggregate premium for flow events (NULL for others)
   - `enrichment JSONB DEFAULT '{}'::jsonb` — bias-composite + CTA zone + PYTHIA structure tags
   - `structure_context TEXT` — PYTHIA level context, or literal `'no_structure'` for IPO-class
     tickers with no profile (PYTHIA requirement: never blank)

1.2 — Because the table already exists in prod, add idempotent migration ALTERs in the SAME
startup path (mirror the `main.py:75` `ADD COLUMN IF NOT EXISTS` pattern). For each new column:
`ALTER TABLE catalyst_events ADD COLUMN IF NOT EXISTS <col> <type>`. Place near the existing
catalyst index creation (postgres_client.py ~2152).

1.3 — Add an index: `CREATE INDEX IF NOT EXISTS idx_catalyst_events_key ON catalyst_events
(catalyst_key, created_at DESC)`.

1.4 — **Rollback path (ATLAS requirement):** document the DOWN in the brief closure note —
`ALTER TABLE catalyst_events DROP COLUMN IF EXISTS <each>`. Do not execute; document only.

1.5 — Extend `_store_catalyst_event()` (hermes.py:510) INSERT to include the new columns, all
optional with safe defaults via `kwargs.get(...)`. Existing Hermes callers omit them → defaults
apply → no regression to the velocity-breach path.

---

### TASK 2 — `SPCX_AI_INDEX` catalyst config (repo-file, per Nick's decision)

2.1 — Create `backend/catalyst/configs/spcx_ai_index.json` (new dir `backend/catalyst/configs/`).
Config is git-tracked and editable for future events (the reconfigurability goal). Schema:

```json
{
  "catalyst_key": "SPCX_AI_INDEX",
  "label": "SPCX IPO + NDX Rebalance / AI Volatility",
  "active_window": { "start": "2026-06-12", "end": "2026-06-22" },
  "universe": {
    "signal_only": ["SPCX"],
    "long_bias": ["TSLA", "RKLB", "ALAB", "CRWV", "NBIS", "TER"],
    "short_bias": ["CHTR", "CTSH", "INSM", "VRSK", "ZS"],
    "index_proxies": ["QQQ", "SPY"]
  },
  "double_catalyst": { "RKLB": "ndx_add + spacex_halo" },
  "rules": {
    "flow_cluster": {
      "min_premium_usd": 250000,
      "min_sweep_count": 2,
      "side": "ask",
      "max_dte": 14,
      "window_minutes": 5
    },
    "index_flow_cluster": {
      "tickers": ["SPY", "QQQ"],
      "min_premium_usd": 1000000,
      "side": "ask",
      "max_dte": 0,
      "window_minutes": 5
    },
    "chain_listing_watch": ["SPCX"],
    "price_velocity": { "long_bias_pct": 5.0, "short_bias_pct": 5.0, "index_pct": 1.0 }
  },
  "scenarios": {
    "A_hot_open": "SPCX holds above issue + halo ask-sweep cluster + index breaks pre-cross high",
    "B_broken_open": "SPCX below issue + basket red + index put-sweep cluster + breaks pre-cross low",
    "C_fizzle": "two-way chop dies; afternoon vol bleed",
    "removal_forced_selling": "NDX removal names dumping into 6/19 effective date"
  },
  "discord": { "enabled": true },
  "vps_scrape_burst": false
}
```

2.2 — Create `backend/catalyst/config_loader.py`: loads + validates any config in
`configs/*.json`, exposes `get_active_configs(now)` (filters by `active_window`) and
`get_universe(catalyst_key)`. Pure-Python, no new deps. Validate required keys; log + skip
malformed configs (fail-visible per PROJECT_RULES principle #2).

---

### TASK 3 — Universe poller (ATLAS-gated: shared UW client)

**ATLAS HARD GATE:** the poller MUST use `backend/integrations/uw_api.py` helpers + existing Redis
TTLs. NO second UW client. NO new yfinance/Polygon/FMP dependency (PROJECT_RULES Data Source
Hierarchy).

**REFERENCE IMPLEMENTATION (added 2026-06-12 — supersedes any conflicting rules in this brief):**
`scripts/flow_scanner.py` (v2) is the LIVE-VALIDATED detection engine — it ran against real RTH
flow on IPO morning after a dual-committee review. CC must PORT its logic into
`backend/catalyst/poller.py`, NOT reinvent detection. Six validated elements, all mandatory:

1. **Imbalance/dominance gate** — a direction fires only if it owns ≥ `dominance_ratio` (0.70)
   of the window's total directional premium. This is the noise-killer: without it, both
   directions alert simultaneously on liquid names (observed live in testing).
2. **Server-side order floor** — pass `min_premium` (~$25K) on `/flow-recent` requests so the
   ~50-record response covers institutional orders, not retail confetti (validated: SPY sample
   premium went $55K → $3.1M with the filter on).
3. **Liquidity buckets** — per-bucket cluster thresholds: mega/index ≥$2M & 4 sweeps;
   TSLA-class ≥$750K; small/mid ≥$250K & 3 sweeps. Flat thresholds across the universe are
   wrong by construction.
4. **Dark-pool block poller** — `/api/darkpool/{ticker}?min_premium=...` for no-options tickers
   (SPCX until chains list ~6/16); emit DP_BLOCK events. Block prints are the only
   institutional read on a new listing. Make it a config flag (`darkpool_watch`), not SPCX-coded.
5. **Scenario mapping** — every emitted event carries its scenario label (port `scenario_for()`)
   per PIVOT's standing rule: an alert that doesn't map to a pre-written scenario is noise.
6. **Ghost-ticker guard** — reject SPCX records with price < $100 (the dead SPAC-ETF corpse is
   live in UW's cache; observed directly).

Config schema impact (Task 2): `spcx_ai_index.json` MUST also carry `dominance_ratio`,
`min_order_premium`, and per-bucket thresholds, mirroring the scanner's CONFIG block.

Endpoint guidance (ATLAS): per-ticker `/api/stock/{ticker}/flow-alerts` is **DEPRECATED**
(api_spec.yaml:15508) — do not build on it. The validated pattern is `/flow-recent` +
`min_premium`. The global `/api/option-trades/flow-alerts` (one call covers ALL tickers; WS
stream available) is the PREFERRED production architecture if runway allows — ATLAS decides at
build time. Keep `scripts/flow_scanner.py` untouched as the rollback/manual tool.

3.1 — Create `backend/catalyst/poller.py` with an async loop (mirror the existing
`uw_flow_poller_loop` pattern in main.py:393). For each active config's universe:
   - Pull flow via the canonical `uw_api.get_flow_per_expiry()` (or the existing flow helper the
     current poller uses — match it).
   - Apply `flow_cluster` / `index_flow_cluster` rules from config → detect ask-side sweep
     clusters meeting premium + count + window thresholds.
   - For `chain_listing_watch` tickers: poll `/option-contracts` (kebab-case REST, snake_case MCP)
     — **MUST pass `?expiry=` + `?option_type=`** (PROJECT_RULES: unbounded `/option-contracts`
     is an ATLAS veto / 500-cap). Detect non-empty chain → emit `chain_listing` event ONCE
     (idempotent via Redis SETNX key `catalyst:chainlisted:{ticker}`).
   - **Ghost-ticker guard (Phase 0 critical finding):** reject any SPCX quote with spot < 100 OR
     a UW timestamp before the listing cross — that is the dead SPAC-ETF corpse, not SpaceX. Hard
     filter in the poller before any SPCX event emits.

3.2 — Register the loop in `main.py` lifespan alongside the other scan loops (follow the exact
`asyncio.create_task(...)` + cancel-on-shutdown pattern already there).

3.3 — Poll cadence: every 30s during RTH. Budget check: 6-name universe @ 30s ≈ 4,700 calls/day —
well within UW 20K/day, 120/min. Document the math in the closure note.

---

### TASK 4 — One event schema + emitter

4.1 — Create `backend/catalyst/emitter.py` with `emit_catalyst_event(event: CatalystEvent)` —
the single funnel that (a) enriches, (b) writes via `_store_catalyst_event()`, (c) pushes to
Discord, (d) broadcasts WS, (e) audit-logs. Define a `CatalystEvent` dataclass/pydantic model =
THE canonical schema (DAEDALUS "enough to act" payload): `catalyst_key, source, event_type,
trigger_ticker, direction, scenario, premium_usd, structure_context, enrichment, correlated_tickers`.

4.2 — **Enrichment (Olympus requirement, reuses mandated path):** before write, populate
`enrichment` with current bias-composite reading + CTA zone + PYTHIA structure context. Pull from
the EXISTING factor sources (composite-bias-engine + CTA scanner + PYTHIA MP). Catalyst events
BYPASS the scoring gates but CARRY the tags (this is the URSA "label don't hide" + PYTHAGORAS
annotation + PYTHIA structure requirements, satisfied via existing infra). For SPCX-class
no-profile tickers set `structure_context='no_structure'`.

4.3 — **Idempotency/dedupe (AEGIS):** Redis SETNX dedupe key per event
(`catalyst:emit:{catalyst_key}:{ticker}:{event_type}:{bucket}`) so the same cluster doesn't
double-fire within its window. Reuse the existing SETNX idempotency pattern.

4.4 — **Audit log (AEGIS — Nick deferred to committee, AEGIS ruled BOTH):** every emission writes
to the audit log AND the Discord sink. Mirror the `/var/log/committee_audit.log` pattern. Audit
entry: timestamp, catalyst_key, ticker, event_type, scenario, premium — NEVER account values.

---

### TASK 5 — Discord sink (AEGIS-gated: new bearer credential)

5.1 — Create `backend/catalyst/discord_sink.py`. Reads webhook URL from NEW Railway env var
`CATALYST_DISCORD_WEBHOOK` (Nick has created the channel + saved the URL off-chat; he sets the env
var). **AEGIS HARD RULES:** URL is a bearer credential — env var ONLY, never in repo, never in a
config file, never logged. Distinct from the existing `DISCORD_WEBHOOK_SIGNALS` (VPS bot).

5.2 — Rich embed per event: ticker, event type, direction, scenario, premium, structure context,
enrichment summary (bias + CTA zone). Embed NEVER carries account values (AEGIS).

5.3 — **Rate-limit (AEGIS):** Discord ~30 msg/min ceiling — throttle/queue emissions; drop-with-
log if exceeded rather than 429-spam. Reuse SETNX dedupe from 4.3 as first-line suppression.

5.4 — **Do NOT repeat the April-24 publisher bug:** the existing `#-signals` publisher fires on
raw signal-generation events and is not tier-aware. The catalyst sink fires ONLY on
`emit_catalyst_event()` (the schema funnel), never on raw signal rows.

---

### TASK 6 — Catalyst tab re-skin (HELIOS-gated: staleness mandatory)

**HELIOS HARD GATES:** (a) staleness indicator mandatory (veto trigger if absent — but
`renderStalenessIndicator()` already exists at app.js:13178, REUSE it); (b) each card leads with
the decisive read (what fired + which scenario), raw payload behind a tap; (c) "armed and quiet"
empty state so silence reads healthy (this is the fix for Top Feed's silent-empty failure);
(d) ride the EXISTING WS — no new polling loop; batch DOM patch on WS burst (no per-card re-render
storm — the dashboard has known perf debt on this path).

6.1 — Backend: confirm/extend the existing catalyst query endpoint (`get_hermes_alerts`,
hermes.py:409, already returns `catalyst_events` by tier) to include the new columns. If a
cleaner `/api/catalyst/events` alias is warranted, add it — but reuse the query logic.

6.2 — Frontend `frontend/app.js` + `frontend/index.html`: replace the four dead Insights tabs
(Top Feed / Watchlist / TA / Research — `.feed-tab[data-tier=...]`) with **Signals** + **Catalyst**.
   - v1 SCOPE: build the **Catalyst** tab fully. Leave **Signals** as a thin relabel of the
     existing Main feed (`loadMainFeed`) — full Signals consolidation is v2. Do NOT delete the
     dead tab endpoints yet (v2 retires them after confirming no orphaned callers — see Phase 0
     open-question #5).
   - Catalyst tab: subscribe to the existing WS `hermes_flash` / catalyst broadcast events; render
     `lightning_cards`-style cards; age-fade + hard cap ~25 visible; `renderStalenessIndicator()`
     on the container; "armed and quiet" empty state.
   - Each card: decisive line = `{ticker} {direction} — {scenario}`; tap expands raw payload +
     enrichment.

6.3 — WS handler: add a `case 'catalyst_event':` (or reuse `hermes_flash`) in the existing WS
message switch (app.js ~1282 region) that prepends a card + batches the DOM patch.

### TASK 7 — Committee visibility: catalyst events over Pandora MCP (Nick directive, 2026-06-12 AM)

Olympus must be able to READ Catalyst-section setups during committee passes.

7.1 — Implementation latitude (ATLAS decides at build): EITHER (a) extend the existing insights
MCP surface (`hub_get_trade_ideas` in `backend/hub_mcp/`) with a clearly-delimited
`catalyst_events` block in its response, OR (b) add a dedicated `hub_get_catalyst_events` tool.
Nick's stated preference: reusing the regular insights connection is acceptable "as long as they
can see the setup."

7.2 — **HARD GUARD either way (ATLAS isolation principle, read-layer):** catalyst events are
unscored and gate-bypassing — they must be unmistakably labeled (e.g., `signal_class: "CATALYST"`
on every record) so a committee pass can never mistake them for scored insights. PIVOT sizing
logic must not treat catalyst events as conviction-tier inputs.

7.3 — **Olympus regression gate:** this changes the committee data surface → triggers the
cross-reference rule. Post-deploy, run a full-committee regression pass on a known-good ticker
(SPY) before any reliance on the new surface.

7.4 — **Severability:** if weekend runway tightens, Task 7 may deploy Monday after market close
WITHOUT blocking Tasks 0–6 going live Monday pre-market. `backend/hub_mcp/` deploys must avoid
market hours per PROJECT_RULES (Railway restart drops hub MCP 60–170s).

---

## Output spec

**New files:**
- `backend/catalyst/__init__.py`
- `backend/catalyst/config_loader.py`
- `backend/catalyst/configs/spcx_ai_index.json`
- `backend/catalyst/poller.py`
- `backend/catalyst/emitter.py`
- `backend/catalyst/discord_sink.py`

**Modified files:**
- `backend/database/postgres_client.py` (catalyst_events schema + ALTERs + index)
- `backend/webhooks/hermes.py` (`_store_catalyst_event` INSERT extension)
- `backend/main.py` (register poller loop in lifespan)
- `frontend/app.js` + `frontend/index.html` (Catalyst tab re-skin)

**Env vars (Nick sets in Railway — CC documents, does not set):**
- `WEBHOOK_HERMES_ENFORCE=1` (Task 0.3, AFTER alert-secret confirmation)
- `CATALYST_DISCORD_WEBHOOK=<url>` (Task 5.1)

**Commit:** stage incrementally; commit message via `git commit -F C:\temp\commitmsg.txt`.
Suggested: `feat(catalyst): v1 module — Hermes fail-closed cutover, catalyst_events extension, SPCX_AI_INDEX config, UW poller, Discord sink, Catalyst tab`.

**Closure note:** `docs/strategy-reviews/catalyst-v1-closure-note-2026-06-1X.md` — Task 0.4
verification results, deploy SHA vs commit SHA, schema DOWN documentation, UW call-budget math,
what shipped vs deferred to v2.

---

## Gates / what NOT to do

- **AEGIS veto:** no new catalyst write path (Tasks 3-6) ships before Task 0.4 passes (Hermes
  fail-closed, empirically verified). Order is non-negotiable.
- **ATLAS veto:** zero writes to `signals` / `signal_outcomes`; no `outcome_source` column in v1;
  poller uses ONLY `uw_api.py`; `/option-contracts` ALWAYS bounded by `?expiry=` + `?option_type=`.
- **HELIOS veto:** Catalyst tab ships with staleness indicator + decisive-card pattern + armed-
  and-quiet empty state, or it does not ship.
- Do NOT `git push origin main` during RTH (09:30–16:00 ET). Commit locally; push after close.
- Do NOT delete the dead Insights tab endpoints in v1 (v2 retires them post-orphan-check).
- Do NOT make the VPS scrape burst a v1 dependency (`vps_scrape_burst: false` in config).
- Do NOT echo/log any secret value (HERMES_WEBHOOK_SECRET, CATALYST_DISCORD_WEBHOOK).
- Do NOT use PowerShell for git. Use cmd with `cd /d C:\trading-hub &&` prefix.

---

## Done definition

1. Task 0.4 empirically verified: bad-secret POST → 401/403; good-secret POST → 200 + row written.
2. `catalyst_events` carries the 7 new columns; existing Hermes velocity-breach path unregressed.
3. `SPCX_AI_INDEX` config loads + validates; `get_active_configs(now)` returns it inside window.
4. Poller emits a catalyst event on a simulated qualifying flow cluster (test payload), with
   ghost-ticker guard rejecting a sub-$100 SPCX quote.
5. Catalyst event appears in: Discord channel (rich embed, no account values) + audit log +
   Catalyst tab (via WS, with staleness indicator) — all three sinks, one schema.
6. Deploy SHA matches commit SHA; closure note written with verification evidence.
7. Friday's manual alert stack is untouched and independent (module is additive).

---

## Olympus Impact

**Skills touched:** none directly in v1 (no skill files edited). The catalyst enrichment READS
from bias-composite + CTA + PYTHIA sources but does not change committee data contracts.

**Committee behavior change:** none in v1. The Catalyst tab + Discord give Nick a new flow-radar
surface; Olympus passes are unaffected.

**MCP surface change (Task 7, NOW IN SCOPE per Nick 2026-06-12):** catalyst events become
readable over Pandora MCP (via insights connection or dedicated tool — ATLAS picks). This IS a
committee data surface change → the cross-reference rule fires → post-deploy full-committee
regression pass on SPY is REQUIRED before reliance (Task 7.3). Severable to Monday-after-close
if the weekend runs tight (Task 7.4).

---

**Next step after this brief:** Titans final review on the brief itself (CC-actionable? gates
present? scope matches Pass 2? Olympus Impact accurate?), then CC launches from repo root.
