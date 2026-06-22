"""LLM service — DeepSeek primary, OpenAI fallback. Both use the OpenAI SDK."""

from openai import OpenAI

from config.settings import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    OPENAI_API_KEY,
    OPENAI_MODEL,
)
from utils.logger import get_logger
from utils.retry import retry

logger = get_logger(__name__)

# Prefer DeepSeek, fall back to OpenAI
if DEEPSEEK_API_KEY:
    _client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    _model = DEEPSEEK_MODEL
    _provider = "DeepSeek"
elif OPENAI_API_KEY:
    _client = OpenAI(api_key=OPENAI_API_KEY)
    _model = OPENAI_MODEL
    _provider = "OpenAI"
else:
    _client = None
    _model = ""
    _provider = "none"

logger.info("LLM provider: %s (model=%s)", _provider, _model or "unset")


def _ensure_client() -> OpenAI:
    if _client is None:
        raise RuntimeError(
            "No LLM API key configured. Set DEEPSEEK_API_KEY or OPENAI_API_KEY in .env"
        )
    return _client


@retry(exceptions=(Exception,))
def generate(prompt: str, user_input: str, max_tokens: int = 2000) -> tuple[str, int]:
    """Generate content from a prompt + user input. Returns (text, token_usage)."""
    client = _ensure_client()
    response = client.chat.completions.create(
        model=_model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_input},
        ],
        max_tokens=max_tokens,
        temperature=0.7,
    )
    text = response.choices[0].message.content or ""
    tokens = response.usage.total_tokens if response.usage else 0
    logger.info("Generated %d chars, %d tokens (%s)", len(text), tokens, _provider)
    return text, tokens


@retry(exceptions=(Exception,))
def classify(prompt: str, user_input: str) -> str:
    """Classify intent from user input. Returns a single label."""
    client = _ensure_client()
    response = client.chat.completions.create(
        model=_model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_input},
        ],
        max_tokens=20,
        temperature=0.0,
    )
    label = (response.choices[0].message.content or "").strip().lower()
    logger.info("Classified as: %s (%s)", label, _provider)
    return label
