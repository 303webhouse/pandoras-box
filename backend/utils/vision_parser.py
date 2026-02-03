"""
AI Vision parser for UW Discord images
Uses Claude Vision API to extract structured data from options flow images
"""

import os
import json
import base64
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

import aiohttp
import anthropic

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")


def _extract_json(raw_text: str) -> Optional[Dict[str, Any]]:
    """Extract JSON from a Claude response (handles fenced blocks)."""
    if not raw_text:
        return None

    text = raw_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


async def _call_claude_vision(image_base64: str, media_type: str) -> str:
    """Call Claude Vision in a worker thread to avoid blocking the event loop."""

    def _call() -> str:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_base64,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Parse this Unusual Whales image and return ONLY valid JSON (no markdown, no explanation).\n\n"
                                "First, identify what type of data this is:\n"
                                "- \"highest_volume_contracts\" - Options flow table with tickers, strikes, volume\n"
                                "- \"market_tide\" - Overall market sentiment with bullish/bearish percentages\n"
                                "- \"sector_flow\" - Sector-by-sector flow data\n"
                                "- \"economic_calendar\" - Upcoming economic events\n"
                                "- \"flow_alerts\" - Unusual options activity alerts\n"
                                "- \"oi_change\" - Open interest changes\n"
                                "- \"other\" - Any other data type\n\n"
                                "Return format based on type:\n\n"
                                "For \"highest_volume_contracts\":\n"
                                "{\n"
                                "  \"data_type\": \"highest_volume_contracts\",\n"
                                "  \"contracts\": [\n"
                                "    {\"ticker\": \"NVDA\", \"strike\": 190, \"option_type\": \"CALL\", \"volume\": 240000, \"open_interest\": 12578, \"premium_pct\": 47},\n"
                                "    ...\n"
                                "  ],\n"
                                "  \"total_calls\": <count>,\n"
                                "  \"total_puts\": <count>,\n"
                                "  \"sentiment\": \"BULLISH\" or \"BEARISH\" or \"NEUTRAL\"\n"
                                "}\n\n"
                                "For \"market_tide\":\n"
                                "{\n"
                                "  \"data_type\": \"market_tide\",\n"
                                "  \"bullish_pct\": <number 0-100>,\n"
                                "  \"bearish_pct\": <number 0-100>,\n"
                                "  \"call_premium\": <total call premium if shown>,\n"
                                "  \"put_premium\": <total put premium if shown>,\n"
                                "  \"sentiment\": \"BULLISH\" or \"BEARISH\" or \"NEUTRAL\",\n"
                                "  \"confidence\": \"HIGH\" or \"MEDIUM\" or \"LOW\" based on how skewed the data is\n"
                                "}\n\n"
                                "For \"sector_flow\":\n"
                                "{\n"
                                "  \"data_type\": \"sector_flow\",\n"
                                "  \"sectors\": [\n"
                                "    {\"name\": \"Technology\", \"sentiment\": \"BULLISH\", \"flow_value\": 1500000},\n"
                                "    {\"name\": \"Healthcare\", \"sentiment\": \"BEARISH\", \"flow_value\": -500000},\n"
                                "    ...\n"
                                "  ],\n"
                                "  \"bullish_sectors\": [\"Technology\", \"Financials\"],\n"
                                "  \"bearish_sectors\": [\"Healthcare\", \"Energy\"],\n"
                                "  \"overall_sentiment\": \"BULLISH\" or \"BEARISH\" or \"NEUTRAL\"\n"
                                "}\n\n"
                                "For \"economic_calendar\":\n"
                                "{\n"
                                "  \"data_type\": \"economic_calendar\",\n"
                                "  \"events\": [\n"
                                "    {\"time\": \"8:30 AM\", \"event\": \"CPI\", \"importance\": \"HIGH\", \"forecast\": \"3.2%\", \"previous\": \"3.1%\"},\n"
                                "    ...\n"
                                "  ],\n"
                                "  \"high_impact_count\": <number of HIGH importance events>,\n"
                                "  \"trading_caution\": true/false\n"
                                "}\n\n"
                                "For \"flow_alerts\" or \"oi_change\":\n"
                                "{\n"
                                "  \"data_type\": \"flow_alerts\",\n"
                                "  \"alerts\": [\n"
                                "    {\"ticker\": \"AAPL\", \"type\": \"SWEEP\", \"sentiment\": \"BULLISH\", \"premium\": 500000, \"strike\": 230, \"expiry\": \"2026-02-07\"},\n"
                                "    ...\n"
                                "  ],\n"
                                "  \"dominant_sentiment\": \"BULLISH\" or \"BEARISH\" or \"MIXED\"\n"
                                "}\n\n"
                                "For \"other\":\n"
                                "{\n"
                                "  \"data_type\": \"other\",\n"
                                "  \"description\": \"<brief description of what the image shows>\",\n"
                                "  \"key_data\": {<any relevant extracted data as key-value pairs>},\n"
                                "  \"sentiment\": \"BULLISH\" or \"BEARISH\" or \"NEUTRAL\" or \"UNKNOWN\"\n"
                                "}\n\n"
                                "Convert K to thousands (240K = 240000), M to millions. Extract all visible data."
                            ),
                        },
                    ],
                }
            ],
        )
        return message.content[0].text.strip()

    return await asyncio.to_thread(_call)


async def parse_uw_image(image_url: str) -> Optional[Dict[str, Any]]:
    """
    Parse a UW options flow image using Claude Vision

    Args:
        image_url: URL of the Discord image attachment

    Returns:
        Structured data extracted from the image
    """
    if not ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set, cannot parse images")
        return None

    try:
        # Download image
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status != 200:
                    logger.error(f"Failed to download image: {resp.status}")
                    return None
                image_data = await resp.read()

        # Convert to base64
        image_base64 = base64.standard_b64encode(image_data).decode("utf-8")

        # Determine media type from URL
        url_lower = image_url.lower()
        if url_lower.endswith(".png"):
            media_type = "image/png"
        elif url_lower.endswith(".jpg") or url_lower.endswith(".jpeg"):
            media_type = "image/jpeg"
        else:
            media_type = "image/png"

        # Call Claude Vision
        response_text = await _call_claude_vision(image_base64, media_type)

        # Parse response
        data = _extract_json(response_text)
        if not data:
            logger.error("Failed to parse JSON from Claude response")
            logger.debug(f"Raw response: {response_text}")
            return None

        data["timestamp"] = datetime.now().isoformat()
        data["source"] = "uw_discord_vision"

        logger.info(
            f"✅ Parsed UW image: {len(data.get('contracts', []))} contracts, "
            f"sentiment: {data.get('sentiment')}"
        )

        return data

    except Exception as e:
        logger.error(f"Error parsing UW image: {e}")
        return None
