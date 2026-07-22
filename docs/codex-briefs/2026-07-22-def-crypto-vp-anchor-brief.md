# BRIEF — DEF-CRYPTO-VP-ANCHOR

**Authored:** 2026-07-22, coordination lane
**Severity:** **P0** — fake-healthy. Confidently wrong structural levels served to the committee with `vp_status: "ok"`.
**Discovered:** Olympus crypto verification pass, 2026-07-22. Pre-existing defect; not caused by the crypto-state work.
**Type:** data-pipeline defect + fail-closed guard. Two fixes, shippable independently.
**Titans review:** ATLAS required — data-integrity invariant on a committee-facing surface.

---

## TASK 0 — FILING

```
cd /d C:\trading-hub
git fetch origin && git status
git mv 2026-07-22-def-crypto-vp-anchor-brief.md docs\codex-briefs\
git add docs/codex-briefs/2026-07-22-def-crypto-vp-anchor-brief.md
git commit -F C:\temp\commitmsg.txt
git push origin main
```

---

## THE DEFECT

`hub_get_crypto_market_profile` returns a volume-profile value area that sits **entirely outside the price range the symbol has actually traded**, while reporting `vp_status: "ok"`.

**Verified independently by the coordination lane, both symbols, 2026-07-22:**

| Symbol | POC | VAH | VAL | Session low | VA vs session |
|---|---|---|---|---|---|
| BTC | 63,107.68 | 63,155.16 | 62,756.36 | **65,484.00** | **−3.6%, no overlap** |
| ETH | 1,835.31 | 1,838.15 | 1,825.17 | **1,911.56** | **−3.9%, no overlap** |

Cross-checked against `hub_get_crypto_quote` for BTC three seconds apart (UW, `status: live`, ts 13:09:48Z): **`low_24h` = 65,484.00, `high_24h` = 66,923.95.** The POC sits **2,376 points below the lowest price BTC traded in the last 24 hours.**

The tool documents the profile as "computed from the last 24 hours of 1H klines (50 bins)." Volume cannot accumulate at a price that never traded. On a shared 24-hour window this is arithmetically impossible.

### Two independent signatures, and they agree

1. **Anchored low.** Both symbols ~3.6–3.9% below their session range, same direction, similar magnitude. Consistent offset implies a systematic window error, not random corruption.
2. **Implausibly narrow.** BTC's value area is 399 points (0.63%); ETH's is 12.98 points (0.71%). A real 24-hour value area on either is typically several times wider.

Both point the same way: **the profile is being computed on a window that is too short AND too old.**

### Internal control — the defect is isolated to the VP leg

Same tool, same call: BTC's `session_low` returns **65,484.00**, matching the quote's `low_24h` **exactly**. The session-partition leg (15m bars via `crypto_sessions.py`) is reading current data correctly. Only the VP leg is anchored elsewhere.

That rules out a whole-tool outage, a symbol mismatch, or a vendor-wide failure, and localizes the fault to the kline fetch or the window computation feeding the profile.

### This is already in the backlog, filed one class too low

`docs/build-backlog.md` carries **"VP window truth — 6h × 15m actual vs 24h × 1H documented, both surfaces"** as a truth-in-labeling item: docs wrong, data assumed fine.

**The data is also wrong.** A 6h × 15m window ending *now* would still contain current prices — it would produce a narrow value area, but not one 3.6% below the traded range. The window is not merely mislabeled; it is **anchored to a stale start**. Reclassify from documentation P3 to data P0.

### Why it matters

`vp_status: "ok"` — not stale, not degraded. **Confidently wrong is the fake-healthy class**, P0 by `PROJECT_RULES.md`.

In the 2026-07-22 committee pass this contaminated the load-bearing structural read: PYTHIA ("spot ~4% above VAH — out of value, unsupported by volume acceptance") and PYTHAGORAS ("above the 24h POC and VAH — upper LVN, no volume acceptance beneath") both built their primary read on a phantom value area, and PIVOT cited "price above value" in its synthesis. The DON'T TRADE verdict survived — it was overdetermined — but the reasoning was contaminated.

**This is the crypto twin of the 2026-07-02→07-15 PYTHIA stale-MP incident:** levels that looked healthy, silently anchored to old input, degrading committee reasoning for two weeks before anyone noticed. Same detection gap — `vp_status` reflects *computation* recency, never *input* recency. Fresh computation on stale input reads as healthy.

---

## PHASE 0 — FIND THE WINDOW (stop-gate)

**Do not add the guard before understanding the cause.** A guard alone converts a lie into an honest `unavailable`, which is better but still leaves the committee without crypto structure.

1. **Locate the VP computation.** Name file and line. Report the **actual** kline window: lookback duration, bar interval, bin count, and — critically — **how the window's start and end timestamps are derived.**
2. **Is the end anchored to `now`, or to something fixed/cached?** The ~3.6–3.9% consistent offset is the strongest clue. Look for a cached kline slice, a fixed anchor, an off-by-one on the window boundary, or a fetch that silently returns an old page.
3. **Reconcile against the documented contract.** Docs say 24h × 1H; the backlog says 6h × 15m actual. Report what the code does **today**, and whether the docs or the backlog is right.
4. **Kline source.** Which vendor and which pair? The quote is UW-sourced; `basis` reports `binance_vision+binance_futures`. If the VP klines come from a different venue or pair than the quote, state it — though a venue difference cannot explain 3.6%.
5. **All six symbols.** BTC and ETH are confirmed. Check SOL, HYPE, ZEC, FARTCOIN and report the matrix.
6. **Does the equity path share this code?** `hub_get_market_profile` is the same class of tool and the PYTHIA incident was on the equity side. If the window logic is shared or duplicated, **this brief's scope extends to it** — report before deciding.
7. **Historical blast radius, bounded.** If VP output is persisted anywhere, determine roughly when POC last fell inside the 24h range. If it is not persisted, say so and stop — do not reconstruct from proxies.

**If Phase 0 contradicts anything above, the brief is wrong, not the codebase.** Report and stop.

---

## PHASE 1 — FIX

Two changes. **Ship the guard even if the root cause takes longer** — the tool is lying to the committee right now.

### 1.1 — The guard (fail-closed, ship first)

Assert at compute time that the profile is consistent with the traded range. **On violation, return `degraded` or `unavailable` with a stated reason. Never serve the values.**

**Design constraint that is the entire point of this brief: the check must cross-reference an INDEPENDENT data path.** A self-consistency check — deriving high/low from the same klines that built the profile — would have **passed today**, because stale klines are internally consistent. That is precisely the trap: *corroboration through a shared instrument is not corroboration.*

Two acceptable references, in preference order:

- **Preferred, and free:** the tool's own `session_high`/`session_low`, which come from a genuinely different pipeline (15m bars via `crypto_sessions.py`) and were **provably correct today**. The current session is a subset of the 24h window, so the profile's range must contain it. Minimum viable invariant: **flag if `VAH < session_low` or `VAL > session_high`** — the value area lying entirely outside the session. Catches today's case on both symbols with no new call.
- **Stronger, costs one read:** cross-check against `hub_get_crypto_quote`'s `low_24h`/`high_24h`, asserting `low_24h ≤ VAL ≤ VAH ≤ high_24h` and `low_24h ≤ POC ≤ high_24h`. Confirm with ATLAS whether the extra read is acceptable.

Use the session-based check as the floor. Add the quote check if ATLAS clears it.

### 1.2 — The root cause

Fix per Phase 0's finding. If the window is stale-anchored, anchor it to `now`. If the documented contract and the implementation disagree, **fix the implementation to match the documented 24h × 1H and correct the docs if the intent was always 6h × 15m** — but do not leave the two surfaces disagreeing, which is how this stayed invisible.

---

## PHASE 2 — VERIFY

**The repro exists right now.** Both symbols, live.

1. **Regression test that fails pre-fix.** State explicitly that it fails against current code. A value area entirely below the session range must be rejected.
2. **Live post-deploy, all six symbols.** Either the VP falls inside the traded range, or the tool honestly reports `degraded`/`unavailable`. **Silently serving today's values is the one unacceptable outcome.**
3. **Cross-tool consistency check on BTC and ETH:** POC/VAH/VAL within `hub_get_crypto_quote`'s `low_24h`/`high_24h`.
4. **Sanity on width.** Post-fix, a 24h value area should be materially wider than 0.65%. If it is still ~0.65%, the window is still too short and the root cause is not fixed — report rather than accept.
5. **Confirm the session leg is untouched.** It was correct throughout; regression here would be self-inflicted.
6. Full suite. Bar: byte-identical known-red **18 failed / 1 skipped / 200 errors**, passed rises by the new test count.
7. Four-step deploy verification.

---

## DONE DEFINITION

1. Phase 0 reports the actual window with named file/line and the derivation of its boundaries.
2. Equity-path scope question answered before any fix lands.
3. Guard shipped, cross-referencing an independent path — never self-consistency.
4. Root cause fixed, or explicitly deferred with the guard live and the reason stated.
5. Regression test demonstrably failing pre-fix.
6. All six symbols verified post-deploy: correct values or honest degradation.
7. Value-area width sanity-checked.
8. Known-red byte-identical; four-step deploy verified.
9. `workstreams.md` updated; the backlog's "VP window truth" item reclassified from P3 documentation to P0 data, annotated in place rather than deleted.

---

## OUT OF SCOPE

- `hub_get_crypto_state` — unaffected. Its blocks are unrelated to the volume profile.
- The equity `hub_get_market_profile` — **unless Phase 0 finds shared window logic**, in which case report before proceeding.
- The FARTCOIN committee pass (check #4 under load) — separate, and not blocked by this.
- `cta_zone` placement on degraded blocks — separate doc-level finding.

---

## OLYMPUS IMPACT

**Direct and currently negative.** PYTHIA's crypto lane is built on this tool; PYTHAGORAS falls back to it for stop distance because crypto ATR is not served. Both are consuming wrong levels today.

Post-fix, run **one crypto committee pass on BTC** and confirm PYTHIA's structural read changes materially from the 2026-07-22 pass. If her read is unchanged after the levels move several percent, she is not actually consuming the tool and that is a second finding.

**Annotate the 2026-07-22 verification pass in place** — all seven acceptance checks genuinely passed and that stands, but the ground truth carried this defect and the PYTHIA/PYTHAGORAS/PIVOT structural reads are contaminated. Correct the record; do not delete it.
