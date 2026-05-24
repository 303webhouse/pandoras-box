# Phase C.1-rev2 — Closure Note (2026-05-24)

**Status:** **SHIPPED → REVERTED** the same session, second time in 4 hours. Smoke failed with a different signature than rev1 — surface this as a NEW failure mode for rev3 to address.

**Predecessors:**
- rev1 brief: `docs/codex-briefs/phase-c.1-rev1-dcr-persistence-2026-05-23.md` (with 2026-05-24 amendment)
- RCA: `docs/codex-briefs/phase-c.1-rev1-rca-2026-05-24.md`
- rev1 closure: `docs/strategy-reviews/phase-c.1-rev1-closure-note-2026-05-24.md`
- Task 0 findings: `docs/codex-briefs/phase-c.1-task0-findings-2026-05-23.md`
- Observation: `docs/observations/mcp-client-401-behavior-2026-05-24.md`

**Branches:**
- `phase-c.1-oauth-rev2` preserved on remote at commit `d0b5400` (the rev2 code, for reference)
- `main` at commit `b6f2082` (Revert of d0b5400)

---

## TL;DR

rev2 added `health_check_interval=30`, `retry_on_timeout=True`, `socket_keepalive=True`, and `decode_responses=False` to a pre-built async redis-py client passed to `RedisStore(client=...)`. This was the targeted fix for rev1's failure mode (Upstash idle-drop → `ConnectionError`).

**The idle-drop fix worked** — empirically validated. After the rev2 deploy at 18:48 UTC and a 5-7 minute idle window before first OAuth registration, `POST /mcp/v1/register` returned **201 Created** with no `ConnectionError`. The connection stayed alive across the Upstash idle threshold.

**But a separate, more concerning bug surfaced**: the registration write doesn't persist for the next read. CC reproduced this with a direct curl test at 19:08 UTC:

```
POST /mcp/v1/register   → 201 Created
                          response body contains client_id=c0e76a24-c998-4805-8347-6fc092d96fac
                          + full DCR metadata (client_secret, redirect_uris, etc.)

(1 second later — same curl process, same TCP session at the user agent)

GET  /mcp/v1/authorize?client_id=c0e76a24-c998-4805-8347-6fc092d96fac
                       → 400 Bad Request
                          error: "Client ID 'c0e76a24-c998-...' is not registered with this server"
```

Same client_id, 1 second apart, server-issued from /register, immediately unknown to /authorize on the same server instance. The write-read consistency holds for the file-backed default storage (verified empirically post-revert at 19:14 UTC) but breaks for our Redis-backed wrapper.

**Per the brief's "smoke fails → revert immediately, don't fix forward" rule**, reverted at 19:08 UTC. Revert deploy succeeded at 19:09 UTC. Service restored; manual reconnect from Claude Desktop verified working at 19:14 UTC.

---

## 1. Sequence of events (2026-05-24)

| UTC | Event |
|---|---|
| 18:48:42 | rev2 deploy SUCCESS (Railway deployment `28693c68`) |
| 18:48:43 | Startup log: `client_storage=redis (persistent, health-check=30s)` — CRITICAL CHECK PASSED |
| 18:50:00 | CC starts 10-min idle wait per rev2 smoke gate |
| 18:55:20 | Nick attempts first reconnect (slightly inside idle window). POST /register → **201 Created** (idle-drop fix WORKED — no ConnectionError). GET /authorize with the issued client_id → 400 Unregistered |
| 18:57-19:04 | Nick attempts remove + re-add cycles. Each cycle: POST /register → 201, GET /authorize → 400 with the SAME client_id from /register |
| 19:00:00 | 10-min idle wait completes (background task notification) |
| 19:05:03 | Unrelated deploy lands (`d058984d`, "chore(skills): Brief A — consolidate shared committee rules") — caused brief 502s during cold start |
| 19:07:52 | App responsive again post-cold-start; rev2 code still active |
| 19:08:10 | CC reproducer via direct curl: POST /register → 201 client_id=c0e76a24-..., GET /authorize with same client_id → 400. **Confirmed server-side write-read inconsistency.** |
| 19:08:59 | `git revert d0b5400` committed on main (`b6f2082`); pushed |
| 19:09:01 | Revert deploy SUCCESS (Railway deployment `ce504381`) |
| 19:14:48 | Nick reconnects Claude Desktop. POST /register → 201 client_id=cba954d4-..., GET /authorize with same client_id → **302 Found**. Full OAuth flow completes (consent, callback, token). MCP traffic flows at 200/202. **Baseline restored.** |

Time from second merge to second revert deploy: ~21 minutes. Tighter than rev1's 36-min cycle.

---

## 2. Root cause hypothesis

The rev2 fix successfully addressed the idle-drop failure mode (rev1's blocker). But the fix uncovered or introduced a SEPARATE bug in the write-read consistency of OAuth state through the Redis-backed `client_storage`.

Possible causes, ranked by my current best guess:

### H1 (most likely): Multiple uvicorn workers with isolated state

Railway containers often run multiple uvicorn workers behind a single port (via gunicorn/uvicorn-worker pattern). Each worker:
- Builds its own `OAuthProxy` via `build_oauth_provider()` at startup
- Has its own redis-py async client (different connection pool, but same Upstash instance)
- Has its own in-process state if OAuthProxy maintains any (e.g., per-worker LRU cache for hot client lookups)

If POST /register lands on Worker A:
- Worker A's OAuthProxy writes to Redis via its Fernet+Redis wrapper
- Worker A's response goes back to Anthropic's client

If GET /authorize lands on Worker B 1 second later:
- Worker B's OAuthProxy reads from Redis via its OWN Fernet+Redis wrapper

**They should both see the same Redis state** since they connect to the same Upstash with the same Fernet key. UNLESS:
- FastMCP's OAuthProxy has an in-process cache that's NOT the injected `client_storage` (e.g., a memoization on top), and reads consult the in-process cache first which is empty for Worker B.
- OR the Fernet encryption key derives from per-worker state (e.g., process-id-salted), making each worker's ciphertext unreadable by other workers.

**Why this is the most likely hypothesis**: rev2 had `health_check_interval=30` which works fine on a single-worker setup but could mask multi-worker issues. The file-backed default ALSO had the multi-worker problem in principle, but file paths are shared on the local filesystem (same container), so all workers see the same files. With Redis, the "sharing" is via the same Upstash instance — which should also work — UNLESS there's an in-process FastMCP layer above the storage that doesn't.

### H2: RedisStore async ordering — .put() returns before write commits

`RedisStore(client=redis_async_client).put(key, value)` should `await` the underlying redis-py call (`SET key value`). If it doesn't — if it's fire-and-forget on a connection pipeline — then the next request can hit Redis before the write commits.

**Why this is less likely than H1**: the gap between /register and /authorize is ~1 second. A pipelined write should have flushed by then. But worth ruling out empirically with a direct test.

### H3: FernetEncryptionWrapper has a write-side issue

`FernetEncryptionWrapper(redis_store, fernet=..., raise_on_decryption_error=False)` wraps both reads and writes. If the wrapper has a write-side ordering bug (e.g., async encryption-then-store split incorrectly), writes might not commit.

**Why this is least likely**: rev1 used the same wrapper and didn't hit this consistency issue (rev1 failed at a deeper layer with `ConnectionError`). If the wrapper had a write-side bug, rev1 would have shown it post-startup before the idle drop. It didn't.

### H4: We injected `client=` instead of `url=` and broke something internal to RedisStore

rev1 used `RedisStore(url=redis_url, ...)`. rev2 used `RedisStore(client=redis_client, ...)`. RedisStore docs say "If client is provided, the store will not manage the client's lifecycle." Maybe there's something subtle about how RedisStore handles a caller-provided client vs an internally-built one — e.g., not entering an async context manager around operations.

**Worth checking**: read `RedisStore` source to see if the code path differs based on `url=` vs `client=`.

---

## 3. Empirical evidence — file backend WORKS, Redis backend DOESN'T (rev2 config)

Post-revert verification at 19:14 UTC (file-backed default):

```
POST /mcp/v1/register             → 201  client_id=cba954d4-435a-4c30-8498-f00be399ced2
GET  /mcp/v1/authorize?client_id=cba954d4-...
                                  → 302  (Found, redirects to GitHub consent)
POST /mcp/v1/consent              → 302
GET  /mcp/v1/auth/callback?code=… → 302  (GitHub returns code)
POST /mcp/v1/token                → 200
POST /mcp/v1 (MCP requests)       → 200/202  (multiple)
```

Same OAuthProxy code, same Anthropic client, same flow shape — but client_id is consistent between register and authorize because file-store doesn't have the consistency issue. Whatever rev2 broke is specific to the Redis path.

---

## 4. What rev2 confirmed that rev1 alone didn't

| Question | rev1 result | rev2 result |
|---|---|---|
| Does FastMCP accept a pluggable `client_storage`? | ✓ confirmed | ✓ confirmed (still works) |
| Does Redis backend survive process startup? | ✓ (`redis (persistent)` startup log) | ✓ (same) |
| Does Redis backend survive idle periods? | ✗ ConnectionError after ~33 min idle | ✅ **survives** with health_check_interval=30 |
| Does write-then-read work in the same flow? | unknown (couldn't get past idle drop) | ✗ **fails** — register returns 201 but lookup misses |
| Does Railway env have REDIS_URL configured? | ✓ | ✓ |
| Does TLS work (rediss://)? | ✓ | ✓ |

So rev2 represents real progress on the connection-lifecycle dimension. The idle-drop fix is correct. There's just a SECOND bug at a different layer that needs solving before any future attempt can succeed.

---

## 5. Recommended path for Phase C.1-rev3

The rev1 closure note listed three options (A: explicit redis-py client; B: `key_value.aio.wrappers.retry`; C: reuse `database/redis_client.py`). Option A is what rev2 implemented, and it surfaced the H1-H4 hypotheses above.

**Pre-implementation work for rev3 should be investigation, not coding:**

### Investigation 1 — Multi-worker detection
Determine how many uvicorn workers Railway runs. Inspect `backend/main.py` and the Railway startup command (Procfile, `railway.toml`, or similar) for worker count. If >1, hypothesis H1 jumps to confirmed-likely and we need a different fix strategy.

Quick check method: look for log lines from the new deploy. If we see `OAuth enabled: GitHub upstream...` ONCE, we have 1 worker. If we see it N times in the startup window, we have N workers.

### Investigation 2 — Direct manual reproducer outside the FastMCP flow
Write a small standalone Python script that:
1. Builds the exact same `RedisStore(client=redis_async_client, default_collection="fastmcp-oauth")` + `FernetEncryptionWrapper` chain we'd use in rev3
2. Does a `.put(key="test-1", value={"foo": "bar"})`
3. Does a `.get(key="test-1")` and verifies the value comes back

If this works → the storage chain is functional → the bug is in FastMCP's OAuthProxy layer above it (likely H1 multi-worker isolation or some in-process cache).

If this fails → the bug is in our redis client / wrapper combination, and H2/H3/H4 need deeper investigation.

### Investigation 3 — FastMCP OAuthProxy source read
Find where the `/register` POST handler writes to `_client_store` and where the `/authorize` GET handler reads. Confirm both go through the same storage instance. Check for in-process caching layers.

### After investigation: pick the right fix

- If H1 confirmed → rev3 needs to either disable multi-worker mode (run 1 worker only) OR find a way to share OAuthProxy's in-process cache between workers (probably impossible without code changes to FastMCP).
- If H2/H3/H4 → fix at the wrapper layer.

**Estimated effort:** investigation 1-2 hours; rev3 code change probably 1 hour; smoke test (with idle wait) 30 min. Total ~3-4 hours.

The key discipline: **don't write rev3 code until investigation confirms the actual root cause.** rev1 had a hypothesis (DCR client persistence) that was partly right but missed the JTI angle. rev2 had a hypothesis (idle drop) that was right but missed the consistency angle. Three strikes in a row would be expensive.

---

## 6. Coexistence trigger state

Still N/A — same as rev1's closure note. The original brief's coexistence flag was for static-bearer/OAuth transition, which is moot post-Task 0.

---

## 7. Tier 2 deferred items (still deferred)

- DCR rate-limiting verification + hardening (still relevant for rev3)
- Audit logging gaps (token issuance / revocation events still uninstrumented)
- Doc extension for `mcp-token-rotation.md` (waits on successful rev3)

---

## 8. Observations from this cycle

Two new things worth carrying forward beyond rev1's three:

4. **The "two-revert" pattern surfaced today is informative.** Each revert is closing a hypothesis. rev1 closed "idle drop is the only issue." rev2 closed "fixing idle drop alone is sufficient." rev3 needs to close whatever the actual write-read issue is. The rev1 closure note's framing ("don't write code until investigation confirms") gets stronger here.

5. **A direct curl reproducer (CC, not Anthropic's client) confirms server-side issues much faster than Claude Desktop reconnect attempts.** Saved time by getting from "Nick reports an error" to "verified server-side bug, reverting" in ~10 minutes via the curl test. Worth keeping as the standard troubleshooting first move for any future OAuth issue: ALWAYS reproduce via curl before drawing conclusions about Anthropic-client behavior. Take this back to the deferred "Anthropic-client-401" observation — it makes that observation's recommendations more concrete.

---

## 9. Done definition (revised for this second aborted cycle)

| Item | Status |
|---|---|
| Feature branch with all commits | ✅ `phase-c.1-oauth-rev2` preserved |
| Implementation shipped and verified live | ✅ (`client_storage=redis (persistent, health-check=30s)` confirmed) |
| Smoke checks pass | ❌ rev2 smoke step 1 failed (different mode than rev1) |
| Documentation authored | ✅ (this note + rev1 closure preserved + RCA preserved) |
| Branch merged then reverted | ✅ same session, 21 min cycle |
| Stop and notify Nick when complete | ✅ |

**Verdict: second aborted cycle, system fully restored, comprehensive documentation enriched for the third attempt.**

---

## 10. Files touched this build (final state)

```
[reverted on main]
  backend/hub_mcp/auth.py    (no net change — rev2 fix reverted)

[preserved on main]
  docs/codex-briefs/phase-c.1-oauth-2026-05-22.md
  docs/codex-briefs/phase-c.1-rev1-dcr-persistence-2026-05-23.md
  docs/codex-briefs/phase-c.1-rev1-rca-2026-05-24.md
  docs/codex-briefs/phase-c.1-task0-findings-2026-05-23.md
  docs/observations/mcp-client-401-behavior-2026-05-24.md
  docs/strategy-reviews/phase-c.1-rev1-closure-note-2026-05-24.md
  docs/strategy-reviews/phase-c.1-rev2-closure-note-2026-05-24.md  (this file)

[preserved on feature branch only]
  backend/hub_mcp/auth.py @ commit d0b5400  (the rev2 implemented fix, for reference)
```

Total docs preserved: 7. Net code change on main from the entire C.1-rev1+rev2 effort: zero.

---

## 11. Commit references

| Commit | Description | Status |
|---|---|---|
| `8cc2a90` | original brief | preserved |
| `a6e2f09` | Task 0 findings | preserved |
| `1100db0` | rev1 brief | preserved |
| `0b3af0f` | RCA | preserved |
| `21983bf` | rev1 fix code (RedisStore url= variant) | reverted (still on rev1 branch) |
| `1084bd2` | Anthropic-client observation | preserved |
| `8b4a2d1` | merge rev1 → main | preserved (merge commit retained) |
| `8072c5c` | revert of 21983bf | preserved on main |
| `af3ca98` | rev1 closure note | preserved |
| `d0b5400` | rev2 fix code (RedisStore client= variant w/ retry+health-check) | reverted (still on rev2 branch) |
| `077adfd` | merge rev2 → main | preserved (merge commit retained) |
| `b6f2082` | revert of d0b5400 | applied to main |
| (this commit) | rev2 closure note | applied to main |

---

## 12. One question for Nick before any rev3 attempt

The pattern so far: each revision has fixed one layer's issue and surfaced the next layer's issue. rev3 has a real risk of doing the same thing — fix the write-read consistency bug, then discover a fourth layer.

**Worth considering:** does the operational pain of "manual reconnect after each Railway deploy" actually warrant another rev attempt right now, or is it cheap enough to live with while we focus on higher-leverage Phase C work (the Olympus enrichment expansion, etc.)?

If the answer is "the manual reconnect is fine for now," queue Phase C.1-rev3 on the backlog as **investigation-first** (no code) and move on. If the answer is "we want OAuth persistence soon," approach rev3 with the discipline of: 30 min investigation → 30 min reproducer outside FastMCP → only THEN write code. Both options are reasonable. Nick's call.
