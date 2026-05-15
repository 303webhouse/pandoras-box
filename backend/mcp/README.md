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

## Authentication

- Single bearer token in `Authorization: Bearer <token>` header.
- Verified against `MCP_BEARER_TOKEN` env var with `secrets.compare_digest`
  (constant-time).
- 401 on missing or mismatched token; 500 if env var is unset.

## Rate Limits

- **60 requests/minute** per token (rolling 60s).
- **5,000 requests/day** per token (rolling 24h).
- `mcp_ping` is exempt — Olympus calls it once per pass, exhausting the rate
  limit on health checks is wrong.
- Rate-limit-exceeded returns the universal envelope with
  `status="unavailable"`, not a bare HTTP 429.

## Audit Logging

Every request is logged through `pandoras_box.mcp.audit` with:
`timestamp, tool_name, parameters_hash (sha256 trunc 8), response_status,
latency_ms, caller_ip, token_hash (sha256 trunc 8)`.

Full tokens are NEVER logged.

## v1 Risk Profile (AEGIS-mandated disclosure)

The v1 hub MCP server uses a single bearer token for authentication. The
token grants full read access to: bias composite, options flow, sector
strength, catalyst alerts, squeeze scores, all positions across all four
accounts (Robinhood, Fidelity Roth, 401k BrokerageLink, Breakout Prop),
and account balances. A token leak would expose Nick's full trading book
to the attacker. **The leak does NOT grant write access — Olympus reads,
Olympus does NOT trade.** Mitigation: rotate the token immediately if a
leak is suspected per `docs/operations/mcp-token-rotation.md`. v2 plans
introduce account-ID anonymization via a separate lookup tool to reduce
the blast radius of a single-token leak.

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
