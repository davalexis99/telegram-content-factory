#!/usr/bin/env python3
"""
Telegram Content Factory — interactive AI-powered content repurposing bot.

WHAT IT DOES:
    You send a raw idea via Telegram → the bot uses DeepSeek to turn it
    into a LinkedIn post, Twitter thread, or Notion page → you review
    and accept, rewrite, or quit.

ARCHITECTURE (read this first):
    This file is the ORCHESTRATOR.  It ties together all the other modules.
    Think of it as the conductor — it doesn't play any instrument itself,
    but it tells everyone else when to play.

    The dependency chain (bottom-up):
        config/          ← env vars, constants
        utils/           ← logger, retry decorator
        models/          ← IncomingMessage, GeneratedContent, ContentType
        services/        ← DeepSeek, Telegram API, Notion API
        prompts/         ← .txt files with AI instructions
        router/          ← decides WHAT to generate and WHO generates it
        workflows/       ← the actual content generation pipelines
        main.py  ← YOU ARE HERE — ties everything together

STATE MACHINE:
    Each Telegram chat has a Session with one of three states:

    AWAITING_IDEA ──→ AWAITING_DECISION ──→ AWAITING_FEEDBACK
         ↑                   │                     │
         │    /quit          │  /accept            │ feedback sent
         └───────────────────┘  (saves to Notion)  │
         ↑                                         │
         └─────────────────────────────────────────┘

    Commands (/accept, /rewrite, /quit, /start) ALWAYS work,
    regardless of what state you're in.  This prevents the
    frustrating "I typed /quit but nothing happened" bug.

HOW TO RUN:
    cd telegram-content-factory
    python3 src/main.py

    Make sure .env has:
        DEEPSEEK_API_KEY=sk-...
        TELEGRAM_BOT_TOKEN=12345:ABC...
        NOTION_API_KEY=ntn_...
        NOTION_DATABASE_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
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

# ═══════════════════════════════════════════════════════════════
#  STATE MACHINE
# ═══════════════════════════════════════════════════════════════
#
#  Why a state machine?  Because the meaning of a user's message
#  depends on context.  "make it shorter" means FEEDBACK if the
#  bot just showed a draft, but a NEW IDEA if the bot is idle.
#  The state tells us which one it is.


class State(Enum):
    """
    The three states a conversation can be in.

    Enum ensures you can't accidentally set state to "waiting_for_idea"
    (typo).  Only State.AWAITING_IDEA, State.AWAITING_DECISION, or
    State.AWAITING_FEEDBACK are valid.
    """
    AWAITING_IDEA = "awaiting_idea"         # Bot is idle, waiting for a new idea
    AWAITING_DECISION = "awaiting_decision" # Bot showed a result, waiting for /accept or /rewrite or /quit
    AWAITING_FEEDBACK = "awaiting_feedback" # Bot asked "what would you like changed?", waiting for reply


@dataclass
class Session:
    """
    Per-chat state.  One Session per Telegram chat_id.

    This is stored in an in-memory dictionary (sessions dict below).
    IMPORTANT: in-memory storage means sessions are LOST when the bot
    restarts.  For a production bot, you'd persist these to a database.
    For now, it's fine — sessions are short-lived (seconds to minutes).
    """
    state: State = State.AWAITING_IDEA
    last_result: GeneratedContent | None = None  # The most recent generated content
    original_text: str = ""                       # The user's raw idea (preserved for rewrites)
    content_type: ContentType = ContentType.UNKNOWN
    attempts: int = 0                             # How many rewrite rounds for this idea


# The global session store.  key = chat_id (string), value = Session
# In a multi-process deployment, this would be Redis or a database table.
sessions: dict[str, Session] = {}


# ═══════════════════════════════════════════════════════════════
#  CONSTANTS (messages sent to the user)
# ═══════════════════════════════════════════════════════════════

WELCOME = (
    "Send me a raw idea or topic and I'll turn it into a LinkedIn post, "
    "Twitter thread, or Notion page.\n\n"
    "Commands (work anytime):\n"
    "• /accept — save to Notion\n"
    "• /rewrite — request changes\n"
    "• /quit — start over (aliases: /q, /cancel, /reset)\n"
    "• /start — this message"
)

FEEDBACK_PROMPT = "What would you like changed? Send your feedback and I'll regenerate."

UNKNOWN_RESPONSE = (
    "Not sure what to make of that. Send me a topic, idea, or thought "
    "you'd like turned into content."
)


# ═══════════════════════════════════════════════════════════════
#  HELPERS (small utility functions used by the state handlers)
# ═══════════════════════════════════════════════════════════════


def _extract_title(text: str, content_type: ContentType) -> str:
    """
    Pull a short title from generated content for the Notion database.

    Takes the first line, strips markdown headers (#), and truncates
    to 100 characters.  If the first line is empty, falls back to the
    content type name like "Linkedin Post".
    """
    first_line = text.strip().split("\n")[0].strip().lstrip("#").strip()
    return first_line[:100] or content_type.value.replace("_", " ").title()


def _format_preview(result: GeneratedContent) -> str:
    """
    Format generated content for Telegram delivery.

    Adds a header with the content type, emoji, and token count,
    then the generated text, then a footer with command hints.
    """
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
    """
    Get or create a session for a chat.

    Uses dict.setdefault() pattern — if the key doesn't exist,
    create a new Session.  Returns the existing one otherwise.
    """
    if chat_id not in sessions:
        sessions[chat_id] = Session()
    return sessions[chat_id]


# ═══════════════════════════════════════════════════════════════
#  STATE HANDLERS
# ═══════════════════════════════════════════════════════════════
#
#  Each handler is an async function that takes:
#      telegram: TelegramService  — to send messages back
#      msg:      IncomingMessage   — the user's message
#      session:  Session           — this chat's state
#
#  Handlers are "fire and forget" — they don't return anything,
#  they just mutate the session and send Telegram responses.


async def handle_idea(telegram: TelegramService, msg, session: Session) -> None:
    """
    A new idea was received.  Classify it, generate content, present it.

    This is the main entry point for content generation.  Every message
    that isn't a command and isn't feedback flows through here.

    Steps:
        1. Classify: rules first (free), AI fallback (if needed)
        2. Tell the user we're working (async operations take time)
        3. Route to the right workflow (LinkedIn / Twitter / Notion)
        4. Format and send the result
        5. Update session state to AWAITING_DECISION
    """
    content_type = classify_intent(msg.text)
    msg.content_type = content_type

    if content_type == ContentType.UNKNOWN:
        await telegram.send(msg.chat_id, UNKNOWN_RESPONSE)
        return

    # Let the user know we're working — the LLM call might take 5-20 seconds
    await telegram.send(
        msg.chat_id,
        f"Generating {content_type.value.replace('_', ' ')}...",
    )

    result = await route_and_generate(msg)
    if result is None:
        await telegram.send(msg.chat_id, "Something went wrong. Give it another try?")
        return

    # Send the result.  Notion content is sent as plain text because
    # Markdown headers (# ##) in the generated text break Telegram's parser.
    preview = _format_preview(result)
    use_md = content_type != ContentType.NOTION_PAGE
    await telegram.send(msg.chat_id, preview, parse_mode="Markdown" if use_md else None)

    # Update session for the next step (user will /accept, /rewrite, or /quit)
    session.state = State.AWAITING_DECISION
    session.last_result = result
    session.original_text = msg.text
    session.content_type = content_type
    session.attempts = 1


async def handle_accept(telegram: TelegramService, msg, session: Session) -> None:
    """
    User accepted the generated content.  Save it to Notion.

    Flow:
        1. Extract a title from the first line
        2. Call Notion API to add a row to the Content Factory database
        3. Send the Notion URL back to the user
        4. Reset the session (ready for a new idea)

    If there's no last_result (e.g., user typed /accept before generating
    anything), we send a helpful message instead of crashing.
    """
    result = session.last_result
    if result is None:
        await telegram.send(msg.chat_id, "Nothing to save right now. Send me an idea first!")
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
    except Exception:
        logger.exception("Notion save failed")
        await telegram.send(
            msg.chat_id,
            "❌ Couldn't save to Notion. Check that your integration "
            "has access to the Content Factory database.",
        )

    # Reset — ready for a new idea
    session.state = State.AWAITING_IDEA
    session.last_result = None


async def handle_rewrite(telegram: TelegramService, msg, session: Session) -> None:
    """
    User wants changes.  Ask what they want changed.

    We transition to AWAITING_FEEDBACK.  The next non-command message
    the user sends will be treated as rewrite instructions, not a new idea.
    """
    await telegram.send(msg.chat_id, FEEDBACK_PROMPT)
    session.state = State.AWAITING_FEEDBACK


async def handle_quit(telegram: TelegramService, msg, session: Session) -> None:
    """
    User wants to abandon this result.  Reset and let them refine.

    The original idea is discarded.  The user can send a new one
    immediately — perhaps with more context or a different angle.
    """
    await telegram.send(
        msg.chat_id,
        "Send your refined idea when ready — add more context, "
        "change the angle, whatever you need.",
    )
    session.state = State.AWAITING_IDEA
    session.last_result = None


async def handle_feedback(telegram: TelegramService, msg, session: Session) -> None:
    """
    User sent feedback after /rewrite.  Regenerate with enriched context.

    The original idea, user's feedback, and previous draft are all
    combined into one prompt so the LLM has full context.  This is
    more effective than just sending the feedback alone — the LLM
    sees what it wrote before and can adjust specifically.

    The enriched prompt structure:
        Original idea: <what the user first sent>
        Rewrite instructions: <the user's feedback>
        Previous draft for reference: <first 500 chars of last output>
    """
    if session.last_result is None:
        await telegram.send(msg.chat_id, "Nothing to rewrite. Send a fresh idea?")
        session.state = State.AWAITING_IDEA
        return

    await telegram.send(msg.chat_id, "Rewriting with your feedback...")

    # Build an enriched prompt that gives the LLM full context
    enriched = (
        f"Original idea: {session.original_text}\n\n"
        f"Rewrite instructions: {msg.text}\n\n"
        f"Previous draft for reference:\n{session.last_result.output_text[:500]}"
    )

    # Override the message text with our enriched version
    # and re-classify/re-generate
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


# ═══════════════════════════════════════════════════════════════
#  COMMAND ROUTER
# ═══════════════════════════════════════════════════════════════
#
#  Commands are matched by PREFIX, so /q, /qu, /qui, /quit all work.
#  This also handles typos like /quite (resolves to "quit" via prefix).
#
#  The matching algorithm: try exact match first, then longest-prefix
#  match.  "/quit" matches "/quit" exactly → "quit".  "/quite" starts
#  with "/quit" → "quit".  "/q" starts with "/q" → "quit".

COMMAND_MAP: dict[str, str] = {
    # accept
    "/accept": "accept",
    "/acc": "accept",
    "/ac": "accept",
    # rewrite
    "/rewrite": "rewrite",
    "/re": "rewrite",
    "/rw": "rewrite",
    # quit (multiple aliases — the most common command)
    "/quit": "quit",
    "/q": "quit",
    "/cancel": "quit",
    "/reset": "quit",
    # start
    "/start": "start",
}


def _resolve_command(text: str) -> str | None:
    """
    Resolve user text to a command name, or None if it's not a command.

    Tries exact match first, then falls back to prefix matching.
    Sorted by length (longest first) so "/rewrite" matches before "/re".
    """
    text = text.strip().lower()
    # Exact match
    if text in COMMAND_MAP:
        return COMMAND_MAP[text]
    # Prefix match — check longer commands first
    for cmd, action in sorted(COMMAND_MAP.items(), key=lambda x: -len(x[0])):
        if text.startswith(cmd):
            return action
    return None


# ═══════════════════════════════════════════════════════════════
#  MAIN DISPATCHER
# ═══════════════════════════════════════════════════════════════
#
#  Every incoming message passes through this function exactly once.
#  It decides: is this a command?  Feedback?  A new idea?
#
#  ORDER MATTERS here:
#     1. Commands first (always active, regardless of state)
#     2. State-based routing (feedback or new idea)


async def dispatch(telegram: TelegramService, msg) -> None:
    """
    Route an incoming message to the right handler.

    This is the single entry point for ALL messages.  The dispatch
    logic is intentionally flat and readable — no deep nesting,
    no complex conditions.  Each branch either handles the message
    (and returns) or falls through to the next check.
    """
    chat_id = msg.chat_id
    session = _get_session(chat_id)
    text = msg.text.strip().lower()

    # ── Step 1: Is this a command? ──
    cmd = _resolve_command(text)

    if cmd == "start":
        # /start always resets everything and shows the welcome message
        session.state = State.AWAITING_IDEA
        session.last_result = None
        await telegram.send(chat_id, WELCOME, parse_mode="Markdown")
        return

    if cmd == "quit":
        # /quit works in ANY state — resets and lets you start over
        await handle_quit(telegram, msg, session)
        return

    if cmd == "accept":
        # /accept saves to Notion if there's something to save,
        # otherwise sends a helpful message
        if session.last_result is None:
            await telegram.send(chat_id, "Nothing to save right now. Send me an idea first!")
        else:
            await handle_accept(telegram, msg, session)
        return

    if cmd == "rewrite":
        # Same as accept — works if there's something to rewrite
        if session.last_result is None:
            await telegram.send(chat_id, "Nothing to rewrite. Send me an idea first!")
        else:
            await handle_rewrite(telegram, msg, session)
        return

    # ── Step 2: Not a command.  What state are we in? ──

    if session.state == State.AWAITING_FEEDBACK:
        # The bot asked "what would you like changed?" — this message is the answer
        await handle_feedback(telegram, msg, session)
        return

    # ── Step 3: Default — treat as a new idea ──
    await handle_idea(telegram, msg, session)


# ═══════════════════════════════════════════════════════════════
#  MAIN LOOP
# ═══════════════════════════════════════════════════════════════
#
#  This is the entry point.  It runs forever (until Ctrl+C),
#  polling Telegram for new messages and dispatching each one.
#
#  asyncio.run() is the standard way to start an async program
#  in Python 3.7+.  It creates an event loop, runs the coroutine,
#  and cleans up when it finishes.


async def main() -> None:
    """
    Run the bot's main polling loop.

    This function never returns under normal operation.
    It polls Telegram every POLLING_INTERVAL seconds (default 2),
    dispatches any new messages, and repeats.
    """
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
                # Each message is dispatched independently.
                # If one fails, the others still get processed.
                await dispatch(telegram, msg)
        except asyncio.CancelledError:
            # Graceful shutdown on Ctrl+C
            logger.info("Shutting down...")
            break
        except Exception:
            # Catch-all: log the error and keep polling.
            # A single bad message should never crash the bot.
            logger.exception("Polling loop error")
        await asyncio.sleep(POLLING_INTERVAL)


# Python convention: if this file is run directly (not imported),
# execute main().  If someone does `from main import something`,
# main() does NOT run.
if __name__ == "__main__":
    asyncio.run(main())
