# Hunter UI Strip — CC Brief

**Type:** FRONTEND + BACKEND CLEANUP (follow-up to hunter.py removal)
**Estimated runtime:** 15–25 min
**Rationale:** The prior commit (`80b4aca`) removed `backend/scanners/hunter.py` cleanly but left the frontend Scanner UI (app.js + any HTML triggers) wired to endpoints that now return 503. Also left `backend/api/scanner.py` — a full API wrapper whose only purpose was exposing hunter. Finish the deprecation: strip the dead UI and delete the dead wrapper so the "deprecated" state is actually invisible to users.

**Prior context:** `docs/codex-briefs/brief-hunter-py-removal.md`, `docs/audits/holy-grail-audit-2026-04-22.md`, commit `80b4aca`.

---

## 1. Scope

### IN scope
- Remove the "Scan S&P 500" / Hunter Scanner UI from `frontend/app.js`
- Remove any HTML element in `frontend/index.html` (or equivalent) that renders the scanner button/tab/section
- Delete `backend/api/scanner.py` (entire file)
- Remove the scanner router mount from `backend/main.py` (referenced at lines 922 and 981 in the prior audit)
- Remove the 2-line stub added by the prior commit in `backend/api/scanner.py` — wait, that file is about to be deleted entirely, so this is moot; but confirm nothing ELSE imports from `api.scanner`

### OUT of scope
- Do not touch `ursa_taurus.py`
- Do not modify any other API router, scanner, or UI section
- Do not refactor adjacent code "while you're in there" — strict removal only

---

## 2. Verification Pass (Before Any Changes)

### 2.1 Frontend UI block bounds

Known anchors in `frontend/app.js`:
- ~line 5440: `btn.textContent = 'Scanning...'`
- ~line 5442: `'Scanning S&P 500...'`
- ~line 5449: `fetch(\`${API_URL}/scanner/run\`)`
- ~line 5475: `console.error('Hunter scan error:', error)`
- ~line 5483: `fetch(\`${API_URL}/scanner/status\`)`
- ~line 5519: third endpoint call (likely `/scanner/results`)

**Find the FULL bounds of the hunter UI block.** It starts at whichever function/handler contains the "Scanning..." setup and ends after the last scanner-related function (probably after results rendering). Report exact start and end line numbers before removing.

Also scan for:
- Any event listener attachment like `document.getElementById('scanBtn').addEventListener(...)` — these become dead references after the block is removed
- Any CSS-class or DOM ID references (`scanStatus`, `scanBtn`, `scanResults`, etc.) that might appear in both app.js AND index.html

### 2.2 HTML trigger element

Search `frontend/index.html` (and any templated HTML) for:
- Button with id/class referencing "scan", "hunter", "scanner" (e.g., `id="scanBtn"`, `class="scanner-section"`)
- Tab or nav entry linking to a scanner panel
- Any container div that the JS populates with scan results

Report what you find before removing so Nick can sanity-check scope.

### 2.3 api/scanner.py reference check

Search the repo for imports or references to `api.scanner`, `backend.api.scanner`, or `from .scanner` (in the context of the api module):
- `backend/main.py` — expect router mount at lines 922 and 981 per prior audit
- Any other file that imports from `api.scanner`

If found ONLY in `main.py`, deletion is safe. If found elsewhere, STOP and report.

### 2.4 Test references

Check `tests/` for any file that tests scanner endpoints (`test_scanner_api.py`, `test_hunter.py`, etc.). If found, they should be deleted as part of this removal (the endpoints they test won't exist).

---

## 3. Removal (Only If Verification Passes)

### 3.1 Frontend

**`frontend/app.js`:** Remove the entire hunter UI block identified in Section 2.1. Clean up:
- Any orphaned helper functions (formatters, pollers) that only served the scanner UI
- Any event listener registrations tied to removed DOM elements
- Any shared-state variables (`let scanResults = []`, etc.) that are now unused

**`frontend/index.html`:** Remove the HTML element(s) identified in Section 2.2 — button, container div, tab link, any related markup. Do NOT remove shared UI chrome (e.g., generic CSS classes used elsewhere).

### 3.2 Backend

**`backend/api/scanner.py`:** Delete the entire file (`git rm backend/api/scanner.py`).

**`backend/main.py`:** Remove the scanner router mount. Based on prior audit this is at lines 922 and 981 — verify the exact current line numbers (commit `80b4aca` may have shifted them slightly) and remove:
- The `from backend.api.scanner import router` style import (or equivalent)
- The `app.include_router(...)` call for that router
- Any related conditional logic that checks for scanner availability

### 3.3 Test references

Delete any test files found in Section 2.4.

### 3.4 Run test suite

```
pytest
```

All tests must pass. The pre-existing `test_no_unprotected_mutations` failure on `/webhook/footprint` and `/webhook/mp_levels` (noted in commit `80b4aca`) is still expected to fail — that's unrelated. No NEW failures introduced.

### 3.5 Frontend sanity check

Launch the frontend locally or review visually:
- The page that previously had the scanner UI loads without JS console errors
- No orphan buttons, empty containers, or "undefined" strings appear
- Other UI features continue to work (spot-check 2-3 unrelated features)

---

## 4. Commit

Commit message:

```
refactor: strip hunter scanner UI + delete api/scanner.py wrapper

Completes the hunter.py deprecation (commit 80b4aca) by removing
the now-dead frontend UI and the backend API wrapper that exposed
it. No production scanners affected.

Frontend:
- Removed hunter scan UI block from app.js (N lines)
- Removed scanner button/tab from index.html

Backend:
- Deleted backend/api/scanner.py (was a wrapper for removed hunter.py)
- Removed scanner router mount in main.py

Refs:
- docs/codex-briefs/brief-hunter-py-removal.md (initial removal)
- docs/codex-briefs/brief-hunter-ui-strip.md (this cleanup)
- docs/audits/holy-grail-audit-2026-04-22.md
```

Replace `N lines` with the actual count removed from app.js. Push to `origin/main`.

---

## 5. Constraints

- Strict removal only — no refactors, no re-plumbing, no "while I'm here" improvements
- Do not touch `ursa_taurus.py`, Holy Grail code, or any other live scanner
- If verification finds live callers of `api/scanner.py` outside `main.py`, STOP and report
- Clean removals only — no orphan imports, no dead DOM IDs, no commented-out blocks

---

## 6. Output

Reply with:

1. Verification findings (Section 2 — full line bounds, HTML elements, reference counts)
2. Commit SHA
3. Files modified (deletions + edits)
4. Line counts removed (for the commit message)
5. Test suite pass confirmation (plus note about the pre-existing unrelated failure)
6. Any surprises or scope-creep tempted but not taken

---

**End of brief.**
