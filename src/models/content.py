"""
Data models for the Telegram Content Factory.

Python concepts:
    1.  DATACLASS — @dataclass auto-generates __init__, __repr__, and __eq__
        so you don't have to write boilerplate.  Just declare the fields.
    2.  ENUM — ContentType is an enumeration.  Instead of passing raw strings
        like "linkedin_post" around (error-prone), you use ContentType.LINKEDIN_POST.
        The `.value` property gives you the underlying string when needed.
    3.  OPTIONAL TYPES — `str | None` means "this can be a string OR None".
        Python 3.10+ syntax (older code uses Optional[str] from typing).

These models are "dumb" — they just hold data.  All business logic lives
in the service and workflow modules.  This separation makes the codebase
easier to test and reason about.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ContentType(Enum):
    """
    The four possible intents the bot can classify a message into.

    Using an Enum instead of raw strings means:
        - IDE autocompletion shows you the valid options
        - You can't accidentally type "linked_post" (typo caught at runtime)
        - Pattern matching works cleanly: match content_type: case ContentType.LINKEDIN_POST: ...
    """
    LINKEDIN_POST = "linkedin_post"
    TWITTER_THREAD = "twitter_thread"
    NOTION_PAGE = "notion_page"
    UNKNOWN = "unknown"


@dataclass
class IncomingMessage:
    """
    Represents one message received from Telegram.

    This is the input to the entire pipeline.  All fields are either
    extracted from Telegram's raw JSON or set during processing.

    `field(default_factory=datetime.utcnow)` means: every time a new
    IncomingMessage is created without an explicit received_at, set it
    to the current UTC time.  Using default_factory (not just default=)
    ensures each instance gets its own timestamp.
    """
    message_id: str
    chat_id: str             # Telegram chat ID (unique per user/conversation)
    user_name: str            # First name of the sender
    text: str                 # The message text (or caption if photo)
    received_at: datetime = field(default_factory=datetime.utcnow)
    content_type: ContentType = ContentType.UNKNOWN  # Set by the classifier later

    # Callback fields (for inline keyboard presses — currently unused,
    # but kept for future keyboard support)
    callback_data: str | None = None
    callback_message_id: str | None = None


@dataclass
class GeneratedContent:
    """
    The output of a content generation workflow.

    After the bot generates a LinkedIn post, Twitter thread, or Notion page,
    it wraps everything in this object and stores it in the user's session
    so /accept or /rewrite can act on it.

    `notion_url` is set to None initially and populated after the user accepts
    and the content is saved to the Notion database.
    """
    content_type: ContentType          # What kind of content was generated
    source_message: IncomingMessage    # The original idea that triggered this
    output_text: str                   # The final humanizer-passed text
    token_usage: int                   # Total tokens used (draft + humanizer pass)
    generated_at: datetime = field(default_factory=datetime.utcnow)
    notion_url: str | None = None      # Set after saving to Notion
