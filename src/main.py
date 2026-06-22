#!/usr/bin/env python3
"""Telegram Content Factory — interactive AI-powered content repurposing bot.

Flow:
  User sends idea → AI generates → user types accept / rewrite / quit
      accept  → logs to Notion database, done
      rewrite → asks for feedback, regenerates with it
      quit    → clears session, user can refine and resend
"""

import asyncio
from dataclasses import dataclass
from enum import Enum

from config.settings import POLLING_INTERVAL
from models.content import ContentType, GeneratedContent
from router.intent_classifier import classify_intent
from router.workflow_router import route_and_generate
from services.notion_service import add_to_database
from services.telegram_service import TelegramService
from utils.logger import get_logger

logger = get_logger(__name__)

# ── State machine ────────────────────────────────────────────


class State(Enum):
    AWAITING_IDEA = "awaiting_idea"
    AWAITING_DECISION = "awaiting_decision"
    AWAITING_FEEDBACK = "awaiting_feedback"


@dataclass
class Session:
    state: State = State.AWAITING_IDEA
    last_result: GeneratedContent | None = None
    original_text: str = ""
    content_type: ContentType = ContentType.UNKNOWN
    attempts: int = 0


sessions: dict[str, Session] = {}

WELCOME = (
    "Send me a raw idea or topic and I'll turn it into a LinkedIn post, "
    "Twitter thread, or Notion page.\n\n"
    "After you get the result:\n"
    "• /accept — save to Notion\n"
    "• /rewrite — request changes\n"
    "• /quit — start over"
)

FEEDBACK_PROMPT = "What would you like changed? Send your feedback and I'll regenerate."

UNKNOWN_RESPONSE = (
    "Not sure what to make of that. Send me a topic, idea, or thought "
    "you'd like turned into content."
)


# ── Helpers ──────────────────────────────────────────────────


def _extract_title(text: str, content_type: ContentType) -> str:
    first_line = text.strip().split("\n")[0].strip().lstrip("#").strip()
    return first_line[:100] or content_type.value.replace("_", " ").title()


def _format_preview(result: GeneratedContent) -> str:
    ct = result.content_type
    emoji = {"linkedin_post": "📝", "twitter_thread": "🐦", "notion_page": "📄"}.get(
        ct.value, "📄"
    )
    type_name = ct.value.replace("_", " ").title()
    return (
        f"{emoji} *{type_name}* ({result.token_usage} tokens)\n\n"
        f"{result.output_text}\n\n"
        f"━━━━━━━━━━━━━━\n"
        f"_Reply:_ /accept /rewrite /quit"
    )


def _get_session(chat_id: str) -> Session:
    if chat_id not in sessions:
        sessions[chat_id] = Session()
    return sessions[chat_id]


# ── State handlers ───────────────────────────────────────────


async def handle_idea(telegram: TelegramService, msg, session: Session) -> None:
    """Received a raw idea — classify, generate, present."""
    content_type = classify_intent(msg.text)
    msg.content_type = content_type

    if content_type == ContentType.UNKNOWN:
        await telegram.send(msg.chat_id, UNKNOWN_RESPONSE)
        return

    # Notify user we're working
    await telegram.send(msg.chat_id, f"Generating {content_type.value.replace('_', ' ')}...")

    result = await route_and_generate(msg)
    if result is None:
        await telegram.send(msg.chat_id, "Something went wrong. Give it another try?")
        return

    preview = _format_preview(result)
    use_md = content_type != ContentType.NOTION_PAGE
    await telegram.send(msg.chat_id, preview, parse_mode="Markdown" if use_md else None)

    session.state = State.AWAITING_DECISION
    session.last_result = result
    session.original_text = msg.text
    session.content_type = content_type
    session.attempts = 1


async def handle_accept(telegram: TelegramService, msg, session: Session) -> None:
    """User accepted — log to Notion, confirm, reset."""
    result = session.last_result
    if result is None:
        await telegram.send(msg.chat_id, "Nothing to save. Send a fresh idea?")
        session.state = State.AWAITING_IDEA
        return

    title = _extract_title(result.output_text, result.content_type)
    try:
        url = add_to_database(
            title=title,
            source_idea=session.original_text,
            content=result.output_text,
            content_type=result.content_type,
            tokens=result.token_usage,
        )
        await telegram.send(msg.chat_id, f"✅ Saved to Notion: {url}")
    except Exception as exc:
        logger.exception("Notion save failed: %s", exc)
        await telegram.send(msg.chat_id, "❌ Couldn't save to Notion. Check your integration.")

    session.state = State.AWAITING_IDEA
    session.last_result = None


async def handle_rewrite(telegram: TelegramService, msg, session: Session) -> None:
    """User wants changes — ask for feedback."""
    await telegram.send(msg.chat_id, FEEDBACK_PROMPT)
    session.state = State.AWAITING_FEEDBACK


async def handle_quit(telegram: TelegramService, msg, session: Session) -> None:
    """User quit — reset and let them refine."""
    await telegram.send(
        msg.chat_id,
        "Send your refined idea when ready — add more context, change the angle, whatever you need.",
    )
    session.state = State.AWAITING_IDEA
    session.last_result = None


async def handle_feedback(telegram: TelegramService, msg, session: Session) -> None:
    """User sent feedback — regenerate with it appended to original idea."""
    if session.last_result is None:
        await telegram.send(msg.chat_id, "Nothing to rewrite. Send a fresh idea?")
        session.state = State.AWAITING_IDEA
        return

    await telegram.send(msg.chat_id, "Rewriting with your feedback...")

    enriched = (
        f"Original idea: {session.original_text}\n\n"
        f"Rewrite instructions: {msg.text}\n\n"
        f"Previous draft for reference:\n{session.last_result.output_text[:500]}"
    )

    msg.text = enriched
    msg.content_type = session.content_type

    result = await route_and_generate(msg)
    if result is None:
        await telegram.send(msg.chat_id, "Rewrite failed. Try again?")
        return

    preview = _format_preview(result)
    use_md = result.content_type != ContentType.NOTION_PAGE
    await telegram.send(msg.chat_id, preview, parse_mode="Markdown" if use_md else None)

    session.state = State.AWAITING_DECISION
    session.last_result = result
    session.attempts += 1


# ── Router ───────────────────────────────────────────────────

COMMANDS = {"/accept", "/rewrite", "/quit"}


async def dispatch(telegram: TelegramService, msg) -> None:
    """Route a message based on session state and content."""
    chat_id = msg.chat_id
    session = _get_session(chat_id)
    text = msg.text.strip().lower()

    # /start always resets
    if text == "/start":
        session.state = State.AWAITING_IDEA
        session.last_result = None
        await telegram.send(chat_id, WELCOME, parse_mode="Markdown")
        return

    # Command in AWAITING_DECISION state
    if text in COMMANDS and session.state == State.AWAITING_DECISION:
        if text == "/accept":
            await handle_accept(telegram, msg, session)
        elif text == "/rewrite":
            await handle_rewrite(telegram, msg, session)
        elif text == "/quit":
            await handle_quit(telegram, msg, session)
        return

    # If pending feedback, the text IS the feedback
    if session.state == State.AWAITING_FEEDBACK:
        await handle_feedback(telegram, msg, session)
        return

    # Otherwise, treat as a new idea
    await handle_idea(telegram, msg, session)


# ── Main loop ────────────────────────────────────────────────


async def main() -> None:
    """Run the polling loop."""
    logger.info("Starting Telegram Content Factory...")
    telegram = TelegramService()

    if not telegram.token:
        logger.error("TELEGRAM_BOT_TOKEN not set — exiting.")
        return

    logger.info("Bot ready. Polling every %ds.", POLLING_INTERVAL)

    while True:
        try:
            messages = await telegram.poll()
            for msg in messages:
                await dispatch(telegram, msg)
        except asyncio.CancelledError:
            logger.info("Shutting down...")
            break
        except Exception:
            logger.exception("Polling loop error")
        await asyncio.sleep(POLLING_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
