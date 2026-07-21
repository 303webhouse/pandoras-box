# MASTER PLAN — "Vacation-Safe by Aug 4"

**Authored:** 2026-07-21, coordination lane (Fable)
**Horizon:** now → 2026-08-04 (Nick departs)
**Scope:** all four outstanding build threads + the new work required to close them
**Method:** Titans double pass (Pass 1 → Pass 2 → ATHENA Overview) + Olympus pass on the signal thread
**Anchor SHAs:** `10cf67e9` (HEAD at time of writing), `982257c`, `e8ed614`, `e14a8bd`, `bb0a56f`, `fb7292a`

---

## TASK 0 — FILING (CC executes first, before anything else)

The coordination lane cannot write to GitHub (`create_or_update_file` → 403 "Resource not accessible by integration"). This file was delivered to Nick, who drops it at `C:\trading-hub` root.

```
cd /d C:\trading-hub
git fetch origin && git status
git mv 2026-07-21-master-plan-vacation-safe-aug-4.md docs\codex-briefs\
git add docs/codex-briefs/2026-07-21-master-plan-vacation-safe-aug-4.md
git commit -F C:\temp\commitmsg.txt
git push origin main
```

Nothing else in this document executes until Task 0 lands.

---

## PART 0 — CORRECTIONS TO THE 07-21 HANDOFF

Verified against repo HEAD and the live hub before planning. Three of the handoff's assertions are now stale or wrong. Recording them because the epistemic log's stated pattern — *the coordination lane keeps assuming breakage and the system keeps turning out clean* — just repeated itself.

### C-1. CC's ACK **landed**. Handoff FIRST ACTION #1 is closed.

The handoff states the four rulings were "NOT YET RECEIVED." False by the time it was written, or shortly after. Both commits are on `main`:

| SHA | Time (UTC) | Content |
|---|---|---|
| `982257c` | 2026-07-21 19:34:22Z | Rulings 2 + 3 + 4 executed |
| `10cf67e9` | 2026-07-21 19:36:51Z | Rulings 1–4 recorded for recoverability |

- **Ruling 1** (burst tag KEEP all 73) — confirmed, already applied, no action.
- **Ruling 2** (`/api/analytics/log-signal` REMOVED) — precondition verified clean first: zero callers in `frontend/`, `scripts/`, or on the VPS (`/opt/openclaw/workspace/`, `/home/openclaw/.openclaw/`, `/opt/pivot/`). Endpoint, `LogSignalRequest`, dead import, and auth-test case all removed. **This closes the last side door around F-4's `process_signal_unified` chokepoint.**
- **Ruling 3** (historical `source` backfill DECLINED permanently) — replacement doc at `docs/reference/signal-provenance.md`. Correction recorded there: `strategy` is *not* quite lossless — `Holy_Grail` and `Scout Sniper` are dual-origin (server scanner and TV webhook emit the identical strategy string). That is precisely where a backfill would have had to invent data, so the ruling holds; only the "losslessly" premise needed a footnote.
- **Ruling 4** (`CRYPTO_ALERT_MIN_SCORE = 28`) — shipped, VPS-deployed byte-exact (SHA-256 `5205bda9…`), compile-verified. Semantics stated explicitly at the constant and covered by a boundary test: **`score < 28` is SUPPRESSED; exactly 28 IS alerted.** Effective score = `COALESCE(score_v2, score)`.

### C-2. Test baseline moved. Do not carry the handoff's number.

| Source | Baseline |
|---|---|
| Handoff | 460p / 18f / 203e |
| **Actual (`982257c`)** | **488p / 18f / 1s / 200e** |

The 203 → 200 error drop is `982257c`'s own doing — removing one route drops its 3 parametrized auth cases. **Not drift.** Failed and skipped counts unchanged.

### C-3. "Zero trades taken" is wrong. Three positions opened today.

The handoff's closing note says the session ran "all infrastructure, zero trades taken," and flags that opening the next session with more infra deserves a pointed question. That premise was already false when written:

| Position | Structure | Opened (UTC) | Opened (MT) |
|---|---|---|---|
| `POS_QQQ_20260721_170049` | put debit spread 510/500, qty 2, 10/16 exp | 17:00:49Z | 11:00:49 |
| `POS_QQQ_20260721_170404` | put debit spread 360/350, qty 2, 10/16 exp | 17:04:04Z | 11:04:04 |
| `POS_AMC_20260721_170555` | call debit spread 3/7, qty 2, 8/21 exp | 17:05:55Z | 11:05:55 |

Corroborated independently: the Robinhood balance row's `updated_at` is `2026-07-21T17:05:55Z` — the same second as the AMC open, i.e. the broker sync fired on the trade. The handoff was written ~11:30 MT, roughly 25 minutes *after* the third fill.

**Carry the pattern, not just the fact.** This is the same failure class as items (1)–(6) in the handoff's own epistemic log. The lane's prior should be updated: absent evidence, assume the system and the operator are functioning.

---

## PART 1 — LIVE-STATE FINDINGS (new, and they reshape the plan)

Pulled from `hub_get_positions(status=OPEN)` and `hub_get_portfolio_balances` at 2026-07-21.

### F-1 — P0: SOXS phantom gain is **still live**, six days after being filed

```
POS_SOXS_20260610_154556 | fidelity_roth | stock
qty 450 @ entry $4.0395 | current $45.845 | unrealized_pnl +$18,812.48
```

The 1-for-10 reverse split (effective 2026-07-15) was never applied to the position record. True combined gain is approximately **$288**. The record overstates it by roughly **65×**.

This was filed as P0 on 2026-07-15 and independently re-observed on 2026-07-19 and 2026-07-20. It is still uncorrected. Correct transform: divide quantity by 10, multiply cost basis by 10.

**Why this is the spine of the plan, not a side item:** `unified_positions` is the canonical source for `total_capital_at_risk` (currently reporting $3,530 — wrong), every P&L figure in the analytics stack, the risk-budget surface, and DAEDALUS's sizing math. The two largest builds Nick wants — **Stater Swap S-6 (UI) and Abacus v2 (analytics/backtest/journal)** — both read directly from this layer. Building either on top of it produces a beautiful instrument that lies. That is the exact "fake-healthy is P0" class Nick himself codified.

### F-2 — P1: the 07-18 reconciliation rulings are **still not applied**

Live `hub_get_portfolio_balances` returns `status: stale` and this account list:

| Account | Balance | `updated_at` | Ruling (locked 2026-07-18) | Applied? |
|---|---|---|---|---|
| robinhood | $835.69 | 2026-07-21 17:05:55Z | — | fresh |
| fidelity 401a | $11,075.62 | 2026-06-09 | consolidate → `brokerage_link_401k` | **NO** |
| fidelity 403b | $566.73 | 2026-06-09 | consolidate → `brokerage_link_401k` | **NO** |
| fidelity roth | $8,842.09 | 2026-06-22 | untouched (correct) | n/a |
| interactive brokers | $0.00 | 2026-02-25 | **DELETE** (never funded) | **NO** |
| **breakout_prop** | **ABSENT** | — | Tier 1 #3 fake-healthy defect | **NO** |

Three Fidelity rows are 29–42 days stale. `breakout_prop` — the only account structurally able to hold a crypto trade — does not appear at all. The micro-brief and dry-run already exist at `c7df849`. This has been "locked, apply tomorrow" for three days.

### F-3 — P2: two more `unified_positions` artifacts

- `POS_XLF_20260609_233128` — `long_strike: null`, `short_strike: null`, `current_price: null`. Flagged 2026-07-15, still open.
- `POS_XLF_20260609_233055` — `current_price: -0.02`. A negative option price is not a price.

### F-4 — Book context (21 open, $3,530 nominal at risk)

Expiring **before** departure: XLF 53.5/48.5 put debit spread and XLE 60c, both 2026-07-31 (10 DTE). Expiring **during or near** the trip: AMC 3/7, OBE 12.5c, XLE 60/65 — all 2026-08-21. Everything else is 9/18, 9/30, or 10/16.

---

## PART 2 — TITANS DOUBLE PASS

**Build under review:** the four-thread completion program (Agora v2 + Pythia v2.4 / signal finalization / Stater Swap S-5–S-6 / Abacus v2) against a hard 2026-08-04 deadline.

**Working-day count:** Jul 22, 23, 24 | Jul 27, 28, 29, 30, 31 | Aug 3 = **11 weekdays**, of which Jul 27 is the earliest TRITON-AUDIT can legally start.

---

### PASS 1 — INDEPENDENT REVIEWS

#### ATLAS — PASS 1 (backend architecture / data integrity)

**BUILD:** four-thread completion program to 2026-08-04
**PRE-REVIEW PREREQUISITES:** PASS with one note — `docs/build-backlog.md` is at v4, dated 2026-07-15, and is now six days and roughly a dozen closures stale. It does not reflect S-3b, S-4 Phases 0–3, DEF-ENRICH-CLOBBER, DEF-NOTIFIER-STALE, DEF-FEED-TRIAGE, DEF-CVD-DEDUP, or DEF-SIGNAL-METADATA. Arbitration run against it will mis-sequence.

**VALIDATION CHECK:** Threads A and C are validated — Agora v2 is flipped and live since `e9a4840` (2026-07-13), the Pythia crash has a named mechanism, and Stater Swap's remaining scope is documented in the committee brief. Thread D (Abacus v2) is **not validated**: no audit exists for what the current Cockpit/Laboratory surface actually gets wrong today, and the last two analytics rebuilds (March Phase 3 → Cockpit/Laboratory) both shipped without one.

**FINDINGS:**

1. **`unified_positions` integrity is a hard prerequisite, not a parallel track.** F-1 and F-2 sit underneath both remaining large builds. Abacus v2 is definitionally a P&L / journal / backtest surface; S-6's distance-to-floor chip is explicitly gated on `breakout_prop`. Shipping either against the current table means shipping fabricated numbers behind a new UI, which is strictly worse than the current state because the new UI will be trusted more.

2. **The SOXS correction is a destructive write and needs the established phasing.** Predicate-based selector (never a frozen ID list), pre-image JSONL to `C:\temp\`, `--i-have-go` gate, row-count invariance check, post-apply predicate count of zero. `scripts/backfill_suppression.py` and `scripts/quarantine_enrich_clobber.py` are both proven runbooks to model on. **Do not hand-edit.**

3. **`is_test` still does not exist.** Three named rows are waiting on it (`trades.id=171`, `trades.id=126`, and `signals.id=14893` which must be *kept but excluded*, not deleted). Any analytics surface built before this convention exists inherits the leak. This is a genuine Abacus v2 prerequisite, cheap, and has been open since 7/13.

4. **`process_signal_unified()` Tier-1 #0 is still open** — `expires_at` is written as a raw `datetime`, and the duplicate `sanitize_for_json()` copies in `redis_client.py` and `broadcaster.py` handle numpy but not datetime, so Redis cache and WebSocket broadcast have been silently failing for **every signal from every source**. Persistence is unaffected. This is a ~10-line fix with platform-wide blast radius, and it degrades exactly the real-time delivery path that matters most when nobody is watching the screen.

5. **S-5's signal #10 (UW ETF-flow exhaustion) needs my budget sizing before it can be scoped.** Current burn has crossed 17K on 2 of 12 days. I will not sign off on a new recurring UW feed without a per-day call-count estimate against the 17K SHED / 18K ESCALATE thresholds.

**VETO:** **TRIGGERED** — data-integrity invariant. `unified_positions` is designated single-source-of-truth; a record overstating a position's P&L by 65× violates that invariant. I veto any Abacus v2 or S-6 build that reads position or balance data until F-1 and F-2 are applied and verified. The veto lifts on evidence, not on schedule pressure.

**RECOMMENDED VERDICT:** RESCOPE — foundation first, in Week 1, then the surfaces.
**CONVICTION:** HIGH — the defect is live, reproduced twice by two lanes, and sits directly under both proposed builds.

---

#### HELIOS — PASS 1 (frontend / UX / design system)

**BUILD:** four-thread completion program to 2026-08-04
**PRE-REVIEW PREREQUISITES:** PASS.

**VALIDATION CHECK:** "Debugging and completing Agora v2" is under-specified. Agora v2 flipped 2026-07-13, passed Nick's own pixel-check on 2026-07-14 after a full RTH session, and all flip gates are marked cleared. Someone — Nick, from the commit style — shipped scrollbar theming and wordmark restoration this morning at `c2aea5f`. So "complete the dashboard" currently has no defect list attached to it. **I need Nick's actual list before I can review this thread**, and I am flagging that rather than inventing one.

**FINDINGS:**

1. **The mockup gate cannot be compressed, and it is the critical path for S-6.** `helios-mockup-track.md` shows the track OPEN since 2026-07-15 with the concept-session prerequisite met on 2026-07-16 — and **zero concepts produced in the five days since.** The gate requires: ≥3 rendered concepts → Nick reaction pass → iterate → final sign-off recorded in the track file → *only then* may the S-6 brief be authored → Titans final review → CC build → post-deploy screenshot comparison. That is a minimum of three Nick-review round trips. **If the concept session does not start by Friday 2026-07-24, S-6 does not ship before Aug 4, and I will say so rather than waive the gate.**

2. **Threads C and D both want my lane simultaneously, and they cannot have it.** S-6 needs ≥3 concepts covering a seven-item surface inventory (regime header, tape-health strip, signal feed, Cycle Extremes single-axis dial, collapsed macro band, discipline chips, six-symbol switcher with a full Tier-3 FARTCOIN view). Abacus v2 needs its own concept set for a completely different information architecture. Running both mockup gates in 11 days produces two mediocre gates instead of one good one. **Pick one. I recommend S-6**, because its payload contracts are live and real (`/api/crypto/cycle-extremes`, `/tape-health`, `/state`) whereas Abacus v2's data layer is about to change underneath it — see ATHENA.

3. **The mockup gate exists because of a specific past failure.** One prior UI deploy delivered invisible infrastructure improvements while introducing a visual regression. That is precisely what deadline pressure reproduces. The gate is a standing veto for a reason.

4. **Vacation changes the UX requirement, and nobody has scoped for it.** Every surface in this system assumes Nick is looking at it. For a two-week unattended window the relevant question is not "does this dashboard read well at the open" but "what does this system do when nobody reads it for 14 days." That is a real design question with real deliverables (alert-rate ceilings, digest-over-stream, mobile-reachable kill switch) and it is in nobody's brief.

**VETO:** **CONDITIONAL** — I will veto the S-6 brief if it is authored before final mockup sign-off is recorded in `helios-mockup-track.md`. Not triggered yet. It triggers on 2026-07-25 if the concept session has not run.

**RECOMMENDED VERDICT:** RESCOPE — one mockup gate, not two; and Nick must supply the Agora v2 defect list before that thread is reviewable.
**CONVICTION:** HIGH on the gate timing, LOW on Agora v2 scope (I do not have the input).

---

#### AEGIS — PASS 1 (security / auth / credentials)

**BUILD:** four-thread completion program to 2026-08-04
**PRE-REVIEW PREREQUISITES:** PASS.

**VALIDATION CHECK:** One item in this program is validated far past the point of comfort, and it is not one of the four threads.

**FINDINGS:**

1. **The PYTHIA webhook secret is compromised across three independent channels and rotation is still QUEUED.** From the ledger, in order of discovery: (a) the live Pine script hardcoded the secret as a literal string directly in the payload body, meaning it leaked on every share, export, or screenshot of that script for its entire life; (b) it was exported into a CSV; (c) it was pasted into a chat transcript on 2026-07-15 to produce the reconciliation diff. `15dfd42` hardened the *script* — the secret now comes from `input.string("")` per the established TV-family pattern — but **the value itself is unchanged and still live.** Rotation was deferred to "post-stability" on 2026-07-15. It is now 2026-07-21.

2. **Thread A forces the rotation anyway — take the free window.** The Pythia v2.4 crash fix requires editing the Pine script, and TradingView alerts run frozen script snapshots, so every alert must be deleted and recreated regardless. The webhook secret rotation requires exactly that same operation: Railway env var + the script's input field + re-arm all four alerts, **in one coordinated pass** (a partial rotation just manufactures a fourth flavor of the outage this system has already had three times). The two operations are the same operation. Doing the crash fix without rotating is choosing to leave a known-compromised credential live for no saved effort.

3. **Nick is about to be away from the keyboard for roughly two weeks with a live compromised ingress credential.** The exposure is bounded — `webhooks/pythia_events.py:78-86` is fail-closed since inception (`hmac.compare_digest`, no observe-mode fallback, unconditional 503 if unconfigured, 401 on mismatch), so this is a forgery risk on the market-profile ingress path, not an exfiltration path. But a forged `pythia_events` write corrupts the exact structural levels PYTHIA feeds to the committee, and the 7/2–7/15 stale-MP incident already demonstrated that corrupted PYTHIA input silently degrades committee output for weeks before anyone notices.

4. **Residual, separate, not resolved by the rotation:** the TV-family (`_tv_observe`, `WEBHOOK_TV_ENFORCE`) and Hermes (`_hermes_observe`, `WEBHOOK_HERMES_ENFORCE`) webhooks *do* have genuine fail-open observe-mode fallbacks. Whether those `_ENFORCE` flags are actually set in Railway cannot be determined from the repo — it is live config, not git-tracked. **One direct Railway check, five minutes, before departure.** If either is unset, the system spends the vacation accepting unauthenticated webhook writes.

**VETO:** **TRIGGERED** — secret-management policy. No further TradingView-surface work ships, and Nick does not depart, with this credential unrotated. The trigger is "this is a security incident waiting to happen," not a preference.

**Pre-production override eligibility:** this is a data-ingress credential, not a broker credential, so it *is* override-eligible under the Nick-only bounded override. If Nick invokes it, the invocation **must** be recorded in `skills/aegis/references/pre-production-override-log.md` at the time of invocation — unrecorded overrides are invalid. I am recommending against the override here, because the rotation is nearly free: thread A already requires the identical alert re-arm.

**RECOMMENDED VERDICT:** PROCEED, with the rotation folded into thread A as a non-optional sub-task.
**CONVICTION:** HIGH.

---

#### ATHENA — PASS 1 (priority / sequencing / scope)

**BUILD:** four-thread completion program to 2026-08-04
**PRE-REVIEW PREREQUISITES:** **PARTIAL FAIL.** `docs/build-backlog.md` is v4 (2026-07-15) and materially stale — it does not reflect ~12 closures since. I am proceeding using the workstreams ledger as the live source and flagging that **backlog v5 is itself a deliverable of this plan**, not optional housekeeping. Repeatable arbitration requires a current backlog.

**VALIDATION CHECK:** Three of four threads solve verified problems. Thread D does not. The last Abacus rebuild (March, ZEUS Phase III precursor) ran five briefs — 3A Ariadne's Thread, 3B Oracle, 3C UI, 3D Hermes Dispatch, 3E Auth + data quality — and was then rebuilt *again* into Cockpit/Laboratory. Nick's current ask ("redesign and implement v2, updated with all current live market data access and the revised strategies") is a program, not a build, and it has no audit.

**PRIORITY SLOT + DISPLACEMENT:**

| Thread | Fits window? | What it displaces |
|---|---|---|
| A — Agora v2 defects + Pythia v2.4 + secret rotation | **YES** — tactical, 2–3 days | nothing |
| B — signal finalization (Triton-led) | **PARTIAL** — Triton yes, 3-10 structurally no | nothing |
| C — Stater Swap S-5 + S-6 | **TIGHT** — only if mockup session starts by 7/24 | HELIOS's lane for the whole window |
| D — Abacus v2 | **NO** | would displace C entirely |

**DISPLACEMENT WORTH IT? NO** for thread D. Three independent reasons, any one of which is sufficient:

1. **Sequencing.** Abacus v2 is an analytics surface over the strategy roster. The strategy roster changes on 2026-07-27 when TRITON-AUDIT returns a promote-or-not verdict, and again if the Kodiak/Nemesis/Icarus triage reclassifies three silent strategies. Designing analytics for a roster that changes mid-build guarantees rework. **This is not a deferral for capacity reasons — it is the correct order.**
2. **Foundation.** ATLAS's veto is live and correct. Abacus v2 is precisely the surface that would render the $18,812 phantom as a headline number.
3. **Capacity.** HELIOS has one mockup lane and it is already committed to S-6.

**BUCKET FIT:** A = tactical. B = foundation (statistical, gated on data maturity — cannot be compressed). C = foundation + tactical mixed. D = foundation, multi-week, **mismatched to the window**.

**OLYMPUS IMPACT:** Substantial and it must be in the brief. A Triton promotion changes what strategies committee agents see. The `unified_positions` fixes change DAEDALUS's sizing inputs directly — he has already issued a live sizing veto (2026-07-21, NBIS pass) on the basis of unverifiable Breakout Prop balance. S-6 changes the surfaces PYTHIA and MIDAS-class analysis read. Post-build, at minimum one full committee pass on a known-good ticker per the TORO-fabrication-incident rule.

**SCOPE OBSERVATIONS:**
- The completion criterion is wrong. "Complete by Aug 4" for a system that will then run **unattended** should mean *safe to leave running*, not *feature-complete*. Those are different builds, and the second one is not the one that matters here.
- Nobody has scoped the unattended window. It is not in any thread, and it is the only genuinely new requirement the vacation introduces.
- Backlog v5 is a deliverable.

**VETO:** **TRIGGERED** — scope conflict with higher-priority queued work. Abacus v2 UI displaces S-6, which has a live mockup track, live payload contracts, and a named blocking dependency already scheduled for repair. I veto the Abacus v2 **UI build** in this window. I do **not** veto its foundation — the `unified_positions` integrity work and the `is_test` convention are Abacus v2 prerequisites and they ship in Week 1 regardless.

**RECOMMENDED VERDICT:** **RESCOPE.**
**CONVICTION:** HIGH.

---

### PASS 2 — CROSS-REVIEW

#### ATLAS — PASS 2
**Agreements:** AEGIS's rotation-folding is correct and costs nothing — same alert re-arm operation either way. ATHENA's sequencing argument (roster changes 7/27) is stronger than my own capacity argument for deferring Abacus v2; I adopt it.
**Disagreement — with ATHENA, partial:** ATHENA calls S-6 "TIGHT, achievable." I read it as tight *and* conditional on my veto lifting first, which puts real work in front of the mockup gate's build phase. I want the dependency stated as an ordered chain, not a parallel track: **F-2 (`breakout_prop`) → S-6 distance-to-floor chip.** Not "both in Week 2."
**Scope addition:** Tier-1 #0 (`sanitize_for_json` datetime) moves into the unattended-hardening pass rather than sitting in the backlog. It silently degrades real-time delivery, which is the failure mode that matters most when nobody is watching.
**Revised verdict:** RESCOPE, unchanged.

#### HELIOS — PASS 2
**Agreements:** ATHENA's thread-D veto resolves my capacity conflict — one mockup gate, S-6, agreed. ATLAS's point that a new UI over bad data is *worse* than the current state is the sharpest argument in the pass and I want it in the record: **a trusted surface over fabricated numbers is a downgrade, not a feature.**
**Disagreement — with ATHENA, on framing:** ATHENA lists thread A as "nothing displaced." It displaces my review bandwidth in the same week I need to produce three concepts. Small, but real. Mitigation: the Pythia fix is a one-line `math.min()` clamp plus an operational re-arm — it needs AEGIS and Nick, not me. **Withdrawn as a blocker, recorded as a note.**
**Concern the others missed:** the post-deploy screenshot comparison for S-6 must happen *before* Nick departs. If S-6 deploys on Aug 3 and the comparison slips, the gate is not satisfied and the standing veto means the build is not accepted — it would sit unaccepted for two weeks. **Either S-6 deploys by Jul 31 with the comparison on Aug 3, or it does not deploy at all this window.** I would rather ship nothing than ship an unverified UI into an unattended fortnight.
**Revised verdict:** RESCOPE, with S-6's deploy date pulled to 2026-07-31.

#### AEGIS — PASS 2
**Agreements:** HELIOS's "deploy by 7/31 or not at all" is the same instinct as my rotation timing — do not leave an unverified change running unattended. ATHENA's unattended-safety reframe is the correct completion criterion and I would extend it: the security question is not "is the system secure" but "is it secure with no operator for 14 days."
**Concern the others missed:** the alert-rate problem is a security-adjacent availability issue, not just UX. The CVD burst put **94 alerts** into Discord before 10:50 MT on 2026-07-21 pre-fix. That fix is shipped and verified. But the *class* — a scheduler-cadence interaction defeating a cooldown — is not structurally prevented anywhere. During an unattended window, a repeat means either Discord rate-limits Nick's channel or he returns to thousands of messages. **An alert-rate ceiling belongs in the hardening pass, and it is cheap.**
**No disagreements.**
**Revised verdict:** PROCEED with rotation folded in, unchanged.

#### ATHENA — PASS 2

**NICK INJECTION RECEIVED:** No — not yet solicited. Open questions are listed in the Overview.

**AGREEMENTS:** ATLAS on the ordered dependency chain (accepted, folded into sequencing). HELIOS on the 7/31 deploy date (accepted — it converts a soft risk into a hard gate, which is what a gate is for). AEGIS on the alert-rate ceiling (accepted into the hardening pass).

**ARBITRATION CALLS:**

1. **ATLAS vs. my own Pass 1, on S-6 parallelism.** ATLAS is right and I was loose. `breakout_prop` → distance-to-floor chip is an ordered dependency, not a parallel track. **Tie-break: ATLAS.** Sequencing revised.
2. **HELIOS's bandwidth objection to thread A.** Withdrawn by HELIOS before arbitration. Recorded, no call needed.
3. **Vetoes in play — three, none arbitrable:**
   - **ATLAS** (data-integrity invariant): lifts on applied-and-verified F-1 + F-2.
   - **AEGIS** (secret-management): lifts on completed coordinated rotation. Override-eligible by Nick only, and must be logged if invoked.
   - **ATHENA/self** (scope, Abacus v2 UI): overridable by Nick only.

   Per the tie-break rules I do not synthesize past any of these. Two of the three lift on work already scheduled in Week 1.

**VALIDATION FLAG STATUS:** ATLAS flagged validation missing on thread D. **Validation is non-arbitrable except by full consensus, and consensus does not exist** — HELIOS independently flagged it (no defect list for Agora v2; no IA audit for Abacus). Therefore thread D requires an audit before any build. Since my veto already defers the UI, the audit becomes a Week-3 or post-vacation deliverable, not a blocker on anything in this window.

**SCOPE ADJUSTMENTS AGREED:**
- Abacus v2 **UI** deferred; Abacus v2 **foundation** (F-1, F-2, F-3, `is_test`) ships Week 1.
- Secret rotation folded into thread A as non-optional.
- Unattended-safety hardening added as a **new, named thread E** — it did not exist in Nick's four and it is the only thread the vacation actually creates.
- S-6 deploy pulled to 2026-07-31, screenshot comparison 2026-08-03.
- Backlog v5 added as a deliverable.

**REVISED VERDICT:** RESCOPE.

---

### ATHENA — OVERVIEW

**BUILD:** Four-thread completion program → 2026-08-04

> **RECOMMENDED VERDICT: RESCOPE — three of four threads ship, plus one new thread that matters more than the one being cut.**
> **CONVICTION: HIGH.** Three independent vetoes converge on the same sequencing, and two of the three lift on work already scheduled in the first week.

**PASS 1 SUMMARY:**

| Titan | Verdict | Conviction | Veto |
|---|---|---|---|
| ATLAS | RESCOPE | HIGH | **TRIGGERED** — data-integrity invariant |
| HELIOS | RESCOPE | HIGH (gate) / LOW (thread A scope) | **CONDITIONAL** — triggers 2026-07-25 |
| AEGIS | PROCEED w/ rotation folded in | HIGH | **TRIGGERED** — secret management |
| ATHENA | RESCOPE | HIGH | **TRIGGERED** — scope conflict |

**AGREED SCOPE.** Week 1 repairs the data layer both remaining surfaces read from and closes the credential exposure. Week 2 runs the Triton audit the moment its data-maturity gate opens, triages the three silent strategies, and ships S-5. S-6 deploys 7/31 against a signed-off mockup, with the screenshot comparison on 8/3. Abacus v2's *foundation* ships in Week 1; its *UI* is deferred, deliberately, because the strategy roster it would visualize changes on 7/27. A new thread — unattended-safety hardening — is added and is the actual definition of "done" for this window.

**SEQUENCING.** Ordered dependency chains, not parallel tracks:

```
F-1 (SOXS) + F-2 (accounts/breakout_prop)  ──►  ATLAS veto lifts
                    │
                    ├──►  S-6 distance-to-floor chip  ──►  S-6 build
                    └──►  Abacus v2 foundation (is_test, signal→outcome chain)

Pine v2.4 clamp  ──┬──►  alert delete/recreate  ──►  AEGIS veto lifts
secret rotation  ──┘

HELIOS concepts (start ≤7/24)  ──►  Nick sign-off  ──►  S-6 brief  ──►  build
                                          │
                                    [HELIOS veto fires 7/25 if not started]

2026-07-27 data gate  ──►  TRITON-AUDIT  ──►  Olympus interpretive  ──►  promote / not-yet
```

**What this defers, by name:** Abacus v2 UI (ZEUS Phase III). 3-10 oscillator promotion (structurally blocked — gated on Outcome Tracking Phase C, which is not built, plus n≥250 post-Phase-B `both` signals). Rebuild-stack L1/L2. Phase B `get_bars` migration. Committee review logging. Great Library (Phase IV).

**OLYMPUS IMPACT.** Triton promotion changes the committee's visible strategy roster. `unified_positions` repair changes DAEDALUS's sizing inputs directly and should lift his standing sizing veto. S-6 changes PYTHIA-adjacent surfaces. **Required post-build re-test:** one full committee pass on a known-good ticker, per the 2026-05-21 TORO fabrication precedent. Any brief touching these needs an explicit "Olympus Impact" section — I will not approve one without it.

**OPEN QUESTIONS FOR NICK:**
1. **How long is the trip?** Everything in thread E scales to it. Positions at 8/21 expiry are the specific risk.
2. **What is actually broken in Agora v2?** HELIOS cannot review a defect list that does not exist. Even three bullets unblocks him.
3. **Do you accept the Abacus v2 UI deferral, or override my veto?** If you override, S-6 is what gets cut — I will not approve both.
4. **The funding `degraded`-flag duty cycle is still unanswered** and has been asked twice. Both new shadow gates ride the degraded-suppression contract; if funding reads degraded a meaningful fraction of the time, the shadow logs undercount and the eventual flip decisions get made on thin evidence.

---

## PART 3 — OLYMPUS PASS (signal finalization thread)

Committee lane: which signals are genuinely finalizable, and what "finalize" honestly means for each.

**PYTHAGORAS (data / statistics — leads).**
Triton shadow: 2,479 rows 07-02 → 07-20, **1,474 graded / 1,005 pending**. The headline 710 positive vs 764 negative by `fwd_ret_5d` sign is **pooled and therefore meaningless as a verdict** — bearish detections are *supposed* to have negative forward returns, so pooling cancels edge by construction. Direction-conditioned analysis is mandatory, and pre-registration must be written before any query runs. The 07-27 gate takes n from 1,474 to roughly 2,400 as pending rows finish grading; that is a 63% increase in evidence for five days of waiting. **Waiting is correct and I will not endorse an early read.** Holdout law is absolute: pending-grade rows are never queried by TRITON-EXPLORE.

**URSA (kill the case).**
The ask assumes these signals are "in limbo." Several are not in limbo — they are **untested**. Kodiak, Nemesis, and Icarus fired **zero times in 14 days**. A strategy with no fires has no evidence, and no amount of audit produces evidence from an empty set. The honest output for those three is a diagnosis (quiet vs. broken), not a promotion decision — and "quiet" and "broken" look identical from the outside, which is exactly the blind spot the strategy-emission flatline watchdog exists to close and which has now gone unbuilt through an 18-day Crypto Scanner silence.

Two more things I want on the record. **Apis fired 33 times in 14 days** — the second-most-active codenamed strategy. Has Nick ever seen an Apis card? If not, that is a feed-tier visibility defect masquerading as a quiet strategy, and it is a 30-second check. And **`HG_DAILY_CAP=2` per ticker per day is hardcoded at `holy_grail_scanner.py:43` with no kill switch**, on a strategy class Nick never sees. During a two-week unattended window, that is a live production constraint nobody can adjust remotely.

Finally: **promoting anything under a vacation deadline is the precise pressure that produces a bad promotion.** The 3-10 oscillator's "NOT YET" verdict survived exactly this pressure in May and was right to. Hold the same line.

**THALES (regime plausibility).**
Crypto Scanner has been silent 18 days. The benign attribution — 12 of 15 tracked tickers in CAPITULATION/WATERFALL CTA zones against long-only logic, so zero qualifying setups is the *correct* output — was established 2026-07-15 and **has not been re-validated in six days.** Step 1 of any work in that lane is re-checking whether the zone condition still holds. If the zones have turned and the scanner is still silent, the benign explanation no longer covers it and this is a defect, not a market read. Separately, 3 of 15 `CRYPTO_TICKERS` (MATIC-USD, UNI-USD, APT-USD) are delisted on yfinance and have been dead weight — 20% of that universe — with no escalation.

**DAEDALUS (structure / sizing).**
Everything I produce is downstream of the balances layer, and that layer is currently unreliable: `breakout_prop` absent, three Fidelity rows 29–42 days stale, and a position record overstating P&L by 65×. I issued a portfolio-level sizing veto on the NBIS pass on exactly this basis. **Until F-1 and F-2 land, every sizing number from every committee pass between now and Aug 4 is degraded**, and per Override Rule 3 that is a mandatory one-notch conviction demotion on all of them. This is not a nice-to-have — it is the difference between the committee producing advice and producing arithmetic on fiction.

**PIVOT (synthesis).**

> **VERDICT: Finalize one signal on evidence. Triage three. Promote nothing else.**
> **CONVICTION: HIGH.**

- **TRITON** — audit on/after 07-27, pre-registration first, direction-conditioned. Outcome is promote **or** a documented NOT-YET with a named re-evaluation trigger. Both are complete answers; only a rushed promotion is a failure.
- **Kodiak / Nemesis / Icarus** — quiet-vs-broken triage. Diagnosis, not promotion. Half a day.
- **Apis** — 30-second feed-tier visibility check. Ask Nick whether he has ever seen an Apis card.
- **Crypto Scanner** — re-validate the CTA-zone attribution before relying on it.
- **The two crypto shadow gates** (`funding_fade_negative_floor_raise_enabled`, Tier-3 block) — leave shadow. They were *correctly* caught and reverted to shadow by CC's own adversarial verify pass on 2026-07-21. Flipping them to enforce right before an unattended window inverts that judgment for no reason.
- **3-10 oscillator** — structurally cannot finalize in this window. Gated on Outcome Tracking Phase C (unbuilt) plus n≥250 post-Phase-B `both` signals. Say so plainly rather than carrying it as an open item that quietly never closes.

---

## PART 4 — THE PLAN

### WEEK 1 — Jul 22 (Wed) → Jul 26 (Sun): FOUNDATION

*Goal: lift two of three vetoes and repair the layer both dashboards read from.*

| # | Item | Owner | Gate / evidence |
|---|---|---|---|
| **W1-1** | **DEF-POSITION-INTEGRITY** (new brief, P0). SOXS reverse-split correction (qty ÷10, basis ×10); XLF null-strike backfill; negative-price artifact. Predicate-based, pre-image JSONL, `--i-have-go`, row-count invariance, post-apply predicate = 0. | CC | ATLAS veto lifts on applied + independently re-verified |
| **W1-2** | **Reconciliation apply** (rulings locked 7/18, dry-run at `c7df849`): IBKR row DELETE; Fidelity 401a+403b → single `brokerage_link_401k` (Roth untouched); Breakout trade-log INVESTIGATE-ONLY (ATLAS schema proposal first). **Plus `breakout_prop` fake-healthy fix** (Tier 1 #3). | CC | S-6 distance-to-floor unblocks |
| **W1-3** | **`is_test` convention** — boolean + default-exclude in `get_trade_rows()`. Three named rows; `signals.id=14893` is **keep-but-exclude**, not delete. | CC | Abacus foundation prerequisite |
| **W1-4** | **Pythia v2.4 crash fix + coordinated secret rotation.** `math.min(loBinIdx, numBins-1)` clamp. Then, in ONE pass: Railway env var + script input field + re-arm all four alerts. **Partial rotation is forbidden.** | Nick + CC | AEGIS veto lifts |
| **W1-5** | **HELIOS concept session — ≥3 mockups.** Seeds C1 Command Rail / C2 Cockpit Grid / C3 Tape-First. **Must start by Fri 7/24.** | HELIOS + Nick | HELIOS veto fires 7/25 if not started |
| **W1-6** | **TRITON-EXPLORE** (`fb7292a`). Read-only, holdout law absolute. **Must not run concurrent with the audit.** | CC | — |
| **W1-7** | Handoff carry-overs: crypto Discord alert counts by hour for 7/21 (confirm dedup fix stopped the flood *and* didn't over-suppress); `source` eyeball on a fresh live signal; **funding `degraded` duty-cycle characterization** (asked twice, still open). | Coordination | Both shadow gates ride this contract |
| **W1-8** | **Weekly Battlefield Brief** — Sun 7/26. Overdue two runs. | Coordination | — |
| **W1-9** | **Backlog v5** — reconcile ~12 closures since v4. | ATHENA | Arbitration input for Week 2 |

**Also this week, before 7/31:** decide the XLF 53.5/48.5 put spread and XLE 60c (both 7/31 expiry).

### WEEK 2 — Jul 27 (Mon) → Jul 31 (Fri): SIGNALS + SURFACES

| # | Item | Owner | Gate |
|---|---|---|---|
| **W2-1** | **TRITON-AUDIT** — data gate opens Mon 7/27. Pre-registration doc **before** any query. Direction-conditioned, never pooled. | CC | n ≈ 2,400 |
| **W2-2** | **Olympus interpretive pass** on TRITON-EXPLORE output — **FRESH CHAT, not this lane.** DAEDALUS on flow mechanics, PYTHAGORAS on structure, THALES on regime plausibility, **URSA assigned to kill every pattern he can.** Survivors face the matured holdout *after* the audit. | Olympus | — |
| **W2-3** | **Triton verdict + execution** — config flip with rollback criteria, or documented NOT-YET with named re-eval trigger. | CC | Either is complete |
| **W2-4** | **Silent-strategy triage** — Kodiak/Nemesis/Icarus quiet-vs-broken; Apis visibility check; Crypto Scanner CTA-zone re-validation; 3 delisted crypto tickers. | CC | Diagnosis, not promotion |
| **W2-5** | **S-5** — Cycle Extremes single-axis dial + signal #10 (UW ETF-flow). **ATLAS budget sizing against 17K/18K first.** | CC | ATLAS sign-off on call volume |
| **W2-6** | **Alert-floor review** — Mon 7/27, full week of clean post-dedup data. n was 55 across 2 strategies at ratification. | Coordination | Re-check if Crypto Scanner / Funding_Rate_Fade resume |
| **W2-7** | **S-6 brief → Titans final review → build → deploy by Fri 7/31.** | CC | Mockup sign-off recorded first |

### WEEK 3 — Aug 1 (Sat) → Aug 3 (Mon): HARDEN + LEAVE

*This is the thread that did not exist in the original four, and it is the one that defines "done."*

| # | Item | Why |
|---|---|---|
| **W3-1** | **S-6 post-deploy screenshot comparison** vs. approved mockup, recorded in `helios-mockup-track.md`. | HELIOS standing veto; without it the build is not accepted |
| **W3-2** | **Alert-rate circuit breaker.** Hard ceiling on alerts per channel per hour. The CVD burst put 94 alerts up before 10:50 MT on 7/21. That specific bug is fixed; the *class* is not structurally prevented. | Nobody is watching for 14 days |
| **W3-3** | **Shadow-gate audit.** Confirm `gating_enabled` = false, `funding_fade_negative_floor_raise_enabled` = false, ARTEMIS_LONG suppression holding, `crypto_gate_config` at expected id. | An accidental enforce-flip while away is unrecoverable |
| **W3-4** | **Watchdog liveness sweep.** UW budget (17K/18K), PYTHIA per-name staleness, tape-health 15-min job, flow deadfeed. Each must have fired at least once recently. | A dead watchdog and a healthy system look identical |
| **W3-5** | **Strategy-emission flatline watchdog** (Tier 2 #5). | An 18-day silence went unnoticed with an operator present. Vacation is 14 days of guaranteed absence |
| **W3-6** | **Tier-1 #0 fix** — `datetime` handling in the two duplicate `sanitize_for_json()` copies (`redis_client.py`, `broadcaster.py`). ~10 lines. | Redis cache + WebSocket push have been silently failing for every signal, from every source, since written |
| **W3-7** | **Railway `_ENFORCE` flag check** — `WEBHOOK_TV_ENFORCE`, `WEBHOOK_HERMES_ENFORCE`. Five minutes, cannot be verified from the repo. | Unset = accepting unauthenticated webhook writes for two weeks |
| **W3-8** | **Mobile kill-switch reachability test.** Actually trigger it from the phone. | An untested kill switch is a decoration |
| **W3-9** | **Book decision + written rule** — 21 open positions, 8/21 expiries, what happens if a stop-equivalent is hit while away. | — |
| **W3-10** | **Departure handoff note** + backlog v5 final. | — |

---

## PART 5 — WHAT IS BEING CUT, AND WHY

**Abacus v2 UI — deferred to post-vacation (ZEUS Phase III).**

Not a capacity excuse. Three reasons, any one sufficient:

1. **It would be built on numbers that are wrong today.** A P&L/journal/backtest surface reading a position table with an $18,812 phantom is a downgrade, not a feature — a new UI is *trusted more* than the old one, so fabricated numbers do more damage behind it.
2. **The roster it visualizes changes on 07-27.** Triton promotes or doesn't; three silent strategies get reclassified. Designing analytics for a roster that changes mid-build guarantees rework.
3. **It has never been audited.** Two prior rebuilds shipped without one. A third would be the third time.

**What ships instead:** its foundation — W1-1, W1-2, W1-3. When the UI is eventually built, it stands on a position table that is correct, an account table that matches reality, an `is_test` convention that keeps test rows out of live surfaces, and a strategy roster that has stopped moving.

**3-10 oscillator — structurally cannot finalize.** Gated on Outcome Tracking Phase C (unbuilt) plus n≥250 post-Phase-B `both` signals. Stop carrying it as an open item.

---

## PART 6 — THE ONE THING WORTH SAYING PLAINLY

The stated goal is "complete the entire app by Aug 4." The better goal is **"safe to leave running by Aug 4."**

Those produce different plans. Feature-complete produces four half-finished threads and an unverified UI deployed the day before departure. Unattended-safe produces a system with correct position data, a rotated credential, a settled Triton verdict, one properly-gated new surface, and watchdogs that will actually shout if something breaks while nobody is reading.

The second one is achievable in 11 working days. The first one is not, and pursuing it is how the unverified-deploy-before-vacation failure mode happens.

---

## APPENDIX — LEDGER ITEMS NOT TO LOSE

Carried from the 07-21 handoff and the backlog; none are scheduled above, none should be forgotten:

- Stray `source` **file** at repo root — inspect and kill. (Unrelated to the `source` *column* work — name collision only.)
- Strategy → producer mapping doc — ruled to exist *instead of* the declined backfill; nobody assigned.
- `confluence_validation.py` stale source vocabulary (Tier 2 #9) — has matched zero server rows for its entire life; now fixable post-`e8ed614`, scoped to `id ≥ 15678`.
- L0-bypass defect (832-row population) — **STILL OPEN by design**, numerically distinct from DEF-ENRICH-CLOBBER's 148. Do not re-merge.
- VP window truth-in-labeling — 6h × 15m actual vs. 24h × 1H documented, both surfaces.
- Depth-leg alternative vendor (ATLAS) — no fallback when Binance Futures orderbook is unavailable.
- `bars.py` `market_time=='r'` fix — ~4 lines, only matters before ADX-regime Chunk-3 promote.
- LAZR/Robotics upstream score-computation fix — orphaned P3; MCP surface guarded, underlying computation still pinned at 100.0.
- Untracked codex-briefs provenance sweep (Tier 2 #8) — 8 files.
- Hub MCP tool-descriptions spec — 5 tools stale.
- The unexplained 778-minute `age_minutes` sighting from 07-20 — logged as a curiosity, **zero code owed**.
- Desktop Commander pin: npm 0.2.46 (published 7/14) **is** the latest; no newer patch exists. Whether the recommended 0.2.45 pin was actually applied to `claude_desktop_config.json` was **never confirmed.** Fallback 0.2.43. *Still the loose thread from Monday.*
- Lane mechanics: DC and ssh-vps both live inside the Claude Desktop app process. **Leave it running, minimized to tray, on work days.** Instant "No response from server" = cold start, retry once. Full 4-minute hang = app closed or DC dead.
- `mcp__postgres__query` misparses `timestamp without time zone` — reads naive wall-clock as America/Denver, emits a UTC "Z", adding +6h **on display only.** The database is correct. **Always `::text`-cast when timestamps matter.** This fooled both lanes for two days and produced a brief built on a phantom defect.
