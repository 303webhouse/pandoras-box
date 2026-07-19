# HANDOFF — Flip Day + Multi-Lane Coordination (fresh chat takes over)
Written 2026-07-10 pre-market by Opus. This chat is the review/verification/coordination lane. Nick's prefs apply: chunked, decisive, lay-terms, one clear next action per turn.

## Read-first
1. `C:\trading-hub\workstreams.md` — the live lane ledger (every session updates its own section; read at pre-flight).
2. This file.

## State of the world (Fri 2026-07-10, pre-market)
- **v2 dashboard accepted through item 6c** (pixel gate passed on real data, zero mocks). The board is honest end-to-end: six-name roster (ICARUS, HELEN, ARGO, TRITON-shadow, HERA-shadow, ACHILLES), roster gate + "+N non-roster → river" counter, grade v1 (A = validated-cell match only; VALIDATED_A_CELLS table), L0-enforced flat feed, honest staleness everywhere.
- **Stable engine formally closed:** first autonomous production nightly PASSED with provenance (ledger row + advanced tables + Railway log + /health). Flatline detection live (e43dc31). Intraday RTH jobs proven on 7/9.
- **L0.1a measured win:** before = 259 Holy_Grail signals/week reaching the actionable view (6 of top-15 ideas); after = 0 surfacing, research record intact (216/wk still written+tagged).
- **UW budget watchdog BUILT, push HELD** on `feat/uw-budget-watchdog` (3059573), 5/5 acceptance. In-hub circuit breaker: ≥17K → Redis `quota_shed:triton` flag (TTL to UTC rollover) + one Discord CB alert + stable_job_status record; ≥18K → escalation alert naming next-tier candidates for a HUMAN call; `uw_daily_burn` daily snapshots kill the 48h-TTL blindness. Awaiting push go (step 1).
- **MCP: mount healthy, connector broken.** fastmcp pinned 3.4.4 (aaea01c), /mcp/v1/health self-check live. But the claude.ai connector still fails: round 3 = silent bounce back to Connectors page after Allow (no error shown). OAuth callback/token-exchange leg — daylight diagnostic outstanding (step 5). Until fixed: Cowork digest runs degraded (no live positions), Olympus reads dark, parallel chat's Brief 3 blocked.
- **Trading context:** 7/8 read RISK-OFF (41 lows/8 highs); 7/9 bounced hard (SPY +0.8, 82 up>3%). Both regime lenses NEUTRAL. Nick's book changed (KNX puts visible). Before ANY trading discussion: standard pre-flight per memory (trading-memory.md, live positions via hub MCP once reconnected, trading-theses.md, prices via web search).

## Standing rules (compressed)
Mockup gate (≥3 concepts, sign-off before briefs, screenshot acceptance + feature-parity diff) · palette v2, no yellow, lime=bullish/vermilion=bearish/teal=attention · provenance not presence (scheduled jobs accepted only on autonomous production runs) · acceptance evidence must be reproducible (committed capture scripts; the builder never grades its own pixels — screenshots land in Nick's chat) · UW quota ~18K internal / 20K plan, nothing new polls UW · labeling contract (as_of, data_age_seconds, anchor, degraded, flatline) · git: pathspecs only, blackout 07:30–14:00 MT trading days · ledger discipline: every lane updates workstreams.md.

## TODAY'S SEQUENCE — run top to bottom

**Step 1 (pre-market, <07:15 MT) — watchdog push go.** Paste to the SIGNALS session:
```
GO on the watchdog push — dashboard lane is quiet (dd28bd6 was its last push; MCP work today is read-only log pulls). Push feat/uw-budget-watchdog to main in the pre-market window (<07:15 MT). Post-deploy verify: one live watchdog tick during RTH recorded in stable_job_status, and the first uw_daily_burn snapshot after the 00:00 UTC rollover. Today is the first guarded live session — 7/9 ran 16.6K, so a ≥17K trigger is plausible; if it fires, expect exactly one Discord CB alert and Triton skipping cycles, and report it as a SUCCESS, not an incident.
```

**Step 2 (pre-open, ~7:00–7:25 MT) — Nick runs the authenticated round-trip** (the flip gate never yet executed): add a test position in /app/v2 → confirm it appears in legacy /app Ledger → close it from the v2 drawer → confirm gone in both. Do it BEFORE the open (committee bridge reads positions every 3 min during RTH). Report result to this chat.

**Step 3 — Artemis decision (Nick owes one word).** Recommendation stands: suppress longs (June validation: ARTEMIS_LONG −0.11 alpha n=1,118; score≥80 slice −0.52%; named eviction candidate). On "suppress Artemis longs," paste to the SIGNALS session:
```
Nick-approved: add ARTEMIS_LONG to L0 suppression via the chokepoint (Holy_Grail treatment — rows still written+tagged, excluded from all feeds). Basis: June validation, cta-artemis-decompose 2026-06-16 (LONG −0.11, n=1,118) + RSI-2 pilot doc (score≥80 slice = −0.52% alpha; named eviction candidate). ARTEMIS_SHORT stays live-and-contained pending the write-path census. Build during blackout, push after 14:00 MT. Verify post-deploy: zero ARTEMIS_LONG in any feed, tagged rows still accruing.
```

**Step 4 (RTH) — Nick trades the session on /app/v2.** Watch: only roster cards in Kairos; tide cell warms during RTH; movers tape live; watchdog's first guarded day (a fire = success); K badges on the tape remain UNTRUSTED until Step 6's chase list confirms the board_state patch.

**Step 5 (daylight) — MCP round-3 diagnostic.** Confirm the MCP session received this (send if not already):
```
Round-3 window: Nick's connect attempt bounced silently back to the Connectors page after Allow — no error shown, third distinct signature. Pull the window around the attempt. First discriminator: did a token-exchange POST arrive at all? If NO token POST → redirect leg died: check redirect_uri on the CURRENT client registration vs the authorize request, and whether the uninstall/re-add left MULTIPLE claude.ai client registrations (stale-registration collision — the one original suspect never tested). If server logs look clean end-to-end, say so — next experiment is ONE announced incognito attempt. If a token POST arrived and failed → status + OAuth error body. Findings first; daylight fix; extend /mcp/v1/health's self-check with a synthetic code-issue → token-exchange round trip so this leg can't fail silently either.
```

**Step 6 (after MCP fix) — reconnect + cascade.** Nick reconnects the connector (expect GitHub + Allow again), opens a fresh chat, confirms `hub_get_*` tools load. Then: notify the PARALLEL chat that Brief 3 is unblocked; Cowork digest returns to full (live positions).

**Step 7 (post-close, after 14:00 MT) — THE FLIP, if gates hold** (round-trip ✓ + session earned trust + 6c accepted ✓). Paste to the DASHBOARD session:
```
FLIP GO-ORDER — execute c4 from docs/codex-briefs/2026-07-03-dashboard-rebuild-v2.md. Preconditions Nick confirms with this paste: (1) the authenticated position round-trip passed this morning (v2↔legacy same-table, clean close), (2) a full live session was traded on /app/v2 today, (3) item 6c accepted 7/10. Execute: /app serves v2; old layout moves to /app/legacy for 7 days; schedule the day-7 removal commit (legacy modules + hotfixed heatmap + orphaned CSS). Push after 14:00 MT only. Post-flip: hard-refresh check that /app renders v2, /app/legacy renders the old page, and report both URLs + the health check.
```

**Step 8 — post-flip verification (this lane's job):** Nick hard-refreshes /app (renders v2) and /app/legacy (renders old); health 200; screenshot of flipped /app compared against approved mockup v3 + the 6c capture. Then log the flip in workstreams.md and set a 7-day reminder for the legacy-removal commit review.

## Chase list — outstanding from the DASHBOARD lane (fold into any next contact)
1. board_state.py ticker-context L0 patch: CONFIRM shipped + the full read-surface sweep report (every signals/trade_ideas read → filtered yes/no) — ordered in forensics item 1, never explicitly confirmed.
2. Badge acceptance redo (forensics item 5): committed capture script, authenticated, production URL — still owed.
3. Injection-artifact report (forensics item 4): the sub-agent's fabricated "tool-rejection" sighting — file path + verbatim quote never delivered.
4. Cosmetics ticket: Achilles cards' "Scan Only" theme tag; river action-items should read stable_job_status (job=uw_budget_shed) per the signals lane's handoff; concentration lamp mapping sanity (reads "Energy 46%" on Nick's current book — verify against actual holdings).
5. Score-clamp check: TWO exact-100.0 themes in three days (Biotech 7/8, Robotics 7/9) — confirm legit clamp vs normalization artifact (was 6a rider #3; also cross-check vs Ryan's board via the Cowork digest).

## Next-week queue (SIGNALS lane owns, already ledgered)
ohlc_bars per-consumer audit + rebalance (#1 — governor-enforce prerequisite; 7/9 still 3,602 vs 1,500 quota) · write-path census incl. /log-signal (Phase-0 first) · L0.1a re-snapshot ~7/16 · governor enforce-mode decision (staleness gate ✓ shipped; RTH log audit now possible with uw_daily_burn snapshots) · Discord suppression mini-brief · 72→96h lookback decision.

## Pending Nick decisions
1. "Suppress Artemis longs" — yes/no (rec: yes).
2. Post-flip priority order: mobile concepts, MCP Brief 3, Kairos polish tickets, worldmonitor desk surface.

## Pointers
Briefs: docs/codex-briefs/2026-07-03-stable-engine-port.md · 2026-07-03-dashboard-rebuild-v2.md · Ledger: workstreams.md · Hub: /app (legacy, live) · /app/v2 (flip candidate) · /health · /mcp/v1/health · MCP connector URL: https://pandoras-box-production.up.railway.app/mcp/v1/ · Universe: stable_market_board_LATEST\stable_market_board\data\universe.csv · Trading docs: docs/trading-memory.md · docs/trading-theses.md (positions = hub MCP only, never doc mirrors).
