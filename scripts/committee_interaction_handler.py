"""
Committee Interaction Handler — Brief 03C / Brief 10 / Committee Refactor

Handles Discord button interactions for committee recommendations:
  - RUN COMMITTEE → load pending signal, run 4-agent committee, replace embed
  - TAKE  → log decision, prompt Nick for fill screenshot, save last_take.json
  - PASS  → log decision
  - LATER → log decision (deferred for re-evaluation)

Deploy path: /opt/openclaw/workspace/scripts/committee_interaction_handler.py
"""

import json
import logging
import os
import pathlib
import sys
from datetime import datetime, timezone

import discord

logger = logging.getLogger(__name__)

# State directory for last_take.json and pending decisions
STATE_DIR = pathlib.Path(os.getenv("OPENCLAW_STATE_DIR", "/opt/openclaw/workspace/data"))

# Add scripts dir to path so we can import committee modules
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# In-memory store for pending committee recommendations awaiting interaction
# Key: message_id (int), Value: recommendation dict
_pending_recommendations: dict[int, dict] = {}


def register_pending(message_id: int, recommendation: dict) -> None:
    """Register a committee recommendation so button handlers can find it."""
    _pending_recommendations[message_id] = recommendation
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
    Save last_take.json so Pivot can link the next fill screenshot
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

    @discord.ui.button(label="\u2705 TAKE", style=discord.ButtonStyle.green, custom_id="committee_take")
    async def take_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        pending = self.recommendation
        signal_id = pending.get("signal_id", "unknown")
        ticker = pending.get("ticker", "unknown")
        direction = pending.get("direction", "")

        await interaction.response.defer(ephemeral=False)

        _log_decision("TAKE", pending)
        logger.info(f"Committee TAKE: {ticker} {direction} signal_id={signal_id}")

        _save_last_take(pending)

        follow_up_msg = (
            f"\U0001f4f8 **Fill screenshot requested**\n"
            f"When you've placed your **{ticker}** order, upload a screenshot of the fill "
            f"to this channel. I'll parse it and link the position to signal `{signal_id}` "
            f"for tracking.\n\n"
            f"*Or type `skip fill` if you don't want to log this one.*"
        )
        await interaction.followup.send(follow_up_msg)

        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass
        self.stop()

    @discord.ui.button(label="\u274c PASS", style=discord.ButtonStyle.red, custom_id="committee_pass")
    async def pass_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        pending = self.recommendation
        await interaction.response.defer(ephemeral=True)

        _log_decision("PASS", pending)
        logger.info(f"Committee PASS: {pending.get('ticker')} signal_id={pending.get('signal_id')}")

        await interaction.followup.send(
            f"Noted \u2014 passing on **{pending.get('ticker', '')}**.",
            ephemeral=True,
        )

        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass
        self.stop()

    @discord.ui.button(label="\u23f3 LATER", style=discord.ButtonStyle.grey, custom_id="committee_later")
    async def later_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        pending = self.recommendation
        await interaction.response.defer(ephemeral=True)

        _log_decision("LATER", pending)
        logger.info(f"Committee LATER: {pending.get('ticker')} signal_id={pending.get('signal_id')}")

        await interaction.followup.send(
            f"OK \u2014 I'll hold **{pending.get('ticker', '')}** for re-evaluation.",
            ephemeral=True,
        )
        self.stop()


# ── Run Committee Button Handler ──────────────────────────────────────────────

async def handle_analyze_signal(interaction: discord.Interaction, signal_id: str) -> None:
    """
    Handle the "Analyze" button click from #signals channel.
    Runs the full committee pipeline and posts the result as a follow-up.
    """
    from pivot2_committee import (
        run_committee, build_committee_embed,
        pop_pending_signal, load_openclaw_config, load_env_file,
        pick_env, OPENCLAW_ENV_FILE, save_pending_signal,
    )
    from committee_decisions import save_pending
    from committee_context import fetch_technical_snapshot

    # Acknowledge immediately — committee takes 10-30s
    await interaction.response.defer()

    # Update original embed to show analyzing state + disable buttons
    try:
        original_embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if original_embed:
            analyzing_embed = original_embed.copy()
            analyzing_embed.title = f"\u23f3 Committee analyzing..."
            analyzing_embed.color = discord.Color.gold()
            await interaction.message.edit(embed=analyzing_embed, components=[])
    except Exception as e:
        logger.warning(f"Failed to update original embed: {e}")

    # Load the pending signal
    pending_entry = pop_pending_signal(signal_id)
    if not pending_entry:
        await interaction.followup.send(
            f"\u26a0\ufe0f Signal `{signal_id}` not found or already processed.",
            ephemeral=True,
        )
        return

    signal = pending_entry.get("signal", {})
    context = pending_entry.get("context", {})

    # Get LLM API key
    cfg = load_openclaw_config()
    env_file = load_env_file(OPENCLAW_ENV_FILE)
    llm_api_key = pick_env("ANTHROPIC_API_KEY", cfg, env_file) or pick_env("LLM_API_KEY", cfg, env_file)

    if not llm_api_key:
        await interaction.followup.send(
            "\u274c ANTHROPIC_API_KEY not configured \u2014 cannot run committee.",
            ephemeral=True,
        )
        save_pending_signal(signal_id, signal, context)
        return

    # Fetch live technical data
    ticker = signal.get("ticker", "")
    technical_data = {}
    if ticker:
        try:
            technical_data = fetch_technical_snapshot(ticker)
            if technical_data:
                logger.info(f"Fetched technical data for {ticker}: price=${technical_data.get('price')}")
        except Exception as e:
            logger.warning(f"Failed to fetch technical data for {ticker}: {e}")

    # Run the committee
    try:
        recommendation = run_committee(signal, context, llm_api_key, technical_data=technical_data)
    except Exception as e:
        logger.exception(f"Committee run failed for {signal_id}")
        await interaction.followup.send(
            f"\u274c Committee analysis failed: {e}",
            ephemeral=True,
        )
        return

    # Build the committee embed
    embed = build_committee_embed(recommendation, context)

    # Save the recommendation for TAKE/PASS/LATER handlers
    save_pending(signal_id, recommendation)

    # Update original embed to show reviewed status
    try:
        reviewed_embed = discord.Embed(
            title=f"\u2705 Committee reviewed: {ticker}",
            description=f"See follow-up below for full analysis.",
            color=discord.Color.green(),
        )
        await interaction.message.edit(embed=reviewed_embed, components=[])
    except Exception as e:
        logger.warning(f"Failed to update original embed: {e}")

    # Post committee result as follow-up with TAKE/PASS/LATER buttons
    view = CommitteeView(
        recommendation={
            "signal_id": signal_id,
            "ticker": signal.get("ticker", ""),
            "direction": signal.get("direction", ""),
            "strategy": signal.get("strategy", ""),
        },
        timeout=3600.0,
    )
    await interaction.followup.send(
        embed=discord.Embed.from_dict(embed),
        view=view,
    )


async def handle_dismiss_signal(interaction: discord.Interaction, signal_id: str) -> None:
    """
    Handle the "Dismiss" button click from #signals channel.
    Logs dismissal and removes buttons from the embed.
    """
    from committee_decisions import log_decision
    from pivot2_committee import pop_pending_signal

    await interaction.response.defer()

    # Pop the pending signal (if it exists)
    pending_entry = pop_pending_signal(signal_id)
    signal = pending_entry.get("signal", {}) if pending_entry else {}

    # Log the dismissal
    try:
        fake_rec = {"signal": signal} if signal else None
        log_decision(
            signal_id=signal_id,
            nick_decision="DISMISSED",
            committee_action="N/A",
            is_override=False,
            recommendation=fake_rec,
        )
    except Exception as e:
        logger.warning(f"Failed to log dismissal for {signal_id}: {e}")

    # Update original embed to show dismissed status
    try:
        dismissed_embed = discord.Embed(
            title=f"\u274c Dismissed: {signal.get('ticker', signal_id)}",
            description="Signal dismissed by Nick.",
            color=discord.Color.dark_grey(),
        )
        await interaction.message.edit(embed=dismissed_embed, components=[])
    except Exception as e:
        logger.warning(f"Failed to update dismissed embed: {e}")

    await interaction.followup.send(
        f"Signal `{signal_id}` dismissed.",
        ephemeral=True,
    )


async def handle_run_committee(interaction: discord.Interaction, signal_id: str) -> None:
    """
    Handle the "Run Committee" button click.
    Loads the pending signal, runs the 4-agent committee,
    replaces the original signal alert embed with the full committee analysis,
    and attaches TAKE/PASS/LATER buttons.
    """
    from pivot2_committee import (
        run_committee, build_committee_embed, build_gatekeeper_report,
        pop_pending_signal, load_openclaw_config, load_env_file,
        pick_env, OPENCLAW_ENV_FILE,
    )
    from committee_decisions import build_button_components, save_pending
    from committee_context import fetch_technical_snapshot

    # Acknowledge immediately — committee takes 10-30s
    await interaction.response.defer()

    # Load the pending signal
    pending_entry = pop_pending_signal(signal_id)
    if not pending_entry:
        await interaction.followup.send(
            f"\u26a0\ufe0f Signal `{signal_id}` not found or already processed.",
            ephemeral=True,
        )
        return

    signal = pending_entry.get("signal", {})
    context = pending_entry.get("context", {})

    # Get LLM API key
    cfg = load_openclaw_config()
    env_file = load_env_file(OPENCLAW_ENV_FILE)
    llm_api_key = pick_env("ANTHROPIC_API_KEY", cfg, env_file) or pick_env("LLM_API_KEY", cfg, env_file)

    if not llm_api_key:
        await interaction.followup.send(
            "\u274c ANTHROPIC_API_KEY not configured \u2014 cannot run committee.",
            ephemeral=True,
        )
        # Re-store the signal so it can be retried
        from pivot2_committee import save_pending_signal
        save_pending_signal(signal_id, signal, context)
        return

    # Fetch live technical data for the ticker
    ticker = signal.get("ticker", "")
    technical_data = {}
    if ticker:
        try:
            technical_data = fetch_technical_snapshot(ticker)
            if technical_data:
                logger.info(f"Fetched technical data for {ticker}: price=${technical_data.get('price')}")
        except Exception as e:
            logger.warning(f"Failed to fetch technical data for {ticker}: {e}")

    # Send "analyzing" status
    await interaction.followup.send(
        f"\U0001f52c Running committee analysis for **{signal.get('ticker', '?')}**... (4 agents, ~15s)"
    )

    # Run the committee
    try:
        recommendation = run_committee(signal, context, llm_api_key, technical_data=technical_data)
    except Exception as e:
        logger.exception(f"Committee run failed for {signal_id}")
        await interaction.followup.send(
            f"\u274c Committee analysis failed: {e}",
            ephemeral=True,
        )
        return

    # Build the full committee embed
    embed = build_committee_embed(recommendation, context)

    # Build TAKE/PASS/WATCHING/Re-evaluate buttons
    buttons = build_button_components(signal_id)

    # Save the recommendation for TAKE/PASS/LATER handlers
    save_pending(signal_id, recommendation)

    # Edit the original message to replace the signal alert with committee analysis
    try:
        await interaction.message.edit(
            embed=discord.Embed.from_dict(embed),
            components=None,  # Clear old components, we'll add new ones
        )
    except Exception as e:
        logger.warning(f"Failed to edit original message: {e}")

    # Send the committee embed as a follow-up with decision buttons
    # (since editing components via interaction can be tricky with persistent views)
    view = CommitteeView(
        recommendation={
            "signal_id": signal_id,
            "ticker": signal.get("ticker", ""),
            "direction": signal.get("direction", ""),
            "strategy": signal.get("strategy", ""),
        },
        timeout=3600.0,
    )
    await interaction.followup.send(
        embed=discord.Embed.from_dict(embed),
        view=view,
    )


def setup_committee_buttons(bot: discord.Client) -> None:
    """
    Register persistent button handlers on the bot.
    Call this during bot setup to handle Run Committee + TAKE/PASS/LATER buttons
    even after bot restarts.
    """
    @bot.event
    async def on_interaction(interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data.get("custom_id", "")

        # Handle "Analyze" button (new signals channel flow)
        if custom_id.startswith("analyze_"):
            signal_id = custom_id[len("analyze_"):]
            await handle_analyze_signal(interaction, signal_id)
            return

        # Handle "Dismiss" button (new signals channel flow)
        if custom_id.startswith("dismiss_"):
            signal_id = custom_id[len("dismiss_"):]
            await handle_dismiss_signal(interaction, signal_id)
            return

        # Handle "Run Committee" button (legacy)
        if custom_id.startswith("committee_run_"):
            signal_id = custom_id[len("committee_run_"):]
            await handle_run_committee(interaction, signal_id)
            return


# ── Standalone Entry Point ───────────────────────────────────


def main():
    """Run the interaction handler as a standalone Discord bot."""
    from pivot2_committee import load_openclaw_config, load_env_file, pick_env, OPENCLAW_ENV_FILE

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    cfg = load_openclaw_config()
    env_file = load_env_file(OPENCLAW_ENV_FILE)

    # Discord token: env var first, then openclaw.json channels.discord.token
    discord_token = pick_env("DISCORD_BOT_TOKEN", cfg, env_file)
    if not discord_token:
        discord_token = (
            ((cfg.get("channels") or {}).get("discord") or {}).get("token") or ""
        ).strip()

    if not discord_token:
        logger.error("DISCORD_BOT_TOKEN not found")
        return 1

    intents = discord.Intents.default()
    intents.message_content = True
    bot = discord.Client(intents=intents)

    @bot.event
    async def on_ready():
        logger.info(f"Committee Interaction Handler ready as {bot.user}")

    setup_committee_buttons(bot)
    bot.run(discord_token, log_handler=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
