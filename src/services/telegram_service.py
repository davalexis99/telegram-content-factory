"""Telegram Bot API service for polling and sending messages."""

import httpx

from config.settings import TELEGRAM_BOT_TOKEN
from models.content import IncomingMessage
from utils.logger import get_logger

logger = get_logger(__name__)


class TelegramService:
    """Wraps the Telegram Bot API for long-polling and message dispatch."""

    def __init__(self, token: str | None = None) -> None:
        self.token = token or TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self._offset: int = 0

    async def poll(self) -> list[IncomingMessage]:
        """Fetch new messages since the last poll. Returns parsed messages."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self.base_url}/getUpdates",
                    params={"offset": self._offset, "timeout": 30},
                    timeout=35,
                )
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPError as exc:
                logger.error("Telegram API error: %s", exc)
                return []

        if not data.get("ok"):
            logger.error("Telegram API returned not ok: %s", data)
            return []

        messages: list[IncomingMessage] = []
        for update in data.get("result", []):
            self._offset = update["update_id"] + 1
            msg = update.get("message")
            if not msg or "text" not in msg:
                continue
            messages.append(
                IncomingMessage(
                    message_id=str(msg["message_id"]),
                    chat_id=str(msg["chat"]["id"]),
                    user_name=msg["from"].get("first_name", "unknown"),
                    text=msg["text"].strip(),
                )
            )

        if messages:
            logger.info("Received %d message(s)", len(messages))
        return messages

    async def send(self, chat_id: str, text: str) -> bool:
        """Send a Markdown-formatted message to a chat."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": text[:4096],
                        "parse_mode": "Markdown",
                    },
                    timeout=10,
                )
                resp.raise_for_status()
                ok: bool = resp.json().get("ok", False)
            except httpx.HTTPError as exc:
                logger.error("Send failed for %s: %s", chat_id, exc)
                return False

        if ok:
            preview = text[:80].replace("\n", " ")
            logger.info("Sent to %s: %s...", chat_id, preview)
        else:
            logger.error("Send returned not ok: %s", resp.json())
        return ok
