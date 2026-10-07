#!/usr/bin/env python
"""ONE AUTHOR for COMMITTEE_RULES.md -- R-IV.735(c).

`skills/_shared/COMMITTEE_RULES.md` is the author. The seven per-skill copies are GENERATED
from it, byte for byte, and are not to be edited in place.

Why this script exists rather than a convention: eight copies of one text is one fact with eight
writers. Before this, applying a ruling meant eight separate edits, any one of which could be
missed -- and a missed copy does not announce itself, because the skill that loads it still
answers, just under last month's rules. The same shape as a stored total that no longer matches
its ledger: the failure is silent and reads as health.

  python scripts/sync_committee_rules.py --check     # report drift, write nothing, exit 1 if any
  python scripts/sync_committee_rules.py             # regenerate the seven from the author

The roster is EXPLICIT, not discovered. Discovery would be wrong in both directions: eleven
`skills/*/SKILL.md` agents exist, and only these seven are committee members carrying the rules
(aegis, athena, atlas and helios deliberately do not). A filesystem sweep would either plant
copies where no ruling put them, or quietly accept a copy that someone deleted. So the roster is
written down, and `--check` fails if the set of directories actually carrying a copy differs from
it -- in either direction.
"""
import argparse
import hashlib
import io
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELNAME = os.path.join("_shared", "COMMITTEE_RULES.md")
AUTHOR = os.path.join(REPO, "skills", RELNAME)

# The seven committee skills R-IV.735(c) names.
ROSTER = ("daedalus", "pivot", "pythagoras", "pythia", "thales", "toro", "ursa")


def author_path(repo=None):
    return os.path.join(repo or REPO, "skills", RELNAME)


def copy_path(agent, repo=None):
    return os.path.join(repo or REPO, "skills", agent, RELNAME)


def sha256(path):
    """Hash RAW BYTES (#32). Reading as text and re-encoding would make a CRLF copy and an LF
    copy hash the same, and the whole point is that the eight files are identical ON DISK."""
    with io.open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def discovered(repo=None):
    """Every skills/<agent>/ that actually carries a copy right now."""
    root = os.path.join(repo or REPO, "skills")
    return tuple(sorted(d for d in os.listdir(root)
                        if not d.startswith("_") and os.path.isfile(copy_path(d, repo))))


def audit(repo=None):
    """(ok, lines) -- never writes.

    `repo` is threaded through so the test can audit a REAL tree it built and drifted, instead of
    asserting against a mock. A positive control that mocks the thing under test is the kind of
    instrument that cannot fail (#30).
    """
    lines = []
    ok = True

    author = author_path(repo)
    if not os.path.isfile(author):
        return False, ["AUTHOR MISSING: %s" % author]

    want = sha256(author)
    lines.append("author  %-34s %s" % ("skills/" + RELNAME.replace("\\", "/"), want))

    found = discovered(repo)
    if found != ROSTER:
        ok = False
        lines.append("ROSTER MISMATCH: on disk %s, ruled %s" % (list(found), list(ROSTER)))
        for extra in sorted(set(found) - set(ROSTER)):
            lines.append("  UNRULED COPY   skills/%s/ carries a copy no ruling put there" % extra)
        for missing in sorted(set(ROSTER) - set(found)):
            lines.append("  MISSING COPY   skills/%s/ should carry one and does not" % missing)

    for agent in ROSTER:
        p = copy_path(agent, repo)
        if not os.path.isfile(p):
            ok = False
            lines.append("copy    %-34s ABSENT" % ("skills/%s/..." % agent))
            continue
        got = sha256(p)
        same = (got == want)
        ok = ok and same
        lines.append("copy    %-34s %s  %s" % ("skills/%s/..." % agent, got,
                                               "identical" if same else "*** DRIFTED ***"))
    return ok, lines


def regenerate(repo=None):
    with io.open(author_path(repo), "rb") as fh:
        payload = fh.read()
    written = []
    for agent in ROSTER:
        p = copy_path(agent, repo)
        before = sha256(p) if os.path.isfile(p) else None
        d = os.path.dirname(p)
        if not os.path.isdir(d):
            os.makedirs(d)
        if before == hashlib.sha256(payload).hexdigest():
            continue
        with io.open(p, "wb") as fh:
            fh.write(payload)
        written.append(agent)
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="report drift and exit 1; write nothing")
    args = ap.parse_args()

    if not args.check:
        written = regenerate()
        print("regenerated: %s" % (", ".join(written) if written
                                   else "nothing (all seven already matched)"))

    ok, lines = audit()
    for l in lines:
        print("  " + l)
    print("  verdict: %s" % ("all eight identical" if ok else "DRIFT -- see above"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
