# Pandora's Box MCP — Token Rotation Procedure

The MCP server uses a single bearer token (`MCP_BEARER_TOKEN` Railway env var) for authentication. A leaked token grants full read access to bias composite, options flow, positions, and balances across all four accounts. Rotate immediately if you suspect leakage, and on a routine cadence otherwise.

---

## When to rotate

- **Immediately:** suspected leak, accidental commit of the token, accidental paste into a public-visible doc/screen-share, sharing the value with anyone other than yourself.
- **Quarterly:** treat it like any other long-lived credential — rotate every 90 days as routine hygiene.
- **After any vendor/staff change** that touched the Railway dashboard. (N/A for Nick today — documented for completeness.)

---

## Rotation procedure (5 minutes, end-to-end)

### 1. Generate a new token

On any machine with Python:

```
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copy the output. This is 256 bits of entropy URL-safe-base64-encoded.

**Do not paste it into chat with Claude. Do not commit it. Do not log it.** The token belongs in two places: Railway env vars, and your password manager.

### 2. Update the Railway env var

1. Open the Railway project: `https://railway.app/project/<project-id>`
2. Open the **pandoras-box-production** service.
3. **Variables** tab → find `MCP_BEARER_TOKEN`.
4. Click the value, paste the new token, save.
5. Railway redeploys automatically. Wait for the deploy to go green (~1-2 minutes).

### 3. Verify the old token is rejected

From any terminal:

```
curl -X POST https://pandoras-box-production.up.railway.app/mcp/v1/tools/mcp_ping \
  -H "Authorization: Bearer OLD_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{}' -v
```

Expected: HTTP 401. If you get HTTP 200, Railway hasn't picked up the new env var yet — wait another minute and retry.

### 4. Verify the new token works

Same curl with the new token:

```
curl -X POST https://pandoras-box-production.up.railway.app/mcp/v1/tools/mcp_ping \
  -H "Authorization: Bearer NEW_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Expected: HTTP 200 with envelope `{"status": "ok", "data": {...}, "schema_version": "v1.0", ...}`.

### 5. Update Claude.ai

1. Claude.ai → Settings → Connectors → **Pandora's Box Hub** (or whatever you named it) → Edit.
2. Paste the new token in the Bearer field.
3. Save.

### 6. Smoke-test the committee

In a fresh Claude.ai chat (Pandora's Box project):

> Run TORO on SPY.

TORO's first action is `mcp_ping`. If it returns "MCP: connected", the rotation is complete and the committee is reading the new token correctly.

### 7. Store the new token

Drop the new token into your password manager under the entry for the Pandora's Box Railway env var. Optionally annotate with the rotation date.

---

## What rotation does NOT cover

- **Audit log gap:** Rotating the token does NOT invalidate audit log entries written under the old token. The audit log keeps a SHA-256 truncated hash of the token, not the token itself, so historical logs remain analyzable but you'll see a hash change on the cutover boundary. That's expected.
- **Active connections:** Claude.ai's connector caches the token in-app. There's no signaling mechanism — until you update the connector (step 5), Claude will keep sending the old (now invalid) token and getting 401s. You'll see "MCP: unreachable" in TORO/URSA output as the signal.
- **Multiple connectors:** if you've set up the MCP in multiple Claude.ai workspaces or installs, update each independently. There's no fan-out.

---

## v2 plans that affect this procedure

- **Account-ID anonymization:** v2 will introduce per-account scoped tokens. Rotating the master token will not be sufficient — each per-account token will need its own rotation. This procedure will be expanded then.
- **Token expiration with grace window:** v2 may issue tokens with explicit expiration timestamps, allowing scheduled rotation without the rejection cliff.

Until those land, this single-token rotation is the only auth control. Treat it accordingly.
