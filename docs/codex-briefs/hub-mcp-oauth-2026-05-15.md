# Brief: Hub MCP OAuth Authentication (2026-05-15)

**Scope:** Replace the current `MCP_BEARER_TOKEN` auth on the hub MCP server with GitHub OAuth via FastMCP's `OAuthProxy`. The protocol layer (FastMCP 3.3.1 Streamable HTTP) works end-to-end against Claude.ai's connector, but the auth method is incompatible: Claude.ai's custom connector UI only accepts OAuth, not raw bearer tokens. This brief makes the server speak OAuth so Claude.ai can connect.

**Why this needs to happen:** After the protocol-layer fix, all 9 tools work via the MCP protocol — verified locally via `scripts/probe_mcp_local.py`. But when Nick tried to add the connector in Claude.ai → Settings → Connectors, the UI offered only URL + OAuth Client ID (optional) + OAuth Client Secret (optional). No bearer token field. Connection failed. Per FastMCP's auth documentation (https://gofastmcp.com/servers/auth/authentication), Claude.ai expects either:
- A server with full OAuth 2.1 + Dynamic Client Registration (DCR) support
- A server using `OAuthProxy` to delegate to an external OAuth provider (GitHub, Google, Azure, etc.) that doesn't support DCR

We're picking the second path with GitHub as the upstream provider.

**Bonus security upgrade:** OAuth is genuinely better than the bearer token model — tokens are short-lived, per-session, GitHub-revocable. No long-lived secret floating in Railway env vars. The README's v1 risk profile section gets revised after this lands.

**Empirically verified callback URL (CC, 2026-05-15):** `https://pandoras-box-production.up.railway.app/mcp/v1/auth/callback`. FastMCP 3.3.1's `OAuthProxy` defaults `redirect_path="/auth/callback"` and registers it inside the FastMCP Starlette app, which is mounted at `/mcp/v1` on the parent FastAPI app — so the public reachable callback is at that path.

---

## Pre-Flight

```
cd C:\trading-hub
git fetch
git status
```

Confirm working tree is clean and current HEAD includes the FastMCP protocol fix (`backend/hub_mcp/`, FastMCP 3.3.1).

Verify Railway backend health:
```
curl https://pandoras-box-production.up.railway.app/health
```

---

## Deliverables Summary

1. **Nick creates a GitHub OAuth App** (manual step — instructions in Phase 1; CC pauses for Nick's confirmation before Phase 2)
2. **Three new Railway env vars:** `GITHUB_OAUTH_CLIENT_ID`, `GITHUB_OAUTH_CLIENT_SECRET`, `MCP_ALLOWED_GITHUB_USERS` (Nick adds these)
3. **Refactor `backend/hub_mcp/router.py`** to use FastMCP's `OAuthProxy` with GitHub as the upstream IdP
4. **Restrict access to Nick's GitHub username** (`303webhouse`) via the `MCP_ALLOWED_GITHUB_USERS` env var
5. **Repurpose bearer token auth middleware** — OAuth replaces it for the MCP protocol path. Bearer auth stays on the existing REST diagnostic endpoints at `/mcp/v1/tools/*` for CC's curl-based testing and `scripts/probe_mcp_local.py`
6. **Update `docs/operations/mcp-connection-guide.md`** with the new OAuth-based connection flow
7. **Update `docs/operations/mcp-token-rotation.md`** to cover OAuth credential rotation (GitHub App secret rotation)
8. **Update `backend/hub_mcp/README.md`** v1 risk profile section to reflect OAuth (the previous "single bearer token grants full read access" risk is now mitigated)

---

## Architecture Notes

### Why GitHub OAuth via OAuthProxy (not WorkOS or Clerk)

Nick already has GitHub via `303webhouse`. No new external service to onboard. FastMCP's `OAuthProxy` was built specifically for this case (OAuth providers that don't support DCR, like GitHub). The proxy:
- Presents a DCR-compliant interface to Claude.ai (accepts any registration request)
- Uses pre-registered GitHub OAuth credentials for the actual user authentication
- Issues its own access tokens after GitHub auth succeeds
- Validates tokens on subsequent MCP requests

### Why "single user, locked to one GitHub account"

The hub data is Nick's trading book. We don't want any random GitHub user to be able to authenticate and access it. Configure `OAuthProxy` to ONLY accept authentications from a specific GitHub username (or organization).

The exact mechanism: after GitHub returns the authenticated user's info, our server checks the username against an allowlist before issuing the access token. If the username doesn't match, the auth fails.

CC implements this as either:
- A FastMCP `OAuthProxy` configuration option (if one exists for username restriction)
- A custom callback hook that validates the GitHub username before token issuance
- A wrapping check in the auth provider chain

Allowed GitHub username(s) live in a Railway env var: `MCP_ALLOWED_GITHUB_USERS` (comma-separated, default to single value `303webhouse`).

### Why keep the REST diagnostic endpoints

The current REST endpoints at `/mcp/v1/tools/*` (legacy from Phase 1 before the protocol layer was added) still use bearer auth and are useful for direct curl testing. Keep them as-is. They're not exposed to Claude.ai (which only speaks MCP protocol now), but they're handy for CC's own debugging and for the `scripts/probe_mcp_local.py` integration test.

Document them in `backend/hub_mcp/README.md` as "diagnostic-only, bearer auth, not part of the Claude.ai integration path."

### Token storage

OAuth access tokens are issued per session by our server. Storage requirement: where do issued tokens live so the server can validate them on subsequent requests?

Options:
- In-memory (simplest, works for single-instance Railway deployment, tokens lost on restart)
- Railway Postgres (persistent, survives restarts, slight overhead)
- Redis (already in the stack via `rediss://`, fast, can use TTL for token expiry)

**Recommendation: Redis.** TTL on tokens (e.g., 24 hours) handles expiry automatically. The Redis-based pattern is what FastMCP examples typically use. Existing Redis connection in the backend is reusable.

CC's call if a different choice makes the implementation cleaner.

### Scopes

GitHub OAuth scopes requested: `read:user` only. We don't need repo access, email scopes, or anything else — just enough to verify the authenticated user's username.

### What about CC's own access?

CC currently uses curl with the bearer token for verification scripts. After this change, CC can either:
- Keep using bearer auth against the diagnostic REST endpoints at `/mcp/v1/tools/*`
- Generate a long-lived access token via a CLI flow for the protocol endpoints (more complex)

Recommendation: keep using REST endpoints with bearer for CC's tests. The bearer token becomes a "CC-only diagnostic credential," not a primary auth method. Document this in the README.

---

## Phase 1: Nick Creates the GitHub OAuth App (COMPLETED BEFORE THIS BRIEF EXECUTES)

Nick has already performed Phase 1 per Claude's prep guidance. State before CC starts Phase 2:

- GitHub OAuth App created at https://github.com/settings/developers
- Authorization callback URL: `https://pandoras-box-production.up.railway.app/mcp/v1/auth/callback`
- Three Railway env vars set:
  - `GITHUB_OAUTH_CLIENT_ID`
  - `GITHUB_OAUTH_CLIENT_SECRET`
  - `MCP_ALLOWED_GITHUB_USERS=303webhouse`

CC verifies these env vars are visible in the Railway deployment before starting Phase 2 implementation. If any are missing, STOP and tell Nick.

---

## Phase 2: CC Implements the OAuth Server

### Step 2.1: Update `backend/hub_mcp/router.py`

Replace the current bearer-token auth provider with FastMCP's `OAuthProxy` configured for GitHub. Approximate shape:

```python
# Approximate — CC adapts to actual FastMCP 3.3.1 API
from fastmcp import FastMCP
from fastmcp.server.auth.providers.github import GitHubProvider  # or OAuthProxy
import os

allowed_users = os.environ.get("MCP_ALLOWED_GITHUB_USERS", "").split(",")

auth_provider = GitHubProvider(  # or OAuthProxy with GitHub config
    client_id=os.environ["GITHUB_OAUTH_CLIENT_ID"],
    client_secret=os.environ["GITHUB_OAUTH_CLIENT_SECRET"],
    base_url="https://pandoras-box-production.up.railway.app",
    scopes=["read:user"],
    allowed_usernames=allowed_users,  # if natively supported; else custom hook
)

mcp_server = FastMCP(
    name="pandoras-box-hub",
    version="1.0.0",
    auth=auth_provider,
)
```

CC reads the FastMCP 3.3.1 auth docs and uses the recommended pattern. If FastMCP doesn't natively support GitHub username restriction, implement it as a callback hook that validates the username after GitHub returns user info but before our server issues the access token.

### Step 2.2: Token storage

Configure token storage backend (Redis recommended). Use existing `rediss://` connection from the backend's existing config. Set token TTL to 24 hours.

### Step 2.3: Update the lifespan chain in `backend/main.py`

If OAuth changes the FastAPI app's lifespan requirements (additional state to initialize/teardown), update accordingly. The existing chain currently handles FastMCP's `StreamableHTTPSessionManager` — verify nothing breaks.

### Step 2.4: Remove or repurpose the bearer auth middleware

The bearer auth middleware at `backend/hub_mcp/auth.py` (or wherever it now lives after the rename) is no longer in the MCP protocol path. Two options:
- **Remove entirely** — cleanest
- **Repurpose** to gate the REST diagnostic endpoints only — useful for CC's testing

Recommendation: repurpose. Apply it only to the `/mcp/v1/tools/*` REST routes, not the FastMCP-managed routes. Document this in the README.

### Step 2.5: Rate limiting and audit logging

Both stay as-is. They wrap the FastMCP app at the ASGI middleware level and work regardless of which auth provider FastMCP uses internally. Verify with a quick test that audit logs still capture `tool_name`, `latency_ms`, etc. for OAuth-authenticated requests.

The `token_hash` field in audit logs now hashes the OAuth access token instead of the bearer token. Same hashing function (SHA-256 truncated to 8 hex chars).

### Step 2.6: Update CORS

The OAuth callback path at `/mcp/v1/auth/callback` needs to be reachable by GitHub (not Anthropic). Update CORS to allow GitHub's origin for the callback endpoint specifically, while keeping the protocol endpoints restricted to Anthropic's MCP infrastructure.

### Step 2.7: Update tests

The existing 39 unit tests against the tool functions should still pass. The `scripts/probe_mcp_local.py` integration test currently uses bearer auth — it needs to be updated to either:
- Use the diagnostic REST endpoints with bearer (simplest)
- Generate an OAuth access token via a test-only flow

Recommendation: route the probe through the REST diagnostic endpoints so the bearer-based test pattern keeps working for local validation. Add a new probe `scripts/probe_oauth_flow.py` that exercises the OAuth path manually (requires browser interaction, used for verification not CI).

### Step 2.8: Deploy

```
git add backend/hub_mcp/ backend/main.py scripts/ docs/ requirements.txt
git commit -F C:\temp\mcp_oauth_commit_msg.txt
git push origin main
```

Wait for Railway auto-deploy.

### Step 2.9: Verify the OAuth metadata endpoint is reachable

```
curl https://pandoras-box-production.up.railway.app/.well-known/oauth-authorization-server
```

Expected: JSON response with OAuth 2.1 metadata (issuer, authorization_endpoint, token_endpoint, etc.). If this returns 404, the FastMCP OAuth provider isn't exposing the metadata endpoint and CC needs to investigate.

### Step 2.10: Verify the OAuth flow manually

Use the `mcp` CLI or MCP Inspector to attempt connecting to the server. The expected flow:
1. Client requests connection
2. Server returns OAuth metadata
3. Client redirects browser to GitHub
4. Nick authorizes the OAuth App
5. GitHub redirects back to our server's callback at `/mcp/v1/auth/callback`
6. Server validates Nick's username against `MCP_ALLOWED_GITHUB_USERS`
7. Server issues access token to client
8. Client uses token for subsequent MCP requests

If this succeeds, the integration is ready for Claude.ai.

---

## Phase 3: Nick Connects in Claude.ai

CC tells Nick to attempt the connection. Nick performs:

1. Claude.ai → Settings → Connectors → existing Pandora MCP entry → **Remove** (clean slate)
2. Click **Add custom connector**
3. Name: `Pandora's Box Hub`
4. URL: `https://pandoras-box-production.up.railway.app/mcp/v1/`
5. Leave OAuth Client ID and OAuth Client Secret BLANK (DCR is supported by OAuthProxy; Claude.ai auto-registers)
6. Click **Add**
7. Claude.ai should redirect the browser to GitHub OAuth
8. Nick authorizes the OAuth App
9. Browser redirects back, connection succeeds
10. The 9 tools become available in chat

If any step fails, Nick screenshots/copies the error and pastes to CC for diagnosis.

---

## Phase 4: Documentation Updates

### `docs/operations/mcp-connection-guide.md`

Rewrite to cover the OAuth flow. New content:
- "Add custom connector" with URL only (no token field needed)
- First connection triggers GitHub OAuth — user authorizes via browser
- Token managed by Claude.ai automatically (refresh, expiry)
- Mobile note: works on mobile if Nick is signed into GitHub on the mobile browser

### `docs/operations/mcp-token-rotation.md`

Rewrite to cover OAuth credential rotation:
- Rotating the **GitHub OAuth App Client Secret** (when to do it: suspected leak, periodic rotation)
- Procedure: regenerate secret in GitHub → update Railway env var → redeploy → existing Claude.ai sessions remain valid until token expiry → re-authorize on next session
- Revoking access: GitHub Settings → Applications → revoke Pandora's Box Hub MCP authorization → all issued tokens invalidated immediately

### `backend/hub_mcp/README.md` — v1 Risk Profile section

Rewrite the previous "single bearer token grants full read access" risk note. New content:

> **v1 Risk Profile (updated 2026-05-15 — OAuth migration).** The hub MCP server uses GitHub OAuth via FastMCP's OAuthProxy. Access is restricted to authenticated GitHub users on the `MCP_ALLOWED_GITHUB_USERS` allowlist (currently `303webhouse`). Tokens are short-lived (24 hours) and revocable at any time via GitHub. This is materially more secure than the previous bearer-token design:
> - No long-lived secret floating in chat transcripts or env-var dumps
> - Token leak does not grant indefinite access — revoke at GitHub, all sessions die
> - Per-session token isolation
> - GitHub-side audit log of authentication events
> 
> The remaining risk surface: if Nick's GitHub account is compromised AND the attacker has direct access to the MCP URL, they can authenticate and reach the trading book. Mitigations: GitHub two-factor required on the `303webhouse` account; consider hardware key (YubiKey or Passkey).
> 
> v2 plans: IP allowlist restricting to known Claude.ai egress IPs (additional defense-in-depth).

---

## Out of Scope (do NOT do)

- Do NOT redesign the tool surface — 9 tools stay exactly as they are
- Do NOT modify tool descriptions in `docs/specs/hub-mcp-tool-descriptions-2026-05-14.md`
- Do NOT modify the TORO/URSA skill files — they reference tool names, auth is transparent to them
- Do NOT remove the REST diagnostic endpoints at `/mcp/v1/tools/*` unless they actually conflict with the new auth path (recommend keeping as diagnostic surface)
- Do NOT add new tools or change tool behavior
- Do NOT switch from FastMCP 3.3.1 to a different MCP library

---

## Acceptance Criteria

All four must hold:

1. **OAuth metadata endpoint responds correctly** at `/.well-known/oauth-authorization-server` with valid OAuth 2.1 metadata
2. **Manual OAuth flow succeeds** via mcp CLI or MCP Inspector — Nick authorizes via GitHub, server issues token, subsequent MCP calls authenticated
3. **Username restriction works** — attempt to authorize with a different GitHub account fails before token issuance (CC verifies by temporarily setting `MCP_ALLOWED_GITHUB_USERS` to a non-existent username and confirming the auth fails)
4. **Nick can connect in Claude.ai** — adds connector with URL only, GitHub OAuth flow completes, 9 tools available in chat, "Run TORO on TSLA" produces a GROUND TRUTH block from real hub data

CC's responsibility ends at criteria 1-3. Criterion 4 is Nick's verification.

---

## Questions to Resolve Before Starting

If any of these are unclear, ASK NICK before coding:

1. Confirm the GitHub username to allowlist (`303webhouse`?)
2. Confirm Nick's preference on REST diagnostic endpoint retention (keep with bearer auth for CC use, or remove entirely?)
3. Token storage choice (Redis recommended) — confirm or override

Otherwise, proceed with the FastMCP 3.3.1 GitHubProvider / OAuthProxy pattern. Read the FastMCP auth docs at https://gofastmcp.com/servers/auth/authentication for the canonical API as of the current FastMCP version.
