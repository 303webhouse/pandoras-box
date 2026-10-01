"""Wait for Railway to serve a specific commit, and report a mismatch AS a mismatch.

R-IV.638(c). The shell loop this replaces was

    until [ "$(curl .../health | ... )" = "<sha7>" ]; do sleep 15; done; echo "<sha7> LIVE"

and on 2026-10-01 it printed `11dc713 LIVE` when /health was serving `1c2534f`. Three ways
that loop can say LIVE without the deploy having happened, and it distinguishes none of them:

  * the push itself FAILED (it did -- rejected non-fast-forward by a concurrent push), so the
    commit was never on origin to deploy, and nothing in the loop looks at the push;
  * `curl` or the parser fails and the comparison is against an empty string, which the shell
    `[` treats as a perfectly good operand;
  * the loop exits on ANY exit of the body, so a mis-set condition ends it and the `echo`
    afterwards is unconditional -- the success message is not evidence of success, it is a
    line that runs next.

The last one is the real fault: THE ANNOUNCEMENT WAS NOT PRODUCED BY THE CHECK. So this
prints what it actually compared, both sides, every time -- and a mismatch is a non-zero exit
with the two values side by side, never a quiet retry.

    python scripts/await_deploy.py <sha>            # wait, then confirm or fail
    python scripts/await_deploy.py <sha> --once      # one read, no waiting
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

HEALTH = "https://pandoras-box-production.up.railway.app/health"
RAILWAY_JSON = "railway.json"


def watched_patterns(path: str = RAILWAY_JSON):
    """Railway's `build.watchPatterns`, or None when the file cannot be read.

    None means "unknown", and an unknown watch list must NOT be read as "nothing is
    watched" -- that would turn every real failed deploy into a cheerful no-op.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            return ((json.load(fh).get("build") or {}).get("watchPatterns")) or None
    except (OSError, json.JSONDecodeError):
        return None


def _matches_pattern(rel: str, pattern: str) -> bool:
    """`backend/**` matches anything under backend/; a bare name matches itself."""
    if pattern.endswith("/**"):
        return rel.startswith(pattern[:-2])
    return fnmatch.fnmatch(rel, pattern)


def deploy_expected(commit: str, patterns):
    """`(expected, reason)` -- whether this commit should trigger a Railway build.

    R-IV.638(c), SECOND PASS. The first version treated "not served" as a failure full
    stop, and then cried wolf on the very next commit: `e9a2a95` was docs-only, and
    `docs/**` is deliberately outside watchPatterns since f555dcc (2026-09-23,
    "docs commits stop redeploying the app"). A watcher that reports a non-event as a
    failure is one people stop reading -- which is how the false LIVE went unnoticed in
    the first place.
    """
    if not patterns:
        return True, "watchPatterns unknown, so a deploy is assumed"
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", f"{commit}^1", commit],
            capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, OSError) as exc:
        return True, f"could not list the commit's files ({type(exc).__name__}), so a deploy is assumed"
    files = [f.strip().replace("\\", "/") for f in out.splitlines() if f.strip()]
    if not files:
        return True, "the commit touches no files this could read, so a deploy is assumed"
    hits = [f for f in files if any(_matches_pattern(f, p) for p in patterns)]
    if hits:
        return True, f"{len(hits)} of {len(files)} changed file(s) are watched"
    return False, (f"none of the {len(files)} changed file(s) match watchPatterns "
                   f"({', '.join(patterns)})")


def read_served(url: str = HEALTH, timeout: float = 20.0):
    """`(commit, status, error)` from /health. Never raises.

    A read failure returns an ERROR, not an empty string: the whole defect is a falsy value
    being compared as though it were an answer.
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            payload = json.load(r)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return None, None, f"{type(exc).__name__}: {exc}"
    build = payload.get("build") or {}
    commit = build.get("commit")
    if not commit:
        return None, payload.get("status"), "/health carried no build.commit"
    return str(commit), payload.get("status"), None


def matches(served: str | None, wanted: str) -> bool:
    """True only when both are real and one is a prefix of the other.

    `served` is a full sha and `wanted` is usually seven characters, so a prefix test is
    right -- but a MISSING served value can never match, however the caller wrote `wanted`.
    """
    if not served or not wanted:
        return False
    a, b = served.strip().lower(), wanted.strip().lower()
    return a.startswith(b) or b.startswith(a)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("commit", help="the sha that was pushed (7+ chars)")
    ap.add_argument("--timeout", type=float, default=900.0)
    ap.add_argument("--interval", type=float, default=15.0)
    ap.add_argument("--once", action="store_true", help="one read, no waiting")
    ap.add_argument("--url", default=HEALTH)
    a = ap.parse_args()

    # A commit Railway will not build is not a failed deploy. Checked BEFORE waiting, so
    # a docs-only commit returns at once instead of burning the whole timeout.
    expected, why = deploy_expected(a.commit, watched_patterns())
    if not expected:
        served, status, _ = read_served(a.url)
        print(f"NO DEPLOY EXPECTED  commit={a.commit}  ({why})")
        print(f"                    serving={served}  status={status} — unchanged, correctly")
        return 0

    deadline = time.monotonic() + (0 if a.once else a.timeout)
    attempts, served, status, err = 0, None, None, None

    while True:
        attempts += 1
        served, status, err = read_served(a.url)
        if matches(served, a.commit):
            print(f"MATCH   pushed={a.commit}  served={served}  status={status}  "
                  f"(attempt {attempts})")
            return 0
        if time.monotonic() >= deadline:
            break
        time.sleep(a.interval)

    # Both sides, always. A mismatch is reported as a mismatch, with the value that was
    # actually served -- not as silence, and not as a retry that eventually gives up quietly.
    print(f"MISMATCH  pushed={a.commit}  served={served or '<unread>'}  status={status}  "
          f"after {attempts} attempt(s)", file=sys.stderr)
    if err:
        print(f"          last read error: {err}", file=sys.stderr)
    print("          The deploy did NOT serve the commit that was pushed. Check that the "
          "push landed on origin/main — a concurrent push can reject it "
          "non-fast-forward (R-IV.638(c)).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
