# Titans Pass 1 — Pandora's Box Hub MCP Server (2026-05-14)

**Build under review:** A remote MCP (Model Context Protocol) server hosted on Railway, exposing a read-only subset of Pandora's Box hub data as tools that Claude.ai (Olympus committee) and other Claude surfaces (CC in VSCode, mobile) can call from inside a chat. Replaces the current "web_search ground truth" fallback with live, authoritative hub data. UW MCP wiring runs in parallel as a separate workstream (UW provides their own MCP server; we just configure the connection).

**Pass 1 instructions to the Titans:** Review the architecture below independently against your lens. Surface concerns, disagreements, missing requirements. Do NOT cross-reference each other's reviews in this pass — that's Pass 2.

---

## Proposed Architecture (the artifact each Titan reviews)

### Deployment

- New module `backend/mcp/` inside the existing FastAPI app on Railway. Same process, same deployment pipeline, same auto-deploy from `main`.
- MCP routes mounted at `/mcp/v1/` on the existing public Railway URL (`https://pandoras-box-production.up.railway.app/mcp/v1/`).
- Built on **FastMCP** (Python MCP SDK) — production-grade, well-maintained, plays cleanly with FastAPI.
- Transport: SSE (Server-Sent Events) per MCP standard for remote servers.

### Authentication

- Bearer token. Generated once, stored in Railway env var `MCP_BEARER_TOKEN`. Nick pastes the token into Claude.ai → Settings → Connectors → Add custom connector when first wiring it up.
- Token rotation procedure: regenerate env var on Railway, re-paste in Claude.ai. Old token immediately invalid.
- HTTPS-only enforced at the route level. Plain HTTP requests rejected.

### Read-only enforcement

- Hard guard at the module entry point. Any tool implementation that maps to a write operation (POST, PUT, PATCH, DELETE on a hub endpoint, OR any operation that modifies state) is refused at registration time.
- Implementation: a decorator `@read_only` required on every tool function. Functions without the decorator throw an exception at module load — service won't start.
- Downstream HTTP calls from MCP tools to the hub use a read-only role/method enforcement (the MCP module's hub client refuses non-GET requests at the HTTP layer).

### MVP Tool Surface (7 tools)

1. `hub_get_bias_composite(timeframe?: "swing" | "daily" | "intraday")` → composite bias score, per-factor breakdown, staleness flags. Maps to `GET /api/bias/composite/timeframes`.
2. `hub_get_flow_radar(ticker?: str)` → options flow imprint, optionally filtered by ticker. Maps to `GET /api/flow/radar`.
3. `hub_get_sector_strength()` → cross-sectional sector RS, rotation regime tags. Maps to `GET /api/watchlist/sector-strength`. THALES will lean heavily on this.
4. `hub_get_hermes_alerts(ticker?: str, lookback_hours?: int)` → active catalysts (earnings, FDA, M&A, macro prints). Maps to `GET /api/hermes/alerts`.
5. `hub_get_hydra_scores(ticker?: str)` → squeeze setup scoring. Maps to `GET /api/hydra/scores`.
6. `hub_get_positions(account?: str, status?: "OPEN" | "CLOSED")` → unified_positions read. Maps to `GET /api/v2/positions`.
7. `hub_get_portfolio_balances()` → live account balances across Robinhood / 401k BrokerageLink / Fidelity Roth / Breakout Prop. Maps to `GET /api/portfolio/balances`. Per Nick's add 2026-05-14.

### Out of scope for v1

- Writes of any kind (closing positions, modifying bias, triggering committee passes from Claude.ai)
- Live OHLCV streaming (heavy bandwidth, separate problem — UW MCP handles this when wired)
- UI-side anything (Claude.ai's native connector flow handles it)
- Multi-user auth (this is single-user, Nick's token)
- UW MCP itself (separate workstream; we add the UW config to claude_desktop_config.json in parallel)

### Observability

- Every MCP call logged: timestamp, tool name, parameters (with ticker/account redacted to a hash if needed), response status, latency. Logs land in Railway logs, retained per existing policy.
- Dashboard counter (deferred to v2): "MCP calls per day, per tool" so Nick can see what Olympus is actually reaching for.

---

## Pass 1 Reviews

### ATLAS — Backend Architect

**Lens:** Backend correctness, scalability, financial-systems robustness.

The architecture is sound at the right scale. FastMCP mounted on the existing FastAPI app is the cleanest path — single deployment pipeline, single set of secrets, no new infrastructure surface. The existing Railway Postgres connection pool can be shared by the MCP routes because they're read-only — no risk of write contention. I'd reuse `get_postgres_client()` from `backend/database/postgres_client.py` for any tool that needs direct DB access (likely `hub_get_positions` since it touches `unified_positions`).

**Concerns I'd surface:**

1. **Cascading failure from downstream hub endpoint outages.** If `/api/flow/radar` is degraded or returning stale data, the MCP tool returning that data shouldn't pretend everything's fine. I want a `staleness_seconds` field in every tool response so Claude can degrade conviction explicitly. This is the same Phase B–C outcome-tracking pattern we already validated — the system surfaces data integrity, doesn't hide it.

2. **Hub endpoints already implement their own caching/staleness logic** (per the bias engine's "graceful degradation" rule when factors go stale). The MCP tools should NOT add a second caching layer. Pass-through with the source's own staleness metadata preserved. Caching at the MCP layer would create a second source of truth — exactly what `unified_positions` exists to prevent.

3. **UW API rate limits flowing through the hub.** If Olympus burns through hub endpoints that themselves proxy to UW, we eat into the 120 req/min and 20K req/day Basic plan limit. The hub already manages this for its own scanners; MCP traffic adds load. Recommend: the MCP layer respects the hub's own rate-limit responses (HTTP 429) and surfaces them to Claude as a structured error, not a silent timeout.

4. **Tool response schemas need versioning.** When the underlying hub endpoints evolve (new factor added to bias composite, new field on flow radar), MCP responses change. Recommend: each tool response includes a `schema_version` field. Claude can be told via skill instructions to handle schema bumps gracefully.

5. **Performance: synchronous proxying.** MCP tools call hub endpoints synchronously. If a hub endpoint takes 3 seconds, the MCP tool takes 3 seconds. Acceptable for v1 but worth a note — for tools that could be slow (sector_strength scans, hydra_scores across the universe), consider async pre-warming on a cron.

**My verdict:** Approve the architecture. Add the five recommendations above as build requirements. No structural redesign needed.

---

### AEGIS — Security

**Lens:** Auth perimeter, data privacy, attack surface, blast radius.

This is a new public-facing service with authenticated access to position data and portfolio balances. AEGIS-class concern level. Most of the architecture is right but several details need hardening.

**Concerns I'd surface:**

1. **Bearer token is the entire auth perimeter.** If the token leaks (committed to a public repo, screenshotted in a tweet, intercepted on a compromised network), an attacker has full read access to Nick's positions, balances, and trading bias data. That's not catastrophic (it's not write access), but it's reconnaissance gold for someone targeting Nick personally. Mitigation requirements:
   - Token must be at least 256 bits of entropy
   - Token must be stored ONLY in Railway env vars and Claude.ai's connector config, never in repo, never in chat logs, never echoed in any response
   - Rotation procedure must be documented and tested before launch — Nick needs to know exactly how to rotate the token if a leak is suspected
   - Recommend: token-bound IP allowlist for v2 (restrict to known Claude.ai egress IPs once Anthropic publishes them)

2. **Read-only enforcement at the decorator level is good but not enough.** A subtle code change could add a tool without `@read_only` and the service would still start because the decorator is opt-in. Recommend: the FastMCP route registration itself enforces the decorator — tools missing it fail registration, not load. Belt and suspenders.

3. **Position data is PII.** `hub_get_positions` returns tickers, strikes, expiries, quantities, account names — that's a complete trading book. Recommend:
   - Account names should be returned as opaque IDs ("account_a", "account_b") with a separate `hub_get_account_lookup()` tool that maps IDs to friendly names. This way, if a token leaks, the leaker sees an anonymized book unless they also have the lookup tool authorized.
   - OR: accept that single-token-grants-full-read and document the risk explicitly. (This is the v1 reality.)
   - Decision: defer to ATHENA — v1 simplicity vs v2 privacy-by-design.

4. **Rate limiting at the MCP layer.** Independent of UW's rate limits, the MCP server itself should rate-limit per token: e.g., 60 requests/minute, 5K/day. Protects against token-leak abuse cases where someone hammers the endpoint to extract data quickly.

5. **Audit log surface.** Every MCP call logged is good. But the audit log itself becomes a sensitive data surface if it contains parameters (tickers, accounts). Recommend: audit log entries hash or truncate sensitive params, with full parameters only logged in encrypted-at-rest form if at all.

6. **CORS and origin checks.** The MCP endpoint should reject requests with disallowed Origin headers — Claude.ai's connectors come from specific Anthropic infrastructure. Get the allowed origin list from Anthropic's MCP documentation and enforce it.

7. **The "Olympus reads, Olympus does NOT trade" boundary is sacred.** I want to see in the code, not just the spec, an explicit assertion that the MCP server's hub client uses a method-restricted HTTP wrapper that physically cannot send anything other than GET. Not a flag — a class that doesn't implement post/put/patch/delete. Defense in depth.

**My verdict:** Approve in principle. Six hardening requirements before launch (token entropy, rotation procedure, registration-time enforcement, rate limiting per token, audit log hygiene, method-restricted hub client). The account-anonymization question (concern 3) defers to ATHENA on v1 scope.

---

### ATHENA — PM, Final Decisions

**Lens:** Tool surface ergonomics, user flow, product completeness, success criteria.

The 7-tool MVP is the right scope. Don't expand beyond it for v1 — we don't know yet which tools Olympus actually reaches for, and YAGNI applies. Track v2 candidates based on what the committee asks for but can't get.

**Concerns I'd surface:**

1. **Tool descriptions are where this build lives or dies.** Skills under-trigger by default, and the same is true for tools — Claude's relevance ranker decides whether to call them based on the description text. Each tool needs:
   - A description that names the use case ("Use this when evaluating bias context for a trade idea, when checking whether the market regime supports the directional thesis, when running pre-market briefing setup")
   - Negative examples of when NOT to call it (prevent over-firing)
   - Concrete keyword anchors that match how Olympus skills phrase requests
   
   I want to review draft descriptions before CC writes the implementation. This is product copy, not engineering output.

2. **Parameter ergonomics.** `hub_get_flow_radar(ticker?: str)` — should optional parameter default to the most recently mentioned ticker in the conversation context? No, that's Claude's job to infer. The tool itself should accept either ticker or None (returns global flow imprint). Keep tool surface minimal; let Claude handle context-routing.

3. **Error handling needs a structured contract.** When a tool fails (hub down, rate limited, downstream timeout), the response shape needs to be predictable so the skills know how to degrade. Proposed contract:
   ```
   { "status": "ok" | "stale" | "degraded" | "unavailable",
     "data": <tool-specific or null>,
     "staleness_seconds": int | null,
     "error": str | null,
     "schema_version": str }
   ```
   This lets the skill output a `DATA NOTE` block deterministically.

4. **Migration plan for TORO and URSA.** Current skills have the "Context A (hub) vs Context B (web_search)" structure. Once MCP lands, Context A becomes the default path. The skills need a small patch updating the Pre-Output Data Checklist's Context A section to call the specific MCP tool names ("call `hub_get_bias_composite` with timeframe='swing' first"). This patch is part of the MCP build's acceptance criteria, not a follow-up.

5. **Success criteria for v1:**
   - All 7 tools return real data when called from a Claude.ai chat in the Pandora's Box project
   - TORO and URSA, when updated to use the MCP, produce GROUND TRUTH blocks that cite hub data (not web_search results)
   - Read-only enforcement validated by attempting a write and watching it fail
   - Token rotation tested end-to-end
   - 7 days of observability data showing which tools actually get called and at what rate
   
   If those five hold after 7 days, v1 is done and we move to v2 expansion.

6. **v2 roadmap (track but don't build):**
   - `hub_get_signal_outcomes` for backtest-aware committee analysis (per the committee-review-logging TODO in memory)
   - `hub_get_battlefield_brief` for current-week mechanical flow context
   - `hub_get_unified_positions_pnl` for unrealized PnL across the book
   - Per-tool latency metrics
   - Anonymized account IDs (AEGIS's concern 3)
   - IP allowlist (AEGIS's v2 recommendation)

7. **On AEGIS's account-anonymization question (concern 3).** Defer to v2. Single-user system, single-token risk, low-likelihood breach scenario, high implementation cost (every reference to account names everywhere flows through a lookup). Document the tradeoff explicitly in the README, ship v1 with friendly names, revisit if usage patterns change.

**My verdict:** Approve scope. Tool description copy needs an Olympus-aware review before implementation. Migration patch for TORO/URSA is in scope, not deferred. v2 candidates tracked.

---

### HELIOS — Frontend UI/UX

**Lens:** User flow for Nick connecting the MCP, in-chat experience when tools fire, error visibility, mobile.

This build is light on HELIOS surface because the UI is mostly Claude.ai-native, but there are three things worth surfacing.

**Concerns I'd surface:**

1. **Connection flow needs documentation.** Adding a custom MCP connector in Claude.ai involves: Settings → Connectors → Add custom → paste URL → paste bearer token → confirm. Nick has done this for desktop-commander, but every new MCP is a friction point. Recommend: a short doc at `docs/operations/mcp-connection-guide.md` with screenshots of the exact flow, the URL, where the token lives, and how to verify the connection works (one trigger prompt that should call a known tool). Pin it in trading-memory.md as a "if MCP disconnects, here's how to reconnect" reference.

2. **In-chat tool output formatting.** When `hub_get_bias_composite` returns 8 factors × 3 timeframes worth of data, the raw JSON dump will eat 200+ lines of chat real estate and overwhelm the conversation. Recommend: tools return data in two forms — a structured payload (for the skill to parse) and a concise human-readable summary (for the chat thread). Claude can choose to surface the summary unless the user asks for detail. The skill instructions handle this routing.

3. **Connection status visibility.** When the MCP server is down or the token is expired, the failure mode is "Claude silently can't call the tool, falls back to web_search or fabrication." That's the worst possible UX because Nick doesn't know why output quality dropped. Recommend: at the start of every Olympus committee pass, the skill performs a no-op MCP call to verify connection, and surfaces "MCP: connected" or "MCP: unreachable" in the output's DATA NOTE block. This makes connection state explicit, not implicit.

4. **Mobile experience.** Nick may invoke committee from his phone (the Claude mobile app supports skills and connectors). The bearer token entry on mobile is a friction point — long string to paste. Solvable: he sets it up once on desktop, mobile inherits the connection via account sync. But the rotation flow is harder on mobile. Recommend: token rotation is desktop-first; mobile inherits.

5. **Out of HELIOS's wheelhouse but worth flagging:** The Claude.ai connector UI doesn't (currently) show which tools a custom connector exposes in a discoverable way. Nick adds the URL, gets "Connected," and the tools just appear in chats. If he wonders "what can this MCP do?", there's no built-in answer. Recommend: the MCP server exposes a `mcp_describe_tools()` meta-tool that lists every available tool with its description. Self-documenting.

**My verdict:** Approve. Four lightweight requirements (connection doc, dual-format output, connection-status check in skill output, self-describing meta-tool). Mobile is fine.

---

## Pass 1 Synthesis: Where the Titans Agree and Disagree

**Unanimous approval of:**
- Architecture (FastMCP on existing FastAPI app, mounted at `/mcp/v1/`)
- Bearer token auth as the v1 mechanism
- 7-tool MVP scope
- Read-only enforcement as a hard requirement
- Observability via Railway logs

**Pass 1 disagreements / open questions:**

1. **Account name anonymization (AEGIS concern 3 vs ATHENA concern 7).** AEGIS prefers anonymized account IDs with a separate lookup tool. ATHENA says defer to v2 and ship friendly names in v1 with documented tradeoff. Nick decides — but ATHENA's pragmatic call is the right v1 default.

2. **Caching at the MCP layer (ATLAS concern 2).** ATLAS wants pass-through with no MCP-layer cache. Implicit agreement from others (no one proposed caching). Confirmed: pass-through only, preserve source staleness metadata.

3. **Tool description authoring (ATHENA concern 1).** ATHENA wants to review descriptions before CC writes them. No conflict, just adds a step to the implementation flow.

**Cross-cutting requirements not in the original spec:**

- (ATLAS) `staleness_seconds` field in every tool response
- (ATLAS) `schema_version` field in every tool response
- (ATLAS) Pass-through hub rate-limit responses as structured errors
- (AEGIS) Method-restricted HTTP client class for downstream hub calls (defense in depth on read-only enforcement)
- (AEGIS) Per-token rate limiting at the MCP layer (60 req/min, 5K/day)
- (AEGIS) Token rotation procedure documented and tested
- (AEGIS) CORS origin restriction to Anthropic's MCP infrastructure
- (ATHENA) Structured error contract (status / data / staleness / error / schema_version)
- (ATHENA) Migration patch for TORO/URSA Context A as in-scope, not deferred
- (HELIOS) Connection flow documentation
- (HELIOS) Dual-format tool responses (structured + summary)
- (HELIOS) Connection-status check in Olympus committee skill output
- (HELIOS) Self-describing meta-tool (`mcp_describe_tools`)

---

## What I Need From Nick Before Pass 2

Three decisions, one optional:

1. **AEGIS vs ATHENA on account anonymization.** I lean ATHENA — defer to v2, ship friendly names, document the tradeoff. Confirm or override?

2. **Tool description authoring flow.** ATHENA wants to review descriptions before CC writes them. That means: after Pass 2, ATHENA drafts descriptions in a follow-up step, Nick reviews, then implementation brief. Adds ~1 day. Confirm or skip (skip = CC writes descriptions and we iterate post-launch)?

3. **Cross-cutting requirements list.** Above. Anything you'd remove, anything you'd add?

4. **(Optional) v2 candidates priority order.** ATHENA listed v2 items. If you have a strong opinion on which lands next after v1 (signal_outcomes for backtesting? battlefield_brief? PnL?), say so now and I'll note it.

Answer those and I run Pass 2 — each Titan cross-references the others, refines their concerns, and ATHENA writes the synthesis overview for your final approval before the implementation brief goes to CC.
