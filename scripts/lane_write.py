"""Convention #45 — the only sanctioned way to write a lane file.

WHY THIS EXISTS. On 2026-10-18 I truncated C:\\lane-state\\BUILD.md to zero bytes and lost
about 3,760 lines of lane state. The pattern was:

    io.open(P, "w", ...).write(src[:i] + (ENTRY % stamp) + src[i:])

`open(..., "w")` TRUNCATES THE FILE THE MOMENT IT IS EVALUATED, and Python evaluates it before
the argument. An entry containing a literal percent sign made `ENTRY % stamp` raise TypeError
after the truncation and before the write. The file was already empty.

The pattern was wrong in every lane-file script I had written and had only ever worked because
no entry had happened to contain a `%`. That is a latent bug, not a near miss, which is why
R-IV.1213(c) rules the fix for every lane rather than for the one script that fired.

THE THREE RULES, each enforced here rather than left to a caller's discipline:

  1. BACK UP FIRST. A copy into C:\\lane-state\\backup\\<LANE>-<UTC>.md before anything is
     written, newest 30 kept. The 2026-10-15 backup that saved most of BUILD.md existed by
     accident; this one exists by rule.
  2. BUILD THE WHOLE FILE, THEN ASSERT. Length, header, footer, newest entry at line 1. A write
     that cannot be prepared cannot truncate -- which is the whole point. Every assertion runs
     while the live file is still untouched.
  3. ATOMIC REPLACE. A temp file in the same folder, then os.replace. Never "w" on the live
     file. A crash mid-write leaves the original, not a fragment.

A SECOND FAULT THE INCIDENT EXPOSED, fixed in `prepend_entry`: BUILD.md runs NEWEST-FIRST from
the top while its `## Interrupt handler` footer sits at the BOTTOM. Inserting at the footer's
index appends at the OLDEST end, which is where every entry I wrote that session actually went.
A new entry belongs at line 1.
"""

from __future__ import annotations

import datetime as _dt
import io
import os
import shutil

#: Where the lane files live, and where their backups go.
LANE_DIR = r"C:\lane-state"
BACKUP_DIR = os.path.join(LANE_DIR, "backup")

#: R-IV.1213(c)1.
KEEP_BACKUPS = 30

#: The footer every lane file ends with. Part of the sanity check: a write that loses it has
#: lost the end of the file.
FOOTER = "## Interrupt handler"


class LaneWriteRefused(RuntimeError):
    """A sanity check failed, so nothing was written. The live file is untouched."""


def _utc_stamp() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S")


def backup(path: str, lane: str | None = None) -> str:
    """Copy `path` into the backup folder and prune to the newest KEEP_BACKUPS. Returns the copy.

    Runs BEFORE any write, so the copy is of the file as it stands and not of a half-written one.
    """
    lane = lane or os.path.splitext(os.path.basename(path))[0]
    os.makedirs(BACKUP_DIR, exist_ok=True)
    dest = os.path.join(BACKUP_DIR, "%s-%s.md" % (lane, _utc_stamp()))
    shutil.copy2(path, dest)

    mine = sorted(
        (f for f in os.listdir(BACKUP_DIR)
         if f.startswith(lane + "-") and f.endswith(".md")),
        reverse=True)
    # Pruned per LANE, not across the folder: one busy lane must not evict another's history.
    for old in mine[KEEP_BACKUPS:]:
        try:
            os.remove(os.path.join(BACKUP_DIR, old))
        except OSError:
            pass
    return dest


def check(new: str, old: str, *, allow_shrink: int = 0) -> None:
    """R-IV.1213(c)2. Raises LaneWriteRefused with the reason; writes nothing either way.

    `allow_shrink` is how many characters the caller INTENDED to remove. The default of 0 means
    a write may only grow the file, which is what an append-only lane log does -- so a caller
    that means to delete has to say so, by a number, in the call.
    """
    if not new.strip():
        raise LaneWriteRefused("the new content is empty")
    if len(new) < len(old) - allow_shrink:
        raise LaneWriteRefused(
            "shrinks by %d chars, more than the %d allowed"
            % (len(old) - len(new), allow_shrink))
    if not new.lstrip().startswith("## "):
        raise LaneWriteRefused("no heading on the first line")
    if new.count(FOOTER) != 1:
        raise LaneWriteRefused("footer appears %d times, expected 1" % new.count(FOOTER))
    # THE FOOTER BLOCK, VERBATIM -- not "the last N characters". An N-character anchor is a
    # check whose strictness depends on the file's size: on a file shorter than N it demands
    # the whole file survive, so no declared shrink is ever possible, and on a huge file N
    # characters is an arbitrarily small slice of it. Everything from the footer onward is the
    # invariant that actually matters, and it is the part the truncation took.
    if FOOTER in old:
        tail = old[old.index(FOOTER):]
        if not new.endswith(tail):
            raise LaneWriteRefused("the footer block did not survive verbatim")


def write(path: str, new: str, *, lane: str | None = None, allow_shrink: int = 0) -> dict:
    """Back up, check, then atomically replace. The live file is opened for WRITING never.

    Returns what happened, so a caller can report it rather than assume it.
    """
    old = io.open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    b = backup(path, lane) if old else None
    check(new, old, allow_shrink=allow_shrink)

    # A temp file in the SAME folder, so os.replace is a rename on one volume and therefore
    # atomic. A temp in %TEMP% could be on another drive, where replace falls back to a copy.
    tmp = path + ".tmp-%s" % _utc_stamp()
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(new)
    os.replace(tmp, path)
    return {"backup": b, "bytes_before": len(old), "bytes_after": len(new),
            "lines_after": len(new.splitlines())}


def prepend_entry(path: str, entry: str, *, lane: str | None = None) -> dict:
    """Put `entry` at LINE 1 and leave the rest, footer included, exactly where it is.

    NEWEST-FIRST, which is the order these files are read in. The old scripts inserted at the
    footer's index -- and the footer is at the BOTTOM, so they appended at the oldest end. Every
    entry I wrote that session went to the wrong end of the file.
    """
    old = io.open(path, encoding="utf-8").read()
    if not entry.endswith("\n\n"):
        entry = entry.rstrip("\n") + "\n\n"
    new = entry + old
    first = entry.strip().splitlines()[0]
    if not new.startswith(first):
        raise LaneWriteRefused("the entry did not land on line 1")
    return write(path, new, lane=lane)
