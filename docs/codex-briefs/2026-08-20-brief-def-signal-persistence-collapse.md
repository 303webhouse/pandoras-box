# FIX BRIEF — DEF-SIGNAL-PERSISTENCE-COLLAPSE (P0)
**MANIFEST: 10 sections, numbered 0–9. Spine echoes this count before grading.**
**Author:** CC-BUILD · **Rev:** v2 (v1 revised against R-IV.28(e) pre-signals 1–5)
**Governing SHA:** 2de26c6 · **Status:** DRAFT, awaiting ATLAS-lens grade
**Deploy class:** HARDENING (T1-EARLY proved full restoration; no live outage)
**Ships:** the freeze's first and only cleared push (R-IV.7(i))

---

## 0 · MECHANISM OF RECORD

> A non-finite Python float reaches `json.dumps` (default `allow_nan=True`), which emits the bare
> tokens `NaN` / `Infinity` / `-Infinity`. These are valid JavaScript and **invalid JSON**. Postgres
> rejects the bind: `invalid input syntax for type json`, `DETAIL: Token "NaN" is invalid.`
> The exception is caught, logged, and execution continues — so the pipeline reports success on a
> row that does not exist.

Signature, as reframed by spine: **healthy writer, per-row JSONB rejection of a globally poisoned
payload.** The sole `INSERT INTO signals` (`postgres_client.py:1646`, verified 1 hit repo-wide)
binds 37 columns of which exactly two are JSONB — `$19 triggering_factors` (`:1681`) and
`$20 bias_at_signal` (`:1682`). By elimination the failing bind is one of those two.

**Retracted (CC-BUILD, refuter-caught pre-ship):** the ATR/enrichment attribution. `enrich_signal()`
runs at `pipeline.py:1447`, **69 lines after** `log_signal()` at `:1378`; the `ATR=nan` line is
emitted *after* that signal's INSERT was already attempted. Adjacent log lines belong to different
signals. `enrichment_data` is not in the INSERT at all — every enrichment write is an `UPDATE`, and
an UPDATE cannot delete a row that never existed. Lost signals include `SOL-USD_*`, and
`signal_enricher.py:53-54` returns early for CRYPTO before any enrichment dict exists. **ATR NaN is a
concurrent non-lethal decoy.**

**Poison-entry bracket:** (07:17:00Z, 13:23:37.8Z] on 08-18. Source condition cleared by
**22:30:31Z 08-19** — the first successful write, which is the only defensible upper bound.
**The clearing MECHANISM is FORMALLY OPEN (LETH-1):** no write was attempted in
[22:02:11Z → 22:27:44Z], so restart/container-wipe cannot be distinguished from independent
clearing inside that attempt-free interval. Citing 22:27Z would assert the restart as the
clearing agent on no evidence.

**UNPROVEN candidate — and it must stay unproven in this document.**
`bias_at_signal["scheduler_bias"]`, sourced `bias_snapshot.py:30-34` → `_load_bias_history()` →
`data/bias_history.json`, written `json.dump(..., default=str)` and read `json.load` — both
NaN-permissive — carrying ~40 nested float leaves from pandas/yfinance frames, global to every
signal, and **untracked in git**, so on Railway it lives on ephemeral container FS. A poison written
there survives one container lifetime and is wiped by the next deploy, which matches the deploy
bracket. **This cannot be proven: the value is retained nowhere.** It is named as a candidate, not a
cause. **The fix does not depend on resolving it** — it closes the class, not the instance.

---

## 1 · BLAST RADIUS — CENSUS OF RECORD

`write_signal_outcome` (`pipeline.py:1382-1385`) runs six lines after `log_signal`, in a **separate
transaction**, binds **no JSON**, and succeeded throughout. Orphan `signal_outcomes` rows are
therefore an exact census — a better instrument than log-line counting.

| UTC day | `signals` | `signal_outcomes` | orphaned |
|---|---|---|---|
| 2026-08-17 | 140 | 140 | 0 |
| 2026-08-18 | 2 | 251 | **249** |
| 2026-08-19 | 4 | 214 | **210** |
| 2026-08-20 | 205 | 203 | **0** |

**459 signals lost.** T6-C's 188/128 were floors, as flagged at filing, and are superseded.
100% of sources; 97 distinct symbols on 08-18, 95 on 08-19 — global, not per-ticker.

---

## 2 · SCOPE FENCE

Live schema: **48 JSONB columns across 33 tables.**

| Metric | Count |
|---|---|
| JSONB bind **statements** under `backend/` | **43** |
| **Column-level** JSONB binds | **53** |
| Float-reachable | **41 of 52 live** |
| Using `json.dumps` **without** `allow_nan=False` | **53 / 53** |
| Using `psycopg2.extras.Json` or an asyncpg codec | **0** (`grep set_type_codec` → 0) |
| `isnan` / `isfinite` / `allow_nan` anywhere in `backend/` | **0** |
| Routed through `sanitize_for_json` | **6–9** (the other ~34 call bare `json.dumps`) |

Two independent enumerations (AST-resolved SQL vs callee-agnostic string scan) both returned **43**.
656 execute-family calls scanned, 12 statically unresolvable, all 12 read, all `SELECT`.
**Residual uncertainty inside `backend/` is zero.**

**The sanitizer is not a guard.** `utils/json_sanitize.py:22-49` has no non-finite branch, and its
numpy path (`return float(obj)`) converts a numpy NaN into a Python NaN. A bare `float('nan')` exits
at `return obj` untouched.

**Two adopted widenings:** `Infinity`/`-Infinity` are a second invalid-token class (a NaN-only fix
leaves a live hole); and **`json.loads` accepts `NaN`**, so caches are reservoirs (§7).

---

## 3 · WHY IT WAS INVISIBLE FOR TWO DAYS

`pipeline.py:1376-1386`, verbatim:

```python
    # 4. Persist to PostgreSQL
    try:
        await log_signal(signal_data)          # return value DISCARDED
    except Exception as e:
        logger.error(f"Failed to log signal: {e}")   # swallowed, continues

    # Write PENDING outcome record for accuracy tracking
    try:
        await write_signal_outcome(signal_data)      # separate txn — SUCCEEDS
    except Exception as e:
        logger.warning(f"Failed to write signal outcome: {e}")
```

`log_signal` returns `inserted: bool` (`postgres_client.py:1708-1712`); the caller discards it.
`pipeline.py:1560` then logs `✅ Pipeline complete`. **That is the ghost-id factory**, and it is why
459 orphan outcome rows exist while the signals table stayed empty.

A second silent path shares the symptom with **no error line at all**: the INSERT ends
`ON CONFLICT (signal_id) DO NOTHING`, so a duplicate `signal_id` yields a ghost id and only a
`logger.warning` inside `postgres_client.py`.

**Swallow census** (AST-derived, `signals/` + `enrichment/` + `jobs/`): **139** broad handlers,
**139/139** `except Exception`, **0** re-raise, **109** log-and-continue swallows, **30** silent
(16 `pass`-only), **26** with a DB write in the `try` body. `pipeline.py` alone holds 53.
Remediation beyond the write path is REC-008, not this brief.

**Supervision: NOTHING restarts the signals writer.** `add_done_callback` → 0 repo-wide. No
supervisor, no retry wrapper, no Railway `healthcheckPath`/`restartPolicy`, **0 clients of
`/health`**. `Procfile` is a single unmanaged uvicorn. Railway restarts only on **process exit**, and
a dead background task never exits the process. This is DEF-BGTASK-NO-SUPERVISION (P2), registered,
post-fix queue — named here because it explains the 39.2-hour non-recovery, not fixed here.

---

## 4 · CR-1 VERDICT (chartered; mechanism no longer depends on it)

**L0 cannot be the cause.** `SUPPRESS_ALWAYS` membership is tested at exactly **2 lines repo-wide**
(`l0_routing.py:107`, `:109`), reachable only via `evaluate_l0_gate()`, which has **exactly 1
production caller** (`pipeline.py:1210`) that is pure, non-blocking, and never diverts.
`should_divert()` has **0 production call sites**. Of 10 production invocations the other 9 are
read-side and sit **after** persistence.

Independent, code-based confirmation of `ae99def`'s exoneration. The stale crypto-bypass docstring at
`l0_routing.py:29-34` rides the future L0 hygiene commit (R-IV.10(6)), not this brief.

---

## 5 · THE FIX

### STEP 0 — WORKTREE SEPARATION (R-IV.7(h)) — precondition, local-only, no push
```
git -C C:\trading-hub worktree add C:\th-build -b fix/def-signal-persistence-collapse
```
All work happens in `C:\th-build`. The shared clone is not touched. This is the structural corrective
for both case-law-(a) events.

### STEP 1 — Close the class at the serializer (`utils/json_sanitize.py`)

Non-finite → `None`, **never `0`**, never silent (GREEKS-ZERO precedent), with a field-level
degraded marker:

```python
import math

_NONFINITE = "_degraded_nonfinite"     # dotted paths coerced to null

def sanitize_for_json(obj, _path="", _degraded=None):
    if isinstance(obj, float) and not math.isfinite(obj):
        if _degraded is not None:
            _degraded.append(_path or "<root>")
        return None
    ...  # existing dict / list / datetime / date / Decimal / numpy branches,
         # each threading _path and _degraded; numpy float branch must test
         # isfinite AFTER float(obj), since float(np.float64('nan')) is still NaN

def dumps_jsonb(obj):
    """THE chokepoint for every JSONB bind. Non-finite -> null + degraded flag."""
    degraded = []
    clean = sanitize_for_json(obj, _degraded=degraded)
    if degraded and isinstance(clean, dict):
        clean[_NONFINITE] = degraded          # field-level degradation, row still lands
    return json.dumps(clean, allow_nan=False) # assertion: a bare token is now unreachable
```

**Design law honoured:** *field-level degradation must not cost the row.* The row lands with a null
field and a named degraded path instead of vanishing. `allow_nan=False` asserts the sanitizer worked;
if it ever raises, that is a sanitizer bug and Step 4's control catches it pre-deploy.

### STEP 2 — Route all **43 statements / 53 column binds** through it

Sequenced so review is possible:
- **2a — captured vector (2 binds):** `postgres_client.py:1681`, `:1682`.
- **2b — `signals` remainder (7 binds):** `postgres_client.py:2112`; `signal_enricher.py:287`
  *(bare `json.dumps`, no sanitizer at all — worse than the INSERT path)*; `api/signals.py:100`;
  `api/committee_bridge.py:143`; `scoring/score_v2.py:345`; `enrichment/context_modifier.py:365`;
  `api/unified_positions.py:1567`.
- **2c — remaining 44 binds** (`composite.py`, `bias.py`, `crypto_dual_write_shadow.py`,
  `analytics/queries.py`, …): mechanical substitution only.

Every changed line is a serializer swap. **No behavioural change to any already-finite payload** —
which is the entire current corpus (T1-EARLY: 109/109 landed).

### STEP 3 — Completion status = persistence outcome

`pipeline.py:1376-1380` captures the boolean and propagates it. `pipeline.py:1560` renders
`✅ Pipeline complete` **only on a landed row**, and `❌ Pipeline FAILED — row not persisted`
otherwise. `log_signal` already returns `inserted: bool`; no signature change. The
`ON CONFLICT DO NOTHING` duplicate path renders as **dedupe**, distinct from failure, so a dedupe
never reads as data loss nor vice-versa.

### STEP 4 — Tests, including the deploy-gating control (REC-007 A4 precedent)

Matrix, per R-IV.28(e)(3) — **both bind targets × both injection shapes × all three token types:**

| # | target | shape | value | assertion |
|---|---|---|---|---|
| 1 | `$19 triggering_factors` | global field | `NaN` | row lands · field null · path named · `inserted True` |
| 2 | `$19` | per-field leaf | `NaN` | as above, sibling fields intact |
| 3 | `$20 bias_at_signal` | global field (`scheduler_bias` nested) | `NaN` | as above |
| 4 | `$20` | per-field leaf | `NaN` | as above |
| 5 | `$19` / `$20` | both shapes | `Infinity` | as above — second token class |
| 6 | `$19` / `$20` | both shapes | `-Infinity` | as above |
| 7 | `$19` | leaf | `np.float64('nan')` | numpy branch guarded post-`float()` |
| 8 | — | finite payload | — | serializes byte-identically to today (regression) |
| 9 | — | forced INSERT failure | — | `❌`, not `✅` (ghost-id regression) |
| 10 | — | duplicate `signal_id` | — | reports dedupe, not failure |

Test 1 is the **deploy gate**: it must fail on `2de26c6` and pass on the fix.

### STEP 5 — Watermark: issued-vs-persisted, per emitter class — **with a named consumer**

Surface mirrors the existing `stable_jobs` contract exactly:

```
signals_freshness: { worst_status, any_flatline,
  classes: { <emitter>: { status, last_persist_age_s, issued, persisted,
                          reconciliation_gap, last_error } } }
```
rolling into the existing top-level `worst_status`.

**SOURCE is the `signals` table** (`MAX(created_at)` per emitter class) — **never pipeline
self-report.** Completions-logged-rows-absent was this defect's entire signature; a watermark that
asks the pipeline how it did would have reported healthy for two days.

**TERMS are staleness AND rate-vs-expectation**, RTH- and weekend-aware. Age alone is disqualified on
two-sided evidence: QS-03-A1 read `CLEAN` at 15m34s *inside* the collapse, and 2m36s read green on
08-19 while throughput was 4 rows from one emitter against a ~140/day baseline.

`reconciliation_gap = issued − persisted` is the direct counter (R-IV.16(g)).

**CONSUMER — named, because the surface alone is the bug it is fixing.** The enumeration found
**0 clients of `/health`** anywhere in `backend/`, `scripts/`, `pivot/`, or `openclaw/` — only
server-side route definitions. Adding `signals_freshness` to `/health` and stopping there would put
the number on a page nobody reads, which is the fake-healthy pattern reproduced *inside* the fix for
fake-healthy. `/health` is therefore the **record**, not the alarm.

The alarm is an active consumer following the proven in-repo pattern —
`main.py:412 flow_deadfeed_watchdog_loop`, which polls freshness and posts to Discord:

```
signals_freshness_watchdog_loop()   # backend/main.py, alongside the existing four
  every 5 min, RTH- and weekend-aware
  reads signals_freshness (table-sourced, per emitter class)
  on status RED or reconciliation_gap > 0  ->  Discord alert naming the emitter class,
      the gap, and last_persist_age_s
  re-alert throttled; recovery posts an explicit CLEARED
```

**Operator path to red, end to end:** table → `signals_freshness` → `worst_status` → watchdog loop
→ Discord. Nick sees it on his phone without opening anything. Four alerting watchdogs already run
in that file on that exact contract, so this adds a peer, not a mechanism.

**Disclosed limit:** the watchdog is itself an unsupervised background task
(DEF-BGTASK-NO-SUPERVISION), so it can die silently like any other. It reduces detection time from
two days to five minutes; it does not make detection guaranteed. The guarantee needs supervision,
which is out of scope by §8.

---

## 6 · COVERAGE MECHANISM — why per-site, not a codec (R-IV.28(e)(1))

**There is no existing chokepoint to use.** All 53 binds pre-serialize independently and no asyncpg
type codec is registered (`grep set_type_codec` → **0**), which the repo states as a deliberate
convention at `crypto_dual_write_shadow.py:141-153`: *"asyncpg needs JSONB params pre-serialized (no
type codec registered on this pool)."*

Two candidate mechanisms, compared on failure mode:

| | **(A) per-site → `dumps_jsonb`** | **(B) connection-level JSONB codec** |
|---|---|---|
| edits required | 53 call sites | 53 call sites **+** pool init |
| what a MISSED site does | stays exactly as today — no regression, latent as before | **double-encodes**: the pre-serialized string is JSON-encoded *again*, writing `"{\"a\":1}"` as a JSON **string** instead of an object |
| failure direction | **fails safe** | **fails destructive, silently, and passes tests that only check "row landed"** |
| review surface | one-line diffs, greppable | invisible runtime coupling at pool init |

**(B) is strictly more work and strictly more dangerous.** It cannot reduce the edit count — every
site must still drop its `json.dumps` or be corrupted — so it buys nothing and risks silent data
corruption on any omission. **(A) is adopted.**

**Fence verified mechanically, not by eye.** Post-change, in `C:\th-build`:
```
grep -rn "dumps_jsonb(" backend/ | wc -l          # expect 53
<AST enumerator from T2/T4> --assert-all-jsonb-binds-use dumps_jsonb   # expect 0 violations
```
The AST enumerator that produced the 43/53 count is re-run as a **coverage assertion in CI**, so the
fence is machine-checked and cannot silently drift.

---

## 7 · RESERVOIRS — handling and residual risk (R-IV.28(e)(4))

`json.loads` **accepts** `NaN`. Confirmed reservoirs: `universe_cache.py:215` (`setex` into **Redis**,
external state that survives restarts), `pipeline.py:262-266 / :275-286 / :311-319` (Redis →
scoring inputs), `bias_scheduler.py:430-444` (`data/bias_history.json`).

**The write-side fix fully contains the data-loss risk.** `dumps_jsonb` sanitizes **at the moment of
binding**, so a NaN that entered from any reservoir is nulled before it reaches Postgres. Reservoir
provenance is irrelevant to persistence: **no reservoir can cause row loss after this fix.**

**Residual risk, disclosed rather than fixed here:** a reservoir NaN still poisons *computation*.
A NaN in a scoring input propagates through arithmetic to produce a NaN or a wrong score, and that
score is a plain numeric column — it lands. So the fix converts *silent total data loss* into
*visible field-level degradation*, which is the intended trade, but it does **not** make the upstream
value correct.

Read-side sanitizing is **deliberately excluded** from this brief: it would touch every `json.loads`
call site in the backend, is not required to close the P0, and belongs with REC-008.

**Detector, free:** repeated `_degraded_nonfinite` entries naming the same field path identify a live
reservoir and its exact leaf — which is the instrument that was missing when this defect ran for two
days unattributed.

---

## 8 · OUT OF SCOPE — filed, queued, deliberately not bundled

DEF-UW-CLIENT-DEATH (P1; chain death bracketed 16:40:27–16:51:24Z 08-18; tide/flow dead now) ·
DEF-BIAS-STALE-FACTOR-RENDER · DEF-BGTASK-NO-SUPERVISION (P2) · PRICE-COLLECTOR-GUARD (1032 MB vs
300 MB, 70 refusals/4 min, probable cause of `price_history = 0`) · the b2 `$3`/`$5` date-bind
defect · the stale `l0_routing.py:29-34` docstring · REC-008 swallow hardening · read-side
reservoir sanitize · `bias_history.json` provenance (→ T8).

**Supervision is named but not fixed.** Adding a supervisor is a process-lifecycle change with its
own blast radius; bundling it inside a P0 data-integrity fix would ship an unreviewed change under
this fix's clearance — the precise error case-law (a) exists to prevent.

---

## 9 · PUSH-SET + DEPLOY VERIFICATION

**Push-set (enumerated, CHAT 4 law):**

| # | path | kind |
|---|---|---|
| 1 | `backend/utils/json_sanitize.py` | CODE — non-finite branch + `dumps_jsonb` |
| 2 | `backend/database/postgres_client.py` | CODE — `:1681`, `:1682`, `:2112` |
| 3 | `backend/enrichment/signal_enricher.py` | CODE — `:287` |
| 4 | `backend/api/signals.py`, `api/committee_bridge.py`, `api/unified_positions.py` | CODE |
| 5 | `backend/scoring/score_v2.py`, `backend/enrichment/context_modifier.py` | CODE |
| 6 | remaining 2c bind sites | CODE — mechanical |
| 7 | `backend/signals/pipeline.py` | CODE — completion-status = persistence outcome |
| 8 | `backend/main.py` (+ `/health` module) | CODE — `signals_freshness` **+ watchdog consumer** |
| 9 | `backend/tests/test_json_sanitize_nonfinite.py` | TEST — 10-case matrix, case 1 gates deploy |
| 10 | `backend/tests/test_pipeline_persistence_status.py` | TEST — ghost-id + dedupe regression |
| 11 | `backend/tests/test_jsonb_bind_coverage.py` | TEST — AST fence assertion (53 sites) |
| 12 | `docs/codex-briefs/2026-08-20-brief-def-signal-persistence-collapse.md` | DOCS — this brief |
| 13 | `docs/defects/DEF-SIGNAL-PERSISTENCE-COLLAPSE.md` | DOCS — mechanism, 459 census, retractions |

**Refspec, explicit:** `git push origin fix/def-signal-persistence-collapse:main` — fast-forward
only, with `git diff --stat origin/main <sha>` proving contents **before** pushing.
**Every commit carries a sid trailer** (R-IV.6(c)).

**FOUR-STEP DEPLOY VERIFICATION:**

1. **Source** — `git show origin/main:backend/utils/json_sanitize.py` contains the non-finite branch;
   local and remote blob hashes identical (content check, not SHA-identity — §0-R1 convention).
2. **Behavioural probe — tests the RULE, not the data.** Two assertions, both required:
   - **serializer:** `dumps_jsonb({"a": float('nan'), "b": float('inf')})` →
     `{"a": null, "b": null, "_degraded_nonfinite": ["a","b"]}`, and `json.loads` round-trips.
   - **completion-status (R-IV.28(e)(5)):** drive one signal through the deployed pipeline with a
     forced INSERT failure and assert the emitted status is `❌ … row not persisted`; then a clean
     signal and assert `✅` **with a matching row present**. Probing the serializer alone would leave
     Step 3 unverified — the T1-EARLY lesson, where a count-based check reads 0 either way.
3. **Tests** — full `backend/tests/` green; the NaN-injection control and the 53-site fence
   assertion named explicitly in the output.
4. **Deployed liveness AND integrity** — Railway deployment carries the SHA; `/health` exposes
   `signals_freshness` with `reconciliation_gap: 0`; **and** a post-deploy issued-vs-persisted census
   over the first RTH hour returns **zero orphans** by the T6-C method (log-issued ids matched
   against the table).

Step 4's second half is the one that matters. `/health` green is liveness, and liveness is exactly
what passed twice while the pipeline was deaf.

---

# ADDENDUM — v3 REMEDIATION RECORD (2026-08-21)

The v2 brief above was graded PASS AS AMENDED and implemented. An adversarial
review of the completed diff, run before staging, returned a P0 regression the
implementation had introduced and a P0 the implementation did NOT close. Both are
fixed below. This addendum is the record of what the review found and how each
finding was dispositioned; the design above stands unchanged except where noted.

## Corrections to the v2 text

* §3/§9 cite `pipeline.py:1560` for the completion log. **It is `:1546`** (v2
  worktree). Final line numbers are those in the shipped commit.
* §9 push-set item 8 names `backend/main.py (+ /health module)`. The accurate
  target is **`backend/stable_engine/job_status.py`** (which owns
  `health_summary()`) plus the `main.py` splice point.
* §0 "cleared by 22:27Z" is superseded: the only defensible bound is **22:30:31Z**
  (first successful write), and the clearing MECHANISM is **FORMALLY OPEN** — no
  write was attempted in [22:02:11Z → 22:27:44Z], so restart/container-wipe cannot
  be distinguished from independent clearing inside that attempt-free interval.

## NUMBER VINTAGE (each figure dated to its enumeration method)

* **45** — bind sites found 2026-08-20 by the v1 AST enumerator (bare `json.dumps`
  appearing lexically inside an execute-family call argument).
* **53** — column-level binds from the T2/T4 dual enumeration, same day
  (AST-resolved SQL + callee-agnostic string scan); the superset, including
  helper-wrapped and multi-column binds.
* **FINAL: 51 routed call sites** — the 45, plus `_to_jsonable`, plus the 5 the
  adversarial review found, against a fence inventory of **49 columns / 31 tables**
  (48 live columns across 30 tables, plus `committee_recommendations.raw_json`,
  declared JSONB at `postgres_client.py:2432` but absent from the live DB).

## FINDING DISPOSITIONS

| # | Finding | Disposition |
|---|---|---|
| F1 | `dumps_jsonb(..., default=str)` → TypeError; every `POST /analytics/weekly-reports` 500s | FIXED — `**kwargs` passthrough, `allow_nan` popped and LOCKED non-overridable |
| F2 | Composition survivor at `composite.py:353`, written multi-line | FIXED — unwrapped |
| F3 | Fence line-scoped, structurally could not detect F2 | FIXED — `re.S` whole-file scan; fireability re-proven |
| F4 | 5 live bare-`json.dumps` JSONB binds (variable-held / star-unpacked / inventory gap) | FIXED — all routed; fence gained variable + `*params` resolution and the missing column |
| F5 | Cumulative gap pinned a class to flatline forever; heal unreachable; 2h re-fire | FIXED — alarm keys on NEW rejections; heals after 3 clean cycles; cumulative retained in /health as diagnostic |
| F6 | Dedupe counted as a gap — alarm contradicted `completion_status` in the same commit | FIXED — three outcomes (persisted/rejected/deduped); gap = rejections only |
| F7 | `_degraded_nonfinite` injected into map-shaped payloads, leaking into HTTP responses | FIXED — `marker=False` at `portfolio_snapshots.sector_exposure`, `.direction_exposure`, `bias_composite_history.factor_scores`; A1 logging stays unconditional |
| F8 | Non-finite dict KEYS bypassed the sanitizer and raised at the chokepoint | FIXED — keys sanitized, stringified, path recorded as `<key nan>` |
| F9 | `except (TypeError, ValueError)` swallowed the locked guard's own assertion | FIXED — ERROR logged before fallback |
| F10 | `signals_freshness_task` never cancelled at shutdown | FIXED — cancel added; `CancelledError` re-raised ahead of the catch-all |
| F11 | Counter key `"unknown"` vs column `"tradingview"` | FIXED — one `class_key()` + `DEFAULT_SOURCE` mirroring `postgres_client.py:1707` |
| P0 | `signal_enricher.py:288` `if` branch bound a caller-supplied string to `$2::jsonb` unsanitized — the guaranteed path for EVERY crypto signal | FIXED — `_as_payload()` decodes first; `json.loads` accepts bare NaN, so the chokepoint can then null it. A non-decoding string passes through loudly, never fabricated |
| — | 7-day window meant total silence read as healthy | FIXED — static `REGISTERED_CLASSES`; a registered class with no rows renders `no_data`, never absent |
| — | Watchdog would page on boot-time-dark classes (crypto_engine 07-22, crypto_cvd_engine 07-24) | FIXED — first cycle adopts `baseline_dark` and never pages it; only a TRANSITION pages; recovery removes a class from the baseline |

## ENVIRONMENTAL INCIDENT — worktree provisioning

A one-test delta (218 vs 217) initially read as a regression. It was not.
`git worktree add` carries **tracked files only**, so `config/.env`, `.mcp.json`
and `data/bias_history.json` were absent from the build worktree. Unconfigured,
the Redis client fell back to `localhost:6379` and burned a ~60s connect/retry
budget per call; `get_cached_composite()` returned `None` and the countertrend
gate rejected.

Proof it was not the diff: **with all 28 modified source files reverted to
`2de26c6`, the failure persisted.** Controlled comparison, both arms inside the
same worktree with identical config:

```
ARM A  2de26c6  : 17 failed, 528 passed, 1 skipped, 200 errors   217 failing ids
ARM B  325199b  : 17 failed, 572 passed, 1 skipped, 200 errors   217 failing ids
regressions: 0   newly-passing: 0
```

The 217 pre-existing failures are unchanged by this diff and remain a standing
condition of their own. Suite runtime with config: ~21s (vs 6m46s unconfigured).
