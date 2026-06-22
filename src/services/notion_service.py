"""
Notion API service — logs accepted content to the Content Factory database.

Python concepts:
    1.  TYPE HINTS — `dict[ContentType, str]` tells you this is a dictionary
        mapping ContentType enums to strings.  Your IDE uses this for
        autocompletion and type-checking.
    2.  f-STRING — f"Bearer {NOTION_API_KEY}" interpolates the variable
        directly into the string.  Cleaner than "Bearer " + NOTION_API_KEY.
    3.  UTC DATETIME — We store times in UTC (timezone-aware) to avoid
        timezone bugs when the bot runs in a different region than the user.

The Notion flow:
    1.  User types /accept after reviewing generated content
    2.  main.py calls add_to_database() from this module
    3.  A new row appears in the Content Factory database with:
        Title, Type, Source Idea, Content, Tokens, Created date
"""

import httpx
from datetime import datetime, timezone

from config.settings import NOTION_API_KEY, NOTION_API_VERSION, NOTION_DATABASE_ID
from models.content import ContentType
from utils.logger import get_logger
from utils.retry import retry

logger = get_logger(__name__)

NOTION_BASE = "https://api.notion.com/v1"

# Headers shared by all Notion API calls
HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": NOTION_API_VERSION,
    "Content-Type": "application/json",
}

# Maps our internal ContentType enum to the human-readable labels
# shown in the Notion database's "Type" select column.
TYPE_LABELS: dict[ContentType, str] = {
    ContentType.LINKEDIN_POST: "LinkedIn Post",
    ContentType.TWITTER_THREAD: "Twitter Thread",
    ContentType.NOTION_PAGE: "Notion Page",
}


def _format_page_id(raw: str) -> str:
    """
    Insert hyphens into a 32-char hex page/database ID to make a valid UUID.

    Notion IDs in URLs are 32 hex chars without hyphens:
        https://notion.so/387de492352481a28849d3d056c7ca29

    The API expects hyphenated UUID format:
        387de492-3524-81a2-8849-d3d056c7ca29

    If the ID is already hyphenated, we strip and re-insert to be safe.
    """
    clean = raw.strip().replace("-", "")
    if len(clean) == 32:
        return f"{clean[:8]}-{clean[8:12]}-{clean[12:16]}-{clean[16:20]}-{clean[20:]}"
    return raw  # Return as-is if it doesn't look like a 32-char hex ID


@retry(exceptions=(Exception,))
def add_to_database(
    title: str,
    source_idea: str,
    content: str,
    content_type: ContentType,
    tokens: int,
) -> str:
    """
    Add a row to the Content Factory database.  Returns the page URL.

    This creates a new page INSIDE the database (not a standalone page).
    The database ID comes from NOTION_DATABASE_ID in .env.

    Each property in the database (Title, Type, Source Idea, etc.) must
    be specified with its correct Notion API type:
        - title:     array of rich text objects
        - select:    {name: "LinkedIn Post"}
        - rich_text: array of rich text objects
        - number:    plain integer
        - date:      {start: ISO 8601 string}

    Content is truncated to 2000 chars per Notion's rich_text limit.
    For longer content, we'd need to split across multiple blocks.
    """
    page_id = _format_page_id(NOTION_DATABASE_ID)

    body = {
        "parent": {"database_id": page_id},
        "properties": {
            "Title": {
                "title": [{"text": {"content": title[:100]}}],
            },
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
            "Tokens": {
                "type": "number",
                "number": tokens,
            },
            "Created": {
                "type": "date",
                "date": {"start": datetime.now(timezone.utc).isoformat()},
            },
        },
    }

    resp = httpx.post(f"{NOTION_BASE}/pages", headers=HEADERS, json=body, timeout=30)
    resp.raise_for_status()  # Raise an exception on 4xx/5xx
    data = resp.json()

    page_id_result: str = data.get("id", "")
    url = f"https://notion.so/{page_id_result.replace('-', '')}"
    logger.info("Added to database: %s → %s", title, url)
    return url
