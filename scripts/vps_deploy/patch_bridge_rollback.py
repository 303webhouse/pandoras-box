#!/usr/bin/env python3
"""
Patch: committee_railway_bridge.py — credit-retry-rollback (2026-04-21)

When Anthropic credits are exhausted, the bridge currently increments the
attempt counter BEFORE the committee call, then breaks on CREDIT_EXHAUSTED
without rolling it back. After 3 cron ticks the signal is permanently
blacklisted even though it never ran. This patch rolls back both the attempt
counter and the daily dedup entry on CREDIT_EXHAUSTED.

Run once on VPS:
  python3 /opt/openclaw/workspace/scripts/patch_bridge_rollback.py
"""
import pathlib

path = pathlib.Path('/opt/openclaw/workspace/scripts/committee_railway_bridge.py')
lines = path.read_text(encoding='utf-8').splitlines(keepends=True)

# Target block is lines 422-427 (1-indexed), i.e. index 421-426 inclusive
expected = (
    '        # Circuit breaker: credit/auth error -> stop entire batch\n'
    '        if result == "CREDIT_EXHAUSTED":\n'
    '            retries[signal_id]["last_error"] = "credit/auth exhausted"\n'
    '            save_retry_tracker(retries)\n'
    '            log.error("Credit/auth exhausted \u2014 halting all processing")\n'
    '            break\n'
)

actual = ''.join(lines[421:427])
if actual != expected:
    print('SKIP: block does not match expected (already patched or code differs)')
    print('Actual:')
    print(repr(actual))
    raise SystemExit(1)

new_block = (
    '        # Circuit breaker: credit/auth error -> stop entire batch\n'
    '        if result == "CREDIT_EXHAUSTED":\n'
    '            # Roll back attempt increment so signal retries once credits are restored\n'
    '            retries[signal_id]["attempts"] = max(0, retries[signal_id].get("attempts", 1) - 1)\n'
    '            retries[signal_id]["last_error"] = "credit/auth exhausted"\n'
    '            save_retry_tracker(retries)\n'
    '            # Roll back daily dedup so this run is not counted\n'
    '            if signal_id in daily.get("signal_ids", []):\n'
    '                daily["signal_ids"].remove(signal_id)\n'
    '                daily["count"] = max(0, daily.get("count", 1) - 1)\n'
    '                save_daily_count(daily)\n'
    '            log.error(\n'
    '                "Credit/auth exhausted \u2014 rolled back attempt for %s, halting batch",\n'
    '                signal_id,\n'
    '            )\n'
    '            break\n'
)

lines[421:427] = [new_block]
path.write_text(''.join(lines), encoding='utf-8')
print('OK: credit-retry-rollback patch applied to committee_railway_bridge.py')

# Quick syntax check
import py_compile, tempfile, shutil
tmp = pathlib.Path(tempfile.mktemp(suffix='.py'))
shutil.copy(path, tmp)
try:
    py_compile.compile(str(tmp), doraise=True)
    print('OK: syntax check passed')
finally:
    tmp.unlink(missing_ok=True)

# Show the patched block
result_lines = path.read_text(encoding='utf-8').splitlines()
print('\nPatched block (lines 422-437):')
for i in range(421, min(437, len(result_lines))):
    print(f'{i+1:4d}: {result_lines[i]}')
