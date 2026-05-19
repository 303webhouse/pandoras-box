# Pandora's Box MCP — Credential Rotation Procedure

The MCP server (v3+) uses GitHub OAuth via FastMCP's OAuthProxy. Two distinct credentials need rotation procedures:

1. **GitHub OAuth App Client Secret** — the secret Railway uses to exchange OAuth codes for GitHub access tokens. If leaked, an attacker with this secret + the Client ID could impersonate our server during an OAuth handshake.
2. **GitHub OAuth Authorizations** — the per-user access tokens GitHub issues after authorization. Revoke at GitHub to kill all active sessions.

The pre-v3 `MCP_BEARER_TOKEN` is no longer in the live auth path; it can be removed from Railway as cleanup.

---

## Rotating the GitHub OAuth App Client Secret

### When to rotate

- **Immediately:** suspected leak (accidental commit, paste into a public-visible log, screen-share exposure).
- **Quarterly:** treat like any long-lived credential — rotate every 90 days as hygiene.
- **After a Railway env-var dump operation** that produced a transcript with the secret value.

### Procedure (5-10 minutes end-to-end)

1. Open the GitHub OAuth App settings:
   `https://github.com/settings/developers` → OAuth Apps → **Pandora's Box MCP** (or whatever you named it).

2. Click **Generate a new client secret**.

3. Copy the new secret. GitHub shows it once — paste into your password manager immediately.

4. Open Railway → `pandoras-box-production` service → Variables. Find `GITHUB_OAUTH_CLIENT_SECRET`. Replace the value with the new secret. Save.

5. Railway redeploys automatically (~1-2 minutes). Wait for the deploy to go green.

6. In GitHub OAuth App settings, **delete the old client secret** (it's still listed until you explicitly remove it).

7. Existing Claude.ai sessions: any user with an OAuth access token already issued will continue to work until their token expires or they revoke at GitHub. The new client secret only matters for NEW OAuth handshakes. To force re-auth on a specific session, revoke at GitHub (procedure below).

8. Verify the new secret works: open a fresh Claude.ai chat. If your existing connector still works, the session was using a token issued BEFORE the rotation — that's expected. To test that NEW handshakes work, Settings → Connectors → Remove the connector → Re-add. The fresh OAuth flow exercises the new secret.

---

## Revoking active sessions (kill all OAuth tokens immediately)

1. `https://github.com/settings/applications`
2. Find **Pandora's Box MCP** under "Authorized OAuth Apps".
3. Click **Revoke**.

All access tokens GitHub has issued for the app are invalidated immediately. The next MCP call from any active Claude.ai session will fail with 401 and the connector will prompt for re-auth.

This is the heavy-handed option — use it if you suspect a specific GitHub session token leaked but don't want to rotate the App secret yet.

---

## Adjusting the allowlist (`MCP_ALLOWED_GITHUB_USERS`)

To add or remove allowed GitHub users:

1. Railway → Variables → `MCP_ALLOWED_GITHUB_USERS`.
2. Update to comma-separated list (e.g., `303webhouse,trusted-other-user`).
3. Save. Railway redeploys (~1-2 minutes).
4. New allowlist takes effect on the next token-verification cycle. Cached verifications stay valid for `cache_ttl_seconds` (5 minutes) — so a user just removed from the list keeps working for up to 5 minutes. To kill immediately, also revoke at GitHub.

---

## What rotation does NOT cover

- **Audit log gap:** rotation does NOT invalidate audit log entries. The audit log keeps a SHA-256 truncated hash of whatever token was in the Authorization header on each request. After rotation, new requests have different token hashes — historical hashes from before rotation can't be cross-referenced to current sessions.
- **GitHub-side leak of the access token itself:** the OAuth Client Secret is OUR end of the trust chain. If a user's per-session GitHub access token leaks (e.g., from a compromised browser session), revoke at GitHub.

---

## Cleanup: removing the legacy `MCP_BEARER_TOKEN` env var

After v3 is in production and confirmed working, remove the unused env var to reduce attack surface:

1. Railway → Variables → find `MCP_BEARER_TOKEN`.
2. Confirm no code path still reads it: `grep -r MCP_BEARER_TOKEN backend/` should return zero matches in active code. (`docs/` may still mention it historically — that's fine.)
3. Delete the variable.

No redeploy or downtime needed; nothing references it.

---

## v2 plans that affect this procedure

- **Per-account scoped tokens:** v2 may issue tokens with finer scope (e.g., read-only-positions vs. read-only-balances) so a leak doesn't expose the whole book.
- **Token TTL tuning:** currently relying on GitHub's default token lifetime (effectively indefinite, manually revocable). v2 may issue our own short-lived JWTs derived from the GitHub auth.

Until those land, this OAuth rotation is the auth control. Treat the GitHub OAuth App credentials accordingly.
