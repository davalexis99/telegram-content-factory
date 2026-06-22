"""Notion API service — adds accepted content to the Content Factory database."""

import httpx
from datetime import datetime, timezone

from config.settings import NOTION_API_KEY, NOTION_API_VERSION, NOTION_DATABASE_ID
from models.content import ContentType
from utils.logger import get_logger
from utils.retry import retry

logger = get_logger(__name__)

NOTION_BASE = "https://api.notion.com/v1"

HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": NOTION_API_VERSION,
    "Content-Type": "application/json",
}

TYPE_LABELS: dict[ContentType, str] = {
    ContentType.LINKEDIN_POST: "LinkedIn Post",
    ContentType.TWITTER_THREAD: "Twitter Thread",
    ContentType.NOTION_PAGE: "Notion Page",
}


@retry(exceptions=(Exception,))
def add_to_database(
    title: str,
    source_idea: str,
    content: str,
    content_type: ContentType,
    tokens: int,
) -> str:
    """Add a row to the Content Factory database. Returns the page URL."""
    body = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "Title": {"title": [{"text": {"content": title[:100]}}]},
            "Type": {
                "type": "select",
                "select": {"name": TYPE_LABELS.get(content_type, "LinkedIn Post")},
            },
            "Source Idea": {
                "type": "rich_text",
                "rich_text": [{"text": {"content": source_idea[:2000]}}],
            },
            "Content": {
                "type": "rich_text",
                "rich_text": [{"text": {"content": content[:2000]}}],
            },
            "Tokens": {"type": "number", "number": tokens},
            "Created": {
                "type": "date",
                "date": {"start": datetime.now(timezone.utc).isoformat()},
            },
        },
    }

    resp = httpx.post(f"{NOTION_BASE}/pages", headers=HEADERS, json=body, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    page_id: str = data.get("id", "")
    url = f"https://notion.so/{page_id.replace('-', '')}"
    logger.info("Added to database: %s → %s", title, url)
    return url
