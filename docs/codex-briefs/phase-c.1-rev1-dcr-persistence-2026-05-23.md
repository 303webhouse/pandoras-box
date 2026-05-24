# CC Brief: Phase C.1-rev1 — MCP OAuth Reliability (DCR Persistence?) (2026-05-23)

> **AMENDMENT 2026-05-24 — read this before executing any task.**
>
> Phase 1.A + 1.B empirical reproducer (2026-05-24 16:41-17:10 UTC) showed the lost in-memory state is FastMCP's **JTI mapping store** (`proxy.py:1684`), not specifically the DCR client registrations as this brief originally hypothesized. The architecture pattern is the same (persist OAuthProxy state to a network-backed store), but the **target is broader and more elegant**: swap the `client_storage` constructor argument on `OAuthProxy(...)` to a Redis-backed `AsyncKeyValue` implementation, which persists ALL six OAuthProxy state collections (JTI mappings, DCR clients, refresh tokens, transactions, auth codes, upstream tokens) at once. No new Postgres tables needed.
>
> **Authoritative on the corrected diagnosis and fix shape:** [docs/codex-briefs/phase-c.1-rev1-rca-2026-05-24.md](phase-c.1-rev1-rca-2026-05-24.md). Read the RCA before Task 2.
>
> What still applies from this brief: Task 1 (gating client-side discovery — done), Task 3 (DCR rate-limit verification), Task 4 (audit logging gaps), Task 5 (doc extension), Task 6 (smoke tests), Task 7 (closure note), the Gates section, the Olympus impact section, and the Done definition. What is **superseded**: Task 2's specific scoping around an `oauth_clients` table — see RCA §5 for the corrected fix shape.

**Supersedes:** `docs/codex-briefs/phase-c.1-oauth-2026-05-22.md` (original Phase C.1 brief, scope retired after Task 0 findings).
**Predecessor findings:** `docs/codex-briefs/phase-c.1-task0-findings-2026-05-23.md` (committed as `a6e2f09` on the `phase-c.1-oauth` branch).
**Branch:** `phase-c.1-oauth` (continues; do not rebase or rename).

## Purpose

The original Phase C.1 brief assumed the MCP server uses a static `MCP_BEARER_TOKEN` and tasked CC with building OAuth 2.1 + PKCE + DCR from scratch. Task 0 server-side discovery empirically established that:

- OAuth 2.1 + PKCE + DCR are already live via FastMCP 3.3.1's `OAuthProxy`
- GitHub is the upstream IdP; the `MCP_ALLOWED_GITHUB_USERS` allowlist controls access
- All four metadata + flow endpoints (PRM, AS metadata, `/authorize`, `/register`) respond correctly
- The static bearer token is dead code

The **stated user-visible problem** was: *"Every Railway deploy invalidates the bearer token Anthropic's client side is holding, requiring Nick to manually restart Claude Desktop to recover."*

Phase C.1-rev1 narrows scope to **diagnose and fix that reliability symptom**, without rebuilding the OAuth surface that already works.

**Explicit caveat raised by Nick on 2026-05-23:** The 2026-05-22 (Phase A deploy) and 2026-05-23 (Task 0 diagnosis) symptom observations may be **different bugs with different root causes**. The CC findings hypothesize an in-memory DCR client persistence loss; this is unverified. Phase C.1-rev1 makes client-side reproducer work the gating Task 1 — no code changes until root cause is empirically confirmed.

## Pre-flight

1. `cd /d C:\trading-hub`
2. Confirm on branch `phase-c.1-oauth` at `a6e2f09` or later: `git status && git log --oneline -2`
3. This brief lives at `docs/codex-briefs/phase-c.1-rev1-dcr-persistence-2026-05-23.md` — read in full before starting Task 1.
4. Read `docs/codex-briefs/phase-c.1-task0-findings-2026-05-23.md` — empirical findings on current OAuth state. Sections 4 ("real problem (probable diagnosis)") and 5 (client-side discovery not yet done) are the relevant context.
5. Read `backend/hub_mcp/auth.py`, `backend/hub_mcp/server.py`, `backend/hub_mcp/router.py` if not already in working context.
6. Confirm `MCP_ALLOWED_GITHUB_USERS`, `GITHUB_OAUTH_CLIENT_ID`, `GITHUB_OAUTH_CLIENT_SECRET` are set in Railway env. Do NOT print, log, or commit values.

## Tasks

### Task 1 — Client-side discovery + root cause confirmation (GATING)

**This task is the gate.** No code changes happen until Task 1 produces an empirically-confirmed root cause for the deploy-invalidates-MCP symptom. Likely the work involves 1-3 reproducer attempts coordinated with Nick.

CC sets up the diagnostic plan; Nick drives the client side. CC observes server-side logs + state during the reproducer.

**Phase 1.A — Establish baseline (10-15 min)**

1. Nick clears Claude Desktop's existing MCP connection state (Settings → Connectors → remove the Pandora connector → re-add). This forces a fresh OAuth handshake.
2. CC monitors Railway logs in real-time during the handshake (`railway logs --tail | grep -iE "oauth|register|authorize|token|callback"`).
3. CC captures:
   - The exact sequence of endpoint hits Claude Desktop makes (`/authorize`, `/register`, `/token`, `/callback`)
   - Whether DCR is triggered, and the resulting `client_id`
   - Whether GitHub redirects fire correctly
   - Whether the consent screen renders correctly (Nick describes / screenshots)
4. Nick verifies an MCP tool call works (e.g., `mcp_ping` via Claude Desktop). CC confirms the corresponding log entry.

**Phase 1.B — Deploy reproducer (15-30 min)**

5. CC triggers a trivial no-op Railway redeploy (e.g., empty commit on `phase-c.1-oauth` pushed and Railway auto-deploys, OR Nick triggers a manual redeploy from the Railway dashboard). The empty commit doesn't merge to main — it just exercises the deploy cycle.
6. Wait for Railway to settle (`railway deployment list` shows SUCCESS).
7. Nick attempts another MCP tool call from Claude Desktop without manually doing anything.
8. **Observation point — three possible outcomes:**
   - **(a) Tool call succeeds silently.** The problem is not reproducing in this attempt. Could be intermittent; try one more cycle or escalate to a deploy that touches Python code (forces full process restart).
   - **(b) Tool call fails AND Claude Desktop prompts for reconnect.** Capture the exact error path: which endpoint was hit, what status code came back, what the OAuthProxy log says. This is the reproducer.
   - **(c) Tool call fails but Claude Desktop auto-reconnects transparently.** The reliability problem is partially or fully solved by Anthropic's client logic alone — re-evaluate whether the brief's scope is still needed.

**Phase 1.C — Root cause analysis (CC-driven, 30-60 min)**

9. From Phase 1.B observations, CC writes a root-cause analysis. Hypotheses to test in order of likelihood:
   - **H1 — DCR client registration lost on restart:** Claude Desktop's `client_id` is unknown to the fresh process; refresh-token exchange at `/token` fails with `invalid_client`.
   - **H2 — Refresh token storage lost on restart:** the `client_id` is recognized (because Anthropic registered it durably or because the brief's H1 is wrong), but the refresh-token-to-access-token exchange fails because the refresh-token state is gone.
   - **H3 — Authorization code state expired or lost:** less likely (auth codes are short-lived anyway), but worth ruling out.
   - **H4 — Token verifier cache flush + slow GitHub round-trip:** the first post-restart request blocks long enough that Claude Desktop times out and considers the connection broken.
   - **H5 — Something else entirely:** TLS / cookie / connection-resume issue not in the OAuth layer.

10. CC writes a short root-cause note at `docs/codex-briefs/phase-c.1-rev1-rca-2026-05-23.md` (or whatever date applies) documenting which hypothesis the empirical data supports.

**Pause and surface to Nick after Task 1.** Do not proceed to Task 2 until Nick confirms the root cause finding is correct and the implementation plan is appropriate.

### Task 2 — Implementation (CONDITIONAL on Task 1 findings)

Scope determined by Task 1. The most likely shape, given the Task 0 hypothesis, is below. If Task 1 reveals a different root cause, the implementation plan adapts.

**If H1 (DCR client registration lost on restart):**

2.a. Read FastMCP 3.3.1 `OAuthProxy` source to identify the storage backend interface for DCR client registrations.
2.b. Determine whether FastMCP exposes a pluggable storage backend (injectable interface) or whether storage is hardcoded in-memory.
2.c. If pluggable: implement a Postgres-backed storage class implementing the interface. New migration: `oauth_clients` table with at minimum `(client_id PRIMARY KEY, client_metadata JSONB, created_at, last_used_at)`.
2.d. If not pluggable: wrap FastMCP's OAuthProxy with a custom layer that intercepts DCR registration calls and persists to Postgres; on lookup, repopulate the OAuthProxy in-memory dict from Postgres on a cache miss. This is uglier but contained.
2.e. Wire the persistence layer into `build_oauth_provider()` in `backend/hub_mcp/auth.py`.

**If H2 (Refresh token storage lost):**

Same shape as H1 but for refresh tokens. New table: `oauth_refresh_tokens` with `(token_hash UNIQUE, client_id, expires_at, revoked_at, revoked_reason, created_at)`. Refresh tokens stored as hash, not plaintext.

**If H3, H4, H5 or any combination:** scope tbd; surface to Nick before implementing.

In all cases:
- Do NOT modify the upstream GitHub OAuth flow or the allowlist verifier
- Do NOT issue our own JWTs
- Do NOT replace OAuthProxy
- Persistence happens BENEATH OAuthProxy, not as a replacement

### Task 3 — DCR rate-limit verification + hardening

Independent of Task 1 findings:

3.a. Confirm current `RateLimitMiddleware` (`router.py:91`) behavior for anonymous requests to `/mcp/v1/register`. Per `router.py:113`, anonymous requests get keyed off the caller IP — but the rate-limit quota and refill schedule may not match the 5/IP/hour ceiling the original brief specified.
3.b. Inspect `backend/hub_mcp/rate_limit.py` (`limiter.check()` semantics).
3.c. If a DCR-specific rate limit is not in place, add one. Redis-backed counter, sliding 1-hour window, 5 registrations per IP, 429 on exceed. Audit-log violations.

### Task 4 — Audit logging gaps

Per the original brief's Task 11, with adjustments for the FastMCP-as-auth-owner architecture:

4.a. **DCR registration:** every `POST /mcp/v1/register` success logs `client_id`, `client_name`, `redirect_uris`, `created_ip`, `timestamp` to existing audit infrastructure (`pandoras_box.mcp.audit.log_call` or equivalent).
4.b. **Token issuance:** every `POST /mcp/v1/token` success logs `client_id`, `grant_type`, `ip`, `timestamp`. May require subclassing OAuthProxy or wrapping its token endpoint at the FastAPI mount level.
4.c. **Token revocation:** if `/mcp/v1/revoke` is live (verify in Task 1.A logs), log `client_id`, `revoked_token_hash_truncated`, `reason`, `timestamp`.
4.d. **Failed authentications:** the 401 path already logs via AuditMiddleware (`router.py:177`); confirm the log entry contains enough context (token hash truncated, source IP). If not, augment.

If wrapping OAuthProxy is required, this task can be deferred to a follow-up build to avoid scope creep. Nick's call after seeing the FastMCP source for available hooks.

### Task 5 — Documentation

5.a. **Extend** `docs/operations/mcp-token-rotation.md` (do NOT deprecate). Add sections:
   - "DCR client lifecycle" (how clients register, how registrations are persisted, how to revoke a client manually if needed)
   - "Persistence backend" (what's in Postgres, what's still in-memory, what survives restart)
   - "Audit log entries" (where the new log entries live, what fields they contain)
5.b. If Task 2 changes any env-var contract (e.g., a new flag for Postgres persistence), document at the top of the file under "Required environment variables."

### Task 6 — Smoke tests

6.a. Re-run Task 1.A baseline handshake — confirm it still works post-Task-2 change.
6.b. Re-run Task 1.B deploy reproducer — **this is the canonical fix verification.** Trigger Railway redeploy, attempt MCP tool call from Claude Desktop, confirm no reconnect prompt. Repeat 3× to rule out intermittent success.
6.c. Wait 15+ min after last Railway deploy, attempt MCP tool call, confirm transparent token refresh.
6.d. DCR rate-limit verification (if Task 3 added one): 6 rapid `/register` calls from one IP, confirm 6th gets 429.
6.e. Audit log spot-check: verify Task 4's new log lines appear with expected fields.
6.f. **Olympus committee pass on SPY** (per original brief Task 12 #6): one full committee round-trip via OAuth-authenticated MCP. Confirms no regression in committee data pipeline.

### Task 7 — Closure note

Author `docs/strategy-reviews/phase-c.1-rev1-closure-note-YYYY-MM-DD.md`. Cover:
- Task 1 RCA finding (which hypothesis was confirmed)
- Task 2 implementation decisions
- Task 3 rate-limit state (added new? confirmed existing?)
- Task 4 audit-logging state (full coverage? deferred items?)
- All Task 6 smoke-test results
- Coexistence: there is no static bearer to coexist with (already dead code); this section in the original brief is dropped
- Anything deferred or surprises encountered
- Tier 2 follow-ups: any audit-logging gaps Task 4 deferred, any rate-limit hardening Task 3 deferred

## Output spec

- Modified: `backend/hub_mcp/auth.py` (if Task 2 adds persistence wiring)
- Modified: `backend/hub_mcp/rate_limit.py` (if Task 3 adds DCR-specific limit)
- Possibly modified: `backend/hub_mcp/router.py` (if Task 4 adds new audit hooks at the mount layer)
- Possibly modified: `backend/hub_mcp/audit.py` (if Task 4 adds new log helpers)
- Possibly new: `backend/hub_mcp/oauth_storage.py` or `backend/hub_mcp/dcr_storage.py` (if Task 2 needs a new module)
- New: Postgres migration script for `oauth_clients` and/or `oauth_refresh_tokens` (per Task 2 findings)
- New: `docs/codex-briefs/phase-c.1-rev1-rca-2026-05-23.md` (Task 1 root cause analysis)
- Modified: `docs/operations/mcp-token-rotation.md` (Task 5 extension, NOT deprecated)
- New: `docs/strategy-reviews/phase-c.1-rev1-closure-note-YYYY-MM-DD.md`

Commit messages by task group:
- RCA: `docs(c.1-rev1): Task 1 root cause analysis from client-side reproducer`
- Implementation: `feat(hub_mcp): Phase C.1-rev1 — <H1/H2/...> persistence fix`
- Rate-limit hardening (if applicable): `fix(hub_mcp): Phase C.1-rev1 — DCR per-IP rate limit`
- Audit logging: `feat(hub_mcp): Phase C.1-rev1 — OAuth event audit logging`
- Documentation: `docs(operations): Phase C.1-rev1 — extend mcp-token-rotation for DCR lifecycle`
- Closure: `docs(strategy-reviews): Phase C.1-rev1 closure note`

## Gates / what NOT to do

- Do NOT merge `phase-c.1-oauth` branch to `main` until Nick gives explicit greenlight.
- Do NOT proceed to Task 2 without an empirically-confirmed root cause from Task 1, surfaced to and approved by Nick.
- Do NOT replace FastMCP's OAuthProxy or the GitHub upstream. The OAuth surface is working; we are adding persistence beneath it, nothing more.
- Do NOT remove the `MCP_BEARER_TOKEN` env var. It's already dead code; cleanup is a separate Tier 3 housekeeping item.
- Do NOT touch `unified_positions`, `signal_outcomes`, `signals`, or any canonical strategy data table. New tables are OAuth-specific.
- Do NOT modify Phase A.3's `sector_constituent_refresh.py`, `sector_cache.py`, or `frontend/app.js` — entirely different code paths.
- Do NOT introduce new credentials. The current GitHub OAuth App credentials are sufficient.
- Do NOT print, log, or commit any token values (GitHub access tokens, refresh tokens, client secrets, signing keys if any).
- Do NOT issue our own JWTs. We don't sign tokens; we verify GitHub-issued ones.
- Do NOT bundle Phase C.2/C.3/C.4 (committee enrichment expansion) into this brief.
- Do NOT attempt to fix the trailing-slash 307-to-HTTP redirect on the PRM endpoint in this build. That's a Tier 3 follow-up; canonical URL works.

## Olympus Impact

Phase C.1-rev1 introduces no behavior change in any Olympus skill during the build. The committee reads via hub MCP tools (`hub_get_quote`, `hub_get_bias_composite`, etc.), and Phase C.1-rev1 modifies storage-and-logging layers BENEATH the tools — not the tools themselves.

**Indirect benefit:** post-deploy, Railway restarts no longer break Claude Desktop's MCP connection — Phase C.2/C.3/C.4 deploys won't break Olympus committee data access.

**Required post-build re-test (Task 6.f):** full Olympus committee pass on SPY during market hours via OAuth-authenticated MCP. Verify all 9 hub tools return data correctly. Canonical sign-off that Phase C.1-rev1 doesn't break the existing committee data pipeline.

## Done definition

- Task 1 root-cause analysis committed and approved by Nick.
- Task 2 implementation shipped on `phase-c.1-oauth` branch.
- Task 3 (rate-limit verification) closed — either added or confirmed-existing.
- Task 4 (audit logging) closed — coverage assessed, additions made or deferral documented.
- Task 5 (`mcp-token-rotation.md` extension) committed.
- All Task 6 smoke checks pass; deploy-reproducer empirically confirms the reliability fix works (3× clean cycles).
- Closure note authored.
- Branch ready to merge to `main` pending Nick greenlight.
- Stop and notify Nick when complete.

## Notes for the implementer

- **Friday vs Saturday symptom may be different bugs.** The Phase A.3 deploy on Friday correlated with Claude Desktop losing MCP access. The Task 0 hypothesis on Saturday was a logical-derivation from code reading, NOT from observing the Friday failure. Task 1's reproducer is the empirical bridge — confirm the same failure mode reproduces on a fresh deploy attempt, observe the actual server-side log signature, and only then commit to a root cause.
- Anthropic-side OAuth client behavior is part of the validation. If the reproducer reveals Claude Desktop doing something unexpected (e.g., not retrying token refresh, not following 307s, dropping the `client_id` from session state), that's a finding to flag and may shift the fix from server-side persistence to a different remedy entirely.
- The FastMCP 3.3.1 source is a library dependency, not in this repo. CC may need to read installed package files at `<venv>/lib/python3.*/site-packages/fastmcp/server/auth/oauth_proxy.py` or fetch via pip download. If FastMCP has been updated upstream with persistence fixes, that's a finding to flag — the right fix may be a version bump.
- Effort estimate per Task 0 findings: 1-2 days at most. The implementation should be small. If during Task 2 the scope balloons beyond 1 day of work, pause and surface — that's a sign the fix is bigger than the diagnosis warrants.
- Olympus full committee smoke (Task 6.f) requires market hours. If the implementation lands after-hours on a weekend, defer the committee smoke to next market open and ship the closure note with that one item marked "pending Monday."
