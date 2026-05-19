# Pandora's Box Hub MCP Server (v1)

Read-only MCP exposing hub data (bias composite, options flow, sector strength,
catalysts, squeeze scores, positions, balances) to Claude.ai (Olympus
committee). Mounted at `/mcp/v1/` on the existing FastAPI app.

## Three-Layer Read-Only Enforcement (AEGIS-mandated)

1. **`@mcp_tool` decorator** (`decorators.py`) — function name must be in a
   hard-coded whitelist of 9 tools, or import fails at registration time.
2. **Import-based isolation** — every tool imports its data from
   `backend/services/read_only/` only. The lint check at
   `scripts/lint_mcp_imports.py` fails the build if anything under
   `backend/mcp/` imports a write-capable module.
3. **AEGIS code review on every PR.**

This replaces the Pass 1 "method-restricted HTTP client" recommendation.
ATHENA confirmed in Pass 2 that import-based isolation provides equivalent
defense-in-depth without HTTP overhead — both achieve "tools physically
cannot trigger a write."

## Read-Only Namespace Layout Choice

`backend/services/read_only/` re-exports read functions from existing
domain modules (`bias_engine/`, `bias_filters/`, `api/`, `database/`) rather
than moving them. Rationale: existing routes and other callers continue to
import from their original locations, no churn outside `mcp/`. Cost: the lint
check has to verify that re-exports don't surface write-capable names —
implemented by inspecting the symbol's original module.

## Universal Response Envelope

Every tool returns:

```json
{
  "status": "ok" | "stale" | "degraded" | "unavailable",
  "data": <tool-specific payload or null>,
  "summary": "≤300 char human-readable line",
  "staleness_seconds": int | null,
  "schema_version": "v1.0",
  "error": null | "Brief error description"
}
```

Direct dict construction is disallowed — use `envelope.make_response()`.

## Authentication (v3+: GitHub OAuth)

FastMCP's `OAuthProxy` with GitHub as the upstream IdP. The protocol-layer
auth is fully delegated to FastMCP; our `AllowlistedGitHubTokenVerifier`
(`hub_mcp/auth.py`) subclasses the default `GitHubTokenVerifier` to also
enforce a username allowlist after GitHub returns user info.

- Required env vars: `GITHUB_OAUTH_CLIENT_ID`, `GITHUB_OAUTH_CLIENT_SECRET`,
  `MCP_ALLOWED_GITHUB_USERS` (comma-separated GitHub usernames).
- Optional: `MCP_PUBLIC_BASE_URL` (defaults to the production Railway URL).
- Scopes requested from GitHub: `read:user` only.
- GitHub OAuth App callback URL: `<base>/auth/callback`
  (= `https://pandoras-box-production.up.railway.app/mcp/v1/auth/callback`).
- Token cache TTL: 5 minutes (so a user removed from the allowlist keeps
  working for up to 5 minutes; revoke at GitHub to kill immediately).

If any required env var is unset, `build_oauth_provider()` returns None and
the FastMCP instance starts in unauthenticated mode — only acceptable for
local pytest runs. In production, missing env vars are logged as a critical
error and the server effectively becomes open; deploy with the env vars set.

The pre-v3 `MCP_BEARER_TOKEN` env var is no longer read by any live code
path. Remove it from Railway as cleanup after v3 has been stable for ~24h.

## Rate Limits

- **60 requests/minute** per token (rolling 60s).
- **5,000 requests/day** per token (rolling 24h).
- Keying: the Authorization header value (FastMCP-issued OAuth access token).
  Anonymous requests (OAuth metadata, callback) key off caller IP instead.
- `mcp_ping` is exempt — Olympus calls it once per pass, exhausting the rate
  limit on health checks is wrong.
- Rate-limit-exceeded returns HTTP 429 with a JSON body describing the limit.

## Audit Logging

Every request is logged through `pandoras_box.mcp.audit` with:
`timestamp, tool_name, parameters_hash (sha256 trunc 8), response_status,
latency_ms, caller_ip, token_hash (sha256 trunc 8)`.

Full tokens are NEVER logged.

## v1 Risk Profile (updated 2026-05-18 — OAuth migration)

The hub MCP server uses GitHub OAuth via FastMCP's `OAuthProxy`. Access is
restricted to authenticated GitHub users on the `MCP_ALLOWED_GITHUB_USERS`
allowlist (currently `303webhouse`). Tokens are issued by FastMCP per
session and verified per request (with a 5-minute cache to avoid hammering
GitHub's API). Revocation is one click at GitHub.

This is materially more secure than the previous bearer-token design:

- No long-lived secret floating in chat transcripts or env-var dumps
- Token leak does not grant indefinite access — revoke at GitHub, all
  sessions die at next verification cycle (≤5 min cache TTL)
- Per-session token isolation
- GitHub-side audit log of authentication events
- Allowlist enforcement means even a valid GitHub user from outside the
  allowlist cannot access the tools

The remaining risk surface: if Nick's GitHub account (`303webhouse`) is
compromised AND the attacker has the MCP URL, they can authenticate and
reach the trading book. **The leak does NOT grant write access — Olympus
reads, Olympus does NOT trade.** Mitigations:
- GitHub two-factor required on the `303webhouse` account
- Consider hardware key (YubiKey or Passkey) for the GitHub account
- Rotate the OAuth Client Secret if any env-var-dump command produced a
  transcript containing it (procedure: `docs/operations/mcp-token-rotation.md`)

v2 plans (separate brief): IP allowlist restricting to known Claude.ai
egress IPs (additional defense-in-depth); per-account scoped tokens.

## Tool List (v1)

Canonical descriptions live at
`docs/specs/hub-mcp-tool-descriptions-2026-05-14.md`. The `description`
arguments to every `@mcp_tool` decorator are copied verbatim from that doc.

| Tool | Source data |
|------|-------------|
| `hub_get_bias_composite` | `bias_engine/composite.py:get_cached_composite` |
| `hub_get_flow_radar` | `api/flow_radar.py:get_flow_radar` |
| `hub_get_sector_strength` | `api/sector_rotation.py:get_status` |
| `hub_get_hermes_alerts` | `api/catalyst_calendar.py:get_upcoming_catalysts` |
| `hub_get_hydra_scores` | `api/hydra.py:get_squeeze_scores` |
| `hub_get_positions` | `api/unified_positions.py:list_positions` |
| `hub_get_portfolio_balances` | `api/portfolio.py:get_balances` |
| `mcp_ping` | (internal — no data source) |
| `mcp_describe_tools` | (internal — reads decorator registry) |

## v2 Candidates (out of scope here)

- IP allowlist on top of bearer auth
- Account-ID anonymization (lookup tool gates the mapping)
- Per-account-scoped tokens
- `hub_get_signal_outcomes`, `hub_get_battlefield_brief`, `hub_get_pnl`
- Observability dashboards
