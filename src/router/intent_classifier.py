"""Hybrid intent classifier — rules-first with LLM fallback."""

from pathlib import Path

from config.settings import DEEPSEEK_API_KEY, OPENAI_API_KEY
from models.content import ContentType
from utils.logger import get_logger

logger = get_logger(__name__)

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"

# Rule-based keywords mapped to content types
RULES: dict[ContentType, list[str]] = {
    ContentType.LINKEDIN_POST: [
        "linkedin", "linkedin post", "professional", "career",
        "business insight", "thought leadership", "industry",
        "my experience", "i learned", "story for linkedin",
    ],
    ContentType.TWITTER_THREAD: [
        "twitter", "tweet", "x post", "thread", "hot take",
        "short post", "quick thought", "tweet this",
    ],
    ContentType.NOTION_PAGE: [
        "notion", "long form", "guide", "documentation",
        "detailed", "wiki", "knowledge base", "how to",
        "write a page", "notion doc", "research",
    ],
}


def _rule_classify(text: str) -> ContentType | None:
    """Try to classify using keyword rules. Returns None if no match."""
    lowered = text.lower()
    for content_type, keywords in RULES.items():
        if any(kw in lowered for kw in keywords):
            logger.info("Rule matched: %s", content_type.value)
            return content_type
    return None


def _ai_classify(text: str) -> ContentType:
    """Fallback: classify using LLM."""
    from services.openai_service import classify

    prompt_path = PROMPT_DIR / "intent_classifier_prompt.txt"
    system_prompt = prompt_path.read_text()
    label = classify(system_prompt, text)

    # Map label string to ContentType
    label = label.strip().lower().replace("-", "_")
    for ct in ContentType:
        if ct.value == label:
            return ct

    logger.warning("Unrecognized label '%s', defaulting to UNKNOWN", label)
    return ContentType.UNKNOWN


def classify_intent(text: str) -> ContentType:
    """Classify a user message into a content type. Rules first, AI fallback."""
    if not (DEEPSEEK_API_KEY or OPENAI_API_KEY):
        logger.warning("No LLM API key set — using rules only")
        return _rule_classify(text) or ContentType.UNKNOWN

    result = _rule_classify(text)
    if result is not None:
        return result

    logger.info("Rules missed — falling back to AI classifier")
    return _ai_classify(text)
