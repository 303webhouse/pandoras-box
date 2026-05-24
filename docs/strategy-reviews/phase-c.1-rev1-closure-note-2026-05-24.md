# Phase C.1-rev1 — Closure Note (2026-05-24)

**Status:** **SHIPPED → REVERTED** the same session. Smoke test failed; reverted per the rev1 brief's "if smoke fails, git revert immediately; don't fix forward" gate. Service restored to pre-fix baseline.

**Branch:** `phase-c.1-oauth` (preserved on remote; not deleted — fix-forward attempt will branch from a new base).
**Predecessors:**
- Brief: `docs/codex-briefs/phase-c.1-rev1-dcr-persistence-2026-05-23.md` (with 2026-05-24 amendment pointer)
- RCA: `docs/codex-briefs/phase-c.1-rev1-rca-2026-05-24.md`
- Task 0 findings: `docs/codex-briefs/phase-c.1-task0-findings-2026-05-23.md`
- Observation: `docs/observations/mcp-client-401-behavior-2026-05-24.md`

---

## TL;DR

The fix (Redis-backed OAuth state persistence via `key_value.aio.stores.redis`) shipped at 17:58 UTC after passing pre-merge verification (REDIS_URL confirmed set, derive_jwt_key chain confirmed deterministic, AEGIS self-review with no vetoes). Critical post-merge startup-log check passed: `client_storage=redis (persistent)`.

**Smoke step 1 (baseline reconnect) failed at 18:31 UTC** — `POST /mcp/v1/register` returned 500 Internal Server Error with `redis.exceptions.ConnectionError: Connection closed by server.`. Anthropic's client surfaced the failure as OAuth correlation ID `ofid_c8808da4ecffa5b8`. Three back-to-back registration attempts (18:31:56, 18:32:07, 18:32:08 UTC) all failed identically.

Per the brief gate, reverted immediately: commit `8072c5c` on main reverts the code change (`21983bf`). All documentation (brief, RCA, Task 0 findings, observation) preserved — only the `backend/hub_mcp/auth.py` change was reverted. Service redeployed at 18:34 UTC; pre-fix file-backed OAuth state restored.

---

## 1. Sequence of events (2026-05-24)

| UTC | Event |
|---|---|
| 17:58:08 | Phase C.1-rev1 merge deploy SUCCESS (Railway deployment `dd67aa79`) |
| 17:58:18 | Startup log confirms `client_storage=redis (persistent)` — critical check PASSED |
| 18:31:48 | Nick begins Claude Desktop reconnect; OAuth handshake initiates |
| 18:31:56 | First `POST /mcp/v1/register` → 500 Internal Server Error (`redis.ConnectionError`) |
| 18:32:07 | Second `POST /mcp/v1/register` → 500 (same error) |
| 18:32:08 | Third `POST /mcp/v1/register` → 500 (same error) |
| 18:32:34 | CC identifies failure pattern from Railway logs; confirms smoke failure |
| 18:33:38 | `git revert 21983bf` committed on main (`8072c5c`) |
| 18:34:15 | Revert deploy SUCCESS (Railway deployment `8c49ccf4`) |
| 18:37:10 | Post-revert verification: `/health=200 redis=ok`, `/mcp/v1/register` returns 400 (validation error, not 500) |

Time from merge to revert deploy: ~36 minutes (with ~33 min idle window in between).

---

## 2. Root cause hypothesis

The Redis-backed `client_storage` was successfully constructed at startup (`client_storage=redis (persistent)` log confirms init succeeded). It also passed a startup-time connectivity check (otherwise FastMCP would have failed earlier).

**The failure happened after a ~33-minute idle window** between the post-deploy startup (~17:58 UTC) and the first OAuth request (~18:31 UTC). The most likely root cause is:

> **Upstash drops idle connections (~5-minute default timeout). The `RedisStore` from `key_value.aio.stores.redis` constructs its underlying redis-py client without `retry_on_timeout`, `health_check_interval`, or auto-reconnect configuration. After the idle period, the underlying TCP socket is silently dead from the server side; the next operation hits a stale fd and raises `ConnectionError: Connection closed by server` at `redis/_parsers/base.py:561`.**

Evidence supporting this hypothesis:
- The error is `Connection closed by server`, not authentication failure, timeout on connect, or DNS resolution failure
- Identical failure across 3 sequential attempts ~10s apart — consistent with a fully dead socket (not a transient blip)
- Other Redis users (`sector_cache`, UW cache) work fine because they use the project's `database/redis_client.py` which presumably has different connection handling (worth a comparison check)
- Phase A.3's overnight smoke confirmed sector_cache survives idle periods without issue

**To validate before re-attempt:** Read the redis-py client construction in `RedisStore` and confirm whether it accepts retry/health-check kwargs, OR test the failure mode in a controlled environment by creating a `RedisStore(url=...)`, idling 10+ minutes, then performing an operation.

---

## 3. Why the fix passed pre-checks but failed in the wild

Each pre-merge check verified what it was supposed to, but none of them tested **post-idle connection resilience**:

| Pre-check | What it verified | What it did NOT verify |
|---|---|---|
| V1: `REDIS_URL` set | env var presence + scheme (`rediss://`) | actual connection survival under idle |
| V2: `derive_jwt_key` stable | deterministic encryption key across restarts | runtime Redis connection behavior |
| AEGIS self-review | secret handling, encryption-at-rest, threat model | runtime resilience of underlying transport |
| Startup INFO log | the right code branch executed and connected once | sustained operability through real-world idle patterns |
| Task 0 findings | OAuthProxy storage interface is pluggable; backends exist | the chosen backend's idle-connection behavior |

A `mcp_ping` immediately after startup would likely have succeeded. The 33-min idle gap between deploy and first user action is exactly the kind of real-world delay that pre-merge smoke testing would have missed even if we'd done it.

**Lesson for next attempt:** any candidate fix must include an idle-resilience verification step (e.g., explicit "trigger deploy, wait 10 min, then hit /register" as a smoke gate before declaring success).

---

## 4. What's preserved vs reverted

**Preserved on `main`:**
- `docs/codex-briefs/phase-c.1-oauth-2026-05-22.md` (original brief)
- `docs/codex-briefs/phase-c.1-rev1-dcr-persistence-2026-05-23.md` (rev1 brief)
- `docs/codex-briefs/phase-c.1-rev1-rca-2026-05-24.md` (RCA)
- `docs/codex-briefs/phase-c.1-task0-findings-2026-05-23.md` (Task 0 findings)
- `docs/observations/mcp-client-401-behavior-2026-05-24.md` (Anthropic client-side observation)
- This closure note

**Reverted on `main`:**
- `backend/hub_mcp/auth.py` — back to pre-fix state. The `_build_client_storage()` helper, `REDIS_URL_ENV` constant, `client_storage=` argument to `OAuthProxy(...)`, and the startup log suffix are all gone.

**Preserved on `phase-c.1-oauth` branch (remote):**
- The full implementation (commit `21983bf`) is still available on the feature branch for reference / cherry-pick by a future rev2 attempt.

---

## 5. Fix-forward options for Phase C.1-rev2

Three concrete paths to evaluate, in order of complexity:

### Option A — Configure redis-py client with auto-retry, pass via `client=` arg

`RedisStore(url=...)` constructs the client internally with default settings. The constructor also accepts `client=<existing redis.asyncio.Redis>` to share an externally-managed client. Build a client with the resilience flags:

```python
import redis.asyncio as redis_async

redis_client = redis_async.Redis.from_url(
    redis_url,
    retry_on_timeout=True,
    retry_on_error=[redis_async.ConnectionError, redis_async.TimeoutError],
    health_check_interval=30,
    socket_keepalive=True,
)
redis_store = RedisStore(client=redis_client, default_collection="fastmcp-oauth")
```

Standard redis-py pattern. Should handle Upstash idle-drop transparently.

**Risk:** redis-py's `retry_on_*` semantics differ between versions; test that the version we're on does what's documented.

### Option B — Use `key_value.aio.wrappers.retry`

The `key_value` package ships a `retry` wrapper that re-attempts operations on failure. Chain it:

```python
from key_value.aio.wrappers.retry import RetryWrapper

redis_store = RedisStore(url=redis_url, default_collection="fastmcp-oauth")
resilient_store = RetryWrapper(key_value=redis_store, max_attempts=3, ...)
client_storage = FernetEncryptionWrapper(key_value=resilient_store, ...)
```

Cleaner separation of concerns — `key_value`-layer retry, not redis-py-layer retry.

**Risk:** retry wrapper retries the failed operation, but if the underlying client's socket is dead, every retry hits the same dead socket. Needs the redis-py client to reconnect on retry. May need Option A + Option B in combination.

### Option C — Use the same Redis client construction the rest of the codebase uses

Our `backend/database/redis_client.py` has a working Redis client that's used by sector_cache, UW cache, etc. for months without idle-drop issues. Build the OAuth state store on top of THAT client rather than constructing a new one:

```python
from database.redis_client import get_redis_client  # existing helper
redis_client = await get_redis_client()  # async; returns configured client
redis_store = RedisStore(client=redis_client, default_collection="fastmcp-oauth")
```

**Risk:** need to handle async construction at OAuthProxy init time (FastMCP's `build_oauth_provider()` is currently sync). May require a deferred-init pattern.

**Risk:** the existing client may not have the keep-alive/retry config we need — first verify by reading `database/redis_client.py` and possibly running an idle-test before committing.

---

### Recommended path for Phase C.1-rev2

**Option A** (explicit redis-py client config), with an empirical idle-test BEFORE merging:

1. Construct the redis-py client locally with the resilience flags
2. Write a 10-line Python script that opens the client, idles 7 min, then performs a SET+GET — confirm it survives
3. If yes, integrate via `client=` kwarg to `RedisStore`
4. Re-attempt the merge with the SAME smoke discipline (deploy, wait 10+ min, then test reconnect)

Estimated effort: 1-2 hours including the idle-test verification.

If Option A's idle-test fails, try Option B layered on top, OR fall back to Option C (reuse `database/redis_client.py`). Both add complexity but should eventually work.

---

## 6. Coexistence trigger state

N/A. There was no static-bearer coexistence flag in this build — the brief evolved past that scoping (per Task 0 findings, static `MCP_BEARER_TOKEN` was already dead code pre-Phase-C.1). Post-revert the system is back to its pre-Phase-C.1 state: GitHub OAuth via FastMCP OAuthProxy, default file-backed `client_storage`, manual reconnect required after Railway deploys.

The original brief's coexistence trigger ("N≥3 successful OAuth authentications across both clients sustained over a 72-hour window") never had occasion to activate.

---

## 7. Tier 2 deferred items (still deferred after this build)

- **DCR rate-limiting verification + hardening** (rev1 Task 3). Independent of persistence; still relevant for the next attempt.
- **Audit logging gaps** (rev1 Task 4). Token issuance/revocation events still not logged at fine grain.
- **Doc extension** (rev1 Task 5). `docs/operations/mcp-token-rotation.md` not yet extended with persistence-backend operator notes — depends on a successful rev2.

These should be re-bundled into the Phase C.1-rev2 brief once the persistence fix lands.

---

## 8. Observations from this cycle

Three things worth carrying forward:

1. **Pre-merge verifications are worthwhile but not sufficient.** V1 (env var set), V2 (key stability), AEGIS review, startup-log check all passed. The fix still broke. Real-world idle patterns are not exercised by any of those gates. Future fixes touching network-backed external services need an explicit "wait N minutes then exercise" gate.

2. **Surgical revert preserves learning.** The first revert attempt (`git revert -m 1 <merge>`) would have wiped the brief/RCA/observation docs along with the code. Reverting just the code commit (`git revert <commit>`) kept the documentation — which is the entire value of this build's work. **Pattern worth remembering:** for merges of feature branches with mixed code + docs, revert specific commits rather than the merge.

3. **Anthropic's client-side 401 behavior** documented in `mcp-client-401-behavior-2026-05-24.md` was the user-visible amplifier here. With the server returning 500 (not 401), the client didn't even reach the 401-retry path — it surfaced the failure immediately as the OAuth correlation ID. That's actually informative: Anthropic's client distinguishes "transport failure" (500) from "auth failure" (401) and handles them differently. The 500 path leaks the correlation ID directly to the user; the 401 path enters the retry loop. Worth noting in the observation doc.

---

## 9. Done definition (revised for this aborted cycle)

| Item | Status |
|---|---|
| Feature branch `phase-c.1-oauth` exists with all commits | ✅ |
| Task 0 findings + RCA committed and approved | ✅ |
| Implementation shipped and verified live | ✅ (verified live at 17:58 UTC) |
| All Task 12 smoke checks pass | ❌ Smoke step 1 failed; remaining steps not attempted |
| Documentation authored | ✅ (this note + RCA + brief + observation + findings) |
| Branch ready for merge | N/A — merged then reverted same session |
| Stop and notify Nick when complete | ✅ |

**Verdict: aborted cycle, system restored, comprehensive documentation in place for the next attempt.** The next attempt (Phase C.1-rev2) inherits the brief, RCA, Task 0 findings, this closure note, and the observation doc as authoritative context.

---

## 10. Files touched this build (final state)

```
[reverted on main]
  backend/hub_mcp/auth.py                   (no net change — fix reverted)

[preserved on main]
  docs/codex-briefs/phase-c.1-oauth-2026-05-22.md            (original brief)
  docs/codex-briefs/phase-c.1-rev1-dcr-persistence-2026-05-23.md  (rev1 brief)
  docs/codex-briefs/phase-c.1-rev1-rca-2026-05-24.md         (RCA)
  docs/codex-briefs/phase-c.1-task0-findings-2026-05-23.md   (Task 0 findings)
  docs/observations/mcp-client-401-behavior-2026-05-24.md    (deferred observation)
  docs/strategy-reviews/phase-c.1-rev1-closure-note-2026-05-24.md  (this file)

[preserved on feature branch only]
  backend/hub_mcp/auth.py @ commit 21983bf  (the implemented fix, for reference)
```

Total: 6 docs preserved, 0 code changes net on main.

---

## 11. Commit references

| Commit | Description | Status |
|---|---|---|
| `8cc2a90` | original brief committed on feature branch | preserved |
| `a6e2f09` | Task 0 findings | preserved |
| `1100db0` | rev1 brief | preserved |
| `0b3af0f` | RCA | preserved |
| `21983bf` | **the fix** (Redis client_storage) | reverted (still on feature branch) |
| `1084bd2` | Anthropic-client observation | preserved |
| `8b4a2d1` | merge → main | preserved (merge commit retained) |
| `8072c5c` | **revert of 21983bf** | applied to main |
| (this commit) | closure note | applied to main |
