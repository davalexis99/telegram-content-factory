"""Data models for the Telegram Content Factory."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ContentType(Enum):
    LINKEDIN_POST = "linkedin_post"
    TWITTER_THREAD = "twitter_thread"
    NOTION_PAGE = "notion_page"
    UNKNOWN = "unknown"


@dataclass
class IncomingMessage:
    message_id: str
    chat_id: str
    user_name: str
    text: str
    received_at: datetime = field(default_factory=datetime.utcnow)
    content_type: ContentType = ContentType.UNKNOWN
    # Callback fields (inline keyboard presses)
    callback_data: str | None = None
    callback_message_id: str | None = None


@dataclass
class GeneratedContent:
    content_type: ContentType
    source_message: IncomingMessage
    output_text: str
    token_usage: int
    generated_at: datetime = field(default_factory=datetime.utcnow)
    notion_url: str | None = None
