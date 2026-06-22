"""
Raw idea → polished LinkedIn post with humanizer pass.

This is a WORKFLOW — a self-contained pipeline that transforms one kind
of input into one kind of output.  Every workflow in this project follows
the same interface:
    async def generate(msg: IncomingMessage) -> GeneratedContent

The two-pass approach:
    1.  DRAFT PASS — Use the LinkedIn prompt to generate a post
    2.  HUMANIZER PASS — Feed the draft through a de-AI filter that
        strips corporate buzzwords, AI vocabulary, em-dashes, etc.

Why two passes instead of one better prompt?
    Even with strong anti-AI-ism instructions in the main prompt, LLMs
    tend to drift back toward "additionally, moreover, furthermore" on
    long outputs.  A dedicated second pass with a focused de-AI prompt
    catches what the first pass missed.
"""

from pathlib import Path

from models.content import ContentType, GeneratedContent, IncomingMessage
from services.openai_service import generate as ai_generate
from utils.logger import get_logger

logger = get_logger(__name__)

# All prompts live in src/prompts/, two levels up from this file
PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"


def _load_prompt(name: str) -> str:
    """Read a .txt prompt file from the prompts directory."""
    return (PROMPT_DIR / name).read_text()


async def generate(msg: IncomingMessage) -> GeneratedContent:
    """
    Generate a LinkedIn post from a raw idea.

    Pipeline:
        raw idea → LinkedIn draft → humanizer filter → final post

    The humanizer pass roughly doubles token usage but produces output
    that reads like a real person wrote it, not a corporate AI.
    """
    system_prompt = _load_prompt("linkedin_prompt.txt")

    logger.info("Generating LinkedIn post for %s...", msg.user_name)

    # ── Pass 1: Generate draft ──
    draft, tokens1 = ai_generate(system_prompt, msg.text, max_tokens=1500)

    # ── Pass 2: De-AI the draft ──
    humanizer_prompt = _load_prompt("humanizer_pass.txt")
    final, tokens2 = ai_generate(humanizer_prompt, draft, max_tokens=1500)

    result = GeneratedContent(
        content_type=ContentType.LINKEDIN_POST,
        source_message=msg,
        output_text=final.strip(),
        token_usage=tokens1 + tokens2,  # Total cost of both passes
    )
    logger.info(
        "LinkedIn post ready — %d chars, %d tokens (draft %d + humanizer %d)",
        len(result.output_text), result.token_usage, tokens1, tokens2,
    )
    return result
