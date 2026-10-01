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
import json
import sys
import time
import urllib.error
import urllib.request

HEALTH = "https://pandoras-box-production.up.railway.app/health"


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
