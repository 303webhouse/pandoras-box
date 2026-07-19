# HANDOFF — Monday 2026-07-13: micro-brief execution + THE FLIP (fresh chat takes over)
Written 2026-07-10 night by Fable (coordination lane). This chat is review/verification/coordination. Nick's prefs apply: chunked, decisive, lay-terms, one clear next action per turn.

## Read-first
1. `docs/workstreams.md` — live lane ledger. Pre-flight checks: (a) coordination lane owes its 7/10 section — fold into Monday's step-0 commit or write via DC; (b) verify CC's 7/10 entries cover LAZR / ACK rule / XLF null-strike / test failures — `e9ab1cf`'s message headlines only the watchdog items; if the rest didn't land, fold them into step-0 too.
2. This file.
3. `docs/codex-briefs/2026-07-13-l0-transition-and-watchdog-micro-brief.md` — ATLAS-approved (gate satisfied in-file, amendments A1–A7), ready for CC.
4. Prior day context if needed: `docs/handoff-flip-day-2026-07-10.md`.

## State of the world (as of Fri 7/10 night)
- **Artemis suppressed at the chokepoint** (788d466, verified independently). The post-push sweep found a 3-cause leak: 1,439 historical rows (tag-trust transition window), board_state kairos sub-query never L0-wired, legacy trio unfiltered (5 SQL statements incl. 2 fallbacks). All fixed in Monday's micro-brief. Part (b) "tagged rows still accruing" = PENDING-MONDAY (no fresh Artemis signals until RTH).
- **Watchdog live, day-1 verdict:** PASS within its designed window, but the window assumption was FALSIFIED — 7/10 crossed 17K after the close (final 17,394; last tick 15,870 @ 19:58 UTC). The 24/7 snapshot caught what live checks missed. Fix (delete weekday+RTH gate) is micro-brief item 4. **Burn trend: 16,626 → 17,394, margin to 18K escalation = 606.** ohlc_bars audit is the pressure valve.
- **MCP connector HEALED.** Root cause: stale client-side OAuth state; server was clean since the fastmcp 3.4.4 pin. Verified live from the desktop app (mcp_ping + hub_get_positions returning the real book). Do NOT disconnect/re-add. Cowork digest back to full; Olympus reads restored; Brief 3 unblocked.
- **LAZR = universe-integrity failure ("dead-but-chatty").** Luminar Ch.11 (12/15/25) → delisted/LAZRQ → liquidation effective ~4/6-7/26, equity cancelled. The 7/8 "resumption" is a dead/recycled symbol resolving to something that isn't Luminar; one corrupted name pinned Robotics to 100.0. **Robotics theme = KNOWN-BAD until the fix brief ships.** Biotech is legit (peaked 92.7, sane internals, Ryan corroborates).
- **Flip gates:** (1) authenticated round-trip ✓ **PASSED Sat 7/11**, Fable-verified at three vantages (v2 write → canonical row `POS_SPY_20260711_164210` → legacy read → v2 close → OPEN book back to exact baseline 18 / $3,620.35; closed row transitioned, not deleted); (2) full live session on /app/v2 — Monday; (3) 6c accepted ✓ 7/10. Pre-flip requirement: micro-brief sweep passed (makes K badges trustworthy). Round-trip flags, non-blocking: close path stamps trade_outcome but NOT closed_at (null on BOTH closed SPY rows — systemic, chase item 8); test row carries a phantom WIN +$654.95 (placeholder $100 entry vs real ~$755 quote) — CC neutralizes it Monday pre-market, BEFORE the Mon 19:30 MT feedback loop.
- **Stable engine closed** (autonomous nightly with provenance). Trading context: standard pre-flight per memory before ANY trading discussion; positions via hub MCP only.

## Standing rules (compressed)
Mockup gate · palette v2 (lime=bullish/vermilion=bearish/teal=attention, no yellow) · provenance not presence · reproducible acceptance evidence (builder never grades own pixels) · UW ~18K internal / 20K plan · labeling contract (as_of, data_age_seconds, anchor, degraded, flatline) · git: pathspec-only (tree is NOISY, 50+ untracked), commitmsg via C:\temp\commitmsg.txt, blackout 07:30–14:00 MT trading days, push windows <07:15 or ≥14:00 · ledger discipline: every lane updates workstreams.md · **ACK RULE (new 7/10): a cross-lane order is not delivered until the receiving session replies with an explicit ACK; coordination tracks unacked orders as open items** · shadow before enforcement · verify-don't-trust: repo/live state overrides memory and handoffs.

## MONDAY SEQUENCE — run top to bottom

**S0 — ✓ DONE Sat 7/11.** Round-trip PASSED, Fable-verified at three vantages (see flip gates in State of the world). Residue handled in S1: CC neutralizes test row `POS_SPY_20260711_164210` per the kickoff rider.

**S1 (pre-market, ~6:00–6:45 MT) — CC kickoff.** Paste to the CC/SIGNALS session:
```
Execute docs/codex-briefs/2026-07-13-l0-transition-and-watchdog-micro-brief.md — ATLAS-approved 2026-07-10 (gate satisfied in-file, amendments A1–A7 incorporated). Pre-flight: git fetch && git status; main must match origin/main at 788d466+. Step 0: pathspec-commit the brief file itself. Commits 2–3 per the brief, ONE push before 07:15 MT, confirm deploy healthy + /mcp/v1/health new SHA. Then backfill DRY-RUN → post FULL output here AND to the coordination chat → WAIT for explicit GO before --execute (amendment A5). Then acceptance sweep items 1–6; items 7–8 close after 20:00 UTC. Reply with an explicit ACK line + ETA before starting (standing rule as of 7/10). RIDER: neutralize round-trip test row POS_SPY_20260711_164210 in unified_positions (carries a phantom WIN +654.95 — placeholder $100 entry vs real quote, from the 7/11 gate test): delete or tag TEST, done BEFORE the Mon 19:30 MT feedback loop. Also ledger the closed_at defect: close path sets status+trade_outcome but leaves closed_at NULL (confirmed on both closed SPY rows) — chase item, fix at the close-handler surface.
```

**S2 — backfill GO gate (this lane's job).** Delegation CONFIRMED by Nick Sat 7/11 ("GO"): the coordination lane issues the --execute GO if and only if dry-run counts are EXACTLY P1=307, P2=1,132, total=1,439 AND the 3 sample rows render correctly AND the A1 pre-image path is reported. Any deviation → Nick decides, no exceptions. This delegates WHO reviews the dry-run, not WHETHER it's reviewed — the A5 gate itself is untouched.

**S3 (pre-open, before 7:25 MT) — round-trip test if S0 didn't happen.** Must complete before the 7:30 open (committee bridge reads positions every 3 min during RTH).

**S4 (RTH) — Nick trades the session on /app/v2 (flip gate 2).** Watch: watchdog's first 24/7 day; burn vs the 606-point escalation margin; sweep results holding (zero ARTEMIS_LONG anywhere); first fresh Artemis signal = acceptance item 8.

**S5 (post-close, ≥14:00 MT) — THE FLIP, if gates hold** (round-trip ✓ + session traded on v2 ✓ + 6c ✓ + micro-brief sweep ✓). Paste to the DASHBOARD session:
```
FLIP GO-ORDER — execute c4 from docs/codex-briefs/2026-07-03-dashboard-rebuild-v2.md. Preconditions Nick confirms with this paste: (1) authenticated position round-trip passed (v2↔legacy same-table, clean close), (2) a full live session was traded on /app/v2 today Mon 7/13, (3) item 6c accepted 7/10, (4) the 7/13 micro-brief acceptance sweep passed — board_state K badges now L0-filtered and trustworthy. Execute: /app serves v2; old layout moves to /app/legacy for 7 days; schedule the day-7 removal commit (legacy modules + hotfixed heatmap + orphaned CSS — legacy trio endpoints die here too). Push after 14:00 MT only. Post-flip: hard-refresh check that /app renders v2, /app/legacy renders the old page, and report both URLs + the health check.
```

**S6 — post-flip verification (this lane's job):** /app renders v2, /app/legacy renders old, health 200, screenshot of flipped /app vs approved mockup v3 + the 6c capture, log the flip in workstreams.md, set the day-7 legacy-removal reminder (~7/20).

**S7 (evening) — closures:** CC's acceptance items 7 (24/7 tick after 20:00 UTC) + 8 (fresh Artemis rider) + EOS watchdog report. MCP lane may push its OAuth synthetic self-check hardening after its own test pass (≥14:00 rule applies).

## Chase list — carried open items (fold into any next contact)
1. Badge acceptance redo (dashboard forensics item 5): committed capture script, authenticated, production URL — still owed.
2. Injection-artifact report (forensics item 4): the sub-agent's fabricated "tool-rejection" sighting — file path + verbatim quote never delivered.
3. Cosmetics ticket: Achilles cards' "Scan Only" theme tag; river action-items should read stable_job_status (job=uw_budget_shed); concentration lamp mapping vs actual holdings.
4. `POS_XLF_20260609_233128` — null strike + null current_price in unified_positions (fidelity blemish, signals lane).
5. 3 pre-existing test failures (footprint_long, session_sweep, pullback_entry ceiling) — fix or mark expected-fail with reasons.
6. Orphaned unfiltered unwired endpoints (confluence.py, flow_summary.py /summary) — low-priority cleanup.
7. L0.1a re-snapshot ~7/16 (measure suppression win with Artemis included).
8. Close path doesn't stamp `closed_at` — status + trade_outcome set, timestamp NULL (confirmed on both closed SPY rows, 7/11). Fix at the close-handler surface; note `migrate_close_handler.py` in the untracked tree suggests prior surgery there.

## Larger goals / next-week queue (ordered; ATHENA re-sequences post-flip)
1. **ohlc_bars per-consumer audit + rebalance** — governor-enforce prerequisite AND the burn pressure valve (two straight days ≥16.6K; 7/9: ohlc_bars 3,602 vs 1,500 quota; per-caller attribution durable in uw_daily_burn). 7/10 growth math (Fable-verified): ohlc_bars +479 + option_contracts +347 = +826 vs total climb +768 — the pair OVER-explains the growth; every other caller net-declined ~58. Growth is >100% concentrated in these two; start the audit there.
2. **LAZR universe-integrity fix brief** (signals lane, 3 layers): evict LAZR + DEAD-ticker listing-status hygiene for the 691 universe; sanity-bounded calendar-aware pct_change in metrics.py; quarantine-on-resume after long gaps. Robotics stays KNOWN-BAD until shipped.
3. **Write-path census** incl. /log-signal (Phase-0 first). Artemis single-path already confirmed by trace; Monday item 8 adds the empirical point. Crypto Scanner bypass is the known open case; ARTEMIS_SHORT containment depends on this.
4. **Brief 3 — MCP Stable Tools** (hub_get_stable_regime/themes/movers/rates_fx + riders): UNBLOCKED by the connector fix. Titans pass first (ATLAS lead, AEGIS on the OAuth/tool surface); brief FILE must land in the repo; fold in the biotech cross-check redo (7/10: Biotech legit, Robotics bug). After shipping: Nick toggles the Pandora connector to refresh the manifest.
5. **Governor enforce-mode decision** — staleness gate shipped; RTH WOULD-BLOCK log audit now feasible with uw_daily_burn snapshots.
6. **Committee review logging** → n≥250: PIVOT calibration, per-agent edge, B.06 hit rate, regime conditioning.
7. **L1b factor queue:** HG Tier 1, 80-20, Anti HG, News Reversal; 3-10 stays shadow (NOT YET).
8. **Triton:** n≥150 graded shadow events → make-or-break premise decision.
9. Then: Discord suppression mini-brief · 72→96h lookback decision · Stater Swap re-eval (UW+TV MCPs) · X Bookmark Intel (post-ZEUS, Titans one-pager) · mobile concepts · Kairos polish tickets · worldmonitor desk surface · bars.py session filter (low urgency).

## Pending Nick decisions
1. Post-flip priority order: mobile concepts vs Brief 3 vs Kairos polish vs worldmonitor — decide after the flip lands (ATHENA can sequence).
2. RESOLVED Sat 7/11 — backfill-GO delegation confirmed by Nick ("GO"); stands under the exact-match conditions in S2.

## Pointers
Micro-brief: docs/codex-briefs/2026-07-13-l0-transition-and-watchdog-micro-brief.md · Flip brief: docs/codex-briefs/2026-07-03-dashboard-rebuild-v2.md (c4) · Ledger: docs/workstreams.md · Prior handoff: docs/handoff-flip-day-2026-07-10.md · Hub: /app (legacy, live) · /app/v2 (flip candidate) · /health · /mcp/v1/health · MCP connector: https://pandoras-box-production.up.railway.app/mcp/v1/ (HEALTHY — do not disconnect/re-add) · Trading docs: docs/trading-memory.md · docs/trading-theses.md · positions = hub MCP only (hub_get_positions + hub_get_portfolio_balances).
