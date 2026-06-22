"""OpenAI service for content generation and intent classification."""

from openai import OpenAI

from config.settings import OPENAI_API_KEY, OPENAI_MODEL
from utils.logger import get_logger
from utils.retry import retry

logger = get_logger(__name__)

client = OpenAI(api_key=OPENAI_API_KEY)


@retry(exceptions=(Exception,))
def generate(prompt: str, user_input: str, max_tokens: int = 2000) -> tuple[str, int]:
    """Generate content from a prompt + user input. Returns (text, token_usage)."""
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_input},
        ],
        max_tokens=max_tokens,
        temperature=0.7,
    )
    text = response.choices[0].message.content or ""
    tokens = response.usage.total_tokens if response.usage else 0
    logger.info("Generated %d chars, %d tokens", len(text), tokens)
    return text, tokens


@retry(exceptions=(Exception,))
def classify(prompt: str, user_input: str) -> str:
    """Classify intent from user input. Returns a single label."""
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_input},
        ],
        max_tokens=20,
        temperature=0.0,
    )
    label = (response.choices[0].message.content or "").strip().lower()
    logger.info("Classified as: %s", label)
    return label
