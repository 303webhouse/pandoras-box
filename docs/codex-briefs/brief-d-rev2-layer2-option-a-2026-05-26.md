# Brief D rev2 — Layer 2 Sub-Brief (Option A: Railway Volume + FASTMCP_HOME)

**Author:** Claude Code (CC) execution plan, written 2026-05-26 during market hours
**Date:** 2026-05-26
**Owner:** CC for execution; Nick for `railway login` refresh + ATLAS approval if any
**Target repo:** `303webhouse/pandoras-box`, main branch
**Files in scope:** Railway dashboard / CLI (volume + env var). Zero code changes in repo for the persistence fix itself. One separate cleanup commit removes the Phase 0 diagnostic surfaces from `backend/main.py` and `scripts/`.
**Depends on:** Brief D rev2 Phase 0 closure (`450ca1a`) — Option A recommended
**Estimated effort:** 30 min – 1 hour (5 min for the volume add + env var, ~10 min for the two redeploys to settle, 5 min for validation, 5 min for cleanup commit)
**Risk:** Low. No code changes for the persistence fix. Two redeploys severs the active Claude.ai session twice — must run outside market hours per `PROJECT_RULES.md`.
**Priority:** High. Closes Brief D rev2.

---

## 1. TL;DR

FastMCP's default file-backed OAuth `client_storage` writes to `settings.home / "oauth-proxy" / <key_fingerprint>/...`. Three facts make Option A trivial:

1. `settings.home` is overridable via the `FASTMCP_HOME` env var (Pydantic settings `env_prefix="FASTMCP_"`).
2. The `key_fingerprint` is sha256(derive_jwt_key(GITHUB_OAUTH_CLIENT_SECRET))[:12] — **stable across deploys** as long as `GITHUB_OAUTH_CLIENT_SECRET` doesn't rotate (it doesn't).
3. The default `FernetEncryptionWrapper` on top of `FileTreeStore` was empirically verified working at 19:14 UTC 2026-05-24 (rev2 closure § 3). It's only on top of `RedisStore(client=...)` that the wrapper breaks — H4 confirmed.

So: mount a Railway persistent volume at `/data` on the `pandoras-box` service, set `FASTMCP_HOME=/data`, redeploy. OAuth state will live at `/data/oauth-proxy/<key_fingerprint>/...` and survive container restarts. Manual reconnect after Railway redeploy goes away.

---

## 2. Why Option A (recap)

Per Phase 0 closure (`docs/strategy-reviews/brief-d-rev2-phase0-closure-note-2026-05-25.md`):

- **Option A (Railway volume):** zero code, ~30 min, file-backed storage path is empirically verified working.
- **Option B (Postgres-backed adapter):** 4–8 hours, strongest consistency, but new code path + schema migration.
- **Option C (Redis with H3/H4 fix):** rejected. Bug lives in `key_value` library's `RedisStore(client=...)` (H4). Third aborted Redis cycle would be high-cost, low-value.
- **Option D (status quo):** floor, not goal.

Option A wins on effort × risk × time-to-relief.

---

## 3. Pre-execution checks (before any state change)

### 3a. Refresh Railway CLI auth (Nick action)

CLI auth has expired from the last session. CC's last attempt to `railway volume list` failed with `Token refresh failed: invalid_grant`. Nick runs once, before CC executes the rest of this brief:

```
railway login
```

(Interactive browser flow. CC cannot drive this — it requires Nick's manual auth.)

After login, CC verifies:

```
railway whoami     # should return: nickhrtzg@gmail.com
railway status     # should show: fabulous-essence / production / pandoras-box
```

### 3b. Confirm market is closed

CC pulls the actual time:

```
python -c "from datetime import datetime; import zoneinfo; print(datetime.now(zoneinfo.ZoneInfo('America/New_York')).strftime('%a %Y-%m-%d %H:%M %Z'))"
```

Must be **after 16:00 ET on a weekday, OR a weekend, OR a market holiday.** Per the `PROJECT_RULES.md` rule shipped in commit `7a424ab`:

> Hub MCP backend deploys avoid market hours (09:30–16:00 ET, Mon–Fri) unless fixing an active production issue.

Brief D rev2 is NOT an active production issue (the manual-reconnect workaround works). So: no execution during market hours.

### 3c. Verify Phase 0 closure was approved

If ATLAS pass on `450ca1a` has happened — surface evidence (commit / chat / external note). If not, CC proceeds only on Nick's direct go-ahead (which Nick gave in chat 2026-05-26 after asking "Did the ATLAS pass already happen in another chat/commit? If not, proceed").

### 3d. Confirm `/mcp/v1/health` is currently live and returning 200

```
curl -sS --ssl-no-revoke https://pandoras-box-production.up.railway.app/mcp/v1/health
```

Expected: `{"status":"ok","service":"mcp/v1","uptime_seconds":...,"deployed_at":"...","worker_id":"pid-2","version":"..."}`.

If the endpoint is down or returning 5xx, the production app has a different problem and Brief D Layer 2 should pause until it's resolved.

---

## 4. Execution

### Step 1 — Provision the volume

```
railway volume add --mount-path /data --service pandoras-box
```

Or via dashboard: Railway → fabulous-essence → pandoras-box → Settings → Volumes → Add Volume → mount path `/data`, default size.

Verify:

```
railway volume list
```

Expected: one volume listed, attached to `pandoras-box`, mount path `/data`.

**This triggers an automatic redeploy of the service** to mount the volume. Sit through it (~30–90s cold start).

### Step 2 — Verify the volume is mounted before setting FASTMCP_HOME

```
railway run python -c "import os; print('exists=', os.path.isdir('/data'))"
```

Expected: `exists= True`. If False, the volume mount didn't take effect — diagnose before continuing.

(Note: `railway run` injects Railway env vars into a LOCAL process. It does NOT execute on the container. To verify `/data` exists on the container's filesystem, hit a container-running endpoint that checks `os.path.isdir('/data')`. CC will either temporarily add this to `/mcp/v1/health` for one deploy cycle, or shell into the container via `railway ssh`, or skip the check and proceed to Step 3 directly since the next redeploy will surface any volume problem clearly.)

**Simplest path:** skip the explicit volume check. The volume `add` is documented to succeed atomically (volume provisioned + service redeployed with mount). If it didn't mount, Step 3's deploy will fail or the service won't start, and CC will see it immediately in the next `/mcp/v1/health` poll.

### Step 3 — Set FASTMCP_HOME env var

```
railway variables --set "FASTMCP_HOME=/data"
```

This triggers a second automatic redeploy to pick up the new env var.

Verify the env var is set:

```
railway run python -c "import os; print('FASTMCP_HOME=', os.environ.get('FASTMCP_HOME','unset'))"
```

Expected: `FASTMCP_HOME= /data`. The `railway run` injects the variable into CC's local process, confirming it's set in Railway's environment for the service.

### Step 4 — Wait for redeploy + verify the service is up

Poll `/mcp/v1/health` until `uptime_seconds < 60` (indicating fresh process). Verify the JSON includes the new `version` SHA (if it changes — env-var-only redeploys may preserve the SHA).

```
curl -sS --ssl-no-revoke https://pandoras-box-production.up.railway.app/mcp/v1/health
```

If a 5xx persists beyond ~3 minutes, abort and diagnose (likely the env var or volume broke startup).

### Step 5 — Validate persistence

This is the test: kill the process, bring it back, verify Claude.ai's existing OAuth session still works.

**Option 5a (manual redeploy via dashboard):** Railway dashboard → pandoras-box → Deployments → Redeploy. Wait ~30–90s. Hit `/mcp/v1/health` — should show fresh `uptime_seconds` and new `deployed_at`.

**Option 5b (via CLI):**

```
railway redeploy --service pandoras-box
```

(Or `railway up` if a no-op deploy is needed.)

**Validation:**

After the redeploy completes, in Claude.ai, run a hub tool that uses the existing OAuth session (e.g., "Use the Pandora's Box MCP to show current bias composite"). If it works **without prompting for a Settings → Connectors → Disconnect/Reconnect cycle**, persistence is working.

If it fails — Claude.ai prompts for reconnect — the OAuth state was lost across redeploy. Diagnose:
- Check `FASTMCP_HOME` is set in the env (per Step 3).
- Check `/data` is mounted as a volume on the service.
- Check `/data/oauth-proxy/` exists (would require an endpoint or shell access).

### Step 6 — Cleanup commit

Bundle into the same deploy window:

- Remove the `/mcp/v1/_repro` endpoint from `backend/main.py` (lines added in commit `427a019`).
- Remove `scripts/repro_oauth_storage.py` (added in commit `ddb7c3b`).
- Leave the closure note and this sub-brief in place as Phase 0 record.

Commit message:

```
chore(hub_mcp): Brief D rev2 Layer 2 cleanup — remove Phase 0 diagnostic surfaces

Phase 0 closure note (450ca1a) and Layer 2 sub-brief shipped. Diagnostic
endpoint /mcp/v1/_repro (commit 427a019) and standalone reproducer
scripts/repro_oauth_storage.py (commit ddb7c3b) are no longer needed.
Disabled since 2026-05-26 02:34 UTC (token env var deleted).

Removed:
- /mcp/v1/_repro endpoint from backend/main.py
- scripts/repro_oauth_storage.py

Kept:
- /mcp/v1/health endpoint (commit c51ee04) — Layer 1, ongoing utility
- docs/operations/mcp-connection-guide.md § 1 stale-session playbook (c51ee04)
- PROJECT_RULES.md market-hours rule (7a424ab)
- docs/strategy-reviews/brief-d-rev2-phase0-closure-note-2026-05-25.md (450ca1a)
- docs/codex-briefs/brief-d-rev2-layer2-option-a-2026-05-26.md (this brief)

Refs: Brief D rev2 § 11 — cleanup after Phase 0 deliverable lands.
```

This is a code change in `backend/main.py` and a file deletion. Push triggers a deploy. Run during the same post-close window as the volume + env var work; the active session was already severed by Step 4 anyway.

---

## 5. Rollback

If Step 5 validation fails:

### Fast rollback (5 min)

```
railway variables --remove FASTMCP_HOME    # or set to empty
```

Triggers a redeploy. FastMCP reverts to default `settings.home` (container-ephemeral, the rev2-baseline behavior).

The volume can stay attached — it doesn't hurt anything, just won't be the storage target. Volume can be deleted later via `railway volume delete` if not needed.

### Deeper rollback

If something more fundamental breaks (e.g., the service won't start with the volume mount for some reason):

```
railway volume detach --service pandoras-box
railway variables --remove FASTMCP_HOME
```

Triggers a redeploy without the volume + without the env var. Returns the service to its pre-Brief-D-Layer-2 state.

The Layer 1 health endpoint + docs + market-hours rule all stay. Phase 0 closure note stays. /_repro endpoint is removed (per Step 6) regardless.

---

## 6. Validation success criteria

Layer 2 ships when ALL of the following are true:

1. `/data` volume mounted on `pandoras-box` service in `production`.
2. `FASTMCP_HOME=/data` env var set on the service.
3. `/mcp/v1/health` returns 200 with new `deployed_at` post-redeploy.
4. Manual redeploy triggered; Claude.ai's existing OAuth session continues working WITHOUT Disconnect/Reconnect cycle.
5. `/mcp/v1/_repro` endpoint removed from `backend/main.py`.
6. `scripts/repro_oauth_storage.py` removed.
7. Closure note (Layer 2 completion) drafted at `docs/strategy-reviews/brief-d-rev2-layer2-closure-note-<date>.md`.

---

## 7. Open risks (acknowledged, accepted)

1. **The volume mount path `/data` is opinionated.** If FastMCP, the OS, or some other dependency wants a different path, the choice is wrong. Mitigation: `/data` is a Railway convention and a clean Linux choice; if it conflicts with something, the service won't start and CC catches it in Step 4.

2. **FASTMCP_HOME default may not honor at runtime as expected.** Pydantic settings with `env_prefix="FASTMCP_"` SHOULD pick up `FASTMCP_HOME`, but if FastMCP's settings instance is constructed before the env is read (e.g., import-time singletonization), the override wouldn't take effect. Mitigation: Pydantic settings is well-tested to read env at construction time, and the convention is documented in FastMCP. If empirically broken, fallback is to set the directory via code rather than env var (small one-line addition to `backend/hub_mcp/server.py`).

3. **Volume size.** Default Railway volume size is fine for KB-scale OAuth state. No risk.

4. **Volume billing.** Railway volumes have a free tier (typically 1GB) and per-GB pricing above that. KB-scale OAuth state stays well within free tier.

5. **Single-volume single-service.** If we ever scale to multi-worker or multi-replica, this volume-attached-to-one-service approach doesn't migrate cleanly. Option B (Postgres-backed) is the right fix at that point. For Nick's solo-trader scale, this is fine for years.

---

## 8. Out of scope

- **Updating `docs/operations/mcp-token-rotation.md`.** Token rotation procedure doesn't change with the storage backend swap. Doc stays.
- **Adding write tools to hub MCP.** Memory item #24 (committee review logging). Separate brief.
- **PydanticAdapter as bug suspect for the rev2 Redis chain.** Investigation 2 didn't test it. Out of scope; Option A sidesteps the entire chain.
- **Migration from file-backed to Postgres later.** Option B is queued as a follow-on if scale demands.

---

## 9. Approval gates

Per Brief D rev2 § 11:

- Gate 1 (pre-implementation) — ✅ Brief D rev2 itself, 2026-05-24
- Gate 2 (Layer 1 ship) — ✅ commits `7a424ab` + `c51ee04`, 2026-05-24
- Gate 3 (Phase 0 deliverable + Option recommendation) — closure note `450ca1a`, 2026-05-25; Nick gave verbal go-ahead in chat 2026-05-26 ("If not, proceed"). No formal ATLAS pass on record.
- Gate 4 (Layer 2 pre-push) — this sub-brief is the pre-execution doc. **CC reports back after each step with health endpoint + JSON status. Nick approves the cleanup commit separately.**

---

## 10. Reference state at time of writing

- Most recent commits on `main`:
  - `9307a9e` — Task 2 schema Amendment #2 — ATLAS Pass 1 resolution (hub_get_options_chain track, unrelated)
  - `8267d3e` — Task 2 schema Amendment #1 — Greeks restored (hub_get_options_chain, unrelated)
  - `450ca1a` — Brief D rev2 Phase 0 closure note
  - `427a019` — /mcp/v1/_repro endpoint (still on main, disabled via env var deletion)
  - `ddb7c3b` — scripts/repro_oauth_storage.py
  - `c51ee04` — Layer 1 fix (route before mount)
  - `7a424ab` — Layer 1 ship (health + docs + market-hours rule)

- `/mcp/v1/health` live, returning 200.
- `/mcp/v1/_repro` live, returning 503 disabled (`PHASE0_REPRO_TOKEN` env var deleted).
- `PROJECT_RULES.md` market-hours rule live.
- Existing OAuth file storage on the container is at `/root/.local/share/fastmcp/oauth-proxy/<key_fingerprint>/` (or equivalent for the container user) — ephemeral.

---

**End of Layer 2 sub-brief.**
