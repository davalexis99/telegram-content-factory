"""
Raw idea → structured Notion page content with humanizer pass.

Same two-pass pipeline as the other workflows, but different from the
original version that auto-published to Notion.  Now, the workflow only
generates the text — actual Notion database logging happens in main.py
when the user types /accept.
"""

from pathlib import Path

from models.content import ContentType, GeneratedContent, IncomingMessage
from services.openai_service import generate as ai_generate
from utils.logger import get_logger

logger = get_logger(__name__)

PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"


def _load_prompt(name: str) -> str:
    """Read a .txt prompt file from the prompts directory."""
    return (PROMPT_DIR / name).read_text()


async def generate(msg: IncomingMessage) -> GeneratedContent:
    """
    Generate Notion page content from a raw idea.

    Pipeline:
        raw idea → Notion draft (Markdown) → humanizer filter → final text

    The text is returned but NOT published.  Publishing happens when
    the user accepts via /accept in main.py.
    """
    system_prompt = _load_prompt("notion_prompt.txt")

    logger.info("Generating Notion page for %s...", msg.user_name)

    # ── Pass 1: Generate draft ──
    draft, tokens1 = ai_generate(system_prompt, msg.text, max_tokens=3000)

    # ── Pass 2: De-AI the draft ──
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
