# Pandora's Box MCP — Connection Guide

How to connect Claude.ai (Olympus committee skills + direct chats) to the hub MCP server so TORO, URSA, and the rest of Olympus can pull real hub data instead of fabricating context.

---

## What you need before connecting

1. **The MCP URL:** `https://pandoras-box-production.up.railway.app/mcp/v1/`
2. **The bearer token:** the value of the `MCP_BEARER_TOKEN` Railway env var. Keep it in your password manager — Claude.ai will store it but Anthropic does not surface it after the connector is configured.

If Nick rotated the token recently per `docs/operations/mcp-token-rotation.md`, use the new value, not whatever you remember.

---

## Connecting in Claude.ai (desktop)

1. Open Claude.ai → click your profile (lower left) → **Settings**.
2. Open the **Connectors** section.
3. Click **Add custom connector**.
4. Fill in:
   - **Name:** `Pandora's Box Hub` (or whatever; it shows in chat tool calls)
   - **URL:** `https://pandoras-box-production.up.railway.app/mcp/v1/`
   - **Authentication:** Bearer
   - **Bearer token:** paste the token
5. Save.
6. Claude.ai will probe `/mcp/v1/health` and display the connector as available.

## Verifying it works

1. Open a new chat in the Pandora's Box project.
2. Prompt: *"Use the Pandora's Box MCP to list available tools."*
3. Claude should call `mcp_describe_tools` and return the 9-tool manifest. Look for:
   - `mcp_ping`
   - `hub_get_bias_composite`
   - `hub_get_flow_radar`
   - `hub_get_sector_strength`
   - `hub_get_hermes_alerts`
   - `hub_get_hydra_scores`
   - `hub_get_positions`
   - `hub_get_portfolio_balances`
   - `mcp_describe_tools`

If you only see 8 tools, that's a deploy issue — `mcp_describe_tools` should always be present because it reads the registry it's a member of. Check Railway logs.

4. Test a real call: *"Run TORO on SPY."* TORO's skill is patched to call `mcp_ping` first and then `hub_get_bias_composite`, `hub_get_flow_radar`, etc. — you should see those tool calls happen in the chat.

## Mobile

You connect once on desktop. Claude.ai's mobile app inherits connectors via account sync. There's no per-device pairing required.

---

## Troubleshooting

### "MCP: unreachable" in TORO/URSA output

Means `mcp_ping` failed. In order:

1. **Token rotated?** If yes, update the connector with the new token per the rotation doc.
2. **Railway healthy?** `curl https://pandoras-box-production.up.railway.app/health` — should return `status: healthy`. If not, MCP is down because the whole app is down.
3. **MCP-specific health:** `curl https://pandoras-box-production.up.railway.app/mcp/v1/health` — should return `{"status":"ok","service":"mcp/v1"}` with no auth required.
4. **CORS regression?** Check `backend/mcp/router.py` `ALLOWED_ORIGINS` — if Anthropic changed origins and we didn't update, the browser-side connector blocks the call. Curl from a terminal won't catch this because CORS is a browser policy.

### 401 Unauthorized on every call

The bearer token saved in Claude.ai does not match `MCP_BEARER_TOKEN` on Railway. Either:
- The Railway env var was rotated and the connector wasn't updated.
- The connector was configured with whitespace or quotes accidentally pasted around the token.

Fix: re-paste the token in the connector settings.

### Rate limit hit during a normal committee pass

`mcp_ping` is exempt from rate limiting (60/min, 5000/day). If TORO is hitting the per-minute limit, the skill is calling tools too aggressively. Check that TORO is caching the bias composite reading once per pass instead of re-calling each step.

### Tool returns `"status": "unavailable"` with error "Composite bias not cached"

The hub itself doesn't have a cached composite bias reading right now. This isn't an MCP problem — the bias_engine's scheduler hasn't run recently or Redis was flushed. Verify on the dashboard at the Railway URL first; if dashboard also shows blank bias, the upstream issue is on the hub.

### "Unknown tool" with a tool name that should exist

Almost always means a Railway deploy didn't pick up new code. Check `git log -1` against the deployed SHA (visible in Railway logs). Trigger an empty commit + push to force redeploy if needed.

---

## When to disconnect

Disconnect the connector if:
- You're sharing your screen and don't want Claude.ai pulling live positions/balances.
- You're investigating a suspected token leak — disconnect first, then rotate per the rotation doc.
- You're running a Claude.ai chat against a different MCP and don't want this one in the mix.

Reconnect by repeating the "Connecting in Claude.ai" steps above; the token can be reused as long as it hasn't been rotated on Railway.
