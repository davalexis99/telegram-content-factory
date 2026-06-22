"""
Application configuration loaded from environment variables.

Python concept: This module uses the "module-level constants" pattern.
Variables defined at module level (outside any function) are evaluated once
when the module is first imported.  Other modules import these with:
    from config.settings import DEEPSEEK_API_KEY

The `os.getenv("KEY", "default")` call reads environment variables.
python-dotenv loads a `.env` file into the process environment so you
don't have to manually export every variable in your shell.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env file two levels up from this file (project root)
# Path(__file__) = .../src/config/settings.py
# .parents[2]    = .../src  → then up to project root
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# ── LLM Provider ──────────────────────────────────────────────
# DeepSeek is our primary AI.  It's OpenAI-compatible, meaning we use
# the `openai` Python package but point it at api.deepseek.com instead.
# If DEEPSEEK_API_KEY is unset, the service falls back to OpenAI.

DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
DEEPSEEK_MODEL: str = "deepseek-chat"  # DeepSeek's flagship model

# OpenAI (fallback — only used if DeepSeek key is missing)
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = "gpt-4.1"

# ── Telegram ──────────────────────────────────────────────────
# Bot token from @BotFather.  Looks like: 1234567890:ABCdef...
# This is the ONLY thing needed to connect to Telegram's Bot API.

TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

# ── Notion ────────────────────────────────────────────────────
# NOTION_API_KEY: Create at https://notion.so/my-integrations
# NOTION_DATABASE_ID: The Content Factory database (32-char hex UUID)
# NOTION_API_VERSION: Notion's API version header (required on every call)

NOTION_API_KEY: str = os.getenv("NOTION_API_KEY", "")
NOTION_DATABASE_ID: str = os.getenv("NOTION_DATABASE_ID", "")
NOTION_API_VERSION: str = "2022-06-28"

# ── Supabase (optional — unused currently) ────────────────────

SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# ── App behaviour ─────────────────────────────────────────────

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
POLLING_INTERVAL: int = int(os.getenv("POLLING_INTERVAL", "2"))
MAX_RETRIES: int = 3  # How many times to retry a failed API call
