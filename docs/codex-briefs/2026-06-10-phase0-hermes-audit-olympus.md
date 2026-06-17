# Phase 0 Brief — Hermes Audit + Olympus Integration Assessment

**Date:** 2026-06-10 | **Author:** Architecture layer | **Builder:** Claude Code
**Mode:** READ-ONLY INVESTIGATION. No code, schema, migrations, deploys, UI changes.
**Gate:** Produce `docs/phase0-hermes-audit-findings.md`, then STOP for review.
**Queue position:** AFTER sub-brief 3 Phase 1 and global-webhook-hardening
Phase 1 gates clear. Do not start while those two builds are mid-flight unless
Nick explicitly reprioritizes.

---

## Why this exists

Nick's own words: "I'm not really sure what Hermes is doing for me." A feed
that fires ~9 TV alerts, commands VPS scrape bursts, and writes catalyst_events
+ lightning_cards, whose owner can't state its value, gets AUDITED before it
gets expanded. This brief answers three questions in strict order — and only
the third is about building anything:

1. **What is Hermes actually doing?** (data + UI audit)
2. **Does Olympus already consume it?** (wiring audit — likely partial)
3. **Should it inform Olympus more, and how should it surface to Nick?**
   (design — only if 1 and 2 justify it)

If Q1 reveals Hermes earns little keep, the honest outcome may be RETIRE or
SIMPLIFY, not integrate. The audit must be allowed to reach that verdict.

---

## Hard rules
1. Read-only. `git fetch && git status` first. DB inspection via the
   `railway run` + proxy pattern, SELECTs only.
2. Verify against live data and live UI, not memory or skill text. The skills
   *mention* Hermes (TORO/URSA/THALES/PYTHAGORAS/DAEDALUS/PYTHIA all reference
   `hub_get_hermes_alerts`) — but a mention in a skill is NOT proof the tool
   is wired, returns data, or is read in a live pass. Test each link.
3. No verdict-shopping: if Hermes is valuable, say so; if it's dead weight,
   say so. Evidence decides.
4. Folds in the breadcrumbs the hardening session was asked to jot in passing.
5. STOP at the gate report.

---

## T1 — What Hermes writes (data audit)
a. Trace the write path: `/api/webhook/hermes` handler → what rows land in
   `catalyst_events`, what creates `lightning_cards`, what the VPS scrape
   burst does (what it scrapes, how often, where output lands).
b. Live volume: over the last 30 days, how many catalyst_events / lightning
   cards were created? How many are stale, duplicate, or never surfaced?
c. The 9 alert tickers (IBIT/GLD/USO/TLT/IYR/HYG/XLF/SMH/SPY/QQQ per the
   alert log) — fire frequency each. Which are live vs dormant.
d. Data quality: are the catalyst events accurate/timely, or noisy? Sample
   a handful against known recent catalysts (earnings dates, Fed days).

## T2 — How Hermes surfaces to Nick (UI audit)
a. Where do lightning_cards render in Agora? Screenshot-equivalent: which
   view, how prominent, what the card shows.
b. Is there any interaction (dismiss PATCH exists — is it used)? Any signal
   that Nick has engaged with these cards historically?
c. HELIOS-lane read: is the current presentation legible and actionable, or
   is it noise Nick has learned to ignore? (This likely explains "not sure
   what it's doing for me.")

## T3 — Does Olympus already consume Hermes? (wiring audit)
a. Does `hub_get_hermes_alerts` exist as a live hub MCP tool? Confirm in the
   tool registry (the 13-tool list) — present or not.
b. If present: what does it return on a live call, and is it ACTUALLY invoked
   in a committee pass, or only named in skill prose? Trace each skill's
   reference — is Hermes in any agent's Context-A call sequence, or just
   mentioned in passing?
c. `committee_bridge.py` — does the pre-review data sequence pull Hermes
   alerts (memory claims a "Hermes alerts" step #4)? Verify in code; confirm
   it's live, not aspirational.
d. Net verdict: Olympus's current Hermes access = NONE / NAMED-BUT-UNWIRED /
   PARTIALLY-WIRED / FULLY-WIRED. This determines whether Q3 is "wire it" or
   "improve existing wiring" or "nothing to do."

## T4 — Should it inform Olympus more? (design — only if T1-T3 justify)
a. If catalyst data is valuable and under-consumed, which agents legitimately
   want it? Prior: THALES (catalyst = macro/fundamentals lane) and URSA
   (event risk) are the natural homes; TORO for upside catalysts. NOT PYTHIA
   (structural lane) or DAEDALUS (options-structure lane) unless evidence
   says otherwise.
b. Propose the wiring shape WITHOUT choosing: new Context-A tool call vs
   committee_bridge enrichment vs a THALES-trigger condition. Each with cost.
c. UI recommendation (HELIOS lane): keep / redesign / demote / remove the
   lightning-card surface, based on T2.
d. Honest alternative: if the audit shows low value, spec the RETIRE path
   (drop the endpoint, alerts, cards) and what it frees up.

---

## Gate report — required output
`docs/phase0-hermes-audit-findings.md` with:
1. What Hermes writes + 30-day volume/quality evidence (T1)
2. UI surface audit + Nick-engagement read (T2)
3. Olympus wiring verdict: NONE / NAMED-BUT-UNWIRED / PARTIAL / FULL (T3)
4. Recommendation: INTEGRATE (with shape) / IMPROVE / DEMOTE / RETIRE,
   evidence-backed (T4)
5. If INTEGRATE: which agents, wiring options (no final choice), cost each
6. UI recommendation (HELIOS lane)
7. Olympus Impact note — any change touching THALES/URSA/committee_bridge
   needs a post-build full committee regression on a known-good ticker
8. Open questions for Nick

Then **STOP.** This is an assessment, not a build. The verdict (integrate
vs retire) is Nick's to make from the evidence; no code until a separate
greenlit build brief.

---

## Scope guard
This brief does NOT touch the security hardening of the Hermes endpoint —
that ships in the global-webhook-hardening sprint (Chunk B) independent of
this audit's verdict. A door gets locked whether or not the room stays
furnished. Keep the two concerns separate.
