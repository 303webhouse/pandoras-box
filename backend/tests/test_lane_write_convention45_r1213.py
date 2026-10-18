"""Convention #45 (R-IV.1213(c)) — no lane-file writer may open the live file with "w".

THE INCIDENT THIS COMES FROM. On 2026-10-18 I truncated C:\\lane-state\\BUILD.md to zero bytes
and lost about 3,760 lines. The pattern was:

    io.open(P, "w", ...).write(src[:i] + (ENTRY % stamp) + src[i:])

`open(..., "w")` truncates the file the moment it is evaluated, BEFORE the argument expression
runs. An entry with a literal percent sign made `ENTRY % stamp` raise, and the file was already
empty. It had worked until then only because no entry had contained a `%`.

SO THE TEST IS ABOUT THE PATTERN, NOT THE SYMPTOM. Asserting "BUILD.md is not empty" would pass
on every machine where the bug has not fired yet. What makes a difference is refusing the shape:
a lane-file path and a `"w"` mode in the same call.

THE SCAN COVERS BOTH PLACES a lane-file writer can live -- the repository, and C:\\lane-state
itself, where loose helper scripts accumulate. The second half is skipped when the folder is
absent, because this suite also runs on machines that have no lane state.
"""
from __future__ import annotations

import ast
import io
import os
import re

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(BACKEND)
LANE_DIR = r"C:\lane-state"
WRITER = os.path.join(ROOT, "scripts", "lane_write.py")

#: The lane files. A path mentioning one of these is a lane-file writer.
LANE_FILES = ("BUILD.md", "QUERY.md", "POSITIONS.md", "ABACUS.md", "LAB.md", "lane-state")

#: `lane_write.py` is the ONE module allowed to write a lane file, and it does so through a
#: temp file -- so its own "w" is on `path + '.tmp-...'`, never on the live file.
ALLOWED = {os.path.normcase(WRITER)}


def _py_files():
    for base, dirs, files in os.walk(ROOT):
        parts = base.split(os.sep)
        if any(p in parts for p in (".git", "__pycache__", ".venv-test", "node_modules")):
            continue
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(base, f)
    if os.path.isdir(LANE_DIR):
        for f in os.listdir(LANE_DIR):
            if f.endswith(".py"):
                yield os.path.join(LANE_DIR, f)


def _open_calls(src: str):
    """Every open()/io.open() call, as (mode, line, the call's source text)."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = (fn.attr if isinstance(fn, ast.Attribute)
                else fn.id if isinstance(fn, ast.Name) else None)
        if name != "open":
            continue
        mode = None
        if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
            mode = node.args[1].value
        for kw in node.keywords or []:
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                mode = kw.value.value
        try:
            text = ast.unparse(node)
        except Exception:                                        # pragma: no cover
            text = ""
        out.append((mode, getattr(node, "lineno", 0), text))
    return out


def test_NO_LANE_FILE_IS_EVER_OPENED_WITH_W():
    """THE RULED SELF-CHECK.

    THE FIRST VERSION OF THIS TEST WAS BLIND, and a differential probe caught it. It required
    the lane-file NAME to appear inside the open() call itself:

        if any(lf in text for lf in LANE_FILES)

    Real code does not do that. It writes `P = r"C:\\lane-state\\BUILD.md"` and later
    `io.open(P, "w")` -- which is EXACTLY what my broken scripts did -- so the call text is just
    `io.open(P, 'w')` and the name is nowhere in it. A planted offender passed clean.

    So the criterion is the FILE, not the call: a module that mentions a lane file and opens
    something for writing is the shape, whatever the variable is called. That over-flags by
    design -- over-flagging is the safe direction for a guard whose failure mode is silent data
    loss -- and the allowlist is narrow and justified.
    """
    offenders = []
    for path in _py_files():
        if os.path.normcase(path) in ALLOWED:
            continue
        if os.path.normcase(path) == os.path.normcase(os.path.abspath(__file__)):
            continue        # this file names the lane files in order to search for them
        try:
            src = io.open(path, encoding="utf-8-sig").read()
        except (OSError, UnicodeDecodeError):
            continue
        if not any(lf in src for lf in LANE_FILES):
            continue        # the module knows nothing about lane state
        for mode, line, text in _open_calls(src):
            if not mode or "w" not in str(mode):
                continue
            # A temp-file write is the sanctioned route (write then os.replace).
            if "tmp" in text.lower():
                continue
            offenders.append("%s:%d  %s" % (os.path.relpath(path, ROOT), line, text[:110]))
    assert offenders == [], offenders


def test_THE_WRITER_ITSELF_ONLY_OPENS_A_TEMP_FILE_WITH_W():
    """The one exception has to earn it: `lane_write.write` opens `path + '.tmp-...'`, never
    `path`. If that ever changed, the allowlist above would be hiding the very bug it exists
    for."""
    src = io.open(WRITER, encoding="utf-8").read()
    ws = [t for (m, _l, t) in _open_calls(src) if m and "w" in str(m)]
    assert ws, "the writer must write something"
    for t in ws:
        assert "tmp" in t, t
    assert "os.replace(tmp, path)" in src, "and the temp must be moved into place atomically"


def test_THE_WRITER_REFUSES_BEFORE_IT_TOUCHES_ANYTHING():
    """R-IV.1213(c)2 in the order that matters: every check runs while the live file is still
    whole. `check` is a pure function of the two strings, so it CANNOT touch a file."""
    import inspect
    import sys
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import lane_write

    # THE BODY, NOT THE DOCSTRING. "remove" appears in check()'s own docstring explaining what
    # allow_shrink is for, and a raw scan reports the explanation as the offence -- instance
    # fourteen of that fault.
    tree = ast.parse(inspect.getsource(lane_write))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "check")
    body = fn.body[1:] if (fn.body and isinstance(fn.body[0], ast.Expr)
                           and isinstance(fn.body[0].value, ast.Constant)) else fn.body
    code = "\n".join(ast.unparse(st) for st in body)
    for banned in ("open(", "os.replace", "shutil", "remove"):
        assert banned not in code, banned
    # And `write` checks before it replaces.
    w = inspect.getsource(lane_write.write)
    assert w.index("check(new, old") < w.index("os.replace"), "check must precede the replace"
    assert w.index("backup(path") < w.index("check(new, old"), "backup must precede the check"


# ── the sanity checks themselves ──────────────────────────────────────────

def _lw():
    import sys
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import lane_write
    return lane_write


OLD = "## R-IV.1 entry\n\nbody\n\n## Interrupt handler\n\nfooter text here, long enough\n"


def test_an_EMPTY_write_is_refused():
    lw = _lw()
    with pytest.raises(lw.LaneWriteRefused, match="empty"):
        lw.check("   ", OLD)


def test_a_SHRINKING_write_is_refused_unless_declared():
    """The default allows no shrink at all, because a lane log only grows. A caller that means
    to delete has to say so, by a number, in the call -- which is the moment someone asks why."""
    lw = _lw()
    shorter = "## R-IV.1 entry\n\n## Interrupt handler\n\nfooter text here, long enough\n"
    with pytest.raises(lw.LaneWriteRefused, match="shrinks"):
        lw.check(shorter, OLD)
    lw.check(shorter, OLD, allow_shrink=len(OLD))     # declared, so allowed


def test_a_LOST_FOOTER_is_refused():
    lw = _lw()
    no_footer = OLD.replace("## Interrupt handler", "## Something else") + "x" * 50
    with pytest.raises(lw.LaneWriteRefused, match="footer"):
        lw.check(no_footer, OLD)


def test_a_DUPLICATED_FOOTER_is_refused():
    """Two footers means an entry was pasted in with one attached -- the file now has an end in
    the middle of it."""
    lw = _lw()
    with pytest.raises(lw.LaneWriteRefused, match="footer appears 2"):
        lw.check(OLD + OLD, OLD)


def test_a_MISSING_HEADING_is_refused():
    lw = _lw()
    with pytest.raises(lw.LaneWriteRefused, match="heading"):
        lw.check("plain text, no heading\n" + OLD, OLD)


def test_a_TRUNCATED_TAIL_is_refused():
    """The symptom of the incident: the end of the file gone. Checked explicitly, because a
    length test alone passes if something long was added while the tail was dropped."""
    lw = _lw()
    bad = "## New\n\n" + ("padding line\n" * 40) + "## Interrupt handler\n\nDIFFERENT TAIL\n"
    with pytest.raises(lw.LaneWriteRefused, match="footer block"):
        lw.check(bad, OLD)


def test_a_GOOD_prepend_passes():
    lw = _lw()
    lw.check("## R-IV.2 new\n\nmore\n\n" + OLD, OLD)


def test_the_backup_keeps_THIRTY_and_prunes_PER_LANE(tmp_path, monkeypatch):
    """R-IV.1213(c)1. Pruned per lane: one busy lane must not evict another's history, which is
    exactly what a folder-wide prune would do."""
    lw = _lw()
    bdir = tmp_path / "backup"
    monkeypatch.setattr(lw, "BACKUP_DIR", str(bdir))
    bdir.mkdir()
    for i in range(40):
        (bdir / ("BUILD-2026100%02dT000000.md" % i)).write_text("x", encoding="utf-8")
    for i in range(5):
        (bdir / ("QUERY-2026100%02dT000000.md" % i)).write_text("x", encoding="utf-8")

    live = tmp_path / "BUILD.md"
    live.write_text(OLD, encoding="utf-8")
    lw.backup(str(live), "BUILD")

    builds = [f for f in os.listdir(str(bdir)) if f.startswith("BUILD-")]
    queries = [f for f in os.listdir(str(bdir)) if f.startswith("QUERY-")]
    assert len(builds) == lw.KEEP_BACKUPS, len(builds)
    assert len(queries) == 5, "the other lane's backups are untouched"


def test_the_backup_runs_BEFORE_the_write(tmp_path, monkeypatch):
    """So the copy is of the file as it stands, not of a half-written one -- and so a refused
    write still leaves a backup behind to compare against."""
    lw = _lw()
    bdir = tmp_path / "backup"
    monkeypatch.setattr(lw, "BACKUP_DIR", str(bdir))
    live = tmp_path / "BUILD.md"
    live.write_text(OLD, encoding="utf-8")

    with pytest.raises(lw.LaneWriteRefused):
        lw.write(str(live), "## tiny\n\n## Interrupt handler\n", lane="BUILD")

    assert live.read_text(encoding="utf-8") == OLD, "the live file must be untouched"
    assert [f for f in os.listdir(str(bdir)) if f.startswith("BUILD-")], "a backup was taken"


def test_prepend_puts_the_entry_at_LINE_ONE(tmp_path, monkeypatch):
    """The second fault the incident exposed. These files run newest-first from the top while
    the footer sits at the BOTTOM, so inserting at the footer's index appends at the OLDEST
    end -- which is where every entry I wrote that session went."""
    lw = _lw()
    monkeypatch.setattr(lw, "BACKUP_DIR", str(tmp_path / "backup"))
    live = tmp_path / "BUILD.md"
    live.write_text(OLD, encoding="utf-8")
    lw.prepend_entry(str(live), "## R-IV.2 newest\n\nbody\n", lane="BUILD")
    text = live.read_text(encoding="utf-8")
    assert text.splitlines()[0] == "## R-IV.2 newest"
    assert text.index("## R-IV.2") < text.index("## R-IV.1"), "newest first"
    assert text.rstrip().endswith("footer text here, long enough"), "the footer stayed put"


def test_the_live_file_survives_an_entry_containing_a_PERCENT_SIGN(tmp_path, monkeypatch):
    """THE EXACT TRIGGER. The entry that destroyed BUILD.md contained "33.33%" and "66.67%",
    which broke a %-format and raised after the truncation. Nothing here formats the entry, so a
    percent sign is just a character."""
    lw = _lw()
    monkeypatch.setattr(lw, "BACKUP_DIR", str(tmp_path / "backup"))
    live = tmp_path / "BUILD.md"
    live.write_text(OLD, encoding="utf-8")
    lw.prepend_entry(str(live), "## R-IV.2 ticks at 33.33% and 66.67%\n\n100% fine\n",
                     lane="BUILD")
    text = live.read_text(encoding="utf-8")
    assert "33.33%" in text and "100% fine" in text
    assert "## Interrupt handler" in text


def test_NO_LANE_SCRIPT_FORMATS_AN_ENTRY_WITH_PERCENT():
    """The trigger, refused at the source. `ENTRY % stamp` is what turned a percent sign into a
    truncation; a placeholder that is replaced by name cannot."""
    offenders = []
    for path in _py_files():
        try:
            src = io.open(path, encoding="utf-8-sig").read()
        except (OSError, UnicodeDecodeError):
            continue
        if os.path.normcase(path) == os.path.normcase(os.path.abspath(__file__)):
            continue        # this file carries the pattern AS THE THING IT SEARCHES FOR
        if not any(lf in src for lf in LANE_FILES):
            continue
        # Docstrings stripped: lane_write.py's own docstring quotes the broken line verbatim in
        # order to explain it, and an explanation is not an offence.
        try:
            t = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(t):
            if (isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)) and node.body
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body = node.body[1:] or [ast.Pass()]
        if re.search(r"ENTRY\s*%\s*\w", ast.unparse(ast.fix_missing_locations(t))):
            offenders.append(os.path.relpath(path, ROOT))
    assert offenders == [], offenders
