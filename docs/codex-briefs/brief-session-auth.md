# Session Auth — Durable Fix for Public PIVOT_API_KEY

**Type:** Design brief (feeds the security review; precedes the exact find/replace brief for CC)
**Created:** 2026-06-11
**Status:** Staged. Deeper security review scheduled with Fable before 2026-06-22 — that review should also cover the open GET routes and the FOOTPRINT pre-auth bypass listed below.

---

## State as of 2026-06-11 (read first — app.js assumptions are stale)

- `PIVOT_API_KEY` was **rotated** across all 3 stores: Railway env, `/etc/openclaw/openclaw.env`, `/opt/pivot/.env`. Old key is **dead** (it was public in git history since the initial commit).
- `frontend/app.js:11` `const API_KEY` now holds the **dead** key. Every call through `authHeaders()` (23 sites) will 401. Read-only views still work — GET routes are unauthenticated; only POST/mutations are gated by `require_api_key`.
- Repo is now **private**.
- `GITHUB_PAT` was also rotated (`/etc/openclaw/openclaw.env`); VPS docs-sync restored. Independent of this build.
- Verified live: `require_api_key` still enforces (401 with no auth) and accepts the new key via X-API-Key **and** Bearer. The 4 VPS systemd services (openclaw, hermes-trigger, pivot-bot, pivot-collector) restarted on the new key and are healthy.

## Objective

Remove the secret from the browser entirely. Dashboard authenticates via an HttpOnly session cookie; server-to-server callers (VPS) keep using X-API-Key/Bearer unchanged.

## Build scope

1. **Central change — `backend/utils/pivot_auth.py::require_api_key`:** accept **either** a valid session cookie **or** the existing X-API-Key/Bearer header. All ~95 protected routes inject this one dependency, so they inherit session-acceptance with **zero per-route edits**. This is the entire backend surface.
2. **Login/logout endpoints (new):** shared single-user password sets an HttpOnly + Secure + SameSite cookie; logout clears it.
3. **Frontend (`app.js`, 23 sites):** delete `const API_KEY`; `authHeaders()` sends the cookie via `credentials:'include'` instead of the X-API-Key header; add a login screen + redirect-to-login on 401.
4. **Tests (`backend/tests/test_auth.py`):** keep the invariant (protected routes 401 without auth); add session-accept cases; confirm machine header-auth still passes.

## Open decisions — resolve in the security review BEFORE the find/replace brief

Do not let CC pick these silently.

- **Session model:** signed stateless cookie (recommend — no new infra) vs server-side Redis session (if revocation wanted).
- **Cookie SameSite:** Lax recommended (Strict can break dashboard navigations).
- **CSRF:** SameSite + require a custom header (e.g. `X-Requested-With`) on mutations — cheap; custom headers already in use.
- **Login password storage:** new env secret; must NOT land in the repo or `app.js`.
- **Session lifetime / renewal.**

## Constraints

- **Do not** touch the webhook body-secret path (`TRADINGVIEW_WEBHOOK_SECRET`) — TV/signal ingestion is separate; leave it alone.
- Machine callers (VPS Bearer/X-API-Key) must keep working — dual-accept preserves them; verify no regression.
- Deploy outside market hours (7:30 AM–2:00 PM MT).

## Related findings for the same security review

- Several GET routes answer with **no auth** (`/api/committee/queue`, `/api/trade-ideas`, others). Some may be intentional (the VPS polls the queue) — needs a deliberate per-route decision.
- FOOTPRINT pre-auth router bypass (already tracked in `post-b4-webhook-hardening-backlog.md`) — fold into the global endpoint-hardening pass.
- Old `PIVOT_API_KEY` is still in git history but **dead** (rotated) — `filter-repo` purge is optional cleanup, not a security need.

---

*This is the design brief. The exact find/replace brief for CC comes after the open decisions are locked in the security review.*
