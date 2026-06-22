"""Raw idea → structured Notion page content with humanizer pass."""

from pathlib import Path

from models.content import ContentType, GeneratedContent, IncomingMessage
from services.openai_service import generate as ai_generate
from utils.logger import get_logger

logger = get_logger(__name__)

PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"


def _load_prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text()


async def generate(msg: IncomingMessage) -> GeneratedContent:
    """Generate Notion page content from a raw idea, then de-AI it."""
    system_prompt = _load_prompt("notion_prompt.txt")

    logger.info("Generating Notion page for %s...", msg.user_name)
    draft, tokens1 = ai_generate(system_prompt, msg.text, max_tokens=3000)

    # Humanizer pass
    humanizer_prompt = _load_prompt("humanizer_pass.txt")
    final, tokens2 = ai_generate(humanizer_prompt, draft, max_tokens=3000)

    final_text = final.strip()

    result = GeneratedContent(
        content_type=ContentType.NOTION_PAGE,
        source_message=msg,
        output_text=final_text,
        token_usage=tokens1 + tokens2,
    )
    logger.info(
        "Notion page ready — %d chars, %d tokens (draft %d + humanizer %d)",
        len(result.output_text), result.token_usage, tokens1, tokens2,
    )
    return result
