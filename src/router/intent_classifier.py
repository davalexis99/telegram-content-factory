"""
Hybrid intent classifier — rules first, AI fallback.

Python concepts:
    1.  HYBRID PATTERN — Fast/cheap check first (keyword rules), expensive
        check second (LLM call).  Most messages match rules so we rarely
        hit the AI, saving latency and cost.
    2.  EARLY RETURN — `if result is not None: return result` exits the
        function immediately.  This avoids nesting and keeps the code flat.
    3.  PATHLIB — Path(__file__).resolve().parents[1] navigates the
        filesystem relative to this file's location, not the current
        working directory.  Safe and portable.

Classification priority:
    1.  Rule match (free, instant) → return immediately
    2.  No rule match + API key configured → call LLM
    3.  No rule match + no API key → return UNKNOWN
"""

from pathlib import Path

from config.settings import DEEPSEEK_API_KEY, OPENAI_API_KEY
from models.content import ContentType
from utils.logger import get_logger

logger = get_logger(__name__)

# Directory containing prompt .txt files
PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"

# ── Rule-based classification ────────────────────────────────
#
# Each ContentType has a list of trigger keywords.  If the user's
# message (lowercased) contains any of these, we classify immediately
# without calling the LLM.
#
# These rules cover ~80% of messages because users tend to be explicit:
# "write a LinkedIn post about..." or "tweet this: ..."

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
    """
    Try to classify using keyword rules.

    Returns a ContentType if a keyword matches, None otherwise.
    None signals "rules couldn't classify, try AI fallback."
    """
    lowered = text.lower()
    for content_type, keywords in RULES.items():
        if any(kw in lowered for kw in keywords):
            logger.info("Rule matched: %s", content_type.value)
            return content_type
    return None


def _ai_classify(text: str) -> ContentType:
    """
    Fallback: ask the LLM to classify the message.

    Loads the classifier prompt from prompts/intent_classifier_prompt.txt,
    calls the LLM, and maps the response to a ContentType enum.
    If the LLM returns an unrecognized label, defaults to UNKNOWN.
    """
    from services.openai_service import classify  # Lazy import to avoid circular deps

    prompt_path = PROMPT_DIR / "intent_classifier_prompt.txt"
    system_prompt = prompt_path.read_text()
    label = classify(system_prompt, text)

    # Normalize and match.  "linkedin_post" → ContentType.LINKEDIN_POST
    label = label.strip().lower().replace("-", "_")
    for ct in ContentType:
        if ct.value == label:
            return ct

    logger.warning("Unrecognized label '%s', defaulting to UNKNOWN", label)
    return ContentType.UNKNOWN


# ── Public API ────────────────────────────────────────────────

def classify_intent(text: str) -> ContentType:
    """
    Classify a user message into a content type.

    This is the only function the rest of the codebase calls.
    It tries rules first (free), then falls back to the LLM.

    If no LLM API key is configured, only rules are used.
    """
    if not (DEEPSEEK_API_KEY or OPENAI_API_KEY):
        logger.warning("No LLM API key set — using rules only")
        return _rule_classify(text) or ContentType.UNKNOWN

    result = _rule_classify(text)
    if result is not None:
        return result

    logger.info("Rules missed — falling back to AI classifier")
    return _ai_classify(text)
