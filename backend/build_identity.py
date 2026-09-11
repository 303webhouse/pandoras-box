"""Deployed-build identity for /health — R-IV.344(b).

WHY THIS EXISTS
---------------
The readiness gate proved LIVENESS and not IDENTITY: `/health` returned
`status: healthy` both before and after a deploy, so two healthy polls could not
distinguish the old build from the new one. See
`docs/conventions/verification-laws-instance-readiness-gate.md`.

This module gives Step 3 the identity half DIRECTLY, and carries a restart
witness (`process_started_at`, `uptime_seconds`) as the corroborating half.

THE RULE THIS ENCODES
---------------------
**Unreadable is never a pass** (R-IV.344(d)). When no commit can be read, this
reports `commit: None` with `identity_readable: False` — it does NOT guess, and
it does NOT fall back to something that merely looks like an answer. A verifier
reading `identity_readable: False` must FAIL the identity half, never pass it.

SECURITY
--------
`/health` is PUBLIC and UNAUTHENTICATED. Therefore:

  * only the fixed allowlist below is ever read — never `os.environ` at large;
  * a value is emitted ONLY if it matches the expected shape. A value that does
    not match is reported as the string "malformed" and its content is NEVER
    emitted, logged, or echoed anywhere;
  * Railway's internal resource identifiers (deployment / project / service ids)
    are deliberately NOT exposed. The commit SHA is already public — the repo is
    public — and the branch name carries nothing. The ids carry account shape.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone

# Captured at IMPORT, which for this app is process start. This is the restart
# witness: it cannot survive a redeploy, which is exactly the property wanted.
PROCESS_STARTED_AT = datetime.now(timezone.utc)

# Fixed allowlist, most authoritative first. Railway sets RAILWAY_GIT_COMMIT_SHA
# on GitHub-triggered deploys; the rest are conventional names so a manual or
# Docker build can declare identity without this module changing.
COMMIT_ENV_NAMES = (
    "RAILWAY_GIT_COMMIT_SHA",
    "SOURCE_COMMIT",
    "GIT_COMMIT",
    "COMMIT_SHA",
    "BUILD_COMMIT",
)

# WITNESS vs ATTESTATION -- R-IV.345(b).
#
# Measured 2026-09-10: this service has NO RAILWAY_GIT_* variable, and a service
# variable referencing ${{RAILWAY_GIT_COMMIT_SHA}} resolves to EMPTY. So the only
# way a SHA reaches this process is that somebody PUT it there before the deploy.
#
# That is a DECLARATION, not a witness -- conventions #14, a derived value cannot
# witness its own input. A variable set by the pusher says what the pusher intended
# to deploy; it cannot say what is actually running. If a later deploy lands without
# the variable being updated, the field keeps asserting the OLD sha over NEW code --
# which is a fabrication, and worse than reporting nothing.
#
# So the block names which kind it has, and a verifier is told what it may conclude:
#   "platform"    -- only the platform can set this name; it tracks the deploy.
#   "declared"    -- an attestation by whoever configured it. MUST be cross-checked
#                    against the sha the verifier itself pushed; equality is the
#                    whole of its value, and it proves INTENT MATCHED, not identity.
#   "unavailable" -- no sha. Fail the identity half.
PLATFORM_COMMIT_NAMES = frozenset({"RAILWAY_GIT_COMMIT_SHA"})
BRANCH_ENV_NAMES = ("RAILWAY_GIT_BRANCH", "GIT_BRANCH", "BUILD_BRANCH")

_SHA_RE = re.compile(r"\A[0-9a-f]{7,40}\Z")
_BRANCH_RE = re.compile(r"\A[A-Za-z0-9._/-]{1,100}\Z")

MALFORMED = "malformed"


def _read(names: tuple[str, ...], pattern: re.Pattern) -> tuple[str | None, str]:
    """Return (value, source). Never returns a value that failed `pattern`.

    Railway returns '' rather than None for an unset reference, so the `or ""`
    idiom is required here (see CLAUDE.md) — `os.getenv(name, default)` would
    hand back '' and defeat the check.
    """
    for name in names:
        raw = (os.getenv(name) or "").strip()
        if not raw:
            continue
        if pattern.match(raw):
            return raw, name
        # Present but the wrong shape. Say so; never emit the content.
        return MALFORMED, name
    return None, "unavailable"


def build_identity() -> dict:
    """The /health `build` block. Never raises."""
    try:
        commit, commit_source = _read(COMMIT_ENV_NAMES, _SHA_RE)
        branch, branch_source = _read(BRANCH_ENV_NAMES, _BRANCH_RE)
        now = datetime.now(timezone.utc)
        readable = commit is not None and commit != MALFORMED

        if not readable:
            identity_kind = "unavailable"
        elif commit_source in PLATFORM_COMMIT_NAMES:
            identity_kind = "platform"
        else:
            identity_kind = "declared"

        block = {
            "commit": commit,
            "commit_source": commit_source,
            "identity_kind": identity_kind,
            "branch": branch,
            "identity_readable": readable,
            "process_started_at": PROCESS_STARTED_AT.isoformat(),
            "uptime_seconds": int((now - PROCESS_STARTED_AT).total_seconds()),
        }
        if identity_kind == "declared":
            block["note"] = (
                "commit was DECLARED via "
                + commit_source
                + ", not witnessed by the platform. It states what the pusher "
                "intended to deploy and CANNOT witness what is running. A verifier "
                "must compare it to the sha it pushed itself; equality proves the "
                "declaration matched, not that the code is that sha. Corroborate "
                "with uptime_seconds."
            )
        if not readable:
            # An absence that explains itself, so no reader has to guess whether
            # the field is missing because the build is old or because nothing
            # sets it.
            block["note"] = (
                "no commit SHA in the environment: checked "
                + ", ".join(COMMIT_ENV_NAMES)
                + ". IDENTITY IS UNVERIFIABLE FROM THIS SURFACE — a deploy "
                "verifier MUST fail the identity half, not pass it. "
                "uptime_seconds still witnesses a restart."
            )
        return block
    except Exception as exc:  # pragma: no cover - defensive; /health never throws
        return {
            "identity_readable": False,
            "error": type(exc).__name__,
            "note": "build identity unavailable; fail the identity half",
        }
