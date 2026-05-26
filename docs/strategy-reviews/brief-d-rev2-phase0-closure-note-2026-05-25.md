# Brief D rev2 — Phase 0 Closure Note (2026-05-25)

**Status:** Phase 0 deliverable. Awaiting Nick + ATLAS approval before Layer 2 begins.

**Predecessors:**
- Brief: `docs/codex-briefs/` (Brief D rev2, paste from planning chat 2026-05-24)
- Layer 1 ship: commit `c51ee04` on `main`
- Investigation 2 reproducer script: `scripts/repro_oauth_storage.py` (commit `ddb7c3b`)
- Investigation 2 in-container endpoint: `/mcp/v1/_repro` (commit `427a019`, disabled post-run)
- Phase C.1-rev1 closure: `docs/strategy-reviews/phase-c.1-rev1-closure-note-2026-05-24.md`
- Phase C.1-rev2 closure: `docs/strategy-reviews/phase-c.1-rev2-closure-note-2026-05-24.md`

---

## TL;DR

The Phase C.1-rev2 storage chain (`Redis.from_url(..., health_check_interval=30, retry_on_timeout=True, socket_keepalive=True, decode_responses=False)` → `RedisStore(client=...)` → `FernetEncryptionWrapper(raise_on_decryption_error=False)`) has a deterministic write-read consistency bug that surfaces in **a single uvicorn worker, with no in-process cache between writes and reads, with no concurrency, and with no idle period.** `.put()` returns without raising; `.get()` immediately after returns `None`.

This was the rev2 production symptom (POST /register returned 201; GET /authorize 1s later said the same client_id was unregistered). It now reproduces in pure-Python with no FastMCP layer above it.

**H1 (multi-worker isolation) is ruled out** — the leading hypothesis from the rev2 closure note is wrong. The bug is in the storage chain itself: H3 (FernetEncryptionWrapper write/read mismatch) or H4 (`RedisStore(client=...)` vs `url=` internal difference) remain plausible.

**Recommended Layer 2 path: Option A (Railway persistent volume + file-backed storage).** Sidesteps the broken Redis+Fernet chain entirely. File-backed storage was empirically verified working at 19:14 UTC 2026-05-24 (rev2 closure § 3). Smallest possible change: Railway dashboard volume mount + storage path env var. Estimated effort: 30 min – 1 hour. Option B (Postgres-backed OAuth storage) is the strong backup.

**Option C (Phase C.1-rev3 — chase the bug down further) is NOT recommended.** Three aborted cycles in a row would be expensive, and the bug now lives in the key_value library's wrappers rather than anything we own.

---

## 1. Investigation 1 — Multi-worker detection

**Goal:** Determine whether Railway runs the FastMCP service with multiple uvicorn workers (the rev2 closure note's H1 hypothesis).

**Method:** Read `Procfile`, search for worker-count flags, verify via runtime `worker_id` from the enriched `/mcp/v1/health` endpoint.

**Result: SINGLE WORKER CONFIRMED.**

- [Procfile](../../Procfile) is a single line: `web: sh -c "cd backend && python -m uvicorn main:app --host 0.0.0.0 --port $PORT"`
- No `--workers N` flag, no `WEB_CONCURRENCY` env, no gunicorn, no `railway.toml`, no `nixpacks.toml`, no `Dockerfile`.
- Repo-wide grep for `workers|WEB_CONCURRENCY|gunicorn` confirms no multi-worker configuration anywhere in the live deploy path.
- Runtime verification: two hits to `/mcp/v1/health` 2 seconds apart returned identical `worker_id: "pid-2"`.

**Implication:** Single-worker means a single `OAuthProxy` instance with a single `_client_storage` reference. POST `/register` and GET `/authorize` literally go through the same Python object. The "per-worker isolation" concern in rev2 closure note's H1 cannot apply.

---

## 2. Investigation 2 — Standalone storage-chain reproducer

**Goal:** Determine whether the RedisStore + FernetEncryptionWrapper chain works correctly outside the FastMCP request flow. If yes → bug is FastMCP-level (likely H1). If no → bug is at the storage layer (H2/H3/H4).

**Method:** Reconstructed the exact rev2 storage chain in a small Python program and exercised it against the production Upstash instance via a temporary, token-gated endpoint added to the deployed FastAPI app (`/mcp/v1/_repro`, commit `427a019`). Local `railway run` from Windows failed at TLS verification (Python CA-bundle mismatch with Upstash's cert chain), so the test had to execute inside the Railway Linux container to be faithful to production conditions.

**Scenarios run:**
1. **Immediate put-then-get** (microseconds apart — the exact rev2 case)
2. **Two concurrent put/get cycles** via `asyncio.gather` (tests async ordering / serialization)

S2 (10-min idle) was omitted because rev2 closure § 4 already empirically confirmed the keepalive config survives Upstash idle drops. The open question is the write-read consistency.

**Result: BUG REPRODUCES IN SINGLE-PROCESS, ZERO-DELAY MODE.**

```json
{
  "worker_id": "pid-2",
  "scenarios": [
    {"name": "immediate",  "ok": false, "ms": 591.1, "error": "get returned None (key absent)"},
    {"name": "concurrent", "ok": false, "ms": 569.4, "error": "get returned None (key absent); get returned None (key absent)"}
  ]
}
```

**Diagnostic interpretation:**
- `.put()` returned without raising in all four put operations across the two scenarios.
- `.get()` immediately after returned `None` in all four — which `FernetEncryptionWrapper(raise_on_decryption_error=False)` translates to "key absent" (could also mask a silent decryption failure).
- The 591ms / 569ms timings indicate the calls did make round-trips to Upstash; failure is not a TCP-level connection problem.
- Same failure signature for the immediate case (microseconds between put and get) and the concurrent case (two `asyncio.gather`-ed cycles) — argues against a pure async-ordering race (H2 alone). A structural bug fits the data better.

**Hypothesis status after Investigation 2:**

| H | Hypothesis | Status |
|---|---|---|
| H1 | Multi-worker isolation between OAuthProxy instances | **Ruled out** — single worker confirmed; bug still reproduces. |
| H2 | RedisStore `.put()` async ordering — returns before write commits | **Partially challenged** — both immediate and concurrent fail identically; not a timing race alone. |
| H3 | FernetEncryptionWrapper write/read mismatch (decryption silently failing under `raise_on_decryption_error=False`) | **Strong candidate.** Matches "no exception on put, no value on get." |
| H4 | `RedisStore(client=...)` vs `RedisStore(url=...)` internal difference making writes effectively no-ops | **Strong candidate.** Matches the same observable behavior. |

Investigation 2 did not distinguish H3 from H4 definitively. A future diagnostic could (e.g., raw `redis.get` of the same key bypassing the Fernet wrapper, or `RedisStore(url=...)` form for direct comparison). Not needed for the Layer 2 decision because both options below sidestep the entire chain.

---

## 3. Investigation 3 — FastMCP OAuthProxy source read

**Goal:** Confirm POST /register and GET /authorize go through the same `client_storage` instance, with no in-process cache between them above that boundary.

**Method:** Located `fastmcp` package at `C:/Users/nickh/AppData/Roaming/Python/Python314/site-packages/fastmcp/server/auth/oauth_proxy/proxy.py` (FastMCP 3.3.1). Grepped for `client_storage` and traced both handlers.

**Result:** No in-process cache between `_client_store.put()` (register) and `_client_store.get()` (authorize).

**Storage flow (verified from proxy.py):**

```
POST /register handler → register_client(client_info)   [proxy.py:791]
                       → self._client_store.put(client_id, ProxyDCRClient)
                       → PydanticAdapter[ProxyDCRClient].put
                       → FernetEncryptionWrapper.put
                       → RedisStore.put

GET /authorize handler → get_client(client_id)          [proxy.py:729]
                       → self._client_store.get(key=client_id)
                       → PydanticAdapter[ProxyDCRClient].get
                       → FernetEncryptionWrapper.get
                       → RedisStore.get

In-process cache between them: NONE. No LRU, no dict, no memoization
on _client_store or _client_storage. Single _client_store instance
built once in OAuthProxy.__init__ (proxy.py:530-538).
```

**One layer our Investigation 2 reproducer did NOT replicate:** `PydanticAdapter[ProxyDCRClient]`. This sits between OAuthProxy handlers and `FernetEncryptionWrapper`, calling `model_dump()` on put and `Model.model_validate()` on get. It's a type-conversion wrapper, not a cache or storage layer. Since our reproducer fails at the layer *below* PydanticAdapter, PydanticAdapter is not the bug — it would only add more steps on top of an already-broken chain.

---

## 4. Layer 2 — Recommended Option

### Option A — Railway persistent volume + file-backed OAuth storage (RECOMMENDED)

**Premise:** The FastMCP default file-backed `client_storage` works correctly (verified empirically post-rev2-revert at 19:14 UTC 2026-05-24 — see rev2 closure § 3). The only deficiency is that the file lives in ephemeral container storage and dies on every Railway redeploy. Mounting a persistent volume at the storage path eliminates the deficiency entirely without touching the (currently broken) Redis chain.

**Effort:** 30 min – 1 hour.
- Railway dashboard: provision a volume on the `pandoras-box` service in `production` environment, mount at a known path (e.g., `/data` or `/var/lib/fastmcp`).
- Set an env var (`FASTMCP_STORAGE_PATH=/data` or similar — exact name TBD by checking FastMCP's `client_storage` default-path resolution).
- One deploy to pick up the env var.
- Smoke: redeploy intentionally, verify existing Claude.ai session reconnects without manual `Settings → Connectors → Disconnect/Reconnect`.

**Risk:** Very low. Zero code changes. Uses an already-verified-working storage path.

**Multi-worker behavior:** Not an issue — single worker confirmed (Investigation 1). Even if multi-worker were re-enabled later, all workers in the same container share the same filesystem and would see the same files.

**ATLAS/AEGIS review burden:** Light. File permissions, volume backup/snapshot policy if any. No new code surface.

**Pros:** Smallest possible fix. Zero code. Uses an empirically-validated storage backend. Fast to ship, fast to revert if Railway volumes prove unsuitable.

**Cons:** Tied to Railway's volume product (vendor lock-in for OAuth storage). Volume costs (typically free up to a small allotment). If the Railway plan changes or the volume offering is discontinued, would need a re-migration.

### Option B — Postgres-backed OAuth storage (STRONG BACKUP)

**Premise:** Nick already runs Railway Postgres in the same project. A new storage adapter implementing the `key_value.aio.protocols.key_value.AsyncKeyValue` interface backed by Postgres would replace the broken Redis+Fernet chain entirely with a different storage abstraction that has strong ACID guarantees.

**Effort:** 4–8 hours.
- New adapter module (probably `backend/hub_mcp/postgres_oauth_store.py`).
- Schema migration for the OAuth state table (one table, two columns: key TEXT PRIMARY KEY, value BYTEA or JSONB, indexed by key).
- Wire into `OAuthProxy(client_storage=PostgresStore(...))` in `backend/hub_mcp/auth.py`.
- Integration test (similar to the standalone reproducer but using the new adapter).
- Smoke: deploy, exercise the OAuth flow, redeploy, verify reconnection.

**Risk:** Medium. New code path, but Postgres is well-understood and the existing `backend/database/postgres_client.py` provides a working async client.

**Multi-worker behavior:** Postgres handles concurrent reads/writes natively. Future-proof if multi-worker is ever introduced.

**ATLAS/AEGIS review burden:** Moderate. Schema design, connection pooling for the OAuth-specific queries, AEGIS confirms encryption-at-rest for OAuth tokens (Postgres column-level encryption or Fernet-in-the-app layer).

**Pros:** Strongest consistency guarantees. Uses already-provisioned infrastructure. No new external dependency. Future-proof against multi-worker scaling.

**Cons:** Most code of the three options. Schema migration required. Slightly higher attack surface than file-backed (network-attached storage vs local file).

### Option C — Phase C.1-rev3 (Redis with H3/H4 fix)

**Premise:** Continue rev2's path by identifying and fixing the H3 or H4 bug in the key_value library wrappers.

**Effort:** Unknown. Plausibly 4–16 hours to:
- Distinguish H3 from H4 with additional diagnostics (raw redis.get of the same key after a wrapper put).
- Read `key_value.aio.wrappers.encryption.FernetEncryptionWrapper` source and `key_value.aio.stores.redis.RedisStore` source.
- Either submit an upstream PR (slow, no control over timing) or fork+patch (maintenance burden).

**Risk:** Medium-high. Three aborted attempts in a row (rev1, rev2, rev3) would have compounding diagnostic + deploy costs. The bug lives in the key_value library, not our code.

**Multi-worker behavior:** Same as rev2 — H1 already ruled out, so the multi-worker dimension is moot.

**ATLAS/AEGIS review burden:** Higher than Option A or B. Forking a third-party library or running a patched version requires AEGIS sign-off on the security implications of running unaudited or self-maintained crypto code (FernetEncryptionWrapper is in the path).

**Pros:** Builds on existing rev2 investment. Doesn't introduce a new storage technology.

**Cons:** Worst track record. Investigation-first discipline already applied; the bug is genuinely in a third-party library wrapper, not our code. Time spent here is diagnostic; uncertain payoff.

**Strong recommendation against Option C.** The rev2 closure note's question 12 ("does the operational pain warrant another rev attempt right now?") was answered "yes" by Brief D rev2's existence. But the right form of "yes" is "yes, with a different storage backend," not "yes, with the same backend that has already failed twice."

### Option D — Status quo (Layer 1 mitigations + manual reconnect)

**Premise:** Layer 1 quick-wins reduce friction enough that manual reconnect is tolerable.

**Effort:** 0 additional (Layer 1 already shipped: commit `c51ee04` + post-deploy fix).

**Risk:** Ongoing operational pain. Day-trading blocker remains. Continues to compromise the Olympus committee's data substrate.

**Pros:** No new code. No new infrastructure.

**Cons:** Doesn't solve the problem. Brief D rev2 exists precisely because status quo is unacceptable.

**Status quo is the floor, not the goal.** If Option A and B both prove infeasible for reasons we haven't anticipated, D is the fallback. Not the target.

---

## 5. Recommended decision

**Option A first.** Confirm Railway's volume offering and pricing for the `pandoras-box` service. If available, implement and ship. Expected effort 30 min – 1 hour.

**If Option A is unavailable for any reason (volume tier requires Pro plan upgrade, FastMCP's file-backed storage doesn't accept arbitrary paths, etc.):** Option B. Expected effort 4–8 hours.

**Do not pursue Option C.** The empirical data does not support a third Redis attempt being more productive than switching backends.

**ATLAS** owns the architectural review of whichever option Nick selects.
**AEGIS** review burden is light: no new auth surface (OAuth is already shipped); only the storage backend changes. AEGIS confirms encryption-at-rest considerations for the chosen backend.

---

## 6. Open questions for Nick + ATLAS

1. **Railway volume availability check.** Is the `pandoras-box` service on a Railway plan that supports persistent volumes? (Likely yes — Railway's volume support is broad — but worth confirming before Option A scope.)
2. **FastMCP default file-storage path resolution.** Where does FastMCP's default `client_storage` (the `DiskStore` it builds when `client_storage=None`) write its state? If the path is configurable via env var, Option A is essentially a Railway dashboard change. If the path is hardcoded to a container-ephemeral location, Option A needs a small code change to override.
3. **PydanticAdapter as bug suspect.** Investigation 2 reproducer fed plain dicts directly to `FernetEncryptionWrapper`, skipping `PydanticAdapter`. If we ever want to confirm `PydanticAdapter` is not a contributor, a one-line change to the reproducer would do it. Not needed for the Layer 2 decision but worth filing if we ever return to Option C.
4. **Schema design for Option B.** If we end up at Option B, ATLAS should weigh in on whether OAuth state lives in its own table, in a key-value-style `oauth_storage` table, or in an existing namespace. Light decision but worth alignment.

---

## 7. Active state on `main` post-Phase-0

| Item | Status |
|---|---|
| Layer 1 health endpoint at `/mcp/v1/health` | Live (commit `c51ee04`). Returns `status / service / uptime_seconds / deployed_at / worker_id / version`. Unauthenticated. |
| Layer 1 mcp-connection-guide.md § 1 (stale-session playbook) | Live (commit `7a424ab`). |
| Layer 1 market-hours rule in PROJECT_RULES.md | Live (commit `7a424ab`). |
| Investigation 2 reproducer `scripts/repro_oauth_storage.py` | On `main` (commit `ddb7c3b`). Throwaway; remove on cleanup. Cannot execute from Windows due to local TLS-trust issue. |
| Investigation 2 endpoint `/mcp/v1/_repro` | On `main` (commit `427a019`). **Disabled** (`PHASE0_REPRO_TOKEN` env var deleted). Throwaway; remove on cleanup. |

**Cleanup commit (proposed) after Phase 0 approval:**
- Remove `/mcp/v1/_repro` endpoint from `backend/main.py`.
- Remove `scripts/repro_oauth_storage.py`.
- Single commit, single deploy, one final session-severance during low-traffic window.

---

## 8. Files touched this Phase 0 cycle

```
[added on main]
  scripts/repro_oauth_storage.py                                            (ddb7c3b)
  backend/main.py  (+ /mcp/v1/health route)                                 (7a424ab + c51ee04)
  backend/main.py  (+ /mcp/v1/_repro endpoint)                              (427a019)
  docs/operations/mcp-connection-guide.md  (§ 1 stale-session playbook)     (7a424ab)
  PROJECT_RULES.md  (market-hours deploy rule)                              (7a424ab)
  docs/strategy-reviews/brief-d-rev2-phase0-closure-note-2026-05-25.md      (this file)
```

---

## 9. Approval gates

| Gate | Status |
|---|---|
| 1 — Pre-implementation | ✅ Cleared 2026-05-24 |
| 2 — Layer 1 ship | ✅ Cleared 2026-05-24 (`7a424ab` + `c51ee04`) |
| 3 — Phase 0 deliverable + Option recommendation | **← awaiting Nick + ATLAS approval** |
| 4 — Layer 2 pre-push | not yet reached |

---

**End of Phase 0 closure note.**
