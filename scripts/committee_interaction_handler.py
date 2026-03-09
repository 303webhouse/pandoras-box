"""
Committee Interaction Handler — Brief 03C / Brief 10 / Committee Refactor / Trade Logging

Handles Discord button interactions for committee recommendations:
  - RUN COMMITTEE → load pending signal, run 4-agent committee, replace embed
  - TAKE  → log decision, prompt Nick for fill screenshot, save last_take.json
  - PASS  → log decision
  - LATER → log decision (deferred for re-evaluation)

Trade logging features:
  - Auto-detect trade entry messages ("went short PLTR", "I'm in", etc.)
  - /log-trade text command for explicit manual logging
  - Confirm via buttons → write decision_log.jsonl + POST to Railway

Deploy path: /opt/openclaw/workspace/scripts/committee_interaction_handler.py
"""

import json
import logging
import os
import pathlib
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

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


# ── Trade Detection ──────────────────────────────────────────────────────────

TRADE_ENTRY_PATTERNS = [
    re.compile(r"\btook the trade\b", re.I),
    re.compile(r"\bjust entered\b", re.I),
    re.compile(r"\bi['\u2019]m in\b", re.I),
    re.compile(r"\bwent (long|short)\b", re.I),
    re.compile(r"\b(bought|sold|opened|filled|executed)\s", re.I),
    re.compile(r"\btook a position\b", re.I),
    re.compile(r"\bentered (a |the )?(long|short)\b", re.I),
    re.compile(r"\bfilled (at|on)\b", re.I),
]

TRADE_EXIT_PATTERNS = [
    re.compile(r"\bclosed\b", re.I),
    re.compile(r"\btook profits?\b", re.I),
    re.compile(r"\bexited\b", re.I),
    re.compile(r"\bsold\b.*\b(position|spread|calls?|puts?)\b", re.I),
    re.compile(r"\bclosed out\b", re.I),
    re.compile(r"\bcut\b.*\b(loss|position)\b", re.I),
    re.compile(r"\bstopped out\b", re.I),
]

TICKER_RE = re.compile(r"\b([A-Z]{1,5})\b")
PRICE_RE = re.compile(r"\$\s?([\d]+(?:\.[\d]{1,2})?)")

DIRECTION_KEYWORDS = {
    "long": "LONG", "short": "SHORT", "bull": "LONG", "bear": "SHORT",
    "bought": "LONG", "sold": "SHORT", "calls": "LONG", "puts": "SHORT",
}

# Common English words that look like tickers — filter these out
_TICKER_BLACKLIST = frozenset({
    "I", "A", "IT", "AT", "IN", "ON", "OR", "AM", "PM", "OK", "UP", "DO",
    "GO", "SO", "IF", "NO", "IS", "HE", "WE", "AN", "TO", "THE", "FOR",
    "AND", "BUT", "NOT", "ALL", "HAS", "HAD", "GET", "GOT", "WAS", "ARE",
    "CAN", "DID", "MAY", "SAY", "NOW", "NEW", "OLD", "BIG", "OUT", "PUT",
    "SET", "RUN", "OUR", "TWO", "HOW", "ITS", "LET", "TOP", "FEW", "TRY",
    "OWN", "DAY", "TOO", "USE", "HER", "HIM", "JUST", "LONG", "SHORT",
    "TAKE", "PASS", "FILL", "SKIP", "LOG",
})


def _extract_trade_details(text: str) -> dict:
    """Extract ticker, direction, and entry price from a message."""
    details: dict = {"ticker": None, "direction": None, "entry_price": None}

    # Direction
    text_lower = text.lower()
    for kw, direction in DIRECTION_KEYWORDS.items():
        if kw in text_lower.split():
            details["direction"] = direction
            break

    # Ticker — first uppercase 1-5 letter word not in blacklist
    for m in TICKER_RE.finditer(text):
        candidate = m.group(1)
        if candidate not in _TICKER_BLACKLIST and len(candidate) >= 2:
            details["ticker"] = candidate
            break

    # Price — first $XXX.XX pattern
    price_match = PRICE_RE.search(text)
    if price_match:
        try:
            details["entry_price"] = float(price_match.group(1))
        except ValueError:
            pass

    return details


def _extract_exit_details(text: str) -> dict:
    """Extract ticker and exit price from a trade-close message."""
    details: dict = {"ticker": None, "exit_price": None}

    # Ticker — first uppercase 1-5 letter word not in blacklist
    for m in TICKER_RE.finditer(text):
        candidate = m.group(1)
        if candidate not in _TICKER_BLACKLIST and len(candidate) >= 2:
            details["ticker"] = candidate
            break

    # Price — first $XXX.XX pattern
    price_match = PRICE_RE.search(text)
    if price_match:
        try:
            details["exit_price"] = float(price_match.group(1))
        except ValueError:
            pass

    return details


def _load_last_take() -> dict | None:
    """Load last_take.json if it exists and is < 2 hours old."""
    state_path = STATE_DIR / "last_take.json"
    try:
        if not state_path.exists():
            return None
        data = json.loads(state_path.read_text())
        ts_str = data.get("timestamp", "")
        if ts_str:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) - ts > timedelta(hours=2):
                return None
        return data
    except Exception:
        return None


def _post_to_railway(path: str, payload: dict, api_key: str, base_url: str) -> dict | None:
    """POST JSON to a Railway API endpoint. Returns response dict or None."""
    url = f"{base_url.rstrip('/')}{path}"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key,
    }
    body = json.dumps(payload, default=str).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning("Railway POST %s failed: %s", path, e)
        return None


def _get_from_railway(path: str, api_key: str, base_url: str) -> dict | list | None:
    """GET from a Railway API endpoint. Returns response or None."""
    url = f"{base_url.rstrip('/')}{path}"
    headers = {"X-API-Key": api_key}
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning("Railway GET %s failed: %s", path, e)
        return None


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


# ── Trade Log Confirmation View ──────────────────────────────────────────────

class TradeLogView(discord.ui.View):
    """Confirm & Log / Cancel buttons for trade entry detection."""

    def __init__(self, trade_details: dict, cfg: dict = None, env_file: dict = None, timeout: float = 300.0):
        super().__init__(timeout=timeout)
        self.trade_details = trade_details
        self._cfg = cfg or {}
        self._env_file = env_file or {}

    @discord.ui.button(label="\u2705 Confirm & Log", style=discord.ButtonStyle.green)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        details = self.trade_details
        ticker = details.get("ticker", "?")
        signal_id = details.get("signal_id", "MANUAL")

        # 1. Write to decision_log.jsonl (VPS)
        try:
            from committee_decisions import log_decision
            is_committee = not signal_id.startswith("MANUAL_")
            log_decision(
                signal_id=signal_id,
                nick_decision="TAKE",
                committee_action="REVIEWED" if is_committee else "NOT_REVIEWED",
                is_override=False,
                recommendation={
                    "signal": {
                        "ticker": ticker,
                        "direction": details.get("direction"),
                        "signal_type": "MANUAL" if not is_committee else None,
                        "entry_price": details.get("entry_price"),
                        "stop_loss": details.get("stop_loss"),
                        "target_1": details.get("target"),
                    },
                },
            )
            logger.info("Logged manual trade to decision_log: %s %s", ticker, signal_id)
        except Exception as e:
            logger.warning("Failed to log manual trade: %s", e)

        # 2. POST to Railway /api/analytics/log-trade
        from pivot2_committee import load_openclaw_config, load_env_file, pick_env, OPENCLAW_ENV_FILE
        cfg = self._cfg or load_openclaw_config()
        env_file = self._env_file or load_env_file(OPENCLAW_ENV_FILE)
        api_key = pick_env("PIVOT_API_KEY", cfg, env_file) or ""
        base_url = pick_env("PANDORA_API_URL", cfg, env_file) or "https://pandoras-box-production.up.railway.app"

        trade_payload = {
            "signal_id": signal_id,
            "ticker": ticker,
            "direction": details.get("direction"),
            "entry_price": details.get("entry_price"),
            "stop_loss": details.get("stop_loss"),
            "target_1": details.get("target"),
            "notes": details.get("vehicle") or "",
            "origin": "pivot_chat",
        }
        _post_to_railway("/api/analytics/log-trade", trade_payload, api_key, base_url)

        # 3. POST to Railway /api/analytics/outcomes/manual
        outcome_payload = {
            "signal_id": signal_id,
            "symbol": ticker,
            "signal_type": f"MANUAL_{details.get('direction', 'UNK')}",
            "direction": details.get("direction") or "",
            "entry": details.get("entry_price"),
            "stop": details.get("stop_loss"),
            "t1": details.get("target"),
        }
        _post_to_railway("/api/analytics/outcomes/manual", outcome_payload, api_key, base_url)

        # 4. Confirm + disable buttons
        await interaction.followup.send(
            f"\u2705 **Trade logged:** {ticker} {details.get('direction', '')} "
            f"@ ${details.get('entry_price', '?')} \u2014 signal `{signal_id}`"
        )
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass
        self.stop()

    @discord.ui.button(label="\u274c Cancel", style=discord.ButtonStyle.grey)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("Trade logging cancelled.", ephemeral=True)
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass
        self.stop()


# ── Trade Detection Handlers ─────────────────────────────────────────────────

async def _handle_trade_detection(message: discord.Message, cfg: dict, env_file: dict) -> None:
    """Check message for trade entry patterns and prompt to log."""
    text = message.content.strip()

    details = _extract_trade_details(text)
    last_take = _load_last_take()

    # Link to recent committee TAKE if ticker matches
    if last_take and details.get("ticker") and last_take.get("ticker") == details["ticker"]:
        details["signal_id"] = last_take["signal_id"]
        details["direction"] = details.get("direction") or last_take.get("direction")
    elif last_take and not details.get("ticker"):
        # No ticker in message but recent TAKE — assume same ticker
        details["ticker"] = last_take["ticker"]
        details["direction"] = details.get("direction") or last_take.get("direction")
        details["signal_id"] = last_take["signal_id"]

    if not details.get("ticker"):
        await message.reply(
            "\U0001f4dd Looks like you entered a trade but I couldn't extract the ticker. "
            "Use `/log-trade TICKER DIRECTION PRICE` to log it manually."
        )
        return

    # Generate signal_id if not from committee
    if not details.get("signal_id"):
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        details["signal_id"] = f"MANUAL_{details['ticker']}_{details.get('direction', 'UNK')}_{ts}"

    linked = "" if details["signal_id"].startswith("MANUAL_") else " (linked to committee signal)"
    confirm_msg = (
        f"\U0001f4dd **Trade entry detected{linked}:**\n"
        f"Ticker: **{details.get('ticker', '?')}**\n"
        f"Direction: **{details.get('direction', '?')}**\n"
        f"Entry: **${details.get('entry_price', '?')}**\n"
        f"Signal: `{details.get('signal_id', 'MANUAL')}`\n\n"
        f"Confirm to log, or tell me the correct details."
    )
    view = TradeLogView(details, cfg=cfg, env_file=env_file)
    await message.reply(confirm_msg, view=view)


# ── Trade Close Confirmation View ────────────────────────────────────────────

class TradeCloseView(discord.ui.View):
    """Confirm & Close / Cancel buttons for trade exit detection."""

    def __init__(self, exit_details: dict, position: dict, cfg: dict = None, env_file: dict = None, timeout: float = 300.0):
        super().__init__(timeout=timeout)
        self.exit_details = exit_details
        self.position = position
        self._cfg = cfg or {}
        self._env_file = env_file or {}

    @discord.ui.button(label="\u2705 Confirm Close", style=discord.ButtonStyle.red)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        details = self.exit_details
        pos = self.position
        ticker = details.get("ticker", "?")
        exit_price = details.get("exit_price")

        from pivot2_committee import load_openclaw_config, load_env_file, pick_env, OPENCLAW_ENV_FILE
        cfg = self._cfg or load_openclaw_config()
        env_file = self._env_file or load_env_file(OPENCLAW_ENV_FILE)
        api_key = pick_env("PIVOT_API_KEY", cfg, env_file) or ""
        base_url = pick_env("PANDORA_API_URL", cfg, env_file) or "https://pandoras-box-production.up.railway.app"

        position_id = pos.get("position_id")
        close_payload = {
            "exit_price": exit_price,
            "quantity": pos.get("quantity"),
            "close_reason": "manual",
            "notes": "Closed via Pivot chat detection",
        }
        result = _post_to_railway(
            f"/api/v2/positions/{position_id}/close",
            close_payload, api_key, base_url,
        )

        if result and result.get("status") in ("closed", "partial_close"):
            pnl = result.get("realized_pnl", 0)
            outcome = result.get("trade_outcome", "?")
            pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
            await interaction.followup.send(
                f"\u2705 **Position closed:** {ticker} @ ${exit_price} — "
                f"{outcome} ({pnl_str})"
            )
        else:
            detail = result.get("detail", "Unknown error") if result else "API call failed"
            await interaction.followup.send(
                f"\u26a0\ufe0f Close failed for {ticker}: {detail}\n"
                f"Use the hub UI to close manually."
            )

        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass
        self.stop()

    @discord.ui.button(label="\u274c Skip", style=discord.ButtonStyle.grey)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("Close logging skipped.", ephemeral=True)
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass
        self.stop()


async def _handle_trade_exit_detection(message: discord.Message, cfg: dict, env_file: dict) -> None:
    """Check message for trade exit patterns and prompt to log the close."""
    text = message.content.strip()
    details = _extract_exit_details(text)

    if not details.get("ticker"):
        await message.reply(
            "\U0001f4dd Looks like you closed a trade but I couldn't extract the ticker. "
            "Close it via the hub UI or tell me: `closed TICKER at $PRICE`"
        )
        return

    # Look up matching open position via Railway API
    from pivot2_committee import load_openclaw_config, load_env_file, pick_env, OPENCLAW_ENV_FILE
    cfg_local = cfg or load_openclaw_config()
    env_file_local = env_file or load_env_file(OPENCLAW_ENV_FILE)
    api_key = pick_env("PIVOT_API_KEY", cfg_local, env_file_local) or ""
    base_url = pick_env("PANDORA_API_URL", cfg_local, env_file_local) or "https://pandoras-box-production.up.railway.app"

    positions = _get_from_railway(
        f"/api/v2/positions?status=OPEN&ticker={details['ticker']}",
        api_key, base_url,
    )

    if not positions:
        await message.reply(
            f"\U0001f4dd No open position found for **{details['ticker']}**. "
            f"It may already be closed, or close it via the hub UI."
        )
        return

    # Use the first matching open position
    pos = positions[0] if isinstance(positions, list) else None
    if not pos or not pos.get("position_id"):
        await message.reply(
            f"\U0001f4dd Couldn't match an open position for **{details['ticker']}**. "
            f"Close it via the hub UI."
        )
        return

    entry_price = pos.get("entry_price", 0)
    exit_price = details.get("exit_price")
    price_str = f"${exit_price}" if exit_price else "not specified"

    # Preview P&L if we have both prices
    pnl_preview = ""
    if exit_price and entry_price:
        struct = (pos.get("structure") or "").lower()
        is_stock = struct in ("stock", "stock_long", "long_stock", "stock_short", "short_stock")
        mult = 1 if is_stock else 100
        qty = pos.get("quantity", 1)
        est_pnl = round((exit_price - entry_price) * mult * qty, 2)
        pnl_preview = f"\nEst. P&L: **{'+'  if est_pnl >= 0 else ''}{est_pnl:.2f}**"

    if not exit_price:
        await message.reply(
            f"\U0001f4dd Trade exit detected for **{details['ticker']}** but no exit price found.\n"
            f"Tell me the price: `closed {details['ticker']} at $X.XX`"
        )
        return

    confirm_msg = (
        f"\U0001f4dd **Trade exit detected:**\n"
        f"Ticker: **{details['ticker']}**\n"
        f"Entry: **${entry_price}** → Exit: **{price_str}**\n"
        f"Qty: **{pos.get('quantity', '?')}**"
        f"{pnl_preview}\n\n"
        f"Confirm to close position, or skip."
    )
    view = TradeCloseView(details, pos, cfg=cfg, env_file=env_file)
    await message.reply(confirm_msg, view=view)


async def _handle_log_trade_command(message: discord.Message, cfg: dict, env_file: dict) -> None:
    """Parse: /log-trade PLTR SHORT 158.50 stop=161.50 target=150 vehicle=155p/150p"""
    text = message.content[len("/log-trade"):].strip()
    parts = text.split()

    if len(parts) < 2:
        await message.reply(
            "Usage: `/log-trade TICKER DIRECTION [PRICE] [stop=X] [target=X] [vehicle=desc]`\n"
            "Example: `/log-trade PLTR SHORT 158.50 stop=161.50 target=150`"
        )
        return

    ticker = parts[0].upper()
    direction = parts[1].upper() if len(parts) > 1 else "?"
    entry_price = None
    stop_loss = None
    target = None
    vehicle = None

    for p in parts[2:]:
        if p.startswith("stop="):
            try:
                stop_loss = float(p[5:])
            except ValueError:
                pass
        elif p.startswith("target="):
            try:
                target = float(p[7:])
            except ValueError:
                pass
        elif p.startswith("vehicle="):
            vehicle = p[8:].strip("\"'")
        else:
            try:
                entry_price = float(p.replace("$", ""))
            except ValueError:
                pass

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    details = {
        "ticker": ticker,
        "direction": direction,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "target": target,
        "vehicle": vehicle,
        "signal_id": f"MANUAL_{ticker}_{direction}_{ts}",
    }

    # Link to last committee TAKE if ticker matches
    last_take = _load_last_take()
    if last_take and last_take.get("ticker") == ticker:
        details["signal_id"] = last_take["signal_id"]

    linked = "" if details["signal_id"].startswith("MANUAL_") else " (linked to committee signal)"
    confirm_msg = (
        f"\U0001f4dd **Log trade{linked}:**\n"
        f"Ticker: **{ticker}** | Direction: **{direction}**\n"
        f"Entry: **${entry_price or '?'}** | Stop: **${stop_loss or '?'}** | Target: **${target or '?'}**\n"
        f"Signal: `{details['signal_id']}`"
    )
    view = TradeLogView(details, cfg=cfg, env_file=env_file)
    await message.reply(confirm_msg, view=view)


# ── Run Committee Button Handler ──────────────────────────────────────────────

async def _handle_macro_update_command(message: discord.Message, cfg: dict, env_file: dict) -> None:
    """
    Handle /macro-update command to update the persistent macro briefing.

    Usage:
      /macro-update Oil back above $95, Iran strikes expanding
      /macro-update regime=RISK-OFF narrative=New text here
      /macro-update fact Oil above $95
      /macro-update clear-facts  (reset key_facts list)
    """
    text = message.content[len("/macro-update"):].strip()
    if not text:
        await message.reply(
            "Usage:\n"
            "`/macro-update <text>` — add a key fact\n"
            "`/macro-update regime=RISK-OFF / STAGFLATION` — update regime label\n"
            "`/macro-update narrative=<full narrative>` — replace narrative\n"
            "`/macro-update clear-facts` — reset key facts list"
        )
        return

    briefing_path = pathlib.Path("/opt/openclaw/workspace/data/macro_briefing.json")

    # Load existing or start fresh
    try:
        data = json.loads(briefing_path.read_text(encoding="utf-8"))
    except Exception:
        data = {
            "regime": "UNKNOWN",
            "narrative": "",
            "key_facts": [],
            "sectors_to_watch": {},
        }

    # Parse command
    if text.lower() == "clear-facts":
        data["key_facts"] = []
        action = "Cleared all key facts"
    elif text.lower().startswith("regime="):
        data["regime"] = text[7:].strip()
        action = f"Updated regime to: {data['regime']}"
    elif text.lower().startswith("narrative="):
        data["narrative"] = text[10:].strip()
        action = "Updated narrative"
    elif text.lower().startswith("fact "):
        fact = text[5:].strip()
        if "key_facts" not in data:
            data["key_facts"] = []
        data["key_facts"].append(fact)
        action = f"Added fact: {fact}"
    else:
        # Default: add as key fact
        if "key_facts" not in data:
            data["key_facts"] = []
        data["key_facts"].append(text)
        action = f"Added fact: {text}"

    # Update timestamp
    data["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    data["updated_by"] = str(message.author)

    # Save locally
    try:
        briefing_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        await message.reply(f"Failed to save briefing: {e}")
        return

    # Sync to Railway Redis
    from pivot2_committee import pick_env
    api_key = pick_env("PIVOT_API_KEY", cfg, env_file) or ""
    base_url = pick_env("PANDORA_API_URL", cfg, env_file) or ""
    if base_url and api_key:
        try:
            _post_to_railway("/api/macro/briefing", data, api_key, base_url)
        except Exception as e:
            logger.warning("Failed to sync macro briefing to Railway: %s", e)

    facts_count = len(data.get("key_facts", []))
    await message.reply(
        f"Macro briefing updated.\n"
        f"**{action}**\n"
        f"Regime: {data.get('regime', '?')} | Facts: {facts_count}"
    )


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

    # Channel IDs to watch for trade entry messages
    _watch_channel_ids: set[int] = set()
    committee_ch = pick_env("COMMITTEE_CHANNEL_ID", cfg, env_file) or "1474135100521451813"
    if committee_ch:
        try:
            _watch_channel_ids.add(int(committee_ch))
        except ValueError:
            pass

    @bot.event
    async def on_ready():
        logger.info(f"Committee Interaction Handler ready as {bot.user}")
        if _watch_channel_ids:
            logger.info(f"Watching channels for trade detection: {_watch_channel_ids}")
        else:
            logger.warning("No COMMITTEE_CHANNEL_ID set — trade detection disabled")

    @bot.event
    async def on_message(message: discord.Message):
        # Ignore bots and messages outside watched channels
        if message.author.bot:
            return
        if _watch_channel_ids and message.channel.id not in _watch_channel_ids:
            return

        text = message.content.strip()
        if not text:
            return

        # /log-trade command
        if text.lower().startswith("/log-trade"):
            await _handle_log_trade_command(message, cfg, env_file)
            return

        # /macro-update command
        if text.lower().startswith("/macro-update"):
            await _handle_macro_update_command(message, cfg, env_file)
            return

        # "skip fill" acknowledgement
        if text.lower() == "skip fill":
            await message.reply("Got it \u2014 skipping fill logging for this one.")
            return

        # Auto-detect trade exit patterns (check BEFORE entry — "sold" matches both)
        if any(p.search(text) for p in TRADE_EXIT_PATTERNS):
            await _handle_trade_exit_detection(message, cfg, env_file)
            return

        # Auto-detect trade entry patterns
        if any(p.search(text) for p in TRADE_ENTRY_PATTERNS):
            await _handle_trade_detection(message, cfg, env_file)

    setup_committee_buttons(bot)
    bot.run(discord_token, log_handler=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
