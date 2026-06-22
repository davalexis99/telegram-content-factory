"""Workflow router — dispatches classified intents to content generation pipelines."""

from models.content import ContentType, GeneratedContent, IncomingMessage
from utils.logger import get_logger

logger = get_logger(__name__)


async def route_and_generate(msg: IncomingMessage) -> GeneratedContent | None:
    """Route a classified message to the correct workflow and return generated content."""

    if msg.content_type == ContentType.UNKNOWN:
        logger.info("Skipping unknown intent from %s: %s", msg.user_name, msg.text[:60])
        return None

    logger.info(
        "Routing '%s' → %s (%s)",
        msg.text[:60],
        msg.content_type.value,
        msg.user_name,
    )

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

    return await gen(msg)
