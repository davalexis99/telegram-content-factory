"""
Workflow router — dispatches a classified message to the correct content generator.

Python concepts:
    1.  MATCH/CASE — Python 3.10's pattern matching.  Like a switch statement
        but more powerful.  Each `case` branch runs when the value matches.
        The `case _:` is a wildcard (matches anything, like `default:`).
    2.  LAZY IMPORT — `from workflows.linkedin_post import generate as gen`
        inside the function.  This avoids importing all workflow modules at
        startup.  Each is only loaded the first time it's actually needed.

Why a separate router?
    The intent_classifier decides WHAT to generate.  The workflow_router
    decides WHO generates it.  Separating them means you can add new
    workflow types (e.g., "instagram_caption") by:
        1. Adding a keyword rule in intent_classifier.py
        2. Adding a case branch here
        3. Creating the new workflow module
    No other files need to change.
"""

from models.content import ContentType, GeneratedContent, IncomingMessage
from utils.logger import get_logger

logger = get_logger(__name__)


async def route_and_generate(msg: IncomingMessage) -> GeneratedContent | None:
    """
    Route a classified message to the correct workflow and return the result.

    Args:
        msg: An IncomingMessage with content_type already set by the classifier.

    Returns:
        A GeneratedContent object, or None if the content type is unknown
        or an error occurred.

    Each workflow module follows the same interface:
        async def generate(msg: IncomingMessage) -> GeneratedContent
    This consistency means the router doesn't need to know HOW each
    workflow works — just that it accepts a message and returns content.
    """

    if msg.content_type == ContentType.UNKNOWN:
        logger.info("Skipping unknown intent from %s: %s", msg.user_name, msg.text[:60])
        return None

    logger.info(
        "Routing '%s' → %s (%s)",
        msg.text[:60],
        msg.content_type.value,
        msg.user_name,
    )

    # Pattern-match on content type and import the right workflow
    match msg.content_type:
        case ContentType.LINKEDIN_POST:
            from workflows.linkedin_post import generate as gen
        case ContentType.TWITTER_THREAD:
            from workflows.twitter_thread import generate as gen
        case ContentType.NOTION_PAGE:
            from workflows.notion_page import generate as gen
        case _:
            logger.error("Unhandled content type: %s", msg.content_type)
            return None

    # All workflows are called the same way — the router doesn't care
    # about the internal differences between LinkedIn and Twitter generation.
    return await gen(msg)
