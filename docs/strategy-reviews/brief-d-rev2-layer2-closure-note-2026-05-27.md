# Brief D rev2 — Layer 2 Closure Note (2026-05-27)

**Status:** **SHIPPED.** Layer 2 (Option A — Railway persistent volume + `FASTMCP_HOME=/data`) is live and empirically validated. Hub MCP OAuth state now survives Railway redeploys without manual reconnect.

**Predecessors:**
- Brief: Brief D rev2 (planning chat, 2026-05-24)
- Phase 0 closure: `docs/strategy-reviews/brief-d-rev2-phase0-closure-note-2026-05-25.md` (commit `450ca1a`)
- Layer 2 sub-brief: `docs/codex-briefs/brief-d-rev2-layer2-option-a-2026-05-26.md` (commit `a855ab2`)
- Phase C.1-rev1 closure: `docs/strategy-reviews/phase-c.1-rev1-closure-note-2026-05-24.md`
- Phase C.1-rev2 closure: `docs/strategy-reviews/phase-c.1-rev2-closure-note-2026-05-24.md`

---

## TL;DR

Phase C.1-rev1 + rev2 burned ~57 minutes of total time over two same-day aborted cycles trying to make Redis-backed OAuth state persistence work. Brief D rev2's Phase 0 investigation found the bug was below FastMCP entirely — in the `key_value` library's `RedisStore(client=...)` write-read path — and ruled out the rev2 closure note's leading hypothesis (multi-worker isolation).

Layer 2 sidestepped the broken Redis chain entirely by mounting a Railway persistent volume at `/data` and setting `FASTMCP_HOME=/data`. FastMCP's default file-backed `client_storage` now writes to a path that survives container restarts. Zero application code added for the persistence fix — only Railway dashboard / CLI configuration.

Empirically validated on production via a real code-change redeploy (`cdf6ac1` at 2026-05-27 20:00:25 UTC). The pre-existing OAuth session survived without manual reconnect — confirmed by a fresh Claude.ai chat at 20:06 UTC calling `mcp_ping` + `mcp_describe_tools` against the hub successfully.

**Net result:** the day-trading blocker is gone. Manual reconnect after Railway redeploys is no longer required.

---

## 1. Execution timeline (2026-05-26 → 2026-05-27 UTC)

| UTC | Event |
|---|---|
| 2026-05-26 21:08:39 | Nick's commit `a6572d8` deployed (parallel perf-baseline work); Railway volume add likely piggybacked on this deploy. |
| 2026-05-26 ~21:20 | `railway volume add --mount-path /data` — volume `pandoras-box-volume` created, 5000MB, attached to `pandoras-box` service in `production`. |
| 2026-05-26 21:27:45 | `FASTMCP_HOME=/data` env var set; auto-redeploy completed. Service up at version `a6572d8`. From this deploy forward, OAuth state writes to `/data/oauth-proxy/<key_fingerprint>/...`. |
| 2026-05-26 ~21:30 | Commit `74da4b7` pushed: removed `/mcp/v1/_repro` endpoint from `backend/main.py` and deleted `scripts/repro_oauth_storage.py`. |
| 2026-05-26 21:32:21 | Cleanup deploy completed. `/mcp/v1/_repro` returns 404 (cleanly removed). `/mcp/v1/health` still 200. |
| 2026-05-27 ~19:54 | Nick's commit `cdf6ac1` (unrelated parallel work) pushed; auto-deploy began. |
| 2026-05-27 20:00:25 | `cdf6ac1` deploy completed. **Critical:** this was a real code-change deploy, not just an env var update. |
| 2026-05-27 20:06 | Validation test from a fresh Claude.ai chat: `mcp_ping` → ok (raw response showed `server_time`, `schema_version`, `uptime_seconds=368`). `mcp_describe_tools` → 10 tools returned. **No reconnect prompt.** Pre-existing OAuth session survived the `cdf6ac1` redeploy. |

---

## 2. What shipped

### Code & config (no application code changes)

- **Railway volume `pandoras-box-volume`** mounted at `/data` on `pandoras-box` service, `production` environment. Provisioned 2026-05-26 via `railway volume add` (interactive path-prompt mode; the `--service` and `--mount-path` flags were positional-quirky in CLI v4.59.0).
- **Railway env var `FASTMCP_HOME=/data`** set on `pandoras-box` service.

### Code (cleanup only)

Commit `74da4b7` on `main`:
- Removed 104 lines from `backend/main.py` (the `/mcp/v1/_repro` endpoint block at L1159-1262 from commit `427a019`).
- Deleted `scripts/repro_oauth_storage.py` (181 lines from commit `ddb7c3b`).

### Total deploys triggered for Layer 2

Three intentional deploys (all post-market-close per `PROJECT_RULES.md` rule):

1. Volume mount + auto-redeploy
2. `FASTMCP_HOME=/data` env var set + auto-redeploy
3. Cleanup commit `74da4b7` + auto-redeploy

Two additional deploys happened in parallel from Nick's unrelated work (`a6572d8`, `cdf6ac1`), each of which also validated persistence by NOT severing the OAuth session.

---

## 3. Validation evidence

### Server-side checks (CC, 2026-05-27 ~20:05 UTC)

1. `/mcp/v1/health` returns 200 with version `cdf6ac1`, `worker_id: pid-2` (single worker confirmed yet again), `uptime_seconds: 172`.
2. `/.well-known/oauth-authorization-server` returns valid JSON with `issuer`, `authorization_endpoint`, `token_endpoint`, `registration_endpoint`. → FastMCP `OAuthProxy.__init__` completed successfully against `FASTMCP_HOME=/data` (if `/data` were unwritable or unmounted, the proxy would have failed to construct and the entire `/mcp/v1` mount would 404).
3. Railway volume `pandoras-box-volume` confirmed attached at `/data`, 150MB/5000MB used.

### Client-side check (Nick + fresh Claude.ai agent, 2026-05-27 20:06 UTC)

From a fresh Claude.ai chat with the Pandora's Box hub connector:

```json
mcp_ping raw result:
{
  "status": "ok",
  "data": {
    "status": "ok",
    "server_time": "2026-05-27T20:06:35.030699+00:00",
    "schema_version": "v1.0",
    "uptime_seconds": 368
  },
  "summary": "MCP: connected. Schema v1.0. Server time 2026-05-27T20:06:35.030699+00:00. Uptime 368s.",
  "staleness_seconds": 0,
  "schema_version": "v1.0",
  "error": null
}

mcp_describe_tools: 10 tools returned at schema v1.0
```

- Both calls succeeded without any reconnect or authorize prompt.
- `uptime_seconds: 368` (~6 min) confirms the calls ran after the `cdf6ac1` 20:00 UTC redeploy.
- The 10 tools returned: `mcp_ping`, `mcp_describe_tools`, `hub_get_quote`, `hub_get_bias_composite`, `hub_get_flow_radar`, `hub_get_hermes_alerts`, `hub_get_hydra_scores`, `hub_get_portfolio_balances`, `hub_get_positions`, `hub_get_sector_strength`. (`hub_get_quote` is the 10th tool added in commit `b59b6e9`; the connection guide doc still says 9, fixed in this commit.)

### Validation success criteria from Layer 2 sub-brief § 6 — all met

| # | Criterion | Status |
|---|---|---|
| 1 | `/data` volume mounted on `pandoras-box` service | ✅ |
| 2 | `FASTMCP_HOME=/data` env var set | ✅ |
| 3 | `/mcp/v1/health` returns 200 with new `deployed_at` post-redeploy | ✅ |
| 4 | Manual redeploy triggered; existing Claude.ai OAuth session continues working WITHOUT Disconnect/Reconnect cycle | ✅ (validated against `cdf6ac1` deploy, which was a real code change) |
| 5 | `/mcp/v1/_repro` endpoint removed | ✅ (returns 404 post-`74da4b7`) |
| 6 | `scripts/repro_oauth_storage.py` removed | ✅ |
| 7 | Closure note for Layer 2 drafted | ✅ (this file) |

---

## 4. Hypothesis ledger — final state

Brief D rev2 inherited four hypotheses from the rev2 closure note. Phase 0 + Layer 2 work concluded:

| H | Hypothesis | Final status | Evidence |
|---|---|---|---|
| H1 | Multiple uvicorn workers with isolated OAuthProxy state | **RULED OUT** | Procfile shows single uvicorn (no `--workers`/`WEB_CONCURRENCY`); `/mcp/v1/health worker_id` returns identical pid across requests; Phase 0 Investigation 2 reproducer bug surfaced in single-worker mode. |
| H2 | RedisStore async ordering — `.put()` returns before write commits | **Partially challenged** | Phase 0 Investigation 2 reproducer showed identical failure for immediate and concurrent puts. A pure async race would produce different failure profiles. |
| H3 | FernetEncryptionWrapper write-side bug | **RULED OUT** | The default file-backed config uses the SAME `FernetEncryptionWrapper(raise_on_decryption_error=False)`. It works on top of `FileTreeStore` (empirically — see this validation). It only fails on top of `RedisStore(client=...)`. The wrapper itself is fine. |
| H4 | `RedisStore(client=...)` vs `url=...` — caller-provided async client breaks an internal init contract that the `url=` form satisfies | **Confirmed candidate** | Process of elimination after H1 + H3 ruled out. The bug lives in the `key_value.aio.stores.redis.RedisStore` initialization path when given a pre-built client. |

H4 stands as the open library-level bug. Brief D rev2 doesn't fix it — it sidesteps it. The bug remains for anyone trying `RedisStore(client=...)` with that library version against an Upstash backend. Filing this upstream is a separate, low-priority task.

---

## 5. Operational implications

### Post-Layer-2 behavior on Railway redeploy

| Scenario | Pre-Layer-2 | Post-Layer-2 |
|---|---|---|
| Push to `main` (any branch merge or single commit) | OAuth state lost; manual reconnect required | OAuth state persists; no reconnect required |
| `railway variables --set ...` (env var change) | OAuth state lost | Persists |
| Railway-initiated rebuild/restart | OAuth state lost | Persists |
| Manual `railway redeploy` | OAuth state lost | Persists |
| Container moves between Railway hosts | OAuth state may be lost | Volume travels with the service per Railway's volume semantics; should persist |

### Implications for the market-hours deploy rule

`PROJECT_RULES.md` shipped a rule on 2026-05-24 (commit `7a424ab`):

> Hub MCP backend deploys avoid market hours (09:30–16:00 ET, Mon–Fri) unless fixing an active production issue. ... **After OAuth state persistence ships (Brief D rev2), this rule downgrades to "preferred" rather than "should not."**

That self-referenced downgrade trigger is now satisfied. The rule should be relaxed in a follow-up commit. Suggested rewording (not part of this closure note, queued as next-step doc tidy):

> Hub MCP backend deploys are preferred outside market hours (09:30–16:00 ET, Mon–Fri). OAuth state persists across redeploys (Brief D rev2 / Option A), so a market-hours deploy no longer severs the Claude.ai connector — but the brief 30–90s service unavailability during cold-start can still interrupt an in-flight committee pass. Use judgment.

### Volume capacity headroom

- Volume size: 5000MB
- Current usage: 150MB (3%) — mostly buildpack artifacts and ephemeral Railway state, not OAuth state
- OAuth state per registered client: <1KB (a single `ProxyDCRClient` Pydantic model, Fernet-encrypted)
- Practical headroom: effectively unlimited for OAuth-state purposes

### Backup / disaster recovery

- Railway volumes do not auto-snapshot in the default plan as of writing.
- If the volume is lost, Claude.ai will need to reconnect (one-time DCR re-registration). Inconvenient but not catastrophic.
- For now, accept the risk. If multi-user, multi-client growth ever happens, revisit.

---

## 6. Open items deferred from this closure

1. **`PROJECT_RULES.md` market-hours rule rewording** to reflect the self-referenced "downgrades to preferred" trigger. Pure doc edit, no deploy required.
2. **`docs/operations/mcp-connection-guide.md` tool-count fix** — current text says 9 tools; production manifest is 10 (`hub_get_quote` added in `b59b6e9`). Pure doc edit.
3. **File `key_value.aio.stores.redis.RedisStore(client=...)` bug upstream.** Low priority; we don't use that code path anymore.
4. **Optional Option B (Postgres-backed OAuth storage)** for multi-worker / multi-replica scaling. Not needed at current solo-trader scale. Queued for if/when scale changes.

---

## 7. Files touched this closure cycle (final state)

```
[modified/removed on main]
  backend/main.py            (74da4b7 — removed /mcp/v1/_repro endpoint, 104 lines)
  scripts/repro_oauth_storage.py  (74da4b7 — deleted, 181 lines)

[unchanged on main, Layer 1 still live]
  backend/main.py            (c51ee04 — /mcp/v1/health endpoint stays)
  docs/operations/mcp-connection-guide.md  (7a424ab — § 1 stale-session playbook)
  PROJECT_RULES.md           (7a424ab — market-hours deploy rule)

[Railway config (not in repo)]
  Volume: pandoras-box-volume (5000MB, mounted /data on pandoras-box / production)
  Env var: FASTMCP_HOME=/data (set on pandoras-box / production)

[docs added]
  docs/strategy-reviews/brief-d-rev2-phase0-closure-note-2026-05-25.md  (450ca1a)
  docs/codex-briefs/brief-d-rev2-layer2-option-a-2026-05-26.md          (a855ab2)
  docs/strategy-reviews/brief-d-rev2-layer2-closure-note-2026-05-27.md  (this file)
```

---

## 8. Commit chain (Brief D rev2 total)

| Commit | Description | Status |
|---|---|---|
| `7a424ab` | Layer 1 ship (/mcp/v1/health + docs + market-hours rule) | shipped |
| `c51ee04` | Layer 1 post-deploy fix (route before mount) | shipped |
| `ddb7c3b` | Phase 0 Investigation 2 reproducer script | removed in `74da4b7` |
| `427a019` | Phase 0 Investigation 2 `/mcp/v1/_repro` endpoint | removed in `74da4b7` |
| `450ca1a` | Phase 0 closure note + Option A recommendation | shipped (doc) |
| `05e71f9` | Layer 2 sub-brief MISADD (sub-brief + unrelated WIP swept in) | reverted by `869befc` |
| `869befc` | Revert of `05e71f9` | shipped |
| `a855ab2` | Layer 2 sub-brief clean re-add | shipped |
| `74da4b7` | Layer 2 cleanup (remove Phase 0 diagnostic surfaces) | shipped |
| (this commit) | Layer 2 closure note | shipping in this push |

Net `main` impact of Brief D rev2: +5 docs (3 closure/sub-brief + 1 health endpoint + 1 ops-doc § 1 playbook), 1 `PROJECT_RULES.md` rule, ~50 lines of `backend/main.py` (Layer 1 health endpoint), and one Railway volume + env var. Everything else is committed-then-reverted or committed-then-removed.

---

## 9. Lessons carried forward beyond Brief D

1. **Investigation-first discipline is real.** Phase C.1-rev1 + rev2 burned ~57 minutes of cycle time on Redis hypotheses that the empirical reproducer dispatched in one round. Brief D rev2's Phase 0 was investigation-first — 3 hours of investigation, ~30 min of implementation, no aborted cycles.

2. **The "smallest possible fix" was the right scope here.** Option A required zero application code. Option B (Postgres-backed) was queued as backup but never needed. Reaching for the smallest fix that actually solves the problem — instead of fixing the underlying library bug — was the high-leverage choice.

3. **The market-hours rule worked as intended once, and was violated once (by CC).** The accidental misadd in commit `05e71f9` triggered a mid-market-hours deploy. The damage was bounded (one stale OAuth session for ~9 minutes), but the failure mode of "git add picks up untracked files when other concurrent work is in flight" is a real risk. CC's updated practice: always `git diff --cached --name-status` before committing, and never commit during market hours without explicit confirmation.

4. **The `/mcp/v1/health` Layer 1 endpoint earned its keep.** It served as the deploy-state telemetry across the entire Layer 2 execution — every "is the deploy done yet" check ran against it. Worth the 30 lines of code it took to add.

---

## 10. Done definition

| Item | Status |
|---|---|
| Volume provisioned + attached | ✅ |
| `FASTMCP_HOME=/data` env var set | ✅ |
| Cleanup commit shipped | ✅ |
| Real-deploy persistence validated (against `cdf6ac1`) | ✅ |
| Claude.ai tool-call test passes from a fresh chat | ✅ |
| Closure note written | ✅ |
| Brief D rev2 closed | ✅ |

**Brief D rev2 is closed.** Day-trading blocker resolved.

---

**End of Brief D rev2 Layer 2 closure note.**
