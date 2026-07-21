# HUB-MCP-CRYPTO-STATE — completion report (Path B)

**Brief:** `docs/codex-briefs/2026-07-21-hub-mcp-crypto-state-micro-brief.md`
**Commit:** `9038164`. Deployed 2026-07-21, Railway SUCCESS, SHA-verified.
**Path:** B (DB/cache-backed, zero vendor calls) — Nick's ruling after the Phase 0 ATLAS gate.
**Result:** 23rd MCP tool shipped + deploy-verified. Phase 3 handback (skills + connector) is the coordination lane's / Nick's, not CC's.

---

## What shipped

`hub_get_crypto_state(symbol)` — a read-only MCP tool exposing the crypto blocks
the committee could not previously reach: funding, open interest, basis,
liquidations, regime, tape-health (spot/perp CVD), and session. Two crypto
surfaces (quote + market profile) become nine.

**Zero vendor calls.** It reads only already-persisted state and never touches
Coinalyze/Binance/OKX — the `hub_get_board_state` contract:

| Block | Source | Vintage |
|---|---|---|
| funding / open_interest / basis / liquidations | `crypto_cycle_log.cells` (perp_funding / open_interest / quarterly_basis / liquidations) | hourly snapshot |
| regime | `crypto_regime_log` (`{base}-USD` keyed, per D2) | ~hourly |
| tape_health (+ spot/perp CVD) | `crypto_tape_health_log` (bare-symbol keyed) | ~10 min |
| session | `utils.crypto_sessions` (pure clock/config compute) | live |
| atr | — | **omitted** (live-only; see below) |

Files: `services/read_only/crypto_state.py` (service), `hub_mcp/tools/crypto_state.py`
(tool), `decorators.py` whitelist + `tools/__init__.py` import +
`test_decorators.py` deliberate-edit guard, `tests/test_hub_mcp_crypto_state.py`
(18 tests).

## The three non-negotiables, enforced

1. **No fail-open defaults.** Health is derived FAIL-CLOSED in `_classify`: a
   missing/absent `state` resolves to **degraded**, never `ok`. A cell whose
   `state` is anything other than the literal `"LIVE"` is degraded. This is the
   exact class of bug the live endpoint still carries on OI/basis
   (`.get("health_status", "LIVE")`); the tool does not repeat it. Guarded by
   `test_read_cycle_block_with_missing_state_key_is_degraded` — a cell with no
   `state` key renders degraded, proven.
2. **Per-block health with worst-of-blocks top-level rollup**
   (`hub_get_stable_rates_fx` precedent, `worst_status`). A healthy funding read
   still reports degraded if regime or tape is down.
3. **Honest per-symbol unavailable.** Missing row/cell → `unavailable` with
   `value=null`, never a fabricated zero. **ATR is an explicit omission**
   (`available=false` + reason), excluded from the health rollup — it is a
   live-bars-only field with no persisted source, so serving it would require the
   vendor call Path B exists to avoid. Never fabricated.

Scores are not exposed (no composite score, no −45..+35 filter value); `regime`
and `cta_zone` are labeled engine classifications, not scores.

## Verification

**Deploy (4-step):**
1. Railway **SUCCESS**, deploy of `9038164`.
2. SHA attribution: deploy commit `9038164` matches the pushed commit.
3. Empirical side-effect: `mcp_describe_tools` returns **`tool_count: 23`** with
   `hub_get_crypto_state` present and its full description rendered; `mcp_ping` ok
   (uptime 53s, fresh from deploy). Health 200 after a ~50s container cycle.
4. Not silent — deploy completed in ~45s.

**Tests:** `tests/` = **18 failed / 510 passed / 1 skipped / 200 errors** —
byte-identical known-red, passed +18 (the new tests). `hub_mcp/tests/` = 6
pre-existing environmental failures (envelope/hermes/trade_ideas, confirmed
unchanged by stashing this change) + the `describe` `tool_count==23` and
`test_decorators` whitelist assertions both pass.

**Live coverage matrix — INPUTS verified, honest caveat on method.** The
callable interface for `hub_get_crypto_state` does not appear in the connector's
tool manifest until Nick's Phase 3 toggle (the connector caches the callable list
separately from the live `describe` registry — same as the theme-members case).
So I did **not** invoke the tool end-to-end through the connector; I verified its
**live inputs** instead — querying the exact `crypto_cycle_log` / `crypto_regime_log`
/ `crypto_tape_health_log` rows the deployed tool reads and applying the tool's
own thresholds. Right now (post-deploy, writers refreshed ~2 min prior) the tool
would return:

| Symbol | funding | regime | tape | top-level |
|---|---|---|---|---|
| BTC/ETH/SOL/HYPE/ZEC | ok | ok | ok | **ok** |
| FARTCOIN | stale (cycle row ~3.2h) | ok | ok | **stale** |

FARTCOIN's stale-cycle-but-fresh-regime/tape is a real per-block divergence and
the worst-status rollup handles it correctly (top-level = stale). Honest
`unavailable` would trigger only on an absent row/cell (none currently). The
tool's logic is unit-proven against the real cell shapes; the end-to-end live
call is the coordination lane's post-toggle step.

## Operational note (not a blocker, flag for Fable)

The crypto cycle/regime/tape writers are **in-process asyncio loops** that
restart on every backend deploy. Both of this session's deploys left a window
where those logs read stale until the loops next fired. Observed directly: pre-
deploy the endpoint reported regime+tape degraded on all six symbols; ~2 min
after this deploy all six wrote fresh rows. Two consequences worth a look
outside this brief: (a) the "regime+tape degraded on all 6" I flagged in the
HUB-MCP-CRYPTO-STATE Phase 0 findings was deploy-restart-induced, not a standing
writer failure; (b) **FARTCOIN's cycle write specifically lags** (~3.2h stale
while the others refreshed in ~2 min) — a real per-symbol cadence gap. Neither is
in scope here; both are honestly surfaced by the tool rather than hidden.

Also still live and unaddressed (from Phase 0): the endpoint's OI/basis fail-open
`.get("health_status", "LIVE")` defaults. This tool does not depend on them
(it reads the cycle log, not the endpoint), but they remain a latent repeat of
the db5e398 class of bug on the live endpoint — noted for a future micro-brief.

## Phase 3 handback (CC stops here)

| Step | Owner | Status |
|---|---|---|
| Tool ships + deploy-verified | CC | **DONE (`9038164`)** |
| Olympus skill files reference `hub_get_crypto_state` (PYTHIA, THALES, DAEDALUS min.; likely TORO/URSA/PIVOT) | coordination lane | pending |
| Pandora connector toggled (refreshes the callable manifest) | **Nick** | pending |
| One full crypto committee pass on BTC/ETH post-toggle — confirm each agent reaches the new blocks, degraded sub-blocks are surfaced not skipped, and no agent asserts a value for an `unavailable`/omitted block (TORO-fabrication watch; ATR is the obvious fabrication target) | coordination lane | pending |

CC did **not** edit skill files, per the brief.

## Out of scope (untouched)

- Cycle Extremes dial (S-5) — `/api/crypto/cycle-extremes` exists but re-invokes
  the vendor-calling engine; left out, noted as a seam.
- D1.4 suppression contract — untouched.
- `Funding_Rate_Fade` zero-signal — W2-4 triage.
