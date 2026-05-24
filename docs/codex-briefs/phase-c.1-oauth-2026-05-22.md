# CC Brief: Phase C.1 — OAuth on `backend/hub_mcp/` (2026-05-22)

## Purpose

The Pandora MCP server at `https://pandoras-box-production.up.railway.app/mcp/v1/` currently uses a static `MCP_BEARER_TOKEN` for authentication. Every Railway deploy restarts the FastMCP process and invalidates the bearer token Anthropic's client side is holding, requiring Nick to manually restart Claude Desktop to recover. This was empirically observed in the 2026-05-22 session — Phase A's deploy invalidated the token mid-session.

Phase C.1 replaces this with OAuth 2.1 + PKCE per the [MCP authorization specification](https://modelcontextprotocol.io/specification/draft/basic/authorization), so Anthropic's infrastructure auto-refreshes tokens transparently. This eliminates the manual restart cycle and unblocks reliable MCP availability across sessions — a prerequisite for Phase C.2/C.3/C.4 to ship without each deploy breaking the committee.

Notable starting state evidence: the 401 response from the MCP endpoint already includes a `resource_metadata` header pointing at `/.well-known/oauth-protected-resource/mcp/v1/` — FastMCP is partially RFC 9728 compliant. Task 0 determines exactly how much is already wired.

Approved by Olympus Titans full review cycle (Pass 1, Pass 2, ATHENA Overview, no Nick injection) on 2026-05-22.

## Pre-flight (mandatory before starting)

1. `cd /d C:\trading-hub`
2. `git fetch && git status` — confirm clean working tree on `main` at the post-Phase-A.3 SHA.
3. **Create a feature branch:** `git checkout -b phase-c.1-oauth`. All Phase C.1 work happens on this branch. **Do NOT merge to `main` until Phase A.3 smoke tests close clean.** Nick will signal the merge greenlight separately.
4. Read `PROJECT_RULES.md` at repo root.
5. Read `docs/operations/mcp-token-rotation.md` — current canonical reference for MCP auth handling; Phase C.1 deprecates this file in Task 10.
6. Read the four Titan `SKILL.md` files at `skills/atlas/`, `skills/athena/`, `skills/aegis/`, `skills/helios/`. This brief embeds findings from all four; the SKILL.md context helps interpret the gates.
7. Confirm `MCP_BEARER_TOKEN` is set in Railway env (for coexistence phase). Do NOT print, log, or commit the value.
8. Confirm `UW_API_KEY` is unchanged. Do NOT print, log, or commit the value.

## Tasks

### Task 0 — Dual discovery (server-side + client-side)

This task gates the effort estimate for all subsequent tasks. Output: a short findings note CC writes to `docs/codex-briefs/phase-c.1-task0-findings-2026-05-22.md` before beginning Task 1.

**Server-side discovery:**
1. Inspect FastMCP 3.3.1 source/docs in `backend/hub_mcp/` to enumerate what's already implemented:
   - Is `/.well-known/oauth-protected-resource/mcp/v1/` fully implemented? (The 401 response includes the pointer; verify the endpoint actually returns a valid PRM document.)
   - Are `/authorize`, `/token`, `/revoke` partially implemented or absent entirely?
   - Is `/.well-known/oauth-authorization-server` implemented?
   - Does FastMCP have OAuth middleware/helpers, or is the auth implementation purely at the FastAPI level?
2. Document the findings as a table: endpoint → present/absent → notes.
3. Re-estimate effort for the remaining tasks based on findings. Original estimate: 2-3 days if FastMCP has OAuth helpers, 5-7 days if implementing from scratch.

**Client-side discovery (collaboration with Nick required):**
1. Set up a test FastMCP instance OR a temporary scratch endpoint that returns a valid PRM document.
2. **Coordinate with Nick** to attempt an OAuth flow from Claude Desktop and claude.ai against this test endpoint:
   - Does Anthropic's client side detect the PRM document and initiate OAuth discovery?
   - Does it support PKCE (verify in the `/authorize` request parameters)?
   - Does it use Dynamic Client Registration, or does it expect to be pre-registered?
   - What does the consent screen look like? Capture a screenshot of what claude.ai and Claude Desktop display.
3. Document Anthropic-side OAuth client behavior in the findings note.

Pause and surface to Nick after Task 0 completes BEFORE proceeding to Task 1. The findings may change the scope of subsequent tasks materially.

### Task 1 — Protected Resource Metadata endpoint

Implement or complete `/.well-known/oauth-protected-resource/mcp/v1/` per RFC 9728. The endpoint MUST return a JSON document including:

```json
{
  "resource": "https://pandoras-box-production.up.railway.app/mcp/v1/",
  "authorization_servers": ["https://pandoras-box-production.up.railway.app"],
  "bearer_methods_supported": ["header"],
  "resource_documentation": "https://github.com/303webhouse/pandoras-box/blob/main/docs/operations/mcp-oauth-lifecycle.md"
}
```

The exact fields depend on RFC 9728 conformance — verify against the spec during implementation. If Task 0 reveals FastMCP already implements this correctly, this task becomes a no-op verification.

### Task 2 — Authorization Server Metadata endpoint

Implement `/.well-known/oauth-authorization-server` per RFC 8414. The endpoint MUST return a JSON document advertising:
- `issuer`
- `authorization_endpoint` (`/authorize`)
- `token_endpoint` (`/token`)
- `revocation_endpoint` (`/revoke`)
- `registration_endpoint` (`/register`)
- `grant_types_supported`: `["authorization_code", "refresh_token"]`
- `code_challenge_methods_supported`: `["S256"]` (PKCE)
- `token_endpoint_auth_methods_supported`: `["none"]` (public client per MCP spec)

### Task 3 — Authorization endpoint (`/authorize`)

Implement OAuth 2.1 authorization code grant endpoint. Per spec:
- Accepts `response_type=code`, `client_id`, `redirect_uri`, `code_challenge`, `code_challenge_method=S256`, `state`, `scope`
- Validates `client_id` against registered clients (from Task 5)
- PKCE is MANDATORY — reject if `code_challenge` or `code_challenge_method` is missing or invalid
- Issues short-lived authorization codes (e.g., 60-second TTL)
- Stores authorization code state in Redis with TTL, keyed by code value; payload includes `client_id`, `redirect_uri`, `code_challenge`, `scope`, `user_id` (if applicable)
- Redirects to `redirect_uri` with `code=<code>&state=<state>`

For the MVP, there is no human-interactive consent step — this is a single-user dev MCP server. The authorization endpoint can auto-approve based on a valid `client_id`. If future scope adds multi-user support, the consent step becomes a real UI.

### Task 4 — Token endpoint (`/token`)

Implement token exchange. Two grant types:

**Authorization code exchange:**
- Accepts `grant_type=authorization_code`, `code`, `client_id`, `redirect_uri`, `code_verifier`
- Validates code against Redis state, verifies PKCE (`code_verifier` matches `code_challenge`)
- Returns access token (JWT, HS256, 15min TTL) + refresh token (opaque, 7-day TTL)
- Deletes the used authorization code from Redis (one-time use)

**Refresh token exchange:**
- Accepts `grant_type=refresh_token`, `refresh_token`, `client_id`
- Looks up refresh token hash in Postgres `oauth_refresh_tokens` table, verifies not revoked, not expired
- Returns new access token + new refresh token (refresh token rotation per OAuth 2.1 BCP)
- Marks the old refresh token as revoked (token rotation defense)

### Task 5 — Dynamic Client Registration endpoint (`/register`)

Implement RFC 7591 Dynamic Client Registration:
- Accepts JSON: `client_name`, `redirect_uris`, `grant_types`, `token_endpoint_auth_method`, `scope`
- **Rate-limited: 5 registrations per IP per hour.** Use Redis-backed rate limiting.
- Generates a `client_id` (UUID); for public clients per MCP spec, no client_secret issued
- Stores client registration in Postgres `oauth_clients` table: `(id, client_id, client_name, redirect_uris, grant_types, token_endpoint_auth_method, scope, created_at, created_ip)`
- Returns the client registration document

**Logs every registration to a separate audit stream** at `/var/log/mcp-dcr-audit.log` (or equivalent — verify existing log infrastructure in `backend/services/`). Audit fields: `client_id`, `client_name`, `redirect_uris`, `created_ip`, `timestamp`.

### Task 6 — JWT access token implementation

- Library: use `python-jose` or `pyjwt` (pick whichever is already in `requirements.txt`; if neither, add `pyjwt`).
- Algorithm: HS256.
- Signing key: read from Railway env var `MCP_OAUTH_SIGNING_KEY`. If not present at startup, fail fast with a clear error.
- Claims: `iss`, `sub` (client_id), `aud`, `iat`, `exp` (15 min), `scope`.
- Validation: implemented as FastAPI middleware that runs on every MCP request. Reads `Authorization: Bearer <token>`, validates JWT, populates request context with `client_id` and `scope`.

### Task 7 — Refresh token storage (Postgres)

Create migration for new table `oauth_refresh_tokens`:
```sql
CREATE TABLE oauth_refresh_tokens (
  id UUID PRIMARY KEY,
  client_id UUID NOT NULL,
  token_hash VARCHAR(255) NOT NULL UNIQUE,
  scopes TEXT[],
  expires_at TIMESTAMP NOT NULL,
  revoked_at TIMESTAMP,
  revoked_reason VARCHAR(255),
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_oauth_refresh_tokens_client_id ON oauth_refresh_tokens(client_id);
CREATE INDEX idx_oauth_refresh_tokens_token_hash ON oauth_refresh_tokens(token_hash);
```

Refresh tokens are generated as cryptographically random opaque strings (e.g., 32 bytes URL-safe base64). The plaintext is returned to the client once at issuance; only the hash is stored. Lookup is by hash, not plaintext.

Also create `oauth_clients` table for Task 5 registration storage. Schema in the migration.

### Task 8 — JWT signing key rotation pattern

Document and implement multi-key validation:
- Validation key set is a LIST of keys, not a single key. At startup, read `MCP_OAUTH_SIGNING_KEY` (active) AND `MCP_OAUTH_SIGNING_KEY_PREV` (previous, optional).
- Tokens are SIGNED with the active key only.
- Tokens are VALIDATED against any key in the set.
- At rotation: operator sets `MCP_OAUTH_SIGNING_KEY_PREV` to the current value, then sets `MCP_OAUTH_SIGNING_KEY` to the new value, then deploys. Tokens signed with the old key remain valid for one access-token TTL (15 min). After 15 min + buffer, `MCP_OAUTH_SIGNING_KEY_PREV` can be unset.

This is the standard JWT key rotation pattern. Implementation should make the rotation operator-driven (env var changes + deploy), not automatic.

### Task 9 — Static bearer coexistence (trigger-based)

During Phase C.1, the MCP server accepts BOTH:
1. JWT access tokens (Task 6)
2. The existing static `MCP_BEARER_TOKEN` (current behavior)

Both code paths run in the authentication middleware. Either passes the auth check; both populate request context appropriately.

**Trigger-based deprecation:**
- Add a feature flag `MCP_STATIC_BEARER_ENABLED` defaulting to `true`.
- The flag controls whether the middleware ALSO accepts static bearer.
- Closure note documents the trigger condition for flipping the flag to `false`: *"N≥3 successful OAuth authentications observed across both Claude Desktop and claude.ai sustained over a 72-hour window with no fallback to static bearer observed."* When trigger is met, Nick flips the flag in Railway env and redeploys. After 30 days of stable false-state, the static bearer code path is removed entirely in a follow-up cleanup commit.

### Task 10 — Documentation

1. Create `docs/operations/mcp-oauth-lifecycle.md` covering:
   - OAuth flow overview (how Anthropic clients authenticate)
   - Token lifecycle (access TTL, refresh TTL, rotation)
   - JWT signing key rotation runbook (operator steps for routine + emergency rotation)
   - DCR rate-limiting policy + audit log location
   - Revocation procedure (manual via `/revoke` endpoint or DB-level `revoked_at` write)
   - Coexistence end-trigger documented
2. Mark `docs/operations/mcp-token-rotation.md` as deprecated:
   - Add a banner at the top: *"DEPRECATED 2026-05-22 by Phase C.1 — see `mcp-oauth-lifecycle.md` for current OAuth procedures. This document is retained for historical reference only and will be removed after the static bearer coexistence period ends."*
   - Do NOT delete the file yet — it's referenced from operational runbooks Nick may still consult during the coexistence window.

### Task 11 — Audit logging

Beyond Task 5's DCR audit log:
- **Token issuance:** every `/token` call logs `client_id`, `grant_type`, `scopes_granted`, `ip`, `timestamp` to existing audit infrastructure (per `_shared/TITANS_RULES.md` patterns — likely `/var/log/committee_audit.log` or equivalent).
- **Token revocation:** every `/revoke` call OR Postgres-level revocation logs `client_id`, `revoked_token_id`, `reason`, `timestamp`.
- **Token validation:** NOT logged (too high-volume; flooding logs serves no monitoring purpose).
- **Failed authentications:** 401/403 errors with `client_id` (if available) logged at WARNING level for anomaly detection.

### Task 12 — Smoke tests

After deploy, run these verification checks:

1. `GET /.well-known/oauth-protected-resource/mcp/v1/` returns valid PRM document.
2. `GET /.well-known/oauth-authorization-server` returns valid AS metadata.
3. End-to-end OAuth flow: register a test client via `/register` → walk through `/authorize` → exchange code at `/token` → use access token in MCP request → success.
4. Refresh token rotation: exchange refresh token → confirm new access + refresh tokens returned, old refresh token revoked.
5. Static bearer coexistence: existing `MCP_BEARER_TOKEN` still authenticates against MCP endpoint.
6. **Anthropic client integration: with Nick's help, attempt fresh OAuth handshake from Claude Desktop AND claude.ai against the production MCP endpoint.** Capture screenshot of consent screen for closure note. Verify token refresh happens transparently when access token expires (wait 15+ min, run an MCP tool call, confirm no manual restart required).
7. JWT signing key rotation drill: rotate the signing key in a controlled test environment, confirm outstanding tokens validate during the multi-key window, confirm new tokens use the new key.
8. DCR rate-limit verification: attempt 6 registrations in rapid succession from one IP, confirm 6th is 429'd.

### Task 13 — Closure note

Author `docs/strategy-reviews/phase-c1-oauth-closure-note-YYYY-MM-DD.md`. Cover:
- Task 0 findings (what FastMCP had already wired + Anthropic client behavior)
- Implementation decisions per task (any deviations from this brief)
- All Task 12 smoke-test results
- Consent screen screenshot (or link to where it's stored — committed under `docs/screenshots/` if comfortable, or in the closure note attachments otherwise)
- Coexistence trigger status (initial state: trigger NOT yet met; static bearer remains enabled)
- Anything deferred or surprises encountered
- Deferred to Tier 2: refresh token reuse detection (per AEGIS Pass 2 finding)

## Output spec

- Modified: `backend/hub_mcp/` (auth implementation, endpoint handlers, middleware)
- Modified: `requirements.txt` (add `pyjwt` if not present)
- New: `backend/hub_mcp/oauth/` subdirectory (or chosen organization) containing OAuth-specific modules
- New: Postgres migration script for `oauth_clients` + `oauth_refresh_tokens` tables
- New: `docs/operations/mcp-oauth-lifecycle.md`
- Modified: `docs/operations/mcp-token-rotation.md` (deprecation banner)
- New: `docs/codex-briefs/phase-c.1-task0-findings-2026-05-22.md` (Task 0 output, committed before Task 1 starts)
- New: `docs/strategy-reviews/phase-c1-oauth-closure-note-YYYY-MM-DD.md`
- Possibly new: `docs/screenshots/phase-c1-consent-screen-claude-desktop.png` and equivalent for claude.ai

Commit messages by task group:
- Task 0 findings: `docs(c.1): Task 0 dual discovery findings`
- Implementation (Tasks 1-11): `feat(hub_mcp): Phase C.1 — OAuth 2.1 + PKCE + DCR (coexistence with static bearer)`
- Documentation (Task 10): `docs(operations): mcp-oauth-lifecycle replaces mcp-token-rotation`
- Closure: `docs(strategy-reviews): Phase C.1 closure note`

## Gates / what NOT to do

- Do NOT merge `phase-c.1-oauth` branch to `main` until Nick gives explicit greenlight (gated on Phase A.3 smoke tests closing clean).
- Do NOT flip the `MCP_STATIC_BEARER_ENABLED` feature flag to `false` during Phase C.1. That happens after the trigger condition is met — Nick's call, not CC's.
- Do NOT introduce new credentials beyond `MCP_OAUTH_SIGNING_KEY` and `MCP_OAUTH_SIGNING_KEY_PREV`. Both are Railway env vars; reference by location, never store values.
- Do NOT print, log, or commit any signing key values OR any bearer/JWT/refresh token values.
- Do NOT bypass PKCE. If Task 0 reveals an existing implementation that allowed PKCE-less flows, fix it as part of Phase C.1.
- Do NOT open DCR without rate-limiting. The 5/IP/hour ceiling is hard.
- Do NOT touch `unified_positions`, `signal_outcomes`, `signals`, or any canonical strategy data table. New tables are OAuth-specific (`oauth_clients`, `oauth_refresh_tokens`).
- Do NOT modify Phase A.3's `sector_constituent_refresh.py`, `sector_cache.py`, or `frontend/app.js` — entirely different code paths.
- Do NOT implement refresh token reuse detection in this build. Deferred to Tier 2 per AEGIS Pass 2.
- Do NOT bundle Phase C.2/C.3/C.4 work into this brief.

## Olympus Impact

Phase C.1 introduces no behavior change in any Olympus skill during the build. The committee reads via hub MCP tools (`hub_get_quote`, `hub_get_bias_composite`, `hub_get_flow_radar`, etc.), and Phase C.1 modifies the auth layer BENEATH those tools — not the tools themselves.

**Indirect benefit (the whole point of Phase C.1):** post-deploy, each subsequent Railway deploy will not invalidate the MCP token Anthropic's client side holds. Phase C.2/C.3/C.4 deploys will not break Olympus committee data access.

**Required post-build re-test (part of Task 12 #6):** full Olympus committee pass on SPY during market hours via OAuth-authenticated MCP. Verify all 7 hub tools return data correctly. This is the canonical sign-off that Phase C.1 doesn't break the existing committee data pipeline.

## Done definition

- Feature branch `phase-c.1-oauth` exists with all Phase C.1 commits.
- Task 0 findings document committed.
- All 12 Task 12 smoke checks pass.
- `docs/operations/mcp-oauth-lifecycle.md` authored, `mcp-token-rotation.md` deprecated.
- Closure note authored with consent screen screenshots + Olympus smoke-test result.
- Branch is ready to merge to `main` pending Nick's greenlight (Phase A.3 closure trigger).
- Stop and notify Nick when complete. Nick will signal the merge greenlight separately.

## Notes for the implementer

- Task 0 is gating. Do not start Task 1 until Task 0 findings are written down AND surfaced to Nick. The findings might reveal that FastMCP has substantially more wired than expected (cutting scope) OR that Anthropic's client side has quirks requiring different decisions (changing scope).
- The client-side discovery (Task 0 part 2) requires coordinating with Nick to run actual OAuth flow attempts. Surface in chat when ready for that step; Nick will be available.
- If Task 0 reveals Anthropic's client side requires features beyond OAuth 2.1 + PKCE + DCR (e.g., a specific OAuth profile or extension), pause and surface BEFORE implementing. Don't slip extra features in silently.
- The coexistence trigger language is precise on purpose ("N≥3 successful OAuth authentications across both clients sustained over 72 hours with no fallback to static bearer observed"). This is the canonical end-trigger; don't paraphrase it in the closure note.
- Anthropic-side consent screen behavior is part of the UX validation. If the screen displays something alarming (untrusted server warning, mismatched name, weird permissions), that's a finding to flag in Task 0 findings AND closure note. Likely fix is adjusting DCR registration metadata (`client_name`, `redirect_uris`).
- If the implementation goes faster than expected and Phase A.3 smokes are already closed, Nick may give the merge greenlight in real-time during the build. Don't assume the branch will sit on the shelf for days.
