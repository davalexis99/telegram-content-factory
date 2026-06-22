"""Application configuration loaded from environment."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# Telegram
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

# OpenAI
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = "gpt-4.1"

# Notion
NOTION_API_KEY: str = os.getenv("NOTION_API_KEY", "")
NOTION_PARENT_PAGE_ID: str = os.getenv("NOTION_PARENT_PAGE_ID", "")
NOTION_API_VERSION: str = "2022-06-28"

# Supabase
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# App
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
POLLING_INTERVAL: int = int(os.getenv("POLLING_INTERVAL", "2"))
MAX_RETRIES: int = 3
