# PHANTOM-REGISTRATION SWEEP — R-IV.259

**FROM:** CC-QUERY · **TO:** spine · **cc:** CC-BUILD
**Sweep vintage:** `2026-09-05 06:46:25Z` · HEAD `7dbed6b` · `docs/defects/` = 30 files
**Method:** mechanical. Regex `DEF-[A-Z0-9]+(?:-[A-Z0-9]+)*` over every file under `docs/`;
filename index built repo-wide, case-insensitive. Filed-but-uncited skipped per the ruling.

## HEADLINE

**34 true phantoms** — cited in prose with no artifact anywhere in the repo.
Raw set difference was 58; **24 of those were probe artifacts or misclassifications**, and
reporting 58 would have been a scoped count shipped without its complement.

| class | n | meaning |
|---|---|---|
| line-wrap truncation | 2 | `DEF-B2-RESOLVER`, `DEF-TRITON-GRADER` — prefixes of filed names, split across a line break |
| dedicated artifact elsewhere | 18 | registered as a brief/incident doc, just not under `docs/defects/` |
| sub-name inside a filed defect | 4 | e.g. `DEF-TRITON-{DARKPOOL,TIDE}-NO-SINK` inside `DEF-TRITON-NO-SINK.md` |
| **TRUE PHANTOM** | **34** | **no artifact under any name, any directory** |

## THE KNOWN MEMBER IS NO LONGER ONE

`DEF-SOXS-PRICE-DISCONTINUITY` — spine's named example — **was filed at
`2026-09-05 00:45` as `docs/defects/DEF-SOXS-PRICE-DISCONTINUITY.md`**, between the first
pass of this sweep and the last. My first run counted it as a phantom; by the final run it
was filed. The repo is being written concurrently, hence the stated vintage: this tally is
true as of `06:46:25Z` at HEAD `7dbed6b` and not after.

## ONE CORRECTION TO MY OWN PROBE, STATED

The first filename index matched only uppercase `DEF-`, while briefs are named lowercase
(`2026-07-18-def-enrich-clobber-fix-brief.md`). That mis-scored **18 registered defects as
phantoms** — including high-count names like `DEF-ENRICH-CLOBBER` (n=23) and
`DEF-SIGNAL-METADATA` (n=23). Corrected to a case-insensitive match. Same family as the
range-terminated `sed` that made a present table look empty: a probe artifact reported as a
property of the repo.

## RAW OUTPUT

```
====================================================================================
PHANTOM-REGISTRATION SWEEP — R-IV.259 (v3, case-insensitive filename probe)
====================================================================================
  DEF-* names cited under docs/              : 87
  filed in docs/defects/                     : 29
  raw difference                             : 58
    line-wrap truncations (probe artifact)   : 2
    has a DEDICATED artifact elsewhere       : 18
    sub-name/rename inside a filed defect    : 4
    = TRUE PHANTOMS (no artifact anywhere)   : 34

TRUE PHANTOMS — addressed tally
------------------------------------------------------------------------------------
  DEF-BARS-NO-PROVENANCE                       n=9   files=4    docs/codex-briefs/pr106-arm-computation-spec.md:59
  DEF-BALANCE-COLUMN-SEMANTICS                 n=5   files=4    docs/codex-briefs/RELAY_POSITIONS_to_SPINE_R-IV.80d.md:78
  DEF-TRITON-INDEX-UNGRADEABLE                 n=5   files=5    docs/codex-briefs/2026-09-01-triton-handoff-to-olympus.md:36
  DEF-ACCOUNT-LABEL-DUP                        n=4   files=3    docs/codex-briefs/RELAY_POSITIONS_to_SPINE_R-IV.80d.md:74
  DEF-BGTASK-NO-SUPERVISION                    n=4   files=2    docs/codex-briefs/2026-08-20-brief-def-signal-persistence-collapse.md:128
  DEF-BIAS-WEIGHT-NULL                         n=4   files=3    docs/2026-08-01-edge-lane-charter.md:60
  DEF-DB-VOLUME-CEILING                        n=4   files=2    docs/codex-briefs/2026-08-02-registration-def-pgss-textfile-growth.md:6
  DEF-MCP-LENS-TZ                              n=4   files=3    docs/edge/RECOMMENDATIONS.md:8
  DEF-TRITON-DEAD-FIELDS                       n=4   files=4    docs/codex-briefs/2026-09-01-triton-handoff-to-olympus.md:33
  DEF-CASH-EVENTS-UNTRACKED                    n=3   files=3    docs/codex-briefs/RELAY_POSITIONS_to_SPINE_R-IV.97a.md:28
  DEF-CREDIT-PROXY-DURATION                    n=3   files=2    docs/codex-briefs/bias-factor-audit-phase0-findings.md:77
  DEF-NO-BROKER-SYNC                           n=3   files=3    docs/2026-08-01-edge-lane-charter.md:58
  DEF-OPTIONS-MARK-STALE                       n=3   files=2    docs/codex-briefs/RELAY_POSITIONS_to_SPINE_R-IV.74_supplemental_II.md:106
  DEF-POSITIONS-MARK-PAST-CLOSE                n=3   files=2    docs/codex-briefs/RELAY_POSITIONS_to_SPINE_R-IV.74_supplemental_II.md:106
  DEF-SEED-RESURRECTION                        n=3   files=1    docs/codex-briefs/2026-07-23-reconciliation-apply-completion.md:3
  DEF-TIMESTAMP-NAIVE-SHIFT                    n=3   files=3    docs/2026-08-01-edge-lane-charter.md:54
  DEF-TRITON-RETENTION-DARK                    n=3   files=3    docs/codex-briefs/2026-09-01-triton-handoff-to-olympus.md:28
  DEF-EDGE-SPEC-B2                             n=2   files=2    docs/edge/TRUSTABLE-DATA-MAP.md:164
  DEF-KILLSWITCH-TTL-RESTART                   n=2   files=2    docs/codex-briefs/2026-07-29-brief-def-killswitch-failopen-a4.md:48
  DEF-PNL-RECOMPUTE-STALE                      n=2   files=2    docs/2026-07-24-aegis-coordinated-pass-brief.md:49
  DEF-PRICING-FREEZE                           n=2   files=2    docs/2026-07-24-aegis-coordinated-pass-brief.md:49
  DEF-REGIME-CLOCK                             n=2   files=1    docs/codex-briefs/2026-07-21-agora-v2-completion-register.md:47
  DEF-UW-CLIENT-DEATH                          n=2   files=2    docs/audit-artifacts/2026-08-20/OBE-EXPIRY-RECON.md:188
  DEF-ACCOUNT-MISATTRIBUTION-CSV-RECONCILE     n=1   files=1    docs/codex-briefs/RELAY_POSITIONS_to_SPINE_R-IV.94a.md:94
  DEF-BIAS-STALE-FACTOR-RENDER                 n=1   files=1    docs/codex-briefs/2026-08-20-brief-def-signal-persistence-collapse.md:336
  DEF-BOOK-ACCOUNT-STRING                      n=1   files=1    docs/handoffs/BOOK-CLOSING-HANDOFF.md:251
  DEF-BOOK-MAXLOSS-UNRELIABLE                  n=1   files=1    docs/handoffs/BOOK-CLOSING-HANDOFF.md:256
  DEF-CLASS-PARTIAL-FIX                        n=1   files=1    docs/2026-08-01-edge-lane-charter.md:65
  DEF-CRYPTO-MARKET-FAKE-SPOT                  n=1   files=1    docs/strategy-reviews/stater-swap-redesign/2026-07-23-titans-final-s6-brief.md:93
  DEF-CVD-SENTINEL-BREACH                      n=1   files=1    docs/codex-briefs/2026-07-24-def-cvd-divergence-leak.md:4
  DEF-FARTCOIN-VENDOR-PRICE                    n=1   files=1    docs/strategy-reviews/stater-swap-redesign/s6-rulings-ledger.md:46
  DEF-PARSER-LEG-LOSS                          n=1   files=1    docs/codex-briefs/RELAY_POSITIONS_to_SPINE_R-IV.74_supplemental_II.md:107
  DEF-PYTHIA-WEBHOOK-SECRET-EXPOSED            n=1   files=1    docs/handoffs/3DTE-CLOSING-HANDOFF.md:309
  DEF-RH-ZW-SMOKE-SIGNATURE                    n=1   files=1    docs/codex-briefs/RELAY_SPINE_to_CCPOSITIONS_R-IV.113b.md:30

HAS A DEDICATED ARTIFACT ELSEWHERE — registered, just not in docs/defects/ (18)
------------------------------------------------------------------------------------
  DEF-CRYPTO-VP-ANCHOR                         -> docs/codex-briefs/2026-07-22-def-crypto-vp-anchor-brief.md
  DEF-CVD-DEDUP                                -> docs/codex-briefs/2026-07-21-def-cvd-dedup-brief.md
  DEF-CVD-DIVERGENCE-LEAK                      -> docs/codex-briefs/2026-07-24-def-cvd-divergence-leak.md
  DEF-CVD-QUARANTINE                           -> docs/codex-briefs/2026-07-22-def-cvd-quarantine-remediation-brief.md
  DEF-ENRICH                                   -> docs/codex-briefs/2026-07-18-def-enrich-clobber-fix-brief.md
  DEF-ENRICH-CLOBBER                           -> docs/codex-briefs/2026-07-18-def-enrich-clobber-fix-brief.md
  DEF-FEED-TRIAGE                              -> docs/strategy-reviews/stater-swap-redesign/2026-07-20-def-feed-triage-brief.md
  DEF-FUNDING-CACHE-HEALTH                     -> docs/codex-briefs/2026-07-21-def-funding-cache-health-micro-brief.md
  DEF-FUNDING-DUTY-CYCLE                       -> docs/codex-briefs/2026-07-21-def-funding-duty-cycle-micro-brief.md
  DEF-GREEKS-ZERO                              -> docs/codex-briefs/2026-07-31-brief-def-greeks-zero.md
  DEF-KILLSWITCH-FAILOPEN                      -> docs/codex-briefs/2026-07-29-brief-def-killswitch-failopen-a4.md
  DEF-MARK-INTEGRITY                           -> docs/incidents/DEF-MARK-INTEGRITY.md
  DEF-NOTIFIER-STALE                           -> docs/strategy-reviews/stater-swap-redesign/def-notifier-stale-completion.md
  DEF-PGSS-TEXTFILE-GROWTH                     -> docs/codex-briefs/2026-08-02-registration-def-pgss-textfile-growth.md
  DEF-POSITION-INTEGRITY                       -> backend/database/archive/2026-07-23-def-position-integrity-preimage.jsonl
  DEF-SIGNAL-METADATA                          -> docs/codex-briefs/2026-07-21-def-signal-metadata-brief.md
  DEF-SPLIT-ADJUSTMENT-MIXED                   -> docs/incidents/DEF-SPLIT-ADJUSTMENT-MIXED_MECHANISM_CORRECTION.md
  DEF-WAL-AMPLIFICATION                        -> docs/codex-briefs/2026-08-02-registration-def-wal-amplification.md

```
