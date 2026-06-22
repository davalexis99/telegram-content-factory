"""
LLM service — the brain of the operation.

Python concepts:
    1.  MODULE-LEVEL SINGLETON — `_client` is created once when this module
        is first imported, then reused by every call.  Creating a new OpenAI
        client per request would be wasteful.
    2.  LAZY INITIALIZATION — `_ensure_client()` checks that a client exists
        before use, raising a clear error if no API key is configured.
    3.  TUPLE RETURN — `generate()` returns a tuple: (text, token_count).
        Python lets you unpack this inline:
            text, tokens = generate(prompt, user_input)

Provider selection logic:
    - If DEEPSEEK_API_KEY is set → use DeepSeek (cheaper, OpenAI-compatible)
    - Else if OPENAI_API_KEY is set → use OpenAI
    - Else → crash with a helpful message

DeepSeek uses the EXACT SAME OpenAI SDK.  The only difference is we pass
`base_url="https://api.deepseek.com"` when creating the client.  This is
possible because DeepSeek's API is a drop-in replacement for OpenAI's.
"""

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

# ── Provider selection (runs once at import time) ─────────────

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
    """Raise a clear error if no API key is configured."""
    if _client is None:
        raise RuntimeError(
            "No LLM API key configured. Set DEEPSEEK_API_KEY or OPENAI_API_KEY in .env"
        )
    return _client


# ── Public API ────────────────────────────────────────────────

@retry(exceptions=(Exception,))
def generate(prompt: str, user_input: str, max_tokens: int = 2000) -> tuple[str, int]:
    """
    Ask the LLM to generate content.

    Args:
        prompt:      System prompt (instructions for the AI — "You are a...")
        user_input:  The user's message (the idea to transform)
        max_tokens:  Cap on the response length (1 token ≈ ¾ of an English word)

    Returns:
        (response_text, token_usage) — the generated text and how many tokens it cost

    How it works:
        The LLM sees two messages in a "chat":
            1. system: "You are a LinkedIn content strategist. Rules: ..."
            2. user:   "The biggest mistake I made as a solo founder was..."
        It responds with just the generated post.

    `temperature=0.7` controls creativity.  0.0 = robotic/deterministic,
    1.0 = very creative/random.  0.7 is a balanced default for content.
    """
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
    """
    Ask the LLM to classify a message into a content type.

    Same as generate() but with temperature=0.0 (deterministic —
    we want consistent classification, not creative variety)
    and max_tokens=20 (the response is just one word like "linkedin_post").
    """
    client = _ensure_client()
    response = client.chat.completions.create(
        model=_model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_input},
        ],
        max_tokens=20,
        temperature=0.0,  # Deterministic — same input → same output
    )
    label = (response.choices[0].message.content or "").strip().lower()
    logger.info("Classified as: %s (%s)", label, _provider)
    return label
