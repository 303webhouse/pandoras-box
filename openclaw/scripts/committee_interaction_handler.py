"""
Committee Interaction Handler — Brief 03C (original) / Brief 10 (TAKE → screenshot prompt)

Handles Discord button interactions for committee recommendations:
  - TAKE  → log decision, prompt Nick for fill screenshot, save last_take.json
  - PASS  → log decision
  - LATER → log decision (deferred for re-evaluation)
  - PUSHBACK → open modal for feedback

Deploy path: /opt/openclaw/workspace/scripts/committee_interaction_handler.py

Brief 10 change: After a TAKE, send a follow-up message asking Nick to upload
a fill screenshot, and write /opt/openclaw/workspace/data/last_take.json so
Pivot can link the position to this signal_id.
"""

import json
import logging
import os
import pathlib
from datetime import datetime, timezone

import discord

logger = logging.getLogger(__name__)

# State directory for last_take.json and pending decisions
STATE_DIR = pathlib.Path(os.getenv("OPENCLAW_STATE_DIR", "/opt/openclaw/workspace/data"))

# In-memory store for pending committee recommendations awaiting interaction
# Key: message_id (int), Value: recommendation dict
_pending_recommendations: dict[int, dict] = {}


def register_pending(message_id: int, recommendation: dict) -> None:
    """Register a committee recommendation so button handlers can find it."""
    _pending_recommendations[message_id] = recommendation
    # Trim old entries if the store gets large
    if len(_pending_recommendations) > 200:
        oldest_keys = list(_pending_recommendations.keys())[:50]
        for k in oldest_keys:
            _pending_recommendations.pop(k, None)


def get_pending(message_id: int) -> dict | None:
    return _pending_recommendations.get(message_id)


def pop_pending(message_id: int) -> dict | None:
    return _pending_recommendations.pop(message_id, None)


# ── Decision logging ──────────────────────────────────────────────────────────

def _log_decision(decision: str, recommendation: dict, notes: str = "") -> None:
    """Append a decision record to the decisions log file."""
    log_path = STATE_DIR / "committee_decisions.jsonl"
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "signal_id": recommendation.get("signal_id", "unknown"),
        "ticker": recommendation.get("ticker", ""),
        "direction": recommendation.get("direction", ""),
        "strategy": recommendation.get("strategy", ""),
        "notes": notes,
    }
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with log_path.open("a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        logger.warning(f"Failed to log committee decision: {e}")


def _save_last_take(recommendation: dict) -> None:
    """
    Brief 10: Save last_take.json so Pivot can link the next fill screenshot
    to this signal_id for position tracking.
    """
    take_state = {
        "signal_id": recommendation.get("signal_id", "unknown"),
        "ticker": recommendation.get("ticker", ""),
        "direction": recommendation.get("direction", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    state_path = STATE_DIR / "last_take.json"
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(take_state))
        logger.info(f"Saved last_take.json: {take_state}")
    except Exception as e:
        logger.warning(f"Failed to save last_take.json: {e}")


# ── Discord View (buttons) ────────────────────────────────────────────────────

class CommitteeView(discord.ui.View):
    """
    Attaches TAKE / PASS / LATER buttons to a committee recommendation embed.
    Instantiate with the recommendation dict before sending the embed.
    """

    def __init__(self, recommendation: dict, timeout: float = 3600.0):
        super().__init__(timeout=timeout)
        self.recommendation = recommendation

    @discord.ui.button(label="✅ TAKE", style=discord.ButtonStyle.green, custom_id="committee_take")
    async def take_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        pending = self.recommendation
        signal_id = pending.get("signal_id", "unknown")
        ticker = pending.get("ticker", "unknown")
        direction = pending.get("direction", "")

        # Acknowledge immediately so Discord doesn't time out
        await interaction.response.defer(ephemeral=False)

        # Log the TAKE decision
        _log_decision("TAKE", pending)
        logger.info(f"Committee TAKE: {ticker} {direction} signal_id={signal_id}")

        # Brief 10: Save state so Pivot knows which signal_id to attach to fill
        _save_last_take(pending)

        # Brief 10: Prompt Nick for fill screenshot
        follow_up_msg = (
            f"📸 **Fill screenshot requested**\n"
            f"When you've placed your **{ticker}** order, upload a screenshot of the fill "
            f"to this channel. I'll parse it and link the position to signal `{signal_id}` "
            f"for tracking.\n\n"
            f"*Or type `skip fill` if you don't want to log this one.*"
        )
        await interaction.followup.send(follow_up_msg)

        # Disable all buttons after TAKE
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass
        self.stop()

    @discord.ui.button(label="❌ PASS", style=discord.ButtonStyle.red, custom_id="committee_pass")
    async def pass_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        pending = self.recommendation
        await interaction.response.defer(ephemeral=True)

        _log_decision("PASS", pending)
        logger.info(f"Committee PASS: {pending.get('ticker')} signal_id={pending.get('signal_id')}")

        await interaction.followup.send(
            f"Noted — passing on **{pending.get('ticker', '')}**.",
            ephemeral=True,
        )

        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass
        self.stop()

    @discord.ui.button(label="⏳ LATER", style=discord.ButtonStyle.grey, custom_id="committee_later")
    async def later_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        pending = self.recommendation
        await interaction.response.defer(ephemeral=True)

        _log_decision("LATER", pending)
        logger.info(f"Committee LATER: {pending.get('ticker')} signal_id={pending.get('signal_id')}")

        await interaction.followup.send(
            f"OK — I'll hold **{pending.get('ticker', '')}** for re-evaluation.",
            ephemeral=True,
        )
        self.stop()
