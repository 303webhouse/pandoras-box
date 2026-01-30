#!/usr/bin/env python3
"""
Run the Pandora Bridge Discord Bot

Usage:
    python run_discord_bot.py

Environment Variables Required:
    DISCORD_BOT_TOKEN - Your Discord bot token
    DISCORD_FLOW_CHANNEL_ID - Channel ID for flow alerts (default: 1463692055694807201)
    PANDORA_API_URL - Pandora's Box API URL (default: https://pandoras-box-production.up.railway.app/api)
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables from config/.env
load_dotenv(os.path.join(os.path.dirname(__file__), 'config', '.env'))

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from discord_bridge.bot import run_bot

if __name__ == "__main__":
    print("Starting Pandora Bridge Discord Bot...")
    print(f"Channel ID: {os.getenv('DISCORD_FLOW_CHANNEL_ID', '1463692055694807201')}")
    print(f"API URL: {os.getenv('PANDORA_API_URL', 'https://pandoras-box-production.up.railway.app/api')}")
    run_bot()
