# DEF-TEST-SUITE-CANNOT-RUN — P1

**Registered:** R-IV.419(c). **Found:** 2026-09-16, CC-BUILD, while preparing R-IV.417.
**Surface:** `backend/tests/` — every test that uses the `client` fixture.

---

## THE STATEMENT

> **A test suite that cannot execute is a test suite that passes.**

## MEASURED

On the machine where the work is done:

```
httpx      0.28.1   (installed)        backend/requirements.txt pins httpx==0.26.0
starlette  0.35.1                      fastapi==0.109.0
```

httpx 0.28 removed the `app=` argument that starlette 0.35's `TestClient` passes to
`httpx.Client`. So `TestClient(app)` raises `TypeError` in the `client` fixture, and **every
test that uses that fixture errors at setup before a single assertion runs.**

`backend/tests/test_auth.py` on the unmodified tree: **203 errors, 1 pass** — and the one pass
was a test that does not use `client`. The errors all read
`Client.__init__() got an unexpected keyword argument 'app'`, which says nothing about what
the suite was meant to check.

**There is no CI running the suite.** `.github/workflows/` holds only `mcp-lint.yml`.

## WHY THIS IS P1 AND NOT A TOOLING NOTE

**Nothing the suite exists to catch can be caught.** A completeness test — "every route of
kind X has property Y" — is exactly the test whose failure matters most and is noticed least,
and it is also a test that cannot fail if it cannot run. **An erroring suite reads as "the
tests are broken", not as "the thing they guard is broken"**, so the signal is discarded along
with the noise.

This is Addendum 3's Law 3 on a test harness: silence — here, a wall of identical setup errors
— indistinguishable from success.

## MEASURED IN A RUNNABLE ENV

A throwaway venv with `--system-site-packages` and `httpx==0.26.0`:

```
full backend suite (before R-IV.417/419): 25 failed, 1202 passed, 1 skipped
```

**Those 25 had been failing, unseen, for as long as the suite had been unrunnable here.**

## FIX (landed with R-IV.419)

1. **`tests/conftest.py` now checks the capability, not a version number** — it builds a
   `TestClient` at import, and on `TypeError` stops the whole session with the reason and the
   recipe. Verified both ways: against httpx 0.28 the run stops immediately with the message
   (pytest reports it as a conftest usage error, exit 4); in the pinned env the suite runs.
2. **The env is documented** — in the guard's docstring and its exit message:

   ```
   python -m venv --system-site-packages .venv-test
   .venv-test/Scripts/python -m pip install httpx==0.26.0
   .venv-test/Scripts/python -m pytest backend/tests
   ```

## NOT DONE — deliberately

- **The root `requirements.txt` (which Railway builds from) still says `httpx>=0.26.0`.**
  Pinning it below 0.28 would change the HTTP client the production app runs on, and that is
  not a change to make as a side effect of a test fix.
- **No CI.** The guard makes an unrunnable suite loud; it does not make anyone run it. **Until
  the suite runs somewhere on every push, a completeness test is only as good as the last
  person who remembered to run it** — which is the condition this defect was found in.
- **The 25 pre-existing failures are not triaged here.** They are now NAMED in
  `docs/defects/TEST-BASELINE.md` (R-IV.430(f)), with the 4 `hub_mcp` smoke failures that a
  `backend/tests` run never sees; a run is compared to that list by node id, not by count. One (`test_countertrend`) is
  order-dependent: a different test of the pair fails depending on run order, and neither makes
  an HTTP call.
