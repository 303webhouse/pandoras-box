# W1-4 — AEGIS Coordinated Pass — COMPLETION

**Date:** 2026-07-24 · **Lane:** CC in `th-security` worktree · **Branch:** `aegis-coordinated-pass` → merged to `main` (fast-forward)
**Grade gate:** Fable G0 = PASS; veto lifts on R-PG verified + clamp + N-FILE + untrack + RULES.
**Prime directive held:** no secret value appears in this doc, any commit, log, or transcript — env-var names, file paths, counts, line numbers, and pass/fail only.

> **Timestamps** are UTC with Mountain (MDT = UTC−6) in parens, derived from tool timestamps + backend uptime (not guessed).

---

## Outcome summary

| Leg | Result |
|---|---|
| **R-PG** — Postgres password rotation | ✅ **ROTATED + VERIFIED** (old string REJECTED, new ACCEPTED, hub live) |
| **Clamp** — Pythia v2.4 A-7 `loBinIdx` | ✅ **DEPLOYED** (repo `b2e9978`) + **applied live** by Nick; revived a crashing alert fleet |
| **N-FILE** — neutralize `reconcile_rh.py` | ✅ **NEUTRALIZED** in HEAD (`ff1c94c`); credential-with-`@` 1→0 |
| **Untrack** — `.claude/settings.local.json` | ✅ **UNTRACKED + gitignored** (`1963c50`) |
| **RULES** — bulk-checkpoint ban deltas | ✅ **ADDED** (`b5c96b3`) — only the missing deltas vs `c3c35ab` |
| **R-PY** — webhook secret rotation | ⛔ **WAIVED by principal** (Fable ruling) → next-week pile with REDIS-ROTATE |
| **S6** — webhook HMAC-enforcement proof | ✅ garbage/absent → **401** on the live path |
| **S7** — SOXS convergence rider | ⏸ **DEFERRED** — market closed (RTH-only); Monday |
| **R6 / A.5** — VPS pivot-collector + DB-consumer confirm | ⏸ **DEFERRED** — SSH bridge down all session; on-box grep on recovery |

---

## P0.1 — Postgres-credential consumer map (final, with A.4 correction)

Backend sources creds as **discrete** `DB_HOST/PORT/NAME/USER/DB_PASSWORD` (`backend/database/postgres_client.py:85-89`) via `get_postgres_client()` — **not** a single `DATABASE_URL`.

| # | Consumer | Form | Update method (as executed) |
|---|----------|------|-----------------------------|
| 1 | Railway **Postgres** service (authoritative) | the password | `ALTER USER postgres WITH PASSWORD` + `POSTGRES_PASSWORD` var |
| 2 | Railway **backend** service | `DB_PASSWORD` — **LITERAL** *(A.4: not the `${{Postgres.*}}` reference the prior assumed)* | Nick edited the literal → redeploy; startup clean |
| 3 | Local `.mcp.json` (`C:\trading-hub`) | 1 literal `postgres://` (postgres MCP) | edited password segment + MCP restart |
| 4 | Claude Desktop config | 0 postgres / 0 literal | ❌ not a consumer — no action |
| 5 | Committed scripts w/ literal DSN | only `reconcile_rh.py` (see R2 refinement) | neutralized (`ff1c94c`) |
| 6 | VPS OpenClaw bridge | ⏸ pending on-box grep | **A.5 conditionally dropped** — no DB creds expected; confirm on SSH recovery |

**A.4 doc note:** the `ALTER` ran twice — first attempt hand-typed with a suspected typo (brief crash-loop), resolved via local-socket `psql` + clean re-paste. Live value is the clean re-paste; old value held for rollback through S3.

## P0.2 — Webhook consumer inventory + **endpoint reconciliation** (Fable-requested finding)

The live "Pythia Market Profile v2.4" alerts POST to **`/webhook/tradingview`** (`webhook_router`, `prefix="/webhook"`). That handler (`backend/webhooks/tradingview.py:240-246`) **internally forwards** any payload identifying as pythia (`source=="pythia"` / `"pythia" in strategy` / `alert_type` startswith `pythia_`) to `pythia_webhook` (`backend/webhooks/pythia_events.py`), which validates against **`PYTHIA_WEBHOOK_SECRET`** fail-closed (`hmac.compare_digest`; mismatch→401, unset→503).

- **Reconciliation:** P0.2 (secret var = `PYTHIA_WEBHOOK_SECRET`) and Fable (URL = `/webhook/tradingview`) were both correct at different layers. The generic fall-through path validates `TRADINGVIEW_WEBHOOK_SECRET` in **observe mode** (`_tv_observe()` true unless `WEBHOOK_TV_ENFORCE=1`) — tag-only, consistent with the L1 shadow posture.
- `mp_levels.py` (`/webhook/mp_levels`) is a separate endpoint **not** hit by these alerts — reuses `PYTHIA_WEBHOOK_SECRET`.
- **Live Pine hardcode finding:** Nick's line-384 eyeball found a **live 32-char secret embedded in the script body** (not the redacted 21-char placeholder in the stale repo copy). This is the webhook-side twin of the DB-credential anti-pattern. → **Ratified PINE-HYGIENE (post-vacation):** migrate to an empty-default `input.string`, sync the repo Pine, one re-arm cycle. Not fixed this pass (R-PY waived).

## P0.3 — Sweep (66fb98c inventory; **counts only, matches never opened**)

85 files, all present, 0 deleted-since.

**`postgres://` — genuine hardcoded credential in exactly ONE file (R2 refinement):**
| File | Verdict |
|---|---|
| `scripts/reconcile_rh.py` | **real hardcoded DSN** (`DB_URL` const) → neutralized |
| `scripts/fix_ibit_call_roundtrip.py` | **false positive** — `.startswith(("postgres://","postgresql://"))` scheme validator; already reads DSN from `.mcp.json` |
| `scripts/reconcile_window_2026-06-17.py` | **false positive** — same `conn_url()`-from-`.mcp.json` pattern |

Verified value-safe: DSN-with-`@` count = 1 (reconcile_rh) / 0 / 0. The two siblings needed no change (no pointless churn).

**Second-tier (R3 discriminator — `password\s*=\s*['"]` literal-assignment count):**
| File | literal-assign | Disposition |
|---|---|---|
| `scripts/migrate_hermes.py` | **1** | ⚠️ **ESCALATED** — a quoted-literal password assignment (not a `postgres://` DSN). Counts only; not opened. Open finding for ruling/follow-up. |
| `migrate_close_handler.py`, `test_close_double_tap.py`, `test_prod_close_double_tap.py` | 0 | benign-accepted (env-refs / kwarg names) |

Remaining pattern hits (`secret`/`token`/`BEARER`/`API_KEY`/`X-API-Key`) accepted benign-class per R3 (env-refs, header names, `.env.example`, doc mentions).

---

## Verification results (pass/fail — values never displayed)

### R-PG (S3)
| Check | Method | Result |
|---|---|---|
| S3(a) OLD committed DSN | extracted from git history (`9dcb463:scripts/reconcile_rh.py`) → piped to `scripts/aegis_conn_test.py`, never displayed | **REJECTED (auth-failed)** — kill-proof |
| S3(b) NEW credential | via updated `.mcp.json`, piped to helper | **ACCEPTED** |
| S3(c) hub live | `mcp_ping` + `hub_get_portfolio_balances` | connected v2.0; DB read path healthy |
| S3(d) VPS bridge write | — | deferred (SSH down) |

`auth-failed` (not `unreachable`) is the clean isolation: same reachable host, password specifically rejected → the string on origin is now worthless.

### S5 deploy (four-step)
1. `main` fast-forwarded `669013d..b5c96b3`.
2. Redeploy settled healthy — background `/health` poll `oks=8 fails=0 last=200` over ~2 min (no crash-loop).
3. `/health` = 200, `postgres: connected`, `redis: ok`.
4. Hub `mcp_ping` uptime reset **1498s → 334s** = new deploy live. Suite byte-identical known-red (0 backend files changed; nothing imports the two changed standalone scripts; both compile at HEAD).

### S6 webhook enforcement (retargeted `/webhook/tradingview`, HMAC-proof only per waiver)
| Test | Result |
|---|---|
| pythia-routed payload + **garbage** secret | **HTTP 401** `invalid webhook secret` |
| pythia-routed payload + **absent** secret | **HTTP 401** `invalid webhook secret` |
| pythia-routed payload + **live** secret | Nick's local curl template (below) / Monday real-alert round-trip — confirmatory, non-blocking |

401 (not 503) proves enforcement is ON **and** the secret is configured. Negatives rejected before any DB write — no side effect / no spurious signal injected.

---

## Rotation timestamps (approx, UTC / MDT)
- **R-PG rotation live** (backend redeploy w/ new `DB_PASSWORD`): ~**19:42 UTC (13:42 MDT)** (from backend uptime at S3).
- **S3 verification:** ~**20:06 UTC (14:06 MDT)**.
- **S5 deploy to `main`:** push ~**21:04 UTC (15:04 MDT)**; new deploy live ~21:04, settled ~21:07.
- **S6 negatives:** ~**21:10 UTC (15:10 MDT)**.
- **Runbook B (Nick):** 4 alerts (SPY/QQQ/IWM/Prey List ~230 symbols) deleted+recreated on the clamped script, all ACTIVE; Prey List warmup 221→27. Pre-clamp: SPY/QQQ calc-error, IWM active-but-unclamped, Prey List 221 dead → **data-dependent Pine crash was progressively killing the fleet; the A-7 clamp revived it.** Silent-strategy implications flagged for Monday triage.

## Audit-log note (security-relevant-action logging)
Rotation events recorded as the audit trail: (a) this completion doc; (b) the pathspec-scoped commits `ff1c94c` / `1963c50` / `b2e9978` / `b5c96b3`; (c) the **pre-production override-log CLOSED entry** at `skills/aegis/references/pre-production-override-log.md` (2026-07-24), which closes the 2026-07-16 `reconcile_rh.py` flag (raised 07-16 → committed via `66fb98c` 07-19 → quarantined 07-23 → resolved 07-24). History rewrite ruled OUT by design.

## R6 rider — VPS pivot-collector service state
**DEFERRED.** The `ssh-vps` bridge timed out on handshake for the entire session (7+ attempts, concurrent + single). Could not read `pivot-collector` state or `cron_runner.py` jobs (credit_spreads / market_breadth / sector_rotation). **Nick's disable ruling pending** the on-box read. Indirect box-up signal: Postgres shows `flow_events` written ~9 min before check + bias/signals current; pollers live on the VPS `openclaw` service, so the box is *likely up with only SSH/port-22 unreachable* — unconfirmed. **Separate flag (Fable R5):** if the box itself is down, the 3-min committee bridge + pre-market briefing are down with it — verify on recovery, report as its own finding.

## S7 — SOXS convergence rider
**DEFERRED (market closed).** RTH-only; the two-pull ≥5-min PnL-recompute test can't distinguish freeze-vs-stale with prices frozen. Run Monday RTH.

## Finding #1 — rotation doc was stale
`docs/operations/mcp-token-rotation.md` covered only the MCP GitHub OAuth secret. **Extended this pass** with the R-PG (Postgres) procedure as executed + an R-PY section (noting the waiver + PINE-HYGIENE follow-up).

---

## Open follow-ups (next-week / post-vacation pile)
1. **R-PY** webhook-secret rotation (waived) + **REDIS-ROTATE**.
2. **PINE-HYGIENE** (ratified): live Pine `input.string` migration + repo Pine sync + re-arm.
3. **R6 / A.5** on-box grep when SSH recovers (VPS DB-consumer confirm + pivot-collector disable ruling + box-up).
4. **S7** SOXS convergence, Monday RTH.
5. **R3 escalation:** `scripts/migrate_hermes.py` quoted-literal password assignment — ruling/neutralization.
6. **S6 positive** (live secret → accepted) via Monday real-alert round-trip.
7. **Endpoint reconciliation** already documented; confirm no live alert relies on the observe-mode generic path.

## Handback
Branch `aegis-coordinated-pass` fast-forwarded to `main`. SHAs: `9dcb463` (brief) · `ff1c94c` (N-FILE) · `1963c50` (untrack) · `b2e9978` (clamp) · `b5c96b3` (RULES) · **Phase-2 evidence commit: see final push.**
