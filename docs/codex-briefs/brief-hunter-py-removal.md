# hunter.py Removal — CC Brief

**Type:** DEAD CODE REMOVAL (banked deprecation for anti-bloat accounting)
**Target file:** `backend/scanners/hunter.py`
**Estimated runtime:** 10–20 min
**Rationale:** Per Holy Grail audit 2026-04-22 (`docs/audits/holy-grail-audit-2026-04-22.md`), `hunter.py` is self-labeled DEPRECATED in its file header (line 2) but still live in production. Near-duplicate of `ursa_taurus.py`. Olympus anti-bloat framework amendment 3 (see `PROJECT_RULES.md` → "Strategy Anti-Bloat Framework" → "ADD Requirements") requires one-in-one-out MANDATORY for ADDs. Removing `hunter.py` now banks a +1 deprecation slot BEFORE Raschke Phase 1 builds begin, keeping the anti-bloat accounting clean.

---

## 1. Pre-Removal Verification (READ-ONLY)

Before deleting anything, confirm `hunter.py` is not actually wired into any live code path that would break if removed.

### 1.1 Search for all references

Search the entire repo for:
- `from backend.scanners.hunter` (any import style)
- `from backend.scanners import hunter`
- `import hunter` (bare)
- The string `"hunter"` in any scheduler/registry/config file

Expected result based on audit: self-deprecated header means it likely has no live callers. But verify.

### 1.2 Check integration points

Read these files and confirm `hunter.py` is NOT invoked:

- `backend/main.py` — scheduler registration for scanners
- `backend/signals/pipeline.py` — signal routing by source/strategy
- `backend/scanners/__init__.py` — scanner registry exports
- Any config files that enumerate active scanners (e.g., `config/*.yaml`, `config/*.json`)
- Webhook handlers in `backend/webhooks/` (in case TV alerts route to hunter)
- Tests in `tests/scanners/` or similar

### 1.3 Stop and report if hunter IS wired

If `hunter.py` is actually called from any active path contrary to its "DEPRECATED" header, **STOP — DO NOT REMOVE.** Instead, reply with:
- Which file(s) call `hunter.py` and where (file:line)
- What signals it emits in practice
- Whether those signals appear in the DB / trade ideas feed

Nick and Olympus will re-scope before any removal.

---

## 2. Removal (Only If Verification Passes)

If Section 1 confirms `hunter.py` has no live callers:

### 2.1 Delete the file

```
git rm backend/scanners/hunter.py
```

### 2.2 Remove stale references

For each reference found in Section 1.1:
- Remove the import statement
- Remove any function/class usages downstream of the removed import
- If a whole block becomes unreachable after removal (e.g., a scheduler registration), remove that block too

Common patterns to watch for:
- Orphaned imports at the top of a file
- Empty `try/except ImportError` blocks now that the import is gone
- Entries in `__all__` lists
- Entries in scanner registries, even if commented out — clean them

### 2.3 Remove or update tests

- Delete `tests/scanners/test_hunter.py` if it exists
- If any other test file imports hunter (likely a smoke test or integration test), remove the hunter-specific test cases but keep the file if it tests other things

### 2.4 Run the test suite

```
pytest
```

All remaining tests must pass. If anything fails because of the hunter removal, fix the failure by removing the dependency — do NOT restore hunter.

### 2.5 Verify Railway deployment integrity

Confirm nothing in the production startup path imports hunter. Grep for any `importlib` or dynamic-import patterns that might pick up scanner files by filename.

---

## 3. Commit

Commit message:

```
refactor: remove deprecated hunter.py scanner (Olympus anti-bloat banked deprecation)

Per Holy Grail audit 2026-04-22: hunter.py was self-labeled DEPRECATED
in its file header but still present in the repo. Near-duplicate of
ursa_taurus.py. No live production callers confirmed.

Removing this banks +1 deprecation slot under the anti-bloat framework
(PROJECT_RULES.md) ahead of Raschke Phase 1 builds.

Refs:
- docs/audits/holy-grail-audit-2026-04-22.md (hunter.py classification)
- docs/strategy-reviews/raschke/olympus-review-2026-04-22.md (framework)
```

Push to `origin/main`.

---

## 4. Constraints

- **Do NOT touch `ursa_taurus.py`.** Audit classified it as KEEP — distinct non-overlapping logic with clean bull/bear symmetry.
- **Do NOT remove any other scanner or strategy file** — scope is strictly `hunter.py`.
- **If verification in Section 1 finds live callers, STOP.** Report and wait.
- **Clean removals only** — no orphaned imports, no dead test cases, no comments pointing to the removed file.

---

## 5. Output

Reply with:

1. Pre-removal verification findings (live callers: yes/no, with evidence)
2. Commit SHA for the removal
3. List of files modified (deletion + import cleanups + test updates)
4. Test suite pass/fail confirmation
5. Any surprises encountered

---

**End of brief.**
