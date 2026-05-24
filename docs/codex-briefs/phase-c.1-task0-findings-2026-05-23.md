# Phase C.1 — Task 0 Dual Discovery Findings (2026-05-23)

**Status:** Server-side discovery complete. Client-side discovery pending Nick collaboration. **Surfaced to Nick on 2026-05-23 17:17 UTC (11:17 AM MDT) before proceeding to Task 1 per brief gate.**

**Branch:** `phase-c.1-oauth` (no code changes yet — Task 0 is read-only investigation).

---

## TL;DR

**The Phase C.1 brief's premise is materially out of date.** The brief states the MCP server uses static `MCP_BEARER_TOKEN` and tasks CC with building OAuth 2.1 + PKCE + DCR from scratch. **Empirical investigation shows OAuth 2.1 + PKCE + DCR are already live and working** via FastMCP 3.3.1's `OAuthProxy` with GitHub as the upstream IdP. The static bearer token is dead code per `auth.py:14`.

Phase C.1 as scoped (≈80% of the listed tasks) is duplicative work. **Pausing for Nick to make a scope call** before proceeding.

---

## 1. Server-side discovery — endpoint inventory

Live probes against `https://pandoras-box-production.up.railway.app`:

| RFC / endpoint | Brief assumed | Live state | Notes |
|---|---|---|---|
| `/.well-known/oauth-protected-resource/mcp/v1` | "may exist, may not" | **200 OK with valid PRM doc** | Returns `{resource, authorization_servers, scopes_supported, bearer_methods_supported}` per RFC 9728. Trailing-slash variant returns 307 to HTTP (Railway edge anomaly — minor) |
| `/.well-known/oauth-authorization-server` | absent | **200 OK with full RFC 8414 doc** | Advertises `authorization_endpoint`, `token_endpoint`, `registration_endpoint`, `response_types_supported=[code]`, `grant_types_supported=[authorization_code, refresh_token]`, `code_challenge_methods_supported=[S256]` (PKCE), `client_id_metadata_document_supported=true` |
| `/mcp/v1/authorize` | absent | **Live; PKCE enforced** | `GET /mcp/v1/authorize?...` without `code_challenge` returns `400 invalid_request: "code_challenge: Field required"`. PKCE is MANDATORY at the framework level |
| `/mcp/v1/token` | absent | **Live** (FastMCP OAuthProxy) | Not directly probed yet (would need valid auth code); existence inferred from AS metadata + framework architecture |
| `/mcp/v1/register` | absent | **Live** | `POST /mcp/v1/register {}` returns `400 invalid_client_metadata: "redirect_uris: Field required"` — RFC 7591 DCR is wired and validating |
| `/mcp/v1/revoke` | required | Not yet probed | Likely live per OAuthProxy; needs verification |

**WWW-Authenticate header on 401:** Already includes `resource_metadata=...` pointer per RFC 9728. FastMCP's auth challenge is compliant.

---

## 2. Server-side discovery — code reality

**`backend/hub_mcp/auth.py`** (current head, `3703cec`):
- Imports `from fastmcp.server.auth.oauth_proxy import OAuthProxy` and `from fastmcp.server.auth.providers.github import GitHubTokenVerifier`
- Defines `AllowlistedGitHubTokenVerifier(GitHubTokenVerifier)` that chains a `MCP_ALLOWED_GITHUB_USERS` allowlist enforcement on top of the default GitHub verifier
- `build_oauth_provider()` constructs an `OAuthProxy` with:
  - `upstream_authorization_endpoint=https://github.com/login/oauth/authorize`
  - `upstream_token_endpoint=https://github.com/login/oauth/access_token`
  - `upstream_client_id=GITHUB_OAUTH_CLIENT_ID` (Railway env)
  - `upstream_client_secret=GITHUB_OAUTH_CLIENT_SECRET` (Railway env)
  - `token_verifier=AllowlistedGitHubTokenVerifier(...)` with 5-min cache
  - `base_url=MCP_PUBLIC_BASE_URL` (or default Railway URL)
- Module docstring (line 14): *"The `MCP_BEARER_TOKEN` env var is no longer read by any live code path. It can be left set in Railway during the transition; removing it is a follow-up cleanup."*

**`backend/hub_mcp/server.py`:**
- `mcp = FastMCP(name=..., auth=build_oauth_provider())` — OAuthProxy is wired into FastMCP at instance construction time
- Docstring says "Auth: OAuthProxy with GitHub upstream + `MCP_ALLOWED_GITHUB_USERS` allowlist"

**`backend/hub_mcp/router.py`** architecture comment (line 4-22):
- Confirms middleware chain: CORS → RateLimit → Audit → FastMCP (with OAuthProxy)
- *"The bearer-auth middleware from v1/v2 is gone — Claude.ai's connector UI only accepts OAuth, and FastMCP's OAuthProxy is now the authoritative auth gate."*

**`docs/operations/mcp-token-rotation.md`** (already in repo):
- Top line: *"The MCP server (v3+) uses GitHub OAuth via FastMCP's OAuthProxy."*
- Documents GitHub OAuth App rotation, allowlist updates, session revocation via GitHub
- *"The pre-v3 `MCP_BEARER_TOKEN` is no longer in the live auth path; it can be removed from Railway as cleanup."*

**FastMCP version:** `fastmcp>=3.3.1` (per `requirements.txt`). The OAuthProxy / GitHubTokenVerifier / token caching infrastructure all live in the FastMCP library, not in our code.

---

## 3. Comparison to brief's task list

| Brief task | Status given reality |
|---|---|
| Task 1 — PRM endpoint | **Already live and valid.** Task collapses to "verify + document" |
| Task 2 — AS metadata endpoint | **Already live with PKCE S256, DCR enabled.** Task collapses to "verify + document" |
| Task 3 — `/authorize` with PKCE | **Already live, PKCE mandatory.** Implemented by FastMCP OAuthProxy delegating to GitHub |
| Task 4 — `/token` w/ auth-code + refresh-token grants | **Already live.** OAuthProxy handles code exchange; refresh-token rotation is FastMCP's responsibility |
| Task 5 — DCR (`/register`) w/ rate-limit | **DCR endpoint live.** Rate-limiting status TBD — we have a per-token RateLimitMiddleware that keys off Authorization header, IP fallback for anonymous (`router.py:113`). Whether that's adequate for DCR-specific 5/IP/hour ceiling needs verification |
| Task 6 — JWT access tokens (our own HS256 signing) | **Not applicable.** We don't issue our own JWTs. The tokens flowing through the MCP endpoint are FastMCP/OAuthProxy-issued tokens (architecture detail), backed by GitHub's user-token verification. Implementing our own JWT layer would mean *replacing* GitHub OAuth — a major regression in functionality (lose allowlist, lose user attribution) |
| Task 7 — Postgres `oauth_clients` + `oauth_refresh_tokens` tables | **Uncertain.** FastMCP's OAuthProxy stores client registrations + refresh tokens somewhere. Worth confirming whether storage is in-memory (loss on restart) or persisted (e.g. file-backed). **THIS IS LIKELY THE ROOT CAUSE OF THE BRIEF'S STATED PROBLEM** — see §4 |
| Task 8 — JWT signing key rotation | **Not applicable.** We don't sign JWTs; key rotation is GitHub OAuth App secret rotation (already documented in `mcp-token-rotation.md`) |
| Task 9 — Static bearer coexistence flag | **Not applicable.** Static bearer is already dead code; nothing to coexist with |
| Task 10 — Documentation: `mcp-oauth-lifecycle.md` | **Partially applicable.** A canonical OAuth lifecycle doc would be useful; deprecating `mcp-token-rotation.md` is wrong because that doc already covers the live OAuth setup (rotation procedure, allowlist, revocation) — it would need supplementing, not deprecating |
| Task 11 — Audit logging | **Already partly there.** `router.py:177` (AuditMiddleware) logs every MCP request with token-hash, tool-name, latency, response-status. Token issuance/revocation/validation aren't separately logged; that's a gap but small |
| Task 12 — Smoke tests | **Already trivially passing** for items 1, 2, 5. Items 3, 4, 6, 7, 8 either need re-scoping or are not applicable |
| Task 13 — Closure note | Applicable regardless of scope decision |

**Net:** ≈ 80% of the brief is duplicate work that's already done. The 20% that remains is partially:
- Confirming FastMCP/OAuthProxy storage backend (in-memory vs persisted)
- DCR-specific rate-limiting verification
- Audit logging gaps (token issuance/revocation/validation events)
- Documentation: extend `mcp-token-rotation.md` or author a complementary `mcp-oauth-lifecycle.md` covering the FastMCP-handled flow surface

---

## 4. The real problem (probable diagnosis)

The brief's stated motivation:
> "Every Railway deploy restarts the FastMCP process and invalidates the bearer token Anthropic's client side is holding, requiring Nick to manually restart Claude Desktop to recover."

This shouldn't happen with the current GitHub-OAuth setup because:
- GitHub access tokens don't expire on Railway restart — they're issued by GitHub, not by us
- The token verifier cache (5-min TTL) being lost on restart is harmless — first post-restart request just re-hits GitHub `/user` to verify

**The likely actual cause:** FastMCP/OAuthProxy stores **dynamically-registered client metadata** (the `client_id` Claude Desktop received from `/register`) in process memory. On Railway restart, the in-memory client registry is gone. Claude Desktop's next request includes a `client_id` the server no longer recognizes → token refresh fails → Claude Desktop must re-register → user-visible "reconnect" prompt.

If this hypothesis is correct, the right Phase C.1 scope is **drastically smaller** than the brief:

**Minimum viable fix (proposed):**
1. Verify FastMCP 3.3.1's OAuthProxy storage backend for DCR client registrations. Confirm whether it's in-memory, file-backed, or accepts an injectable persistence layer.
2. If in-memory: implement a Postgres-backed persistence layer for `oauth_clients` (Task 5's table from the brief, but the only DB table actually needed — `oauth_refresh_tokens` may already be handled by FastMCP, or may also need persistence).
3. Verify DCR rate-limiting is adequate (Task 5's 5/IP/hour ceiling — current `RateLimitMiddleware` may or may not cover this).
4. Author or extend OAuth lifecycle documentation reflecting the actual FastMCP-handled architecture.
5. Smoke-test: confirm a Railway restart no longer requires Claude Desktop reconnect (the canonical "did the fix work" test).

Optional follow-ups beyond minimum viable:
- Audit-logging gaps: instrument token issuance + revocation events at the FastMCP layer (may require subclassing OAuthProxy or wrapping the token endpoint)
- The 307-to-HTTP redirect on the trailing-slash PRM URL (minor; client follows the 200 OK at the canonical URL anyway)

---

## 5. Client-side discovery — NOT YET DONE

Requires Nick collaboration per the brief. Specifically:
- Attempt a fresh OAuth handshake from Claude Desktop AND claude.ai against the production MCP endpoint
- Observe whether the consent screen shows correctly (it should — GitHub's standard consent screen with Pandora's Box MCP app branding)
- Capture screenshot
- Verify token refresh transparent over deploy boundary (this is the ACTUAL test of whether the brief's stated problem is real and unfixed)
- Verify PKCE in the actual `/authorize` request parameters Anthropic's client sends

**Holding on this step until Nick weighs in on the scope question raised by server-side findings.**

---

## 6. Recommendations for Nick (scope decision)

Three reasonable paths:

### Option A — Reframe Phase C.1 as the "DCR persistence + reliability" fix (recommended)
Drop the 80% of duplicate-work tasks. New scope:
- Verify FastMCP DCR client registration storage; persist to Postgres if in-memory
- Verify DCR rate-limiting (5/IP/hour) is in place; add if not
- Audit-logging gaps (token issue/revoke events)
- OAuth lifecycle documentation (extend `mcp-token-rotation.md` rather than deprecate)
- Smoke-test: Railway restart no longer triggers Claude Desktop reconnect

Estimated effort: 1-2 days instead of the brief's 2-7. Branch stays `phase-c.1-oauth`; commit history reflects the reframed scope.

### Option B — Replace GitHub OAuth with internal IdP per the original brief
This is what the brief literally says to do, but it's a functional regression:
- Lose `MCP_ALLOWED_GITHUB_USERS` allowlist (would need to rebuild user management)
- Need to implement consent UI ourselves (currently outsourced to GitHub)
- Lose GitHub-side revocation (currently a single click at github.com/settings/applications)
- Self-managed JWT signing key, refresh-token storage, etc.

Not recommended unless there's a reason to leave GitHub I'm not seeing.

### Option C — Hybrid: Keep GitHub OAuth, address the real reliability issue
Same as Option A in practice; just naming it explicitly as the recommended path.

---

## 7. Pause point

**Awaiting Nick decision on scope.** Will not proceed to Task 1 (or revised equivalent) until scope is confirmed.

**No code changes have been made on the `phase-c.1-oauth` branch beyond saving the brief.** Branch is at `8cc2a90` (brief commit only). This findings document will be committed once Nick confirms it's ready to land.

---

## Appendix: full live AS metadata response

```json
{
  "issuer": "https://pandoras-box-production.up.railway.app/mcp/v1",
  "authorization_endpoint": "https://pandoras-box-production.up.railway.app/mcp/v1/authorize",
  "token_endpoint": "https://pandoras-box-production.up.railway.app/mcp/v1/token",
  "registration_endpoint": "https://pandoras-box-production.up.railway.app/mcp/v1/register",
  "scopes_supported": ["user"],
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code", "refresh_token"],
  "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
  "code_challenge_methods_supported": ["S256"],
  "client_id_metadata_document_supported": true
}
```

## Appendix: full live PRM response

```json
{
  "resource": "https://pandoras-box-production.up.railway.app/mcp/v1/",
  "authorization_servers": ["https://pandoras-box-production.up.railway.app/mcp/v1"],
  "scopes_supported": ["user"],
  "bearer_methods_supported": ["header"]
}
```
