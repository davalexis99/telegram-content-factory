"""Notion API service for creating pages."""

import httpx

from config.settings import NOTION_API_KEY, NOTION_API_VERSION, NOTION_PARENT_PAGE_ID
from utils.logger import get_logger
from utils.retry import retry

logger = get_logger(__name__)

NOTION_BASE = "https://api.notion.com/v1"

HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": NOTION_API_VERSION,
    "Content-Type": "application/json",
}


@retry(exceptions=(Exception,))
def create_page(title: str, content: str) -> str:
    """Create a Notion page under the configured parent. Returns the page URL."""
    children = [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"text": {"content": chunk[:2000]}}],
            },
        }
        for chunk in (content[i : i + 2000] for i in range(0, len(content), 2000))
    ]

    body = {
        "parent": {"page_id": NOTION_PARENT_PAGE_ID},
        "properties": {
            "title": {"title": [{"text": {"content": title[:100]}}]},
        },
        "children": children,
    }

    resp = httpx.post(f"{NOTION_BASE}/pages", headers=HEADERS, json=body, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    page_id: str = data.get("id", "")
    url = f"https://notion.so/{page_id.replace('-', '')}"
    logger.info("Created Notion page: %s", url)
    return url
