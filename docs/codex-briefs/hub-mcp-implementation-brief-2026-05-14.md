# Brief: Pandora's Box Hub MCP Server v1 Implementation (2026-05-14)

**Scope:** Build a new MCP (Model Context Protocol) server module inside the existing Pandora's Box FastAPI backend on Railway. Expose read-only hub data as MCP tools that Claude.ai (Olympus committee) and other Claude surfaces can call from inside a chat. Migrate TORO and URSA SKILL.md files to call the new tools in their Context A path. Ship documentation for token rotation and connection setup.

**Why this matters:** Olympus currently has no live data access from Claude.ai chats. The committee fabricates context when running unconfirmed (the TSLA failure mode that triggered this build). This MCP closes that gap permanently. After this lands, every TORO/URSA committee output begins with a GROUND TRUTH block built from verified hub data, not from training-data priors.

**This build was Titans-reviewed.** See `docs/strategy-reviews/titans-pass1-hub-mcp-2026-05-14.md` and `docs/strategy-reviews/titans-pass2-hub-mcp-2026-05-14.md` for the architecture rationale. ATHENA's tool-descriptions doc at `docs/specs/hub-mcp-tool-descriptions-2026-05-14.md` is the canonical source for all tool description copy — CC reads description text VERBATIM from that file into the FastMCP decorators.

---

## Pre-Flight

Run from repo root (`C:\trading-hub`):

```
git fetch
git status
```

If behind origin/main:
```
git pull --no-edit
```

Confirm working tree is clean. Confirm the four supporting docs are present at the canonical paths above. If any are missing, STOP and tell Nick — the docs are required references for this build.

Verify Railway backend is currently healthy:
```
curl https://pandoras-box-production.up.railway.app/health
```

If unhealthy, STOP — don't add MCP module to a broken backend.

---

## Deliverables Summary

1. **New module `backend/mcp/`** containing FastMCP server, 9 tools, response envelope helper, read-only enforcement, rate limiter, audit logger, auth.
2. **`backend/mcp/router.py`** mounted on the existing FastAPI app at `/mcp/v1/`.
3. **`backend/services/read_only/`** namespace — refactor existing read-only service functions (bias composite, flow radar, etc.) into a namespace that CANNOT import write services. This is AEGIS-mandated defense-in-depth.
4. **Environment variable `MCP_BEARER_TOKEN`** added to Railway, generated with 256 bits of entropy.
5. **Migration patches to `skills/toro/SKILL.md` and `skills/ursa/SKILL.md`** — update Context A path to reference specific MCP tool names, re-package both `.skill` files.
6. **Documentation:** `docs/operations/mcp-connection-guide.md`, `docs/operations/mcp-token-rotation.md`, README section documenting v1 risk profile.

---

## Architecture Decisions (Read Before Implementing)

**Universal response envelope (every tool returns this shape, no exceptions):**

```python
{
  "status": "ok" | "stale" | "degraded" | "unavailable",
  "data": <tool-specific payload, or None>,
  "summary": str,  # ≤300 chars, human-readable, truncate with ellipsis if implementation produces more
  "staleness_seconds": int | None,
  "schema_version": "v1.0",
  "error": str | None
}
```

A helper function `make_response(status, data, summary, staleness_seconds=None, error=None)` lives at `backend/mcp/envelope.py` and is the ONLY way tools produce responses. Direct dict construction is disallowed by lint rule.

**Read-only enforcement (three layers — all required):**

1. **Decorator `@mcp_tool` on every tool function.** Functions without it fail at registration — service won't start. Implemented in `backend/mcp/decorators.py`.

2. **Import-based read-only namespace.** All MCP tools import their data from `backend/services/read_only/` ONLY. This namespace contains query functions; write functions (mutations, inserts, updates) live in `backend/services/write/` (existing location, unchanged) and are NOT importable from the MCP module. Enforce with a pre-commit lint check at `scripts/lint_mcp_imports.py` that fails if `backend/mcp/` imports anything from `backend/services/write/`.

3. **AEGIS code review before merge.** The MCP module's full diff goes to a security-reviewed PR. No bypassing this.

This replaces the AEGIS Pass 1 "method-restricted HTTP client" recommendation. ATHENA confirmed in Pass 2 that import-based isolation provides equivalent defense-in-depth without HTTP overhead, since both achieve "tools physically cannot trigger a write." Document the rationale in `backend/mcp/README.md`.

**Authentication:**

- Bearer token in `Authorization: Bearer <token>` header
- Token stored ONLY in Railway env var `MCP_BEARER_TOKEN`
- Generate with `secrets.token_urlsafe(32)` — that produces 256 bits of entropy
- Verification in middleware at `backend/mcp/auth.py` — every request to `/mcp/v1/*` checks the header against the env var, rejects with 401 if mismatch
- HTTPS-only enforced — reject plain HTTP requests at the route level

**Rate limiting (per-token):**

- 60 requests/minute, 5,000 requests/day
- Implemented as middleware at `backend/mcp/rate_limit.py`
- `mcp_ping` is EXEMPT (Olympus calls it at the start of every committee pass — burning rate limit on health checks is wrong)
- Use SlowAPI library or equivalent. Token-bucket algorithm.
- Rate-limit exceeded returns the universal envelope with `status="unavailable"` and `error="Rate limit exceeded: <details>"` so skills can degrade gracefully

**Audit logging:**

- Every MCP call logged: timestamp, tool name, parameters (with tickers/accounts hashed), response status, latency ms, caller IP
- Land in Railway logs via the existing logging setup — no new logging infrastructure
- Implementation at `backend/mcp/audit.py`
- Hashing function: SHA-256 truncated to 8 hex chars (enough to correlate without exposing values)

**CORS:**

- Restrict allowed origins to Anthropic's MCP infrastructure. As of 2026-05, the documented origins are `https://claude.ai` and `https://*.anthropic.com`. Check the latest MCP server documentation at https://modelcontextprotocol.io/docs and use the published origin list — if it has changed, use the current list, not these hardcoded values.
- Configured in FastAPI's `CORSMiddleware` on the `/mcp/v1/*` routes specifically (don't loosen CORS on existing hub endpoints).

**Mount point:**

- FastMCP routes mounted at `/mcp/v1/` on the existing FastAPI app
- Final public URL: `https://pandoras-box-production.up.railway.app/mcp/v1/`
- The `/v1/` version segment is mandatory — future v2 will mount in parallel at `/mcp/v2/` to avoid breaking changes

**Dependencies to add to `requirements.txt`:**

- `fastmcp>=2.0.0` (or latest stable — check PyPI)
- `slowapi>=0.1.9` (for rate limiting) — only if not already present

Verify versions against the current Python version of the Railway deployment before pinning.

---

## Phase 1: Build the MCP Server Module

This phase ends with the MCP server deployed to Railway, reachable, and verifiable via `mcp_ping`. Do NOT proceed to Phase 2 (TORO/URSA migration) until Phase 1 is verified working.

### Step 1.1: Create the module structure

Create these new files (empty stubs first, fill in subsequent steps):

```
backend/mcp/
├── __init__.py
├── README.md           # Document the architecture decisions above
├── router.py           # FastMCP server + tool registration
├── envelope.py         # make_response() helper
├── decorators.py       # @mcp_tool with registration-time validation
├── auth.py             # Bearer token middleware
├── rate_limit.py       # SlowAPI integration
├── audit.py            # Audit logging
└── tools/
    ├── __init__.py
    ├── bias_composite.py
    ├── flow_radar.py
    ├── sector_strength.py
    ├── hermes_alerts.py
    ├── hydra_scores.py
    ├── positions.py
    ├── portfolio_balances.py
    ├── ping.py
    └── describe.py
```

Plus the read-only services namespace (refactor existing service functions into it):

```
backend/services/read_only/
├── __init__.py
├── bias.py             # get_composite_bias(), etc.
├── flow.py             # get_flow_radar(), etc.
├── sectors.py
├── catalysts.py        # Hermes
├── squeezes.py         # Hydra
├── positions.py        # unified_positions reads only
└── balances.py
```

CC's call on whether the existing functions move physically or are re-exported from `read_only/` — both are acceptable. Document the choice in `backend/mcp/README.md`.

### Step 1.2: Implement `backend/mcp/envelope.py`

The `make_response()` helper. Signature:

```python
def make_response(
    status: Literal["ok", "stale", "degraded", "unavailable"],
    data: Any | None = None,
    summary: str = "",
    staleness_seconds: int | None = None,
    error: str | None = None,
) -> dict:
    """Build the universal MCP response envelope.
    
    Truncates summary to 300 chars with ellipsis if longer.
    Always includes schema_version="v1.0".
    """
```

Add a unit test at `backend/mcp/tests/test_envelope.py` covering:
- All four status values produce valid envelopes
- Summary >300 chars gets truncated to 297 + "..."
- Missing data is None, not omitted
- schema_version is always "v1.0"

### Step 1.3: Implement `backend/mcp/decorators.py`

The `@mcp_tool` decorator. Behavior:

```python
def mcp_tool(name: str, description: str):
    """Register a function as an MCP tool. 
    
    Fails at module import time if the function is not in the
    registered tool list. The registered tool list is hardcoded
    in this file and matches the 9 tools in the tool-descriptions doc:
    
    - hub_get_bias_composite
    - hub_get_flow_radar
    - hub_get_sector_strength
    - hub_get_hermes_alerts
    - hub_get_hydra_scores
    - hub_get_positions
    - hub_get_portfolio_balances
    - mcp_ping
    - mcp_describe_tools
    
    A 10th tool registration attempt raises AssertionError at import time,
    preventing the service from starting.
    """
```

Add a unit test that confirms registering an unknown tool name raises at import.

### Step 1.4: Implement `backend/mcp/auth.py`

Bearer token middleware. Behavior:

- Reads `Authorization: Bearer <token>` header
- Compares against `os.environ["MCP_BEARER_TOKEN"]` using `secrets.compare_digest()` (constant-time comparison — important per AEGIS)
- Mismatch returns HTTP 401 with body `{"error": "Invalid or missing bearer token"}`
- No token configured (env var unset) returns HTTP 500 with body `{"error": "MCP server misconfigured"}` and logs a critical error

Add a unit test covering: missing header, malformed header, wrong token, correct token, missing env var.

### Step 1.5: Implement `backend/mcp/rate_limit.py`

SlowAPI integration with per-token rate limits:

- 60 requests/minute per token (rolling 60s window)
- 5,000 requests/day per token (rolling 24h window)
- Both limits checked; either being exceeded triggers the rate limit response
- `mcp_ping` route exempt from both limits (use SlowAPI's exemption decorator)
- Rate limit exceeded returns the universal envelope with `status="unavailable"` and a descriptive error

The "token" used as the rate limit key is the bearer token itself (hashed for log safety). If multiple tokens ever exist (v2 multi-user), each gets its own bucket.

### Step 1.6: Implement `backend/mcp/audit.py`

Audit logger middleware. Logs every MCP request to the existing Railway logging setup with fields:

- `timestamp` (ISO-8601 UTC)
- `tool_name`
- `parameters_hash` (SHA-256 truncated to 8 hex chars of the JSON-serialized parameters)
- `response_status` (the envelope's `status` field)
- `latency_ms`
- `caller_ip` (from `X-Forwarded-For` header, falling back to direct connection IP)
- `token_hash` (SHA-256 truncated to 8 hex chars of the bearer token — NEVER log the full token)

Logs go through the existing `logging.getLogger("pandoras_box.mcp.audit")` channel so the existing log aggregation captures them.

### Step 1.7: Implement the 9 tools

For each of the 9 tools, build a Python function in the corresponding file under `backend/mcp/tools/`. Each function:

1. Is decorated with `@mcp_tool(name="hub_get_X", description="<exact verbatim text from tool-descriptions doc>")`
2. Accepts the parameters specified in the tool-descriptions doc
3. Calls into `backend/services/read_only/` to fetch the data
4. Returns a response built with `make_response()`
5. Has the `data` field schema matching what's specified in the tool-descriptions doc
6. Produces a `summary` field matching the style of the example in the tool-descriptions doc

**Critical:** The `description` string in the `@mcp_tool` decorator is the EXACT verbatim text from the "Description (verbatim for FastMCP decorator)" blockquote in `docs/specs/hub-mcp-tool-descriptions-2026-05-14.md`. CC reads it from the doc and copies it character-for-character. This is the part Claude's relevance ranker reads to decide whether to call the tool — getting it right is critical.

For each tool, also write a unit test at `backend/mcp/tests/test_<tool_name>.py` that:
- Calls the tool with valid parameters and asserts the response envelope is correct
- Calls the tool with invalid parameters and asserts a structured error response
- Calls the tool when the underlying service is mocked to fail and asserts `status="unavailable"`

### Step 1.8: Implement `backend/mcp/router.py`

The FastMCP server itself:

- Initialize a FastMCP instance
- Register all 9 tools (the decorators in step 1.7 register them with FastMCP)
- Mount as a FastAPI sub-application at `/mcp/v1/`
- Apply the auth middleware (1.4), rate limit middleware (1.5), audit middleware (1.6), CORS middleware
- The middleware order matters: auth FIRST, then rate limit, then audit. Reject unauthorized requests before any other processing.

### Step 1.9: Integrate into the existing FastAPI app

In the main FastAPI app file (likely `backend/main.py` or `backend/app.py` — CC verifies the actual path):

```python
from backend.mcp.router import mcp_router
app.mount("/mcp/v1", mcp_router)
```

Verify the existing app doesn't have a route conflict at `/mcp/v1`. If it does, STOP and tell Nick.

### Step 1.10: Add the lint check

Create `scripts/lint_mcp_imports.py` that:

- Recursively scans all `.py` files under `backend/mcp/`
- Parses imports
- Fails with exit code 1 if ANY import references `backend.services.write` (or any submodule of it), `backend.database.write`, or any function whose docstring/signature indicates a write operation
- Run this script as a pre-commit hook AND as a CI step in the existing build pipeline

Add the script's invocation to `.github/workflows/` (if CI is GitHub Actions) or wherever the existing CI is configured.

### Step 1.11: Deploy to Railway

- Generate the bearer token: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- Add to Railway env vars as `MCP_BEARER_TOKEN`. Save the token in a SECURE place — Nick will paste it into Claude.ai. Do NOT commit it. Do NOT log it. Do NOT include it in this brief's output.
- Commit and push:
  ```
  git add backend/mcp/ backend/services/read_only/ scripts/lint_mcp_imports.py requirements.txt
  git commit -F C:\temp\mcp_phase1_commit_msg.txt
  git push origin main
  ```
- Wait for Railway auto-deploy to complete. Verify the deployment is healthy:
  ```
  curl https://pandoras-box-production.up.railway.app/health
  ```

### Step 1.12: Verify Phase 1 end-to-end

From a terminal (CC runs these):

1. **Auth verification — bad token should be rejected:**
   ```
   curl -X POST https://pandoras-box-production.up.railway.app/mcp/v1/tools/mcp_ping \
     -H "Authorization: Bearer WRONG_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{}'
   ```
   Expected: HTTP 401.

2. **Auth verification — correct token should work:**
   ```
   curl -X POST https://pandoras-box-production.up.railway.app/mcp/v1/tools/mcp_ping \
     -H "Authorization: Bearer <THE_REAL_TOKEN>" \
     -H "Content-Type: application/json" \
     -d '{}'
   ```
   Expected: HTTP 200 with envelope `{"status": "ok", "data": {...}, "summary": "MCP: connected...", ...}`.

3. **Each of the 9 tools returns a valid envelope.** CC calls each one and verifies the response shape against the spec in the tool-descriptions doc.

4. **Rate limit verification:** Call `hub_get_bias_composite` 61 times in 60 seconds — the 61st should return `status="unavailable"` with rate-limit error. Then call `mcp_ping` once — should succeed (exempt).

5. **Read-only enforcement verification:** Attempt to add a fake write tool to `backend/mcp/tools/`, run the lint script, confirm it fails.

If ALL FIVE verifications pass, Phase 1 is complete. Save the bearer token in a secure note for Nick.

If ANY verification fails, STOP, document the failure mode, and tell Nick before proceeding.

---

## Phase 2: TORO and URSA Migration Patch

This phase only runs AFTER Phase 1 verification passes.

### Step 2.1: Patch `skills/toro/SKILL.md`

Find the `### Context A: Hub reachable` section under `## Pre-Output Data Checklist`. Replace it with this updated version that names specific MCP tools:

**Find this block:**

```markdown
### Context A: Hub reachable (e.g., committee bridge running on the VPS)

Pull these endpoints in order before producing output. Never fabricate; surface stale/missing data explicitly.

1. `GET /api/bias/composite/timeframes` — bias readings, all timeframes
2. `GET /api/flow/radar` — options flow imprint
3. `GET /api/watchlist/sector-strength` — sector rotation context
4. `GET /api/hermes/alerts` — active catalysts
5. `GET /api/hydra/scores` — squeeze setups
6. Recent UW API readings on the specific instrument (flow, GEX, IV regime)
7. Recent TradingView webhook fires relevant to the instrument
8. Open positions in `unified_positions` if the bull case touches an existing exposure
9. Current week's Battlefield Brief for mechanical flow context
```

**Replace with this block:**

```markdown
### Context A: Hub reachable (via Pandora's Box MCP server, e.g., in Claude.ai with MCP connector active)

The Pandora's Box hub MCP server is the authoritative data source. Begin by calling `mcp_ping` to confirm connection state; surface "MCP: connected" or "MCP: unreachable" in the DATA NOTE block at the end of the output. Then call these MCP tools in order; never fabricate, surface stale or missing data explicitly:

1. `hub_get_bias_composite(timeframe="swing")` — directional bias context (swing timeframe for B1/B2 thesis; switch to "intraday" for B3 scalps)
2. `hub_get_flow_radar(ticker=<the ticker>)` — options flow imprint for the specific instrument
3. `hub_get_sector_strength()` — sector rotation context for the instrument's sector
4. `hub_get_hermes_alerts(ticker=<the ticker>)` — active catalysts within DTE window
5. `hub_get_hydra_scores(ticker=<the ticker>)` — squeeze setup score if the thesis touches short positioning
6. `hub_get_positions(ticker=<the ticker>)` — existing exposure on this ticker (triggers the "add to existing position" branch if anything is open)
7. `hub_get_portfolio_balances()` — account balances for sizing recommendations

If ANY MCP tool returns `status="unavailable"` or `status="stale"`, append a DATA NOTE block at the end of the output naming which tool failed and degrade conviction by one notch per missing input. If `mcp_ping` itself fails, fall back to Context B (web_search ground truth) and surface "MCP: unreachable" prominently.
```

### Step 2.2: Patch `skills/ursa/SKILL.md`

Mirror the TORO edit with URSA's wording (URSA's tool emphasis is different — `hub_get_positions` is MANDATORY for URSA, not conditional).

**Find this block:**

```markdown
### Context A: Hub reachable (e.g., committee bridge running on the VPS)

Pull these endpoints in order before producing output. Never fabricate; surface stale/missing data explicitly.

1. `GET /api/bias/composite/timeframes` — bias readings, all timeframes
2. `GET /api/flow/radar` — options flow imprint (look for distribution, put buying, call selling)
3. `GET /api/watchlist/sector-strength` — sector rotation context (look for deteriorating leaders, broadening weakness)
4. `GET /api/hermes/alerts` — adverse catalysts within the DTE window
5. `GET /api/hydra/scores` — fading squeeze setups or short setups
6. Recent UW API readings (look for negative flow imbalance, expanding put skew, GEX flip threats)
7. Open positions in `unified_positions` — portfolio concentration and coherence check
8. Current week's Battlefield Brief for adverse mechanical flow context
```

**Replace with this block:**

```markdown
### Context A: Hub reachable (via Pandora's Box MCP server, e.g., in Claude.ai with MCP connector active)

The Pandora's Box hub MCP server is the authoritative data source. Begin by calling `mcp_ping` to confirm connection state; surface "MCP: connected" or "MCP: unreachable" in the DATA NOTE block at the end of the output. Then call these MCP tools in order; never fabricate, surface stale or missing data explicitly:

1. `hub_get_bias_composite(timeframe="swing")` — directional bias context (look for bias-vs-user-lean mismatch; if user is bearish on a TORO MAJOR day, flag in BIAS CHALLENGE)
2. `hub_get_flow_radar(ticker=<the ticker>)` — options flow (look for distribution, put buying, call selling)
3. `hub_get_sector_strength()` — sector rotation (look for deteriorating leaders, broadening weakness)
4. `hub_get_hermes_alerts(ticker=<the ticker>)` — adverse catalysts within DTE window (URSA's hard rule: catalyst risk awareness is MANDATORY)
5. `hub_get_hydra_scores(ticker=<the ticker>)` — fading squeezes or short setups
6. `hub_get_positions()` — MANDATORY portfolio coherence check across the entire book, not just this ticker. Required on every URSA committee pass per hard rules.
7. `hub_get_portfolio_balances()` — account balances for sizing and concentration check

If ANY MCP tool returns `status="unavailable"` or `status="stale"`, append a DATA NOTE block at the end of the output naming which tool failed and degrade conviction by one notch per missing input. If `mcp_ping` itself fails, fall back to Context B (web_search ground truth) and surface "MCP: unreachable" prominently. If `hub_get_positions` fails specifically, URSA cannot complete its portfolio coherence check — surface this gap explicitly because it violates a hard rule.
```

### Step 2.3: Re-package both skills

```
scripts\package-skill.bat all
```

Verify:
- `dist/skills/toro.skill` rebuilt with patched content
- `dist/skills/ursa.skill` rebuilt with patched content
- Both archives use forward-slash paths internally
- `dist/skills/_archive*` does not exist (underscore-prefix exclusion still working)

### Step 2.4: Verify Phase 2 end-to-end

Nick performs the verification (not CC) because it requires Claude.ai interaction:

1. Nick uploads the new `toro.skill` and `ursa.skill` to Claude.ai → Customize → Skills (replacing existing entries)
2. Nick connects the MCP server in Claude.ai → Settings → Connectors → Add custom connector → URL `https://pandoras-box-production.up.railway.app/mcp/v1/` → paste bearer token
3. Nick runs a TSLA committee pass in a fresh chat
4. Expected output: GROUND TRUTH block at the top sourced from `hub_get_bias_composite`, `hub_get_flow_radar`, `hub_get_positions`, etc. — visible MCP tool calls in the chat, real verified numbers, no fabrication

CC's responsibility ends with the .skill packages being on disk in `dist/skills/`. Nick handles the upload and Claude.ai-side connector setup.

---

## Phase 3: Documentation

### Step 3.1: Write `docs/operations/mcp-connection-guide.md`

A step-by-step guide for connecting the MCP server in Claude.ai. Content:

- Where the public URL lives (`https://pandoras-box-production.up.railway.app/mcp/v1/`)
- Where the bearer token lives (Railway env var; Nick keeps a secure local copy)
- Step-by-step screenshots-worthy instructions: Claude.ai → Settings → Connectors → Add custom → paste URL → paste token → confirm → verify with a test prompt that triggers `mcp_describe_tools`
- Troubleshooting: "MCP: unreachable" — what to check (token rotated? Railway healthy? CORS still valid?)
- Mobile note: connect once on desktop, mobile inherits via account sync

### Step 3.2: Write `docs/operations/mcp-token-rotation.md`

Procedure for rotating the bearer token. Content:

- When to rotate: suspected leak, scheduled rotation (e.g., quarterly), staff change (N/A for Nick but document for completeness)
- How to rotate:
  1. Generate new token: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
  2. Update Railway env var `MCP_BEARER_TOKEN` to the new value
  3. Wait for Railway to redeploy (~1-2 min)
  4. Old token is immediately invalid
  5. Update Claude.ai connector with new token
  6. Verify with a test prompt
- Verification that rotation worked: attempt a call with old token, confirm 401

### Step 3.3: Add README section documenting v1 risk profile

In the existing repo README (or `backend/mcp/README.md`, whichever Nick prefers — recommend `backend/mcp/README.md` for scope), add a section titled "v1 Risk Profile" with:

> The v1 hub MCP server uses a single bearer token for authentication. The token grants full read access to: bias composite, options flow, sector strength, catalyst alerts, squeeze scores, all positions across all four accounts (Robinhood, Fidelity Roth, 401k BrokerageLink, Breakout Prop), and account balances. A token leak would expose Nick's full trading book to the attacker. The leak does NOT grant write access — Olympus reads, Olympus does NOT trade. Mitigation: rotate the token immediately if a leak is suspected per `docs/operations/mcp-token-rotation.md`. v2 plans introduce account-ID anonymization via a separate lookup tool to reduce the blast radius of a single-token leak.

This documentation is AEGIS-mandated. It must exist before launch.

---

## Phase 4: Commit and Push (final)

After Phases 1-3 are complete, the final commit covers documentation and any post-deploy cleanup. Use the file-based commit message workflow:

Write commit message to `C:\temp\mcp_v1_final_commit_msg.txt`:

```
feat(mcp): Pandora's Box hub MCP server v1 — Olympus gets hub access

PHASE 1: New module backend/mcp/ exposes 9 read-only tools (hub_get_bias_composite,
hub_get_flow_radar, hub_get_sector_strength, hub_get_hermes_alerts, hub_get_hydra_scores,
hub_get_positions, hub_get_portfolio_balances, mcp_ping, mcp_describe_tools) via FastMCP
mounted at /mcp/v1/ on the existing FastAPI app. Bearer token auth (MCP_BEARER_TOKEN env
var), per-token rate limiting (60/min, 5K/day, mcp_ping exempt), audit logging, CORS
restricted to Anthropic MCP origins. Three-layer read-only enforcement: @mcp_tool
decorator with registration-time fail, import-based isolation (backend/services/read_only/
namespace cannot import write services), and pre-commit lint check at
scripts/lint_mcp_imports.py.

PHASE 2: TORO and URSA SKILL.md Context A paths updated to call specific MCP tool names
(hub_get_bias_composite, hub_get_flow_radar, etc.). Both skills re-packaged.
URSA's hub_get_positions call is documented as MANDATORY per existing portfolio-coherence
hard rule.

PHASE 3: docs/operations/mcp-connection-guide.md and docs/operations/mcp-token-rotation.md
written. v1 risk profile documented in backend/mcp/README.md per AEGIS requirement.

Architecture review: Titans Pass 1 and Pass 2 at docs/strategy-reviews/. Tool descriptions
canonical at docs/specs/hub-mcp-tool-descriptions-2026-05-14.md. Acceptance criteria from
ATHENA's Pass 2 synthesis: all 9 tools return real data when called from Claude.ai;
TORO/URSA produce GROUND TRUTH blocks sourced from hub data not web_search; read-only
enforcement verified by attempting a write and watching it fail; token rotation tested
end-to-end; 7 days of observability data before declaring v1 done.

Closes Olympus fabrication risk identified during 2026-05-15 TSLA test.
```

Then:
```
git commit -F C:\temp\mcp_v1_final_commit_msg.txt
git push origin main
```

---

## Acceptance Criteria for v1

All five must hold before v1 is declared done:

1. All 9 tools return real data when called from a Claude.ai chat in the Pandora's Box project
2. TORO and URSA, when updated to use the MCP, produce GROUND TRUTH blocks that cite hub data (not web_search results) — verified by a TSLA committee pass
3. Read-only enforcement validated: attempt to add a write tool and watch the lint script + decorator both fail
4. Token rotation tested end-to-end: rotate token, old token rejected with 401, new token works
5. 7 days of observability data showing which tools actually get called and at what rate

If those five hold after 7 days, v1 is done. Next: v2 candidates (signal_outcomes, battlefield_brief, PnL, account anonymization, IP allowlist).

---

## Out of Scope (do NOT do)

- Do not add any write tools or write-capable endpoints
- Do not modify the existing Pandora's Box backend routes (`/api/*`) — the MCP is additive
- Do not modify any other skill files beyond TORO and URSA
- Do not build the UW MCP wiring (separate workstream — UW provides their own MCP, just needs a config block in claude_desktop_config.json which Nick handles)
- Do not implement account-ID anonymization (v2)
- Do not implement IP allowlisting (v2)
- Do not add observability dashboards (v2)
- Do not implement signal_outcomes, battlefield_brief, or PnL tools (v2)
- Do not change the existing FastAPI app's CORS, auth, or rate-limit configuration on existing routes — your changes are scoped to `/mcp/v1/*` only
- Do not upload the new `.skill` files to Claude.ai — Nick handles that manually

---

## Questions to Resolve Before Starting

If any of these are unclear, ASK NICK before coding:

1. Path of the main FastAPI app entry point (`backend/main.py` vs `backend/app.py` vs other)
2. Whether the existing logging setup uses structlog, vanilla logging, or another library
3. Whether the existing CI pipeline is GitHub Actions, Railway-native, or other
4. Whether there's an existing read-only service namespace that we should reuse or whether we're creating it from scratch
5. The Python version Railway is currently running (for pinning FastMCP version)

Otherwise, proceed.
