# Titans Pass 2 — Pandora's Box Hub MCP Server (2026-05-14)

**Pass 2 instructions to the Titans:** Read every other Titan's Pass 1 review. Refine your own position where another Titan's concern interacts with yours, surface new issues that emerge from the cross-reference, agree or disagree explicitly with their requirements. ATHENA writes the synthesis overview for Nick at the end.

**Decisions locked by Nick after Pass 1:**
1. Account anonymization: defer to v2 (ATHENA's call). Ship v1 with friendly account names + documented tradeoff in README.
2. Tool description authoring: ATHENA drafts descriptions before CC implements.
3. Cross-cutting requirements list from Pass 1: accept all as build requirements.

---

## ATLAS Pass 2 — Backend Architect

I've read AEGIS, ATHENA, and HELIOS. Most of what they raised either complements my Pass 1 concerns or pushes on dimensions I didn't cover. Two genuine refinements and one new issue.

**Refinement 1: AEGIS's method-restricted HTTP client class is the right pattern, and it changes my caching concern.** In Pass 1 I said "no MCP-layer caching, pass-through with source staleness." AEGIS's defense-in-depth requirement — a hub client class that physically cannot send POST/PUT/PATCH/DELETE — is consistent with that, AND it gives me a natural place to enforce the no-cache rule. Same class, single responsibility: "read-only HTTP to the hub with no caching layer." If anyone ever tries to add a cache later, they have to modify this one class and the AEGIS-mandated review surface catches it. Approve and adopt.

**Refinement 2: HELIOS's dual-format response (structured payload + summary) interacts with my staleness/schema requirements.** The structured payload carries `staleness_seconds` and `schema_version` machine-readably. The summary is human-readable prose. Both should be part of the standard response envelope ATHENA defined. Updated response contract:

```
{
  "status": "ok" | "stale" | "degraded" | "unavailable",
  "data": <tool-specific structured payload, or null>,
  "summary": str,   # human-readable, ≤300 chars, used by Claude in chat output
  "staleness_seconds": int | null,
  "schema_version": str,
  "error": str | null
}
```

The skill can choose: surface the summary inline, dig into the data for analysis. Both Claude (skill output formatting) and the user (readable chat) win.

**New issue: HELIOS's self-describing meta-tool changes startup behavior.** `mcp_describe_tools()` requires the MCP server to introspect its own registered tool surface at runtime. FastMCP supports this via its tool registry, but if we're going to expose a meta-tool, it should also include each tool's `schema_version` so the user (or Claude) can detect when descriptions have drifted from documented expectations. One-line addition to HELIOS's spec.

**Verdict:** Approve with the updated response envelope. AEGIS's defense-in-depth requirement absorbed cleanly into my no-cache requirement. No conflicts.

---

## AEGIS Pass 2 — Security

Read all three. Two of my Pass 1 concerns are tightened by what others raised, and I have one new concern from ATHENA's migration plan.

**Refinement 1: ATHENA deferring account anonymization to v2 is a calculated risk I accept with one condition.** v1 ships with friendly account names AND the README documents the breach scenario explicitly: "Single bearer token grants full read access including account names, balances, positions. Token leak = trading book exposed to attacker. Mitigation: rotate token immediately if leak suspected; future v2 will introduce account-ID anonymization." I want this in the README, not buried — if a leak happens later and the response is slow because nobody remembered the risk, that's on us collectively for not documenting it. ATHENA's call is reasonable for v1 single-user scope; the documentation requirement makes it defensible.

**Refinement 2: HELIOS's connection-status check elevates a security concern.** The check fires at the start of every Olympus committee pass — that's potentially many calls per day. Each call hits the MCP endpoint and consumes rate-limit budget. Two implications:
   1. The connection-status check should be a lightweight `mcp_ping()` tool, not a real data call. Returns `{status: "ok", schema_version, server_time}`. Adds one tool to the surface, but it's cheap.
   2. The per-token rate limit I proposed (60 req/min, 5K/day) needs a carve-out for `mcp_ping` — otherwise an active testing session burns through rate limit on health checks.

**New concern: token rotation procedure for the TORO/URSA migration patch.** ATHENA brought the migration patch into v1 scope, which I support. But the migration patch references the MCP tools by name in the skill instructions. If the bearer token rotates after migration, do skills break? Answer: no, because the token is configured in Claude.ai's connector settings, not in the skill instructions themselves. Skills are token-agnostic. Confirmed. Documenting in the migration patch's notes.

**One additional hardening item:** the `mcp_describe_tools()` meta-tool returns the list of available tools. If a token leaks, the attacker doesn't need to guess what tools exist — they just call describe-tools. That's the intended behavior (it's a discovery feature), but it lowers the cost of reconnaissance. Acceptable tradeoff for v1, but flagging that v2's IP allowlist becomes more valuable because it caps who can even reach the discovery endpoint.

**Verdict:** Approve the v1 scope with the documentation requirement. `mcp_ping` added as the 8th tool. v2 IP allowlist commitment recorded.

---

## ATHENA Pass 2 — PM, Synthesis

I've read the others. Three substantive things, then the synthesis.

**Refinement 1: Adopt ATLAS's updated response envelope verbatim.** It absorbs my structured-error contract and HELIOS's dual-format requirement into a single coherent schema. The `summary` field is where the skill output's human-readable line comes from — important enough that I want it ≤300 chars enforced server-side (truncate with ellipsis if a tool implementation tries to return more). Predictable output length protects the chat experience.

**Refinement 2: Accept AEGIS's `mcp_ping` tool addition.** Now the v1 tool surface is 8 tools, not 7. Updated list:

1. `hub_get_bias_composite`
2. `hub_get_flow_radar`
3. `hub_get_sector_strength`
4. `hub_get_hermes_alerts`
5. `hub_get_hydra_scores`
6. `hub_get_positions`
7. `hub_get_portfolio_balances`
8. `mcp_ping` (NEW — lightweight health check, rate-limit exempt)

Plus the self-describing meta-tool `mcp_describe_tools()` from HELIOS. That's 9 endpoints total. Still inside MVP discipline.

**Refinement 3: Tool description authoring becomes the gating step before implementation.** Per Nick's confirmation, I draft each tool's description before CC writes the implementation. Process:
   1. Pass 2 (this document) approved by Nick
   2. I write a tool-descriptions doc (`docs/specs/hub-mcp-tool-descriptions-2026-05-XX.md`) with full description text, parameter ergonomics, when-to-call / when-not-to-call examples, and the structured response schema for each tool
   3. Nick reviews descriptions, suggests edits
   4. Implementation brief written for CC referencing the approved descriptions

This adds ~1 day to the timeline but the descriptions ARE the build's user interface. Worth it.

---

### Synthesis Overview for Nick

**What we agreed to build (v1):**

A FastMCP server module mounted on the existing Pandora's Box FastAPI app at `/mcp/v1/`. Bearer-token-authenticated read-only access to 9 endpoints (7 data tools + ping + describe). Returns a uniform response envelope with structured data, a human-readable summary, staleness metadata, schema version, and explicit error contract. Deployed to Railway alongside the existing backend, same auto-deploy from main.

**The hardening layer that emerged from the Titans pass:**

- Read-only enforcement at THREE layers: decorator on every tool function (registration-time fail), method-restricted hub client class (cannot send non-GET requests at the HTTP layer), and AEGIS-reviewed code surface before merge.
- Bearer token: 256-bit entropy, stored only in Railway env vars and Claude.ai connector config, rotation procedure documented in `docs/operations/mcp-token-rotation.md` and tested before launch.
- Per-token rate limiting: 60 req/min, 5K/day, with `mcp_ping` exempt.
- CORS restricted to Anthropic's MCP infrastructure origins.
- Audit log hygiene: tickers and account names hashed or truncated in log entries; full parameters only in encrypted-at-rest log surface if at all.
- README documents the v1 risk explicitly: bearer token leak = trading book read access exposed; v2 will introduce account-ID anonymization.

**The product layer that emerged:**

- Every tool returns a structured payload AND a concise human-readable summary (≤300 chars). Skills can surface the summary in chat without flooding the conversation, dig into the structured payload when needed for analysis.
- `mcp_ping` runs at the start of every Olympus committee pass. Connection status appears in the DATA NOTE block: "MCP: connected" or "MCP: unreachable" — never silently degrades.
- `mcp_describe_tools` self-documents the tool surface so anyone (Nick, Claude, CC) can ask "what's available" from inside a chat.
- Connection flow documented at `docs/operations/mcp-connection-guide.md` with screenshots, the URL, token entry, and a verification trigger prompt. Pinned in trading-memory.md.

**Migration into v1 scope (not deferred):**

- TORO and URSA SKILL.md files patched to call the specific MCP tool names in their Context A path. The current Context B (web_search ground truth) stays as the fallback when MCP is unreachable.
- After this lands, every TORO and URSA committee output starts with a verified GROUND TRUTH block built from real hub data — exactly the fix Nick wanted when he flagged TSLA fabrication.

**Build sequencing:**

1. **Pass 2 approved by Nick** (now)
2. **ATHENA drafts tool descriptions** — 1-day doc, Nick reviews, approves
3. **Implementation brief to CC** — covers the FastMCP module, the read-only hub client class, the response envelope, the 9 tools, the auth and rate limiting, the audit logging, the migration patch for TORO/URSA, and the connection guide doc
4. **CC builds** — estimated 1-2 days based on scope
5. **Test pass on Railway** — verify all 9 tools return real data, verify read-only enforcement by attempting a write, verify token rotation, verify rate limiting, verify `mcp_ping` health check
6. **Nick connects in Claude.ai** → Settings → Connectors → paste URL + token
7. **Run a TSLA committee pass** — first GROUND TRUTH block sourced from hub data, not web_search
8. **7 days of observability** — see which tools actually get called and at what rate
9. **v1 done. v2 candidates queue.**

**v2 roadmap (tracked, not built):**

- Account-ID anonymization with lookup tool (AEGIS's deferred concern)
- IP allowlist (AEGIS's enhancement)
- `hub_get_signal_outcomes` — backtest-aware analysis (links to the committee-review-logging TODO)
- `hub_get_battlefield_brief` — current-week mechanical flow context
- `hub_get_unified_positions_pnl` — unrealized PnL across the book
- Per-tool latency metrics dashboard
- Mobile-friendly token rotation flow

**Open Pass 2 issues:** none. All Pass 1 disagreements resolved by Nick's three decisions or by the cross-reference refinements above.

---

## What I Need From Nick to Proceed

Pass 2 is complete and the design is closed. One final approval gate:

**Approve this synthesis to proceed to ATHENA's tool-description draft?**

If yes: ATHENA writes the tool-descriptions doc next. Nick reviews it (probably ~30 minutes of read time). After Nick approves the descriptions, I write the implementation brief for CC.

If no: name what you'd change and we iterate Pass 2 once more.

Tap-friendly options provided in chat.
