# Phase C.1-rev1 — Root Cause Analysis (2026-05-24)

**Status:** Empirical RCA from Phase 1 client-side discovery walk-through, completed 2026-05-24 ~17:11 UTC (11:11 AM MDT).
**Branch:** `phase-c.1-oauth` (no code changes yet — RCA is pure investigation).
**Predecessor:** `docs/codex-briefs/phase-c.1-task0-findings-2026-05-23.md`
**Authoritative scope reference:** This RCA supersedes the Task 0 hypothesis on the specific failing storage layer. The rev1 brief's Task 2 needs to target the **JTI mapping store** (and adjacent OAuthProxy state stores), not the DCR client registrations specifically. See §5 for the corrected fix shape.

---

## TL;DR

**Confirmed root cause:** FastMCP 3.3.1's `OAuthProxy` defaults to a **file-system-backed** state store (`FileTreeStore` at `settings.home / "oauth-proxy" / <fingerprint>/`). Railway containers have **ephemeral filesystems** — that directory does not survive redeploys. Every Railway redeploy wipes the entire OAuth state set, including JTI mappings, DCR client registrations, refresh tokens, in-flight transactions, and authorization codes.

Anthropic's client holds access tokens issued by the pre-redeploy process. After redeploy, the post-redeploy process has no record of those tokens' JTIs and rejects them with `401 invalid_token` and the diagnostic message *"JTI mapping not found (token may have expired): jti=…"*.

**Friday's (2026-05-22 Phase A deploy) and Saturday's (server-side Task 0 reading) and today's (empirical reproducer) symptom observations are the same root cause.** Different surface signatures (Friday's "token invalid after deploy", Saturday's "DCR client persistence" hypothesis, today's "JTI mapping not found"), all caused by the same file-store ephemerality.

The fix architecture is straightforward: swap `OAuthProxy`'s `client_storage` from the default in-memory/file backend to a network-backed `AsyncKeyValue` implementation (Redis or Postgres). The OAuthProxy interface is already pluggable. **No FastMCP fork or upstream patch required.**

---

## 1. Empirical evidence (Phase 1.A + 1.B)

### Phase 1.A — baseline handshake (2026-05-24 16:41 UTC)

Nick removed and re-added the Pandora's Box MCP connector in Claude Desktop. The full OAuth handshake was captured live from `railway logs`:

```
16:41:28  401 invalid_token                                ← initial probe (expected)
16:41:29  GET  /.well-known/oauth-protected-resource    → 200    PRM discovery
16:41:30  GET  /.well-known/oauth-authorization-server  → 200    AS metadata discovery
16:41:30  POST /mcp/v1/register                         → 201    DCR — new client_id minted
16:41:31  GET  /mcp/v1/auth/callback?code=1f1398a2…     → 302    GitHub returning with code
16:41:31  POST /mcp/v1/token                            → 200    Token exchange (initial)
16:41:41  GET  /mcp/v1/authorize?…code_challenge=…S256  → 302    PKCE-enabled authorize
16:41:42  POST /mcp/v1/consent?txn_id=…                 → 302    Internal consent transaction
16:41:43+ POST /mcp/v1                                  → 200×N  MCP traffic flowing
```

Confirmations:
- **PKCE in use:** `code_challenge_method=S256` in the `/authorize` request.
- **DCR minted a fresh `client_id`:** `46682172-38f4-40ff-80bf-e4844f52bc57` — fresh registration on every reconnect (note: not reusing prior registrations).
- **GitHub silent re-auth:** no consent screen displayed to Nick because GitHub remembers prior authorizations for the OAuth App.
- **Allowlist passed:** `MCP_ALLOWED_GITHUB_USERS=303webhouse` check succeeded.

### Phase 1.B — Railway redeploy + reproducer (2026-05-24 16:51-17:10 UTC)

Nick triggered a no-op redeploy of the `pandoras-box` Railway service from the dashboard at ~16:49 UTC. The new FastMCP process came up at 16:51:48 UTC:

```
16:51:42  INFO:hub_mcp.auth:OAuth enabled: GitHub upstream, 1 allowed user(s),
          base=https://pandoras-box-production.up.railway.app/mcp/v1
16:51:43  INFO:main:✅ MCP v1 server mounted at /mcp/v1
16:51:48  INFO:main:✅ MCP OAuth discovery + DCR exposed at domain root for Claude.ai
```

Nick then sent a message in Claude Desktop ("Have TORO pull data from the Pandora hub using the Pandora MCP. Please make one request for each dataset...") at 11:06 AM MDT (17:06 UTC). TORO attempted four tool calls — all failed identically with generic transport errors. Server-side log signature:

```
17:07:34  POST /mcp/v1 → 401
          ↑ FastMCP internal: "JTI mapping not found (token may have...)"
          proxy.py:1684
          tool: notifications/initialized   token_hash: f0de3faa

17:07:41  POST /mcp/v1 → 401 invalid_token
          tool: notifications/initialized   token_hash: 160d0631  ← different

17:07:44  POST /mcp/v1 → 401 invalid_token   token_hash: 586b8a8e  ← different

17:08:12  POST /mcp/v1 → 401 invalid_token   token_hash: 3c6d4153  ← different

17:10:29  POST /mcp/v1 → 401 invalid_token
          tool: initialize                  token_hash: ba9d687a  ← different
```

Observations:
- **Five different `token_hash` values** across the 5 attempts in 3 minutes. Claude Desktop is presenting multiple distinct access tokens; all rejected. (Likely cycling through cached tokens / refresh attempts from its session state.)
- **Anthropic's client did NOT trigger an OAuth recovery flow** — no `/register` (re-DCR), no `/token` (refresh), no `/.well-known/*` (re-discovery) in the post-redeploy window. Just blind retries with stale tokens.
- **The first 401 explicitly logs "JTI mapping not found"** (FastMCP `proxy.py:1684`), which is the FastMCP-side diagnostic for "this token's JTI claim doesn't match anything in our state store." That message confirms the failure is in the JTI lookup, not in upstream token validation, not in signature verification, not in scope mismatch.

User-visible effect: TORO surfaced the failure to Nick as "MCP unreachable" and recommended a manual reconnect. The OAuth recovery is **not transparent**.

---

## 2. FastMCP code-level confirmation

Read of installed FastMCP 3.3.1 source at `<site-packages>/fastmcp/server/auth/oauth_proxy/proxy.py`:

### The diagnostic message origin (proxy.py:1684)

```python
# proxy.py:1675-1688
try:
    # 1. Verify FastMCP JWT signature and claims
    payload = self.jwt_issuer.verify_token(token)
    jti = payload["jti"]
    upstream_claims = payload.get("upstream_claims")

    # 2. Look up upstream token via JTI mapping
    jti_mapping = await self._jti_mapping_store.get(key=jti)
    if not jti_mapping:
        logger.info(
            "JTI mapping not found (token may have expired): jti=%s...",
            jti[:16],
        )
        return None
```

The flow:
1. Claude Desktop sends a JWT access token (signed by FastMCP).
2. FastMCP verifies the JWT signature/expiry — passes (token was issued ~minutes ago, signing key didn't rotate).
3. FastMCP extracts the `jti` claim and looks it up in `_jti_mapping_store`.
4. **Lookup misses** because the store was wiped at redeploy.
5. Token rejected as if it were invalid/expired.

### The storage interface is pluggable (proxy.py:265, 486-512)

```python
# proxy.py:265 (constructor signature)
client_storage: AsyncKeyValue | None = None,

# proxy.py:486-510 (default fallback when caller passes None)
if client_storage is None:
    storage_encryption_key = derive_jwt_key(
        high_entropy_material=jwt_signing_key.decode(),
        salt="fastmcp-storage-encryption-key",
    )
    key_fingerprint = hashlib.sha256(storage_encryption_key).hexdigest()[:12]
    storage_dir = settings.home / "oauth-proxy" / key_fingerprint
    storage_dir.mkdir(parents=True, exist_ok=True)

    file_store = FileTreeStore(
        data_directory=storage_dir,
        ...
    )
    client_storage = FernetEncryptionWrapper(
        key_value=file_store,
        fernet=Fernet(key=storage_encryption_key),
        raise_on_decryption_error=False,
    )

self._client_storage: AsyncKeyValue = client_storage
```

The constructor accepts any `AsyncKeyValue` implementation (from the `key_value.aio.protocols` package). If `client_storage=None` is passed, it falls back to a filesystem-backed store. **Our current `backend/hub_mcp/auth.py:120-129` does not pass `client_storage`, so we get the default file store.**

### All six OAuth state collections share the same `client_storage` backend (proxy.py:521-577)

```python
self._upstream_token_store    = ... # mcp-upstream-tokens
self._client_store            = ... # mcp-oauth-proxy-clients  (DCR)
self._transaction_store       = ... # mcp-oauth-transactions
self._code_store              = ... # mcp-authorization-codes
self._jti_mapping_store       = ... # mcp-jti-mappings           ← what's blowing up today
self._refresh_token_store     = ... # mcp-refresh-tokens
```

Swapping the backend fixes ALL six collections at once — no need to selectively pick what to persist. The file store's contents are encrypted-at-rest by `FernetEncryptionWrapper`; the replacement should preserve that wrapping pattern.

---

## 3. Why Railway containers wipe `settings.home`

Railway uses **ephemeral filesystems** for container instances by default. Anything written outside a mounted persistent volume vanishes when the container restarts (which happens on every deploy, manual redeploy, or scaling event).

`settings.home` in FastMCP resolves to the user's home directory inside the container (typically `~/.fastmcp/` or platform-equivalent). Railway does NOT persist that path. So:

- 16:41 UTC: FastMCP writes JTI mappings to `~/.fastmcp/oauth-proxy/<fingerprint>/mcp-jti-mappings/…` as Anthropic registers + receives tokens.
- 16:49 UTC: Nick clicks "Redeploy" on Railway dashboard.
- 16:51 UTC: New container starts; `~/.fastmcp/oauth-proxy/<fingerprint>/` is empty.
- 17:07 UTC: Anthropic's first post-redeploy request arrives; JTI lookup misses; 401.

Persistent volumes ARE available on Railway but require explicit configuration and have nontrivial cost / configuration overhead. The cleaner fix is to swap to a network-backed store (Redis or Postgres) which we already have in production.

---

## 4. Hypothesis mapping (per rev1 brief Task 1.C)

The rev1 brief listed five hypotheses (H1-H5) for the failure mode. Mapping evidence to them:

| H# | Hypothesis | Status | Note |
|---|---|---|---|
| H1 | DCR client registration lost on restart | **PARTIAL** | Likely also true (same file store wiped), but not the immediate trigger. The JTI lookup fails BEFORE any client_id lookup would happen for the cached-token path. DCR client loss would surface separately if Claude Desktop attempted refresh-token exchange (`grant_type=refresh_token`), which it did NOT do in the observed reproducer. |
| H2 | Refresh token storage lost on restart | **PARTIAL (same)** | Same file store wipes refresh tokens too. Would manifest if Claude Desktop tried to refresh — it didn't. |
| H3 | Authorization code state expired or lost | **NO** | Auth codes are 60s-TTL and only relevant during the active flow. Not in play during cached-token failures. |
| H4 | Token verifier cache flush + slow GitHub round-trip | **NO** | This would manifest as a slow first request, not 401. Evidence shows fast 401 with FastMCP-internal JTI lookup miss before any GitHub round-trip is attempted. |
| H5 | Something else entirely (TLS/cookie/connection-resume) | **NO** | The 401 + WWW-Authenticate header is a clean OAuth-layer rejection; not a transport-layer failure. |
| **H6 (NEW)** | **JTI mapping store wiped on Railway redeploy due to filesystem ephemerality** | **CONFIRMED** | Direct match between FastMCP `proxy.py:1684` log line and observed evidence; file-store default at `settings.home / "oauth-proxy" / …` documented in FastMCP source. |

H6 is the corrected diagnosis. H1 and H2 are downstream consequences of the same root cause but not the immediate failure path for the cached-token rejection scenario.

---

## 5. Corrected fix shape (supersedes rev1 brief Task 2)

The rev1 brief's Task 2 scoped persistence around an `oauth_clients` table for DCR client registrations. The corrected target is **all six OAuthProxy state collections via a single `client_storage` backend swap**.

### Minimum viable fix (recommended)

In `backend/hub_mcp/auth.py`'s `build_oauth_provider()`:

```python
# Pseudocode — actual import path will be confirmed at implementation time
from key_value.aio.stores.redis import RedisStore
from key_value.aio.wrappers.fernet_encryption import FernetEncryptionWrapper
from cryptography.fernet import Fernet
import os

redis_url = os.environ.get("REDIS_URL")  # already used by other services
client_storage_raw = RedisStore(url=redis_url, namespace="fastmcp-oauth")

# Preserve encryption-at-rest pattern from FastMCP's default
storage_key = derive_jwt_key(...)  # same derivation as FastMCP's default
client_storage = FernetEncryptionWrapper(
    key_value=client_storage_raw,
    fernet=Fernet(key=storage_key),
    raise_on_decryption_error=False,
)

proxy = OAuthProxy(
    upstream_authorization_endpoint="https://github.com/login/oauth/authorize",
    upstream_token_endpoint="https://github.com/login/oauth/access_token",
    upstream_client_id=client_id,
    upstream_client_secret=client_secret,
    token_verifier=verifier,
    base_url=base_url,
    client_storage=client_storage,  # ← THE FIX
)
```

That's the entire architectural change. All six state collections (DCR clients, JTI mappings, refresh tokens, transactions, auth codes, upstream tokens) now persist across Railway redeploys.

### Backend choice: Redis vs Postgres

| Aspect | Redis (Upstash) | Postgres (Railway) |
|---|---|---|
| Already in production | ✓ (used by sector_cache + many other paths) | ✓ |
| TTL semantics | Native (matches OAuth lifetimes) | Manual cleanup job needed |
| Latency for auth checks | Sub-ms | Few ms |
| Durability vs ephemeral | External, durable | External, durable |
| Encryption-at-rest | App-layer via Fernet | App-layer via Fernet (same) |
| Operational visibility | Lower (binary keys) | Higher (SQL queries) |

**Recommend Redis** for the typical OAuth state lifetimes (short-lived auth codes, time-bound refresh tokens, frequently-checked JTI mappings). The `key_value.aio.stores.redis` backend is already installed (it ships with `key_value` which FastMCP depends on). The Fernet encryption wrapper preserves the at-rest protection FastMCP's default provides.

### What this drops from the rev1 brief

- New Postgres migration for `oauth_clients` table — **not needed** if we use Redis. (If we choose Postgres backend, we'd use `key_value.aio.stores.postgresql` which creates its own tables — still don't need to author migrations for OAuth state.)
- DCR-specific rate-limiting (rev1 Task 3) — independent of the persistence fix; keep as a small follow-up Task 3 in the implementation phase.
- Audit logging gaps (rev1 Task 4) — independent; keep as small follow-up Task 4.
- Doc extension (rev1 Task 5) — keep; document the new env var contract (`REDIS_URL` already exists; we'd just be using it from a new caller).

### What the implementation phase looks like (Task 2 reframed)

1. **Add Redis-backed `AsyncKeyValue` instance** to `build_oauth_provider()`. Two-line code change inside the existing function plus the Fernet wrapper. ~30 min.
2. **Smoke-test in production**:
   - Connect Claude Desktop, observe Phase 1.A signature.
   - Trigger Railway redeploy (manual or via empty-commit push to `main`).
   - Send MCP request from Claude Desktop without manual reconnect.
   - Expected outcome: 200 OK, no 401, no reconnect prompt, transparent state survival. ~15 min once the fix is deployed.
3. **Confirm Redis keys created**: `redis-cli` against the Upstash instance, look for keys under the `fastmcp-oauth:*` namespace post-handshake. ~5 min.

Total implementation effort: **30-60 minutes of code + 30 minutes of smoke testing**. Far smaller than the original rev1 brief's 1-2 day estimate.

---

## 6. Items deferred (rev1 brief sections still applicable)

- **Task 3 — DCR rate-limiting verification.** Independent of the persistence fix. Confirm whether `RateLimitMiddleware` covers `/register` at the 5/IP/hour ceiling; add if not.
- **Task 4 — Audit logging gaps.** Token issuance / revocation events still not logged at fine grain. Keep as small follow-up; may require subclassing OAuthProxy or wrapping its token endpoint.
- **Task 5 — Documentation.** Extend `docs/operations/mcp-token-rotation.md` with: the new `client_storage` env contract (none — `REDIS_URL` already set), the persistence-backend rationale, the lifetime of each of the six state collections, and an operator runbook for inspecting/clearing the Redis namespace if a security incident requires it.
- **Olympus committee SPY smoke** (rev1 Task 6.f) — runs market hours via OAuth-authenticated MCP. Required before merging to `main`.

---

## 7. Outstanding open question — Anthropic-side client recovery

The Phase 1.B reproducer also surfaced a secondary issue: **Anthropic's client did not auto-recover from the 401**. It retried with stale tokens 5 times in 3 minutes, then surfaced the error to TORO. The MCP spec presumably expects clients to re-handshake via the OAuth flow when they see `401 invalid_token` with a `WWW-Authenticate` header pointing at PRM. Anthropic's implementation may have a bug, may have a longer retry window than we observed, or may require a specific error-response format we're not emitting.

**This is outside Phase C.1-rev1's scope** to fix (we don't control Anthropic's client). But once our server-side fix lands (state survives restart → no 401 on stale tokens), the client-side recovery issue becomes moot for the common case. It's worth filing a separate observation: "MCP client at Anthropic doesn't auto-re-handshake after 401 even with proper PRM pointer in WWW-Authenticate" — would matter for any future scenario where the server legitimately revokes tokens.

---

## 8. Verification commit reference

This RCA is committed alongside an amendment to `docs/codex-briefs/phase-c.1-rev1-dcr-persistence-2026-05-23.md` that points future readers here for the corrected diagnosis. Both documents committed together so a cold-read of rev1 cannot execute on the wrong target.

The implementation phase remains gated per the rev1 brief's "no code changes until Nick confirms the RCA is approved and the implementation plan is appropriate" clause.
