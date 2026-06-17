# Phase 0 — Catalyst Module / Insights Rebuild — Read-Only Findings

**Authored:** 2026-06-11 (evening, Denver) · **Mode:** investigation-only, no code touched
**Trigger:** SPCX IPO (6/12) + Nasdaq-100 rebalance (eff. 6/22) volatility window. Nick wants a
catalyst-event module that (1) exploits this week's vol and (2) generalizes to future fast-moving
events, wired into the dead Insights tabs + Discord, easily reconfigurable per event.
**Committees:** Olympus (trading) + Titans (build) ran a concept-level double-pass from mobile;
this Phase 0 grounds that concept in the actual codebase before code-level Pass 1.

---

## TL;DR — the build is mostly an EXTENSION, not a greenfield

Phase 0 discovered that **a primitive catalyst module already exists in the codebase** and was
not known to either committee during the mobile concept pass:

1. **`catalyst_events` Postgres table is LIVE** — written by the Hermes webhook
   (`backend/webhooks/hermes.py`). Full lifecycle already implemented: `_store_catalyst_event()`
   (INSERT, line 510-541), tier query (409-456), dismiss (451-461), analysis update (328-407).
2. **`lightning_cards` table is LIVE** — the existing catalyst-card UI surface, with a
   `confirmations` JSONB column (main.py:75) and its own update path (hermes.py:389).
3. **WebSocket `broadcast_event()` is LIVE** — Hermes already broadcasts `hermes_flash` and
   `hermes_analysis` events to the frontend (hermes.py:298-311, 375-389). **This resolves the
   open SSE-vs-poll transport question from the mobile HELIOS pass: the Catalyst tab consumes the
   existing WS stream — no new transport layer.**
4. **Hermes has an ISOLATED secret** (`HERMES_WEBHOOK_SECRET`, hermes.py:112) — independent
   cutover from the TV webhook family, so hardening it does NOT block on the 9-alert TV re-arm.
5. **Frontend is already modular** — `analytics.js`, `cockpit.js`, `laboratory.js`,
   `knowledgebase.js` are all separately-served JS modules (main.py:1419-1439). The Insights
   re-skin extends this established pattern; it is not a single-file rewrite.

**Net:** the mobile committees scoped a build that is ~60% already present. The real work is
(a) generalizing Hermes from its current Twitter-scrape-centric shape into a reusable catalyst
config, (b) re-skinning the dead Insights tabs onto `catalyst_events`/`lightning_cards`, (c) a
clean Discord sink, and (d) finishing webhook hardening that is already in flight.

---

## 1. Repo state at Phase 0

- `git fetch && git status`: clean working tree, up to date with `origin/main` at `fe182bf`
  (Merge `origin/sec-work`). Many untracked local files (briefs, scripts) — none relevant to
  this build; no tracked drift.
- **Current bug-fix work = the `sec-work` branch**, now merged: session-cookie auth
  (`b63804c`), webhook runbook gates (`b5bc543`), Holy Grail Pine fix (`76ae723`). This is
  exactly AEGIS's "Task 0" territory — **webhook hardening is already underway**, not a net-new
  prerequisite.
- **Deploy constraint confirmed** (PROJECT_RULES): Railway auto-deploys on push to `main`;
  `backend/hub_mcp/` changes must avoid 09:30–16:00 ET Mon–Fri. **Practical effect: no
  main-branch deploy of this module until after Friday's close.** Friday's IPO runs on the
  manual UW/TV alert stack regardless — the module was never going to make the IPO and does not
  need to. Target: live for **Monday pre-market** (MSCI inclusion day + ongoing AI vol).

---

## 2. What already exists (extend, don't rebuild)

### 2a. Storage layer — `catalyst_events` (DONE)
`hermes.py:510` `_store_catalyst_event(**kwargs)` already INSERTs into `catalyst_events` and
returns a UUID. Query path (`get_hermes_alerts`, 409) filters by `tier` and `dismissed`.
Dismiss path (451) flips `dismissed=true, dismissed_at=NOW()`. **ATLAS Phase 0 read:** this is
already close to the generic event store the mobile pass wanted as a NEW table. Decision for
code-level Pass 1: extend `catalyst_events` schema (add `catalyst_key`, `source`, `event_type`,
`scenario`, enrichment tags) vs. a sibling table. Leaning EXTEND — the lifecycle code is already
written and tested in production.

### 2b. Card surface — `lightning_cards` (DONE, reusable)
Already the "fast catalyst card" UI primitive with a `confirmations` JSONB column. The Catalyst
tab can render `lightning_cards` directly. **HELIOS Phase 0 read:** this is the decisive-card
surface; staleness/age-fade gets layered on the existing card, not invented.

### 2c. Live transport — WebSocket (DONE)
`broadcast_event("hermes_flash", ...)` and `broadcast_event("hermes_analysis", ...)` already
push to the frontend WS. The four dead Insights tabs are served by the same frontend that holds
the WS connection. **Resolves mobile open-question #2 (SSE vs poll): use existing WS.**

### 2d. VPS scrape-burst trigger (DONE, optional for v1)
Hermes triggers a VPS scrape burst (120s interval, 15min duration) via
`http://188.245.250.2:8000/api/hermes/trigger` with `X-API-Key: HERMES_VPS_KEY` (hermes.py:188-213).
This is the Twitter-intelligence path. **For the SPCX/AI catalyst v1 this is OPTIONAL** — the
flow/DP/index-rebalance signals don't require the Twitter scrape. v1 can emit catalyst events
from UW flow + TV webhooks without triggering the VPS burst. Keep the burst for narrative events
(it's already wired), don't make it a v1 dependency.

### 2e. Frontend module pattern (DONE)
`serve_analytics_js`, `serve_cockpit_js`, `serve_laboratory_js`, `serve_knowledgebase_js`
(main.py:1419-1439) prove the multi-module frontend pattern. A `catalyst.js` (or extension of
the Insights module) follows the same serving convention.

---

## 3. The dead Insights tabs (the re-skin target)

Per `docs/strategy-reviews/insights-feed-architecture-review-2026-04-24.md` (production
diagnostic, still accurate):

- Insights has **5 tabs**: Main / Top Feed / Watchlist / TA / Research.
- **Top Feed has been EMPTY for 30+ days** — its anchor (Whale Hunter ZEUS scanner) produced 1
  signal in 30 days; the classifier requires WH-evidence to reach Top Feed, so it never fills.
- **Watchlist is an 82% dumping ground** (642 of 783 signals/week); tabs don't communicate
  distinct value to a trader.
- The April 24 doc explicitly called for an Olympus+Titans redesign of these tabs that **never
  happened**. **Nick's Catalyst build IS that redesign** — scoped to a concrete, time-boxed use
  case instead of an abstract re-architecture.

**Proposed tab outcome (for committee ratification, not locked):**
- Replace the four never-useful tabs (Top Feed / Watchlist / TA / Research) with **two**:
  1. **Signals** — the main actionable signal list (consolidates what "Main" half-did).
  2. **Catalyst** — fast-moving event cards from `catalyst_events`/`lightning_cards`, live via WS.
- **Discord publisher bug to NOT repeat** (April 24 §5): the existing `#-signals` publisher is
  *not* feed_tier-aware and leaks low-score signals. The Catalyst Discord sink must filter on the
  catalyst event schema explicitly, not fire on raw signal-generation events.

---

## 4. Webhook-hardening state (AEGIS Task 0 — already in flight)

Per `docs/phase0-global-webhook-hardening-findings.md` (2026-06-10):

- **9 inbound POST webhook handlers; only 3 hardened** to the AEGIS fail-closed standard
  (`mp_levels`, `pythia`, circuit-breaker management routes).
- **The Hermes webhook (`/api/webhook/hermes`, #17) is currently NO-AUTH** and is the **highest
  unauth write blast radius** in the system: an unauthenticated POST inserts `catalyst_events`,
  can create `lightning_cards`, AND triggers the VPS scrape burst + WS broadcast.
- **Critical implication for this build:** the catalyst module's primary write path is the exact
  endpoint with the worst current auth posture. **AEGIS conditional veto from the mobile pass
  stands and is now precise:** Hermes hardening (`HERMES_WEBHOOK_SECRET`, fail-closed,
  `hmac.compare_digest`, size cap) is **in-scope Task 0 for this build**, not a separate effort.
  Good news: the secret env var (`HERMES_WEBHOOK_SECRET`) is already referenced in code
  (hermes.py:112) — it's read but the endpoint doesn't yet *enforce* it fail-closed. Finishing
  this is small.
- Hermes secret is **isolated from the TV family**, so this hardening is independent of the
  costly 9-alert TV re-arm (which stays on its own backlog track).

**Discord webhook URL** = a bearer credential (anyone holding it can post to the channel).
Railway env var only; never in repo, never in a catalyst config file, never pasted in chat.
This is a NEW credential for the clean Discord sink (distinct from the existing VPS-bot
`DISCORD_WEBHOOK_SIGNALS`). AEGIS: rotation = regenerate in Discord → update env var.

---

## 5. Scoring-factor reuse (Olympus requirement)

PROJECT_RULES "Signal Enrichment at Trigger Time" already MANDATES that every emitted signal
carry: sector-rotation state tag, auction-state tag (PYTHIA), prior-session VA-relative context,
IV rank. **The catalyst module gets this enrichment for free if it routes events through the
existing enrichment path** rather than emitting raw. This satisfies the mobile Olympus asks
(URSA's "label, don't hide"; PYTHIA's structure context; PYTHAGORAS's CTA-zone annotation;
DAEDALUS's payload spec) via infrastructure that already exists — catalyst events bypass the
*gates* but carry the *tags*.

Bias composite, CTA scanner, and GEX are all live factor sources (PROJECT_RULES Data Source
Hierarchy + composite-bias-engine spec). The Catalyst tab annotates each event with current
bias-composite reading + CTA zone as context; nothing suppresses a catalyst print.

---

## 6. Open questions for code-level Pass 1 (Desktop, full file access)

1. **Schema:** extend `catalyst_events` (add `catalyst_key`/`source`/`event_type`/`scenario`/tags)
   vs. sibling table. ATLAS Phase 0 lean: EXTEND. Needs `\d catalyst_events` + migration-style
   review. Must preserve `outcome_source` discipline — catalyst events must NOT contaminate
   `signals`/`signal_outcomes` BAR_WALK calibration (distinct class/table).
2. **Config representation:** catalyst definitions (name, date window, ticker universe, signal
   rules, scoring profile, routing) as DB rows vs. YAML vs. JSON in repo. Reconfigurability for
   future events is the design goal — favor the lightest editable format.
3. **First config — `SPCX_AI_INDEX`:** window 6/12–6/22; universe = {SPCX-as-signal, TSLA, RKLB
   (double-catalyst: NDX add + halo), ALAB, CRWV, NBIS, TER (NDX adds), plus NDX removals CHTR,
   CTSH, INSM, VRSK, ZS with put-side bias}. Symmetric (URSA): forced sellers (removals into
   6/19) are as tradeable as forced buyers (adds).
4. **Discord sink:** one event schema → two renderers (Discord embed + Catalyst tab row), per
   the mobile HELIOS+DAEDALUS convergence. Dedupe/rate-limit via the existing Redis SETNX
   idempotency pattern; Discord ~30 msg/min ceiling; embeds never carry account values (AEGIS).
5. **What consumes the four dead tabs' endpoints** before deletion — grep
   `/trade-ideas/grouped?feed_tier=` consumers so the re-skin doesn't orphan a live caller.
6. **VPS burst:** confirm v1 emits catalyst events WITHOUT requiring the Twitter scrape (keep
   burst for narrative-tier events only).

---

## 7. Scope split (mobile ATHENA, now Phase-0-confirmed)

- **v1 (tactical, target Monday pre-market):** finish Hermes hardening (Task 0) → extend
  `catalyst_events` schema + config → ingest tap on existing UW poller + TV webhook router →
  one event schema → clean Discord sink → Catalyst tab re-skin on `lightning_cards` via existing
  WS, with staleness + "armed and quiet" empty state. Reuses storage, cards, transport, scoring
  that already exist.
- **v2 (foundation, after the window):** full bias/CTA scoring integration into catalyst ranking,
  Signals-tab consolidation + retire the other three dead tabs, catalyst outcome logging,
  optional MCP `hub_get_catalyst_events` tool.

---

## 8. What did NOT get touched in Phase 0 (scope guard)

Per the parallel-session discipline (another track owns scoring/signals/enrichment internals),
Phase 0 was read-only and did not enter `backend/scoring|signals|enrichment` beyond reading
import/dispatch lines. No code, schema, or config changed. `git status` tracked tree unchanged.

---

**End of Phase 0 findings.** Next: code-level Titans + Olympus Pass 1 against these findings,
then brief authored to `docs/codex-briefs/`, Titans final review, CC build over the weekend,
deploy + verify Sunday for Monday pre-market.
