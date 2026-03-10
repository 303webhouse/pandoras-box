"""
Atomic JSONL file operations.

All rewrite operations use temp-file + os.replace() which is atomic
on Linux (same filesystem). This prevents corruption if the process
crashes mid-write.
"""

import json
import os
import tempfile
import logging
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)


def safe_append(path: Path, entry: dict) -> None:
    """Append a single JSON line to a JSONL file with fsync."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, default=str) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


def safe_rewrite(path: Path, content: str) -> None:
    """Atomically rewrite a file. Write to temp, then os.replace()."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write to temp file in same directory (required for atomic replace)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(path))
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def safe_rewrite_json(path: Path, data: Any) -> None:
    """Atomically rewrite a JSON file (for pending_recommendations.json etc.)."""
    safe_rewrite(path, json.dumps(data, default=str, indent=2) + "\n")


def safe_trim_jsonl(path: Path, max_lines: int) -> None:
    """Trim a JSONL file to the last N lines, atomically."""
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        if len(lines) <= max_lines:
            return
        keep = lines[-max_lines:]
        safe_rewrite(path, "\n".join(keep) + "\n")
        log.info("Trimmed %s: %d -> %d lines", path.name, len(lines), len(keep))
    except Exception as e:
        log.error("Failed to trim %s: %s", path.name, e)


def safe_update_line(
    path: Path,
    match_fn: Callable[[dict], bool],
    update_fn: Callable[[dict], dict],
    scan_limit: int = 100,
) -> bool:
    """
    Find and update a single line in a JSONL file, atomically.

    Scans backwards from the end (last `scan_limit` lines).
    Returns True if a line was updated.
    """
    if not path.exists():
        return False
    try:
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        scan_start = max(0, len(lines) - scan_limit)
        updated = False

        for i in range(len(lines) - 1, scan_start - 1, -1):
            try:
                entry = json.loads(lines[i])
                if match_fn(entry):
                    entry = update_fn(entry)
                    lines[i] = json.dumps(entry, default=str)
                    updated = True
                    break
            except json.JSONDecodeError:
                continue

        if updated:
            safe_rewrite(path, "\n".join(lines) + "\n")

        return updated
    except Exception as e:
        log.error("Failed to update line in %s: %s", path.name, e)
        return False
