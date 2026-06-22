"""Raw idea → structured Notion page with humanizer pass."""

from pathlib import Path

from models.content import ContentType, GeneratedContent, IncomingMessage
from services.openai_service import generate as ai_generate
from services.notion_service import create_page
from utils.logger import get_logger

logger = get_logger(__name__)

PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"


def _load_prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text()


async def generate(msg: IncomingMessage) -> GeneratedContent:
    """Generate a Notion page from a raw idea, de-AI it, and publish to Notion."""
    system_prompt = _load_prompt("notion_prompt.txt")

    logger.info("Generating Notion page for %s...", msg.user_name)
    draft, tokens1 = ai_generate(system_prompt, msg.text, max_tokens=3000)

    # Humanizer pass
    humanizer_prompt = _load_prompt("humanizer_pass.txt")
    final, tokens2 = ai_generate(humanizer_prompt, draft, max_tokens=3000)

    final_text = final.strip()

    # Extract title from first H1 line, or fall back to first 80 chars
    title = final_text.split("\n")[0].lstrip("#").strip()[:100] or msg.text[:80]

    # Publish to Notion
    notion_url: str | None = None
    try:
        notion_url = create_page(title, final_text)
    except Exception as exc:
        logger.error("Notion publish failed: %s", exc)

    result = GeneratedContent(
        content_type=ContentType.NOTION_PAGE,
        source_message=msg,
        output_text=final_text,
        token_usage=tokens1 + tokens2,
        notion_url=notion_url,
    )
    logger.info(
        "Notion page ready — %d chars, %d tokens (draft %d + humanizer %d)%s",
        len(result.output_text),
        result.token_usage,
        tokens1,
        tokens2,
        f" → {notion_url}" if notion_url else "",
    )
    return result
