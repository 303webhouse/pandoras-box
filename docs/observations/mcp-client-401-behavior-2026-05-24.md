# Observation — Anthropic MCP client does not auto-recover from `401 invalid_token` (2026-05-24)

**Type:** Behavioral observation about Anthropic's MCP client (Claude Desktop / claude.ai). Out of scope for Phase C.1-rev1's fix surface — we don't control the client side. Filed for future reference.

**Status:** Filed, not actioned. The server-side persistence fix (Phase C.1-rev1) eliminates the deploy-restart trigger for this scenario, making the client recovery behavior mostly irrelevant in the common case. But it would matter again if the server ever legitimately revokes tokens (security incident, manual operator action, token TTL expiry beyond refresh).

---

## What was observed

During the Phase C.1-rev1 client-side discovery walk-through (Phase 1.B reproducer, 2026-05-24 17:07-17:10 UTC), the Anthropic MCP client failed to auto-recover from `401 invalid_token` responses even though FastMCP's 401 response included a proper `WWW-Authenticate` header with `resource_metadata` pointer per RFC 9728.

Sequence captured in `railway logs`:

```
17:07:34  POST /mcp/v1 → 401 invalid_token   tool: notifications/initialized   token_hash: f0de3faa
17:07:41  POST /mcp/v1 → 401 invalid_token   tool: notifications/initialized   token_hash: 160d0631
17:07:44  POST /mcp/v1 → 401 invalid_token   tool: notifications/initialized   token_hash: 586b8a8e
17:08:12  POST /mcp/v1 → 401 invalid_token   tool: notifications/initialized   token_hash: 3c6d4153
17:10:29  POST /mcp/v1 → 401 invalid_token   tool: initialize                  token_hash: ba9d687a
```

Five distinct `token_hash` values across 3 minutes — the client was attempting to retry with different cached tokens. **What the client did NOT do** during this window:

- ❌ Hit `/.well-known/oauth-protected-resource/mcp/v1` (PRM rediscovery)
- ❌ Hit `/mcp/v1/register` (DCR re-registration)
- ❌ Hit `/mcp/v1/token` with `grant_type=refresh_token` (refresh-token grant)
- ❌ Hit `/mcp/v1/authorize` (fresh authorization flow)

The MCP authorization specification (`https://modelcontextprotocol.io/specification/draft/basic/authorization`) implies that on receiving 401 with proper `WWW-Authenticate`, the client should re-run discovery and obtain new tokens. That did not happen here. The client surfaced the failure to the user (TORO returned "MCP unreachable" with manual-reconnect instructions) instead.

## What was checked / ruled out

- The `WWW-Authenticate` header on our 401 response IS RFC-compliant (verified empirically against the live `pandoras-box-production` endpoint — see Task 0 findings, `phase-c.1-task0-findings-2026-05-23.md` §1). It contains `error="invalid_token", error_description=..., resource_metadata="<PRM URL>"`.
- The PRM document at that URL returns 200 OK with valid content.
- The AS metadata document advertises `code_challenge_methods_supported=[S256]` (PKCE) and `grant_types_supported=[authorization_code, refresh_token]`.
- FastMCP's middleware logs `Auth error returned: invalid_token` (proxy.py:92) on each 401 — server side is behaving correctly per spec.

So the failure is on Anthropic's client side: it sees the 401 + WWW-Authenticate but doesn't act on the implied recovery flow.

## Possible explanations (not investigated)

1. **Retry budget exhausted before refresh trigger** — the client may have a "retry N times before re-handshake" policy and our test fell within the retry window. The user-visible surface ("MCP unreachable") fires before the client gets to the re-handshake step.
2. **Token-refresh logic gated on a specific error code we're not emitting** — perhaps the client looks for `error="invalid_grant"` or `Token-Expired` semantics, not just `invalid_token`.
3. **MCP protocol layer state machine** — Claude Desktop's session may have transitioned to a "session-broken" state after the 401 sequence and exited the OAuth-aware code path entirely, surfacing the error directly to the LLM (TORO).
4. **Spec ambiguity** — the MCP authorization spec's recovery semantics may be optional or not yet enforced in Anthropic's implementation.

## Why this matters

**Today (post Phase C.1-rev1 fix):** mostly moot. Our persistence fix means JTI mappings, DCR clients, refresh tokens, etc. all survive Railway redeploys. The 401 scenario from this observation shouldn't reproduce in steady-state operation.

**Future scenarios where this re-emerges:**
- **GitHub OAuth App secret rotation:** quarterly per `mcp-token-rotation.md`. The Fernet encryption key derived from the secret changes, so decryption errors return cache-miss → effectively wiped state → 401 on existing tokens. Currently expected to require manual reconnect; would be smoother if the client auto-recovered.
- **Allowlist removal:** if a GitHub user is removed from `MCP_ALLOWED_GITHUB_USERS`, their existing token-verification cache entries expire (5-min TTL) and they get 401. Same client-recovery question.
- **Manual token revocation** (e.g., suspected credential leak): operator clears the Redis `fastmcp-oauth:*` namespace. All clients get 401 on next request. Same question.
- **Refresh-token expiry** (7-day TTL): on the 8th day with no use, the refresh token's not in our store, all access tokens have expired. Same question — does the client re-handshake or surface the error?

## What we are NOT doing

- Not filing this with Anthropic as a bug report. Symptom is real but other explanations (retry budget, state-machine boundary) may make it intended behavior.
- Not implementing client-side workarounds (we don't control the client).
- Not changing our 401 response format. FastMCP's response is spec-compliant; downstream clients should handle it.

## What we MIGHT do later

- Once the rev1 fix is live and stable, intentionally trigger a "legitimate revocation" by deleting OAuth state keys in Redis (manual key drop). Observe whether Claude Desktop auto-recovers when there's no concurrent process restart. If it does → just slow recovery in the original reproducer; not a real bug. If it doesn't → we have a reproducer that's independent of the file-store issue and worth filing with Anthropic.
- Worth a 30-minute experiment after a few days of stable operation. Low priority.

## References

- Phase 1.A baseline + 1.B reproducer evidence: `docs/codex-briefs/phase-c.1-rev1-rca-2026-05-24.md` §1
- FastMCP 401 middleware: `<site-packages>/fastmcp/server/auth/middleware.py:92`
- MCP authorization spec: https://modelcontextprotocol.io/specification/draft/basic/authorization
- RFC 9728 (Protected Resource Metadata): https://datatracker.ietf.org/doc/html/rfc9728
