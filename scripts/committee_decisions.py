"""
Committee Decision Tracking — Brief 03C (refactored)

Decision logging, committee log backfill, expiration, rotation.
All functions are synchronous (used by both the cron pipeline and the interaction handler).
"""
from __future__ import annotations

import json
import logging
import pathlib
from datetime import datetime, timezone, timedelta
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

log = logging.getLogger("committee_decisions")

DATA_DIR = pathlib.Path("/opt/openclaw/workspace/data")
DECISION_LOG = DATA_DIR / "decision_log.jsonl"
COMMITTEE_LOG = DATA_DIR / "committee_log.jsonl"

# Persisted pending recommendations (signal_id -> recommendation dict).
PENDING_FILE = DATA_DIR / "pending_recommendations.json"


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


# ── Decision Logging ─────────────────────────────────────────

def log_decision(
    signal_id: str,
    nick_decision: str,
    committee_action: str,
    is_override: bool,
    override_reason: str | None = None,
    recommendation: dict | None = None,
) -> None:
    """Write Nick's decision to decision_log.jsonl."""
    ensure_data_dir()
    signal = (recommendation or {}).get("signal") or {}
    pivot = ((recommendation or {}).get("agents") or {}).get("pivot") or {}

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "signal_id": signal_id,
        "ticker": signal.get("ticker"),
        "direction": signal.get("direction"),
        "alert_type": signal.get("alert_type", signal.get("signal_type")),
        "score": signal.get("score"),
        "committee_action": committee_action,
        "committee_conviction": pivot.get("conviction"),
        "nick_decision": nick_decision,
        "is_override": is_override,
        "override_reason": override_reason,
        "signal_timestamp": signal.get("timestamp"),
        "decision_delay_seconds": None,
    }

    try:
        rec_ts_str = (recommendation or {}).get("timestamp", "")
        if rec_ts_str:
            rec_ts = datetime.fromisoformat(rec_ts_str.replace("Z", "+00:00"))
            delay = (datetime.now(timezone.utc) - rec_ts).total_seconds()
            entry["decision_delay_seconds"] = round(delay, 1)
    except (ValueError, TypeError):
        pass

    with open(DECISION_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")

    log.info(
        "[DECISION] %s: Nick=%s Committee=%s Override=%s",
        signal_id, nick_decision, committee_action, is_override,
    )


def update_committee_log(signal_id: str, nick_decision: str) -> None:
    """Backfill nick_decision into matching committee_log.jsonl entry."""
    try:
        if not COMMITTEE_LOG.exists():
            return
        lines = COMMITTEE_LOG.read_text(encoding="utf-8").strip().split("\n")

        scan_start = max(0, len(lines) - 100)
        updated = False

        for i in range(len(lines) - 1, scan_start - 1, -1):
            try:
                entry = json.loads(lines[i])
                if entry.get("signal_id") == signal_id and entry.get("nick_decision") is None:
                    entry["nick_decision"] = nick_decision
                    lines[i] = json.dumps(entry, default=str)
                    updated = True
                    break
            except json.JSONDecodeError:
                continue

        if updated:
            COMMITTEE_LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
            log.info("Updated committee_log for %s: nick_decision=%s", signal_id, nick_decision)
        else:
            log.warning("Could not find %s in committee_log to update", signal_id)

    except Exception as e:
        log.error("Failed to update committee_log for %s: %s", signal_id, e)


# ── Pending Recommendations (disk-backed) ────────────────────

def save_pending(signal_id: str, recommendation: dict) -> None:
    ensure_data_dir()
    pending = load_all_pending()
    pending[signal_id] = recommendation
    PENDING_FILE.write_text(json.dumps(pending, default=str, indent=2), encoding="utf-8")


def load_all_pending() -> dict:
    try:
        if PENDING_FILE.exists():
            return json.loads(PENDING_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def remove_pending(signal_id: str) -> None:
    pending = load_all_pending()
    pending.pop(signal_id, None)
    ensure_data_dir()
    PENDING_FILE.write_text(json.dumps(pending, default=str, indent=2), encoding="utf-8")


# ── Expiration ────────────────────────────────────────────────

def _next_market_open_after(dt: datetime) -> datetime:
    et = ZoneInfo("America/New_York")
    dt_et = dt.astimezone(et)
    candidate = (dt_et + timedelta(days=1)).replace(
        hour=9, minute=30, second=0, microsecond=0
    )
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


def expire_stale_recommendations(**_kw) -> list[str]:
    pending = load_all_pending()
    now = datetime.now(timezone.utc)
    expired_ids = []

    for signal_id, rec in list(pending.items()):
        try:
            rec_ts_str = rec.get("timestamp", "")
            if not rec_ts_str:
                continue
            rec_ts = datetime.fromisoformat(rec_ts_str.replace("Z", "+00:00"))
            deadline = _next_market_open_after(rec_ts)

            if now >= deadline:
                expired_ids.append(signal_id)
                pivot_action = ((rec.get("agents") or {}).get("pivot") or {}).get("action", "UNKNOWN")
                log_decision(
                    signal_id=signal_id,
                    nick_decision="EXPIRED",
                    committee_action=pivot_action,
                    is_override=False,
                    override_reason="No decision before next market open",
                    recommendation=rec,
                )
                log.info("Recommendation %s expired (deadline was %s)", signal_id, deadline.isoformat())
        except (ValueError, KeyError) as e:
            log.warning("Could not check expiry for %s: %s", signal_id, e)

    for sid in expired_ids:
        pending.pop(sid, None)

    if expired_ids:
        ensure_data_dir()
        PENDING_FILE.write_text(json.dumps(pending, default=str, indent=2), encoding="utf-8")

    return expired_ids


def rotate_log_if_needed(log_path: pathlib.Path, max_lines: int = 5000) -> None:
    try:
        if not log_path.exists():
            return
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        if len(lines) > max_lines:
            keep = lines[-(max_lines // 2):]
            log_path.write_text("\n".join(keep) + "\n", encoding="utf-8")
            log.info("Rotated %s: %d -> %d lines", log_path.name, len(lines), len(keep))
    except FileNotFoundError:
        pass


# ── Discord Button Components ─────────────────────────────────

def build_button_components(signal_id: str) -> list[dict]:
    """Build Discord message components with TAKE/PASS/WATCHING/Re-evaluate buttons."""
    return [
        {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 3,
                    "label": "Take",
                    "custom_id": f"committee_take_{signal_id}",
                    "emoji": {"name": "\u2705"},
                },
                {
                    "type": 2,
                    "style": 4,
                    "label": "Pass",
                    "custom_id": f"committee_pass_{signal_id}",
                    "emoji": {"name": "\u274c"},
                },
                {
                    "type": 2,
                    "style": 2,
                    "label": "Watching",
                    "custom_id": f"committee_watching_{signal_id}",
                    "emoji": {"name": "\U0001f440"},
                },
                {
                    "type": 2,
                    "style": 1,
                    "label": "Re-evaluate",
                    "custom_id": f"committee_reeval_{signal_id}",
                    "emoji": {"name": "\U0001f504"},
                },
            ],
        }
    ]


def build_disabled_components(signal_id: str, chosen_action: str) -> list[dict]:
    action_map = {"TAKE": "take", "PASS": "pass", "WATCHING": "watching", "RE-EVALUATE": "reeval"}
    chosen_key = action_map.get(chosen_action, "")

    buttons = [
        ("take", "Take", "\u2705", 3),
        ("pass", "Pass", "\u274c", 4),
        ("watching", "Watching", "\U0001f440", 2),
        ("reeval", "Re-evaluate", "\U0001f504", 1),
    ]

    components = []
    for key, label, emoji, default_style in buttons:
        style = 1 if key == chosen_key else 2
        components.append({
            "type": 2,
            "style": style,
            "label": label,
            "custom_id": f"committee_{key}_{signal_id}",
            "emoji": {"name": emoji},
            "disabled": True,
        })

    return [{"type": 1, "components": components}]


# ── Pushback Context Builder ─────────────────────────────────

def format_pushback_context(original_recommendation: dict, nick_objection: str) -> str:
    """Build the pushback injection text for re-evaluation."""
    agents = original_recommendation.get("agents") or {}
    toro = agents.get("toro") or {}
    ursa = agents.get("ursa") or {}
    technicals = agents.get("technicals") or {}
    pivot = agents.get("pivot") or {}

    return (
        f"\n\n## PUSHBACK FROM NICK (TRADER)\n"
        f"Nick has reviewed the committee's initial recommendation "
        f"({pivot.get('action', '?')}) and disagrees. His objection:\n\n"
        f"\"{nick_objection}\"\n\n"
        f"Address this objection specifically in your analysis. "
        f"If his point is valid, adjust your assessment. "
        f"If his point is wrong, explain why clearly.\n\n"
        f"## ORIGINAL COMMITTEE RECOMMENDATION\n"
        f"TORO said: {toro.get('analysis', 'N/A')} "
        f"(conviction: {toro.get('conviction', '?')})\n"
        f"URSA said: {ursa.get('analysis', 'N/A')} "
        f"(conviction: {ursa.get('conviction', '?')})\n"
        f"TECHNICALS said: {technicals.get('analysis', 'N/A')} "
        f"(conviction: {technicals.get('conviction', '?')})\n"
        f"Pivot said: {pivot.get('synthesis', 'N/A')} "
        f"(action: {pivot.get('action', '?')})"
    )
