# Brief: Phase 0E — Data Durability

**Priority:** MEDIUM — JSONL files on VPS are the committee pipeline's operational state. A crash during a full-file rewrite corrupts the entire file with no recovery. Appends are lower risk but still benefit from fsync.
**Target:** VPS scripts (`scripts/`)
**Estimated time:** 45–60 minutes
**Prerequisites:** SSH access to VPS for deployment. Phase 0A must be complete (all scripts in repo).

---

## Context

The committee pipeline stores operational state in JSONL files on VPS disk:

| File | Written by | Pattern | Risk |
|------|-----------|---------|------|
| `committee_log.jsonl` | `pivot2_committee.py`, `committee_decisions.py` | Append + full rewrite (update field, trim) | **HIGH** — rewrite corrupts on crash |
| `decision_log.jsonl` | `committee_decisions.py`, `committee_interaction_handler.py` | Append only | LOW |
| `outcome_log.jsonl` | `committee_outcomes.py` | Append + full rewrite (trim) | **HIGH** |
| `lessons_bank.jsonl` | `committee_review.py` | Append + full rewrite (trim/rotate) | **HIGH** |
| `twitter_signals.jsonl` | `pivot2_twitter.py` | Append | LOW |
| `autopsy_log.jsonl` | `committee_autopsy.py` | Append | LOW |
| `pending_recommendations.json` | `committee_decisions.py` | Full rewrite (every update) | **HIGH** |

The dangerous pattern is: read entire file → modify in memory → `write_text()` back. If the process crashes mid-write, the file is truncated/corrupted. On Linux, the fix is atomic write: write to a temp file in the same directory, then `os.replace()` (which is atomic on the same filesystem).

**This brief does NOT migrate to SQLite or Postgres.** It makes the existing JSONL pattern crash-safe. A full database migration can happen later if needed (Phase 3 analytics might drive that).

---

## Task 1: Create safe_jsonl.py utility

Create a new file: `scripts/safe_jsonl.py`

```python
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
from typing import Any, Callable, Optional

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
```

## Task 2: Update pivot2_committee.py — committee_log append + trim

Find `log_committee_event()` (around line 1115):

```python
def log_committee_event(entry: dict) -> None:
    """Append to committee_log.jsonl, trim to LOG_MAX_LINES."""
    ensure_data_dir()
    line = json.dumps(entry, default=str) + "\n"

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)

    try:
        lines = LOG_FILE.read_text(encoding="utf-8").strip().split("\n")
        if len(lines) > LOG_MAX_LINES:
            LOG_FILE.write_text("\n".join(lines[-LOG_MAX_LINES:]) + "\n", encoding="utf-8")
    except Exception:
        pass
```

Replace with:
```python
def log_committee_event(entry: dict) -> None:
    """Append to committee_log.jsonl, trim to LOG_MAX_LINES."""
    ensure_data_dir()
    from safe_jsonl import safe_append, safe_trim_jsonl
    safe_append(LOG_FILE, entry)
    safe_trim_jsonl(LOG_FILE, LOG_MAX_LINES)
```

## Task 3: Update committee_decisions.py — decision_log append + committee_log update + pending rewrites

### 3a: log_decision() — decision_log append

Find the append block in `log_decision()` (around line 72):
```python
    with open(DECISION_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")
```

Replace with:
```python
    from safe_jsonl import safe_append
    safe_append(DECISION_LOG, entry)
```

### 3b: update_committee_log() — full file rewrite to update one field

Find `update_committee_log()` (around line 81). The current code reads all lines, modifies one, rewrites the file with `write_text()`. Replace the matching/update logic with:

```python
def update_committee_log(signal_id: str, nick_decision: str) -> None:
    """Backfill nick_decision into matching committee_log.jsonl entry."""
    from safe_jsonl import safe_update_line

    def match(entry):
        return entry.get("signal_id") == signal_id and entry.get("nick_decision") is None

    def update(entry):
        entry["nick_decision"] = nick_decision
        return entry

    try:
        updated = safe_update_line(COMMITTEE_LOG, match, update, scan_limit=100)
        if updated:
            log.info("Updated committee_log for %s: nick_decision=%s", signal_id, nick_decision)
        else:
            log.warning("Could not find %s in committee_log to update", signal_id)
    except Exception as e:
        log.error("Failed to update committee_log for %s: %s", signal_id, e)
```

### 3c: Pending recommendations rewrites

Find every `PENDING_FILE.write_text(json.dumps(pending, ...))` call (there are ~3 of them, around lines 118, 134, 183). Replace each with:

```python
    from safe_jsonl import safe_rewrite_json
    safe_rewrite_json(PENDING_FILE, pending)
```

Also find the trim operation around line 195:
```python
    log_path.write_text("\n".join(keep) + "\n", encoding="utf-8")
```
Replace with:
```python
    from safe_jsonl import safe_rewrite
    safe_rewrite(log_path, "\n".join(keep) + "\n")
```

## Task 4: Update committee_outcomes.py — outcome_log append + trim

Find the append in `write_outcome()` (around line 230):
```python
    with open(OUTCOME_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
```

Replace with:
```python
    from safe_jsonl import safe_append
    safe_append(OUTCOME_LOG, entry)
```

Find the trim operation (around line 285-290) where old outcomes are pruned. If it uses a pattern like:
```python
    f.writelines(keep)
```
Or:
```python
    OUTCOME_LOG.write_text(...)
```

Replace with:
```python
    from safe_jsonl import safe_rewrite
    safe_rewrite(OUTCOME_LOG, "".join(keep))
```

## Task 5: Update committee_review.py — lessons_bank append + trim

Find the lessons_bank write (likely an append pattern) and any rotation/trim logic.

Replace appends with:
```python
    from safe_jsonl import safe_append
    safe_append(LESSONS_BANK, entry)
```

Replace the rotation at line ~297:
```python
    # OLD: direct write_text
    # NEW: atomic rewrite
    from safe_jsonl import safe_rewrite
    safe_rewrite(LESSONS_BANK, "\n".join(keep) + "\n")
```

## Task 6: Update committee_interaction_handler.py — decision_log append

Find where it writes to `committee_decisions.jsonl` (around line 207 and 342-362). Replace with `safe_append` calls.

## Task 7: Update remaining writers

Check these files for any JSONL write patterns and apply safe_append/safe_rewrite as appropriate:

- `scripts/committee_autopsy.py` — writes to `autopsy_log.jsonl`
- `scripts/pivot2_twitter.py` — writes to `twitter_signals.jsonl`
- `scripts/pivot2_committee.py` — writes to various state files (seen signals, pending signals, daily count, circuit breaker events)

For all JSON state files (not JSONL logs) that use `write_text(json.dumps(...))`, replace with `safe_rewrite_json()`.

## Task 8: Deploy to VPS

After all changes are committed and pushed:

```bash
# Copy the new utility and updated scripts to VPS
scp scripts/safe_jsonl.py root@188.245.250.2:/opt/openclaw/workspace/scripts/
scp scripts/committee_decisions.py root@188.245.250.2:/opt/openclaw/workspace/scripts/
scp scripts/committee_outcomes.py root@188.245.250.2:/opt/openclaw/workspace/scripts/
scp scripts/committee_review.py root@188.245.250.2:/opt/openclaw/workspace/scripts/
scp scripts/committee_interaction_handler.py root@188.245.250.2:/opt/openclaw/workspace/scripts/
scp scripts/committee_autopsy.py root@188.245.250.2:/opt/openclaw/workspace/scripts/
scp scripts/pivot2_committee.py root@188.245.250.2:/opt/openclaw/workspace/scripts/
scp scripts/pivot2_twitter.py root@188.245.250.2:/opt/openclaw/workspace/scripts/

# Set ownership
ssh root@188.245.250.2 "chown openclaw:openclaw /opt/openclaw/workspace/scripts/safe_jsonl.py"

# Restart services that use the modified scripts
ssh root@188.245.250.2 "systemctl restart openclaw && systemctl restart pivot2-interactions"

# Verify services are running
ssh root@188.245.250.2 "systemctl status openclaw pivot2-interactions --no-pager"
```

---

## Definition of Done

1. `scripts/safe_jsonl.py` exists with `safe_append()`, `safe_rewrite()`, `safe_rewrite_json()`, `safe_trim_jsonl()`, `safe_update_line()`
2. Every `write_text()` or `f.write()` that does a full-file rewrite in the committee pipeline now uses `safe_rewrite()` or `safe_rewrite_json()`
3. Every JSONL append uses `safe_append()` (with fsync)
4. Every JSONL trim uses `safe_trim_jsonl()`
5. The `update_committee_log()` function uses `safe_update_line()`
6. All pending_recommendations.json writes use `safe_rewrite_json()`
7. Changes deployed to VPS and services restarted
8. No orphaned temp files accumulating in `/opt/openclaw/workspace/data/` (check after a few hours)

---

## What this brief does NOT do

- Does NOT migrate to SQLite or Postgres (that's a larger effort for Phase 3 analytics)
- Does NOT add backup/rotation for JSONL files (good future improvement)
- Does NOT change the data schema — all files keep their existing format
- Does NOT touch Railway backend code (JSONL files are VPS-only)

---

## Risk notes

- **Low risk** — this only changes HOW data is written, not WHAT data is written. The file format stays identical.
- **Import pattern** — Uses `from safe_jsonl import ...` inside functions (lazy import) to avoid circular imports or import errors if the utility isn't on VPS path. Alternative: add to `sys.path` or use relative import.
- **VPS Python path** — Scripts in `/opt/openclaw/workspace/scripts/` can import from each other because they run with that directory as CWD. Verify `safe_jsonl.py` is importable: `ssh root@188.245.250.2 "cd /opt/openclaw/workspace/scripts && python3 -c 'from safe_jsonl import safe_append; print("OK")'"`
- **Temp file cleanup** — `os.replace()` is atomic, so temp files only linger if the process is killed between `mkstemp()` and `os.replace()`. Very unlikely, but `session_image_cleanup.py` already cleans up the data directory.

---

## Post-build checklist

1. Push to repo: `git push origin main`
2. SCP all modified files to VPS
3. Set ownership: `chown openclaw:openclaw` on new file
4. Restart services
5. Check logs: `journalctl -u openclaw --since '5 min ago'` — no import errors
6. Trigger a test: wait for next committee run or send a test signal — verify `committee_log.jsonl` gets a new entry
7. After a few hours, check for orphaned temp files: `ls -la /opt/openclaw/workspace/data/.*.tmp`
