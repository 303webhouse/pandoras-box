"""
Pivot Discord Bot — entry point for standalone VPS deployment.

Reads Unusual Whales Discord channels and forwards parsed flow data
to the Pandora's Box API.

Required env vars (loaded from .env in the same directory):
    DISCORD_BOT_TOKEN       Discord bot token
    PANDORA_API_URL         Pandora's Box API base URL
    PIVOT_API_KEY           Bearer token for Pandora's Box API
    UW_FLOW_CHANNEL_ID      Unusual Whales live flow channel ID
    UW_TICKER_CHANNEL_ID    Unusual Whales ticker channel ID
    UW_BOT_USER_ID          Unusual Whales bot user ID (to filter its messages)

See .env.example for the full list of optional settings.
"""

import os
import sys

# Load .env from the same directory as this file before any other imports.
# This ensures all env vars are available even if systemd EnvironmentFile
# hasn't propagated them yet (e.g. during manual testing).
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# discord_bridge is deployed alongside this file by deploy.sh
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from discord_bridge.bot import run_bot  # noqa: E402

if __name__ == "__main__":
    run_bot()
