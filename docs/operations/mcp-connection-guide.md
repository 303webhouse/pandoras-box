# Pandora's Box MCP — Connection Guide

How to connect Claude.ai (Olympus committee skills + direct chats) to the hub MCP server so TORO, URSA, and the rest of Olympus can pull real hub data instead of fabricating context.

**Auth model (v3+):** GitHub OAuth. The browser redirects to GitHub on first connect, you authorize the OAuth App, and Claude.ai stores the issued token. There's no bearer token to paste anywhere.

---

## § 1 — Quick: Session went stale mid-trade

If a committee pass fails with "MCP unreachable" or "tool unavailable":

1. Open `https://pandoras-box-production.up.railway.app/mcp/v1/health` in a browser. If it returns `{"status":"ok",...}`, the server is up — your Claude.ai session is stale, go to step 2. If it doesn't respond or returns 5xx, the server itself is down; check Railway.
2. Claude.ai → Settings → Connectors → "Pandora's Box Hub" → Disconnect → Connect. Approve the GitHub OAuth flow.
3. Verify reconnection by asking Claude to run a small hub tool (e.g., "show me current bias composite").
4. Resume the committee pass.

Expected total time: 30 seconds.

The `/mcp/v1/health` response also includes `uptime_seconds` and `deployed_at` — if uptime is < 60s, the server was just redeployed (which is what kills the OAuth session today). The `worker_id` field is a process-ID stamp; if it changes between two refreshes the process restarted under you.

---

## What you need before connecting

1. **The MCP URL:** `https://pandoras-box-production.up.railway.app/mcp/v1/`
2. **A GitHub account** on the `MCP_ALLOWED_GITHUB_USERS` allowlist (currently `303webhouse` only). Any other GitHub user can complete the OAuth handshake but will be rejected at token-verification time and won't see any tools.

That's it. No tokens, no secrets — the GitHub OAuth App credentials live in Railway and are invisible to Claude.ai.

---

## Connecting in Claude.ai (desktop)

1. Open Claude.ai → click your profile (lower left) → **Settings**.
2. Open the **Connectors** section.
3. Click **Add custom connector**.
4. Fill in:
   - **Name:** `Pandora's Box Hub` (or whatever; it shows in chat tool calls)
   - **URL:** `https://pandoras-box-production.up.railway.app/mcp/v1/`
   - **OAuth Client ID:** leave **BLANK**
   - **OAuth Client Secret:** leave **BLANK**

   The OAuth fields stay blank because our server supports DCR (Dynamic Client Registration) via FastMCP's OAuthProxy — Claude.ai auto-registers itself with our server on first connect, then redirects to GitHub for user auth.

5. Click **Add**.
6. Browser redirects to GitHub. You'll see the "Pandora's Box MCP" OAuth App requesting `read:user` scope. Click **Authorize**.
7. Browser redirects back to our server's `/mcp/v1/auth/callback`, which verifies your GitHub username against the allowlist, then back to Claude.ai.
8. Connector shows up as "Connected" and the 10 tools become available.

## Verifying it works

1. Open a new chat in the Pandora's Box project.
2. Prompt: *"Use the Pandora's Box MCP to list available tools."*
3. Claude should call `mcp_describe_tools` and return the 10-tool manifest:
   - `mcp_ping`
   - `mcp_describe_tools`
   - `hub_get_quote`
   - `hub_get_bias_composite`
   - `hub_get_flow_radar`
   - `hub_get_sector_strength`
   - `hub_get_hermes_alerts`
   - `hub_get_hydra_scores`
   - `hub_get_positions`
   - `hub_get_portfolio_balances`

4. Test a real call: *"Run TORO on SPY."* TORO's skill is patched to call `mcp_ping` first and then `hub_get_bias_composite`, `hub_get_flow_radar`, etc. — you should see those tool calls happen in the chat.

## Mobile

Connect once on desktop. Claude.ai's mobile app inherits the OAuth token via account sync — no separate pairing required. If the token ever expires on mobile, you'll be redirected to a mobile browser to re-auth through GitHub.

---

## Troubleshooting

### "Couldn't reach the MCP server" when adding the connector

In order of likelihood:

1. **Railway down or mid-deploy.** Verify: `curl https://pandoras-box-production.up.railway.app/health` should return `{"status":"healthy", ...}`. If it doesn't, the parent app is down.
2. **MCP-specific down.** `curl https://pandoras-box-production.up.railway.app/mcp/v1/health` should return `{"status":"ok","service":"mcp/v1","uptime_seconds":...}`. If parent health is fine but this 404s, the FastMCP mount or the health route registration failed at startup — check Railway logs for `MCP v1 server failed to mount` or a missing `/mcp/v1/health endpoint registered` line.
3. **OAuth metadata endpoint broken.** `curl https://pandoras-box-production.up.railway.app/mcp/v1/.well-known/oauth-authorization-server` should return JSON with `issuer`, `authorization_endpoint`, `token_endpoint`. If it 404s, FastMCP's OAuthProxy didn't initialize — likely the GitHub OAuth env vars aren't set on Railway.

### "MCP: unreachable" inside a TORO/URSA committee output

Means `mcp_ping` (the first call) failed mid-session. Either:
- The connector was disconnected (Claude.ai → Settings → Connectors → reconnect)
- The OAuth token expired and Claude.ai didn't auto-refresh — remove and re-add the connector

### GitHub OAuth redirect lands on "Authorization callback URL mismatch"

The GitHub OAuth App's callback URL must be exactly `https://pandoras-box-production.up.railway.app/mcp/v1/auth/callback`. Go to github.com → Settings → Developer settings → OAuth Apps → Pandora's Box → verify and fix.

### GitHub OAuth completes but Claude.ai reports "Connection failed"

The GitHub username we authenticated as isn't in `MCP_ALLOWED_GITHUB_USERS`. Two reasons this could happen:
- You authorized with the wrong GitHub account (signed into the browser as someone other than `303webhouse`).
- The Railway env var got cleared or has a typo.

Fix: sign into github.com as `303webhouse` in the same browser, then re-trigger the connector setup in Claude.ai.

### Tool returns `"status": "unavailable"` with error about cache

The hub itself doesn't have cached data for that tool right now. Not an MCP/OAuth issue — check the relevant scheduler's last run in Railway logs.

---

## Revoking access

To kill an active session without redeploying:

1. Go to **github.com → Settings → Applications → Authorized OAuth Apps**.
2. Find **Pandora's Box MCP** (or whatever you named the OAuth App).
3. Click **Revoke**.

All issued access tokens are invalidated immediately. The next MCP call from Claude.ai will fail with 401, and the connector will prompt for re-auth.

To rotate just the OAuth App credentials (without revoking sessions), see `docs/operations/mcp-token-rotation.md`.
