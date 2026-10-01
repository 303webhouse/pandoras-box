"""Refuse a credential-shaped string before it reaches a commit. R-IV.605(d)4.

WHY THIS EXISTS, CONCRETELY. On 2026-09-30 two tracked files were found carrying a full
`postgresql://user:password@host:port/db` for the production database, and one carried a Discord
webhook token. The repo had been public for a week. **GitHub's own push protection did not stop
either**, so "the platform will catch it" is not a control this repo has.

BUILT FROM WHAT ACTUALLY GOT THROUGH, not from a generic pattern list:

  * a DSN with an inline password  — the database URL, twice
  * a Discord webhook token        — `COWORK_DISCORD_WEBHOOK`, in four places
  * a long opaque token assigned to a secret-shaped name — the shape of every API key here

WHAT IT DELIBERATELY DOES NOT DO. It does not try to detect every secret in the world; a scanner
that cries wolf gets bypassed, and a bypassed scanner is worse than none. It looks for a small set
of shapes that have actually leaked, and it is loud about each one.

TWO WAYS TO SAY "THIS IS FINE", both narrow and both auditable:

  1. `PLACEHOLDER` — the value is obviously not real: it contains `<`, `>`, `REDACTED`, `example`,
     `xxx`, `your-`, `changeme`, `dummy`, `fake`, `${`, `{{`. Template text, not a credential.
  2. An inline `# secret-scan: allow <reason>` on the same line, which REQUIRES a reason. A bare
     allow marker is refused, because an exemption nobody justified is the thing that hid six
     ungated routes for months.

Exit 0 clean, 1 on a finding. `--staged` scans what is about to be committed (the hook's mode),
`--all` scans every tracked file (CI's mode).
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

# ── the shapes ────────────────────────────────────────────────────────────────────────────────

FINDINGS = [
    ("database URL with an inline password",
     re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis(?:s)?|amqp)://"
                r"[^\s:/@'\"]+:[^\s@'\"]{4,}@[^\s/'\"]+")),
    ("Discord webhook token",
     re.compile(r"https://(?:discord|discordapp)\.com/api/webhooks/\d+/[A-Za-z0-9_\-]{20,}")),
    ("Slack token",
     re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}")),
    ("private key block",
     re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("AWS access key id",
     re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Anthropic / OpenAI style key",
     re.compile(r"\b(?:sk-ant-[A-Za-z0-9\-_]{20,}|sk-[A-Za-z0-9]{32,})\b")),
    ("GitHub token",
     re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    # The generic one, kept narrow: a SECRET-SHAPED NAME assigned a long opaque value. Requiring
    # the name is what keeps this from firing on every hash, git sha and base64 blob in the repo.
    ("secret-shaped assignment",
     re.compile(r"(?i)\b(?:api[_-]?key|secret|passwd|password|token|bearer|private[_-]?key|"
                r"access[_-]?key|auth[_-]?token)\b['\"]?\s*[:=]\s*['\"]?"
                r"([A-Za-z0-9+/=_\-]{24,})['\"]?")),
]

PLACEHOLDER = re.compile(
    r"<|>|REDACTED|EXAMPLE|PLACEHOLDER|XXXX|YOUR[_-]|CHANGE[_-]?ME|DUMMY|FAKE|"
    r"INSERT[_-]|TODO|" + r"null|none" + r"|\*\*\*", re.I)

# A value that is plainly CODE rather than a literal: an interpolation, a call, an attribute or
# an environment read. `redis_url = f"rediss://default:{REDIS_PASSWORD}@..."` is a TEMPLATE, and
# a scanner that calls a template a leak teaches people to ignore it.
NOT_A_LITERAL = re.compile(
    "[" + "".join(map(re.escape, "{}()[]$%")) + "]"
    r"|os\.(?:getenv|environ)|getenv|self\.")

ALLOW = re.compile(r"#\s*secret-scan:\s*allow\s+(\S.*)$")

# Whole paths that are never scanned, each with its reason.
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".venv-test", "venv",
             "dist", "build", ".pytest_cache", "htmlcov"}
SKIP_SUFFIX = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz", ".xlsx",
               ".woff", ".woff2", ".ttf", ".mp4", ".parquet", ".pyc")
# This file states the shapes it hunts, so scanning it finds its own patterns.
SKIP_FILES = {"scripts/secret_scan.py", "backend/tests/test_secret_scan.py"}

MAX_BYTES = 4_000_000


def _tracked(all_files: bool) -> list:
    if all_files:
        cmd = ["git", "ls-files"]
    else:
        cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"]
    out = subprocess.run(cmd, capture_output=True, text=True,
                         encoding="utf-8", errors="replace").stdout
    return [p for p in out.split("\n") if p.strip()]


def _content(path: str, staged: bool) -> str:
    """The version that matters: the STAGED blob when scanning a commit, else the file.

    Scanning the working tree while committing the index is how a scanner passes on content that
    is not what is being committed.
    """
    if staged:
        # encoding is EXPLICIT. With `text=True` alone, Python decodes git's bytes using the
        # console codepage (cp1252 here), and a repo with any non-Latin-1 byte crashes the
        # reader thread -- a scanner that dies on a file has not scanned it.
        r = subprocess.run(["git", "show", ":" + path], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode == 0:
            return r.stdout
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def scan_text(text: str, path: str = "<text>") -> list:
    """[(line_no, label, reason_or_None)] for every unexcused finding."""
    hits = []
    for lineno, line in enumerate(text.split("\n"), 1):
        allow = ALLOW.search(line)
        for label, pattern in FINDINGS:
            m = pattern.search(line)
            if not m:
                continue
            value = m.group(1) if m.groups() else m.group(0)
            if PLACEHOLDER.search(value) or NOT_A_LITERAL.search(value):
                continue
            # `token = _extract_bearer_from_scope(scope)` captures the FUNCTION NAME. A value
            # the source immediately calls is code, not a credential.
            if m.end() < len(line) and line[m.end():m.end() + 1] == "(":
                continue
            if allow:
                continue
            hits.append((lineno, label, None))
            break                       # one finding per line is enough to refuse it
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--staged", action="store_true", help="scan the staged blobs (hook mode)")
    g.add_argument("--all", action="store_true", help="scan every tracked file (CI mode)")
    ap.add_argument("--path", action="append", default=[], help="scan these files instead")
    args = ap.parse_args()

    if args.path:
        paths, staged = args.path, False
    else:
        staged = not args.all
        paths = _tracked(all_files=args.all)

    findings, scanned = [], 0
    for p in paths:
        norm = p.replace("\\", "/")
        if norm in SKIP_FILES:
            continue
        if any(part in SKIP_DIRS for part in norm.split("/")):
            continue
        if norm.lower().endswith(SKIP_SUFFIX):
            continue
        try:
            if os.path.exists(p) and os.path.getsize(p) > MAX_BYTES:
                continue
        except OSError:
            pass
        text = _content(p, staged)
        if not text:
            continue
        scanned += 1
        for lineno, label, _ in scan_text(text, p):
            findings.append((p, lineno, label))

    if not findings:
        print("secret-scan: clean (%d file%s)" % (scanned, "" if scanned == 1 else "s"))
        return 0

    print("secret-scan: REFUSED — %d credential-shaped string%s" % (
        len(findings), "" if len(findings) == 1 else "s"))
    print()
    for p, lineno, label in findings:
        # The path and the SHAPE, never the value. A scanner that prints the secret it found has
        # copied it into a log, a terminal history and a CI transcript.
        print("  %s:%d   %s" % (p, lineno, label))
    print()
    print("  Fix it, or — if the value is genuinely not a credential — mark that line:")
    print("      # secret-scan: allow <why this is safe>")
    print("  A reason is required. An exemption nobody justified is how these get through.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
