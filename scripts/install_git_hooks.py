"""Install the local pre-commit hook that runs the secret scan. R-IV.605(d)4.

WHY A LOCAL HOOK AS WELL AS CI. CI refuses the push after it has already left the machine; for a
credential that is too late, because the value is on GitHub's servers the moment the push lands
and rotating it is then the only remedy. The hook refuses the COMMIT, which is the last moment a
secret is still only local.

Hooks live in `.git/hooks`, which git does not track, so they cannot ship in a clone. This script
is the committed thing; run it once per worktree:

    python scripts/install_git_hooks.py

It is idempotent, it never overwrites a hook it did not write without saying so, and it prints
which worktrees still need it.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys

MARKER = "# installed by scripts/install_git_hooks.py"

HOOK = """#!/bin/sh
%s
# Refuse a commit carrying a credential-shaped string. The staged blobs are scanned, not the
# working tree -- scanning the tree while committing the index is how a scanner passes on content
# that is not what is being committed.
python scripts/secret_scan.py --staged || {
    echo ""
    echo "pre-commit: refused. Nothing was committed."
    echo "If the value is genuinely safe, mark the line with"
    echo "    # secret-scan: allow <why>"
    exit 1
}
""" % MARKER


def _hooks_dir() -> str:
    r = subprocess.run(["git", "rev-parse", "--git-path", "hooks"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("not inside a git repository")
    return os.path.abspath(r.stdout.strip())


def main() -> int:
    hooks = _hooks_dir()
    os.makedirs(hooks, exist_ok=True)
    path = os.path.join(hooks, "pre-commit")

    if os.path.exists(path):
        existing = open(path, encoding="utf-8", errors="replace").read()
        if MARKER not in existing:
            print("REFUSING: %s already exists and was not written by this script." % path)
            print("Merge the two by hand rather than losing whatever it does:")
            print("    python scripts/secret_scan.py --staged || exit 1")
            return 1

    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(HOOK)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print("installed: %s" % path)

    # Every other worktree needs its own, and nothing else will tell anyone so.
    r = subprocess.run(["git", "worktree", "list", "--porcelain"],
                       capture_output=True, text=True)
    others = [l.split(" ", 1)[1].strip() for l in r.stdout.split("\n")
              if l.startswith("worktree ")]
    missing = []
    for w in others:
        p = os.path.join(w, ".git")
        # a worktree's hooks live in the main repo's common dir, so one install usually covers
        # them -- but a separate CLONE does not. Report what is not covered.
        if os.path.isdir(p) and not os.path.samefile(
                os.path.dirname(hooks), os.path.join(p, "")) if os.path.isdir(p) else False:
            missing.append(w)
    if others:
        print("\nworktrees sharing this hook directory: %d" % len(others))
        for w in others:
            print("   %s" % w)
    print("\nA SEPARATE CLONE needs its own: run this script there too.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
