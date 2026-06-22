#!/usr/bin/env python3
"""Telegram Content Factory — AI-powered content repurposing bot.

Polling loop: receive messages → classify intent → generate content → respond.
"""

import asyncio

from config.settings import POLLING_INTERVAL
from models.content import ContentType
from router.intent_classifier import classify_intent
from router.workflow_router import route_and_generate
from services.telegram_service import TelegramService
from utils.logger import get_logger

logger = get_logger(__name__)

WELCOME_TEXT = (
    "Hey! Send me a raw idea, thought, or topic and I'll turn it into:\n"
    "• A LinkedIn post\n"
    "• A Twitter thread\n"
    "• A Notion page\n\n"
    "Just type your idea — I'll figure out the format."
)

UNKNOWN_RESPONSE = (
    "Not sure what to make of that. Try sending me a topic, idea, or thought "
    "you'd like turned into a LinkedIn post, Twitter thread, or Notion page."
)

ERROR_RESPONSE = "Something went wrong generating that. Give it another try?"


async def process_message(telegram: TelegramService, msg) -> None:
    """Full pipeline: classify → generate → respond."""
    chat_id = msg.chat_id

    # Send a quick typing indicator substitute — a brief "working on it" reply
    # (Telegram doesn't expose typing indicator via Bot API in a polling setup)

    # Step 1: classify
    content_type = classify_intent(msg.text)
    msg.content_type = content_type

    if content_type == ContentType.UNKNOWN:
        await telegram.send(chat_id, UNKNOWN_RESPONSE)
        return

    # Step 2: route and generate
    result = await route_and_generate(msg)

    if result is None:
        await telegram.send(chat_id, ERROR_RESPONSE)
        return

    # Step 3: respond
    response_text = _format_response(result)
    await telegram.send(chat_id, response_text)


def _format_response(result) -> str:
    """Format the generated content for Telegram delivery."""
    ct = result.content_type
    text = result.output_text

    if ct == ContentType.LINKEDIN_POST:
        header = "📝 *LinkedIn Post*\n\n"
    elif ct == ContentType.TWITTER_THREAD:
        header = "🐦 *Twitter Thread*\n\n"
    elif ct == ContentType.NOTION_PAGE:
        header = "📄 *Notion Page*\n\n"
        if result.notion_url:
            header += f"🔗 {result.notion_url}\n\n"
    else:
        header = ""

    return header + text


async def main() -> None:
    """Run the polling loop."""
    logger.info("Starting Telegram Content Factory...")
    telegram = TelegramService()

    if not telegram.token:
        logger.error("TELEGRAM_BOT_TOKEN not set — exiting.")
        return

    logger.info(
        "Bot ready. Polling every %ds. Send /start to begin.",
        POLLING_INTERVAL,
    )

    while True:
        try:
            messages = await telegram.poll()

            for msg in messages:
                text = msg.text.strip()

                # Handle /start command
                if text == "/start":
                    await telegram.send(msg.chat_id, WELCOME_TEXT)
                    continue

                # Process content requests
                await process_message(telegram, msg)

        except asyncio.CancelledError:
            logger.info("Shutting down...")
            break
        except Exception as exc:
            logger.exception("Polling loop error: %s", exc)

        await asyncio.sleep(POLLING_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
