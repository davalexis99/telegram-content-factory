"""Telegram Bot API service for polling, sending messages, and inline keyboards."""

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

    # ── polling ──────────────────────────────────────────────

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

        results = data.get("result", [])
        messages: list[IncomingMessage] = []
        for update in results:
            self._offset = update["update_id"] + 1

            # Handle callback queries (inline keyboard presses)
            callback = update.get("callback_query")
            if callback:
                msg_data = callback.get("message", {})
                chat = msg_data.get("chat", {})
                user = callback.get("from", {})
                messages.append(
                    IncomingMessage(
                        message_id=str(callback["id"]),
                        chat_id=str(chat.get("id", "")),
                        user_name=user.get("first_name", "unknown"),
                        text=callback.get("data", ""),
                        callback_data=callback.get("data", ""),
                        callback_message_id=str(msg_data.get("message_id", "")),
                    )
                )
                continue

            # Handle regular text messages
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

    # ── sending ───────────────────────────────────────────────

    async def send(
        self, chat_id: str, text: str, parse_mode: str | None = "Markdown"
    ) -> bool:
        """Send a text message."""
        payload: dict = {"chat_id": chat_id, "text": text[:4096]}
        if parse_mode:
            payload["parse_mode"] = parse_mode

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/sendMessage", json=payload, timeout=10
                )
                resp.raise_for_status()
                ok: bool = resp.json().get("ok", False)
            except httpx.HTTPError as exc:
                logger.error("Send failed for %s: %s", chat_id, exc)
                return False

        if ok:
            preview = text[:80].replace("\n", " ")
            logger.info("Sent to %s: %s...", chat_id, preview)
        return ok

    async def send_with_keyboard(
        self,
        chat_id: str,
        text: str,
        buttons: list[list[tuple[str, str]]],
        parse_mode: str | None = None,
        edit_message_id: str | None = None,
    ) -> bool:
        """Send or edit a message with an inline keyboard.

        buttons is a list of rows, each row is a list of (label, callback_data) pairs.
        Example: [[("Accept", "accept"), ("Rewrite", "rewrite"), ("Quit", "quit")]]
        """
        keyboard = [
            [
                {"text": label, "callback_data": data}
                for label, data in row
            ]
            for row in buttons
        ]
        reply_markup = {"inline_keyboard": keyboard}

        payload: dict = {
            "text": text[:4096],
            "reply_markup": reply_markup,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        async with httpx.AsyncClient() as client:
            try:
                if edit_message_id:
                    payload["chat_id"] = chat_id
                    payload["message_id"] = edit_message_id
                    resp = await client.post(
                        f"{self.base_url}/editMessageText",
                        json=payload,
                        timeout=10,
                    )
                else:
                    payload["chat_id"] = chat_id
                    resp = await client.post(
                        f"{self.base_url}/sendMessage",
                        json=payload,
                        timeout=10,
                    )
                resp.raise_for_status()
                ok: bool = resp.json().get("ok", False)
            except httpx.HTTPError as exc:
                logger.error("Keyboard send failed: %s", exc)
                return False

        logger.info("Keyboard %s to %s", "edited" if edit_message_id else "sent", chat_id)
        return ok

    async def answer_callback(self, callback_id: str, text: str = "") -> bool:
        """Acknowledge a callback query (removes the loading spinner)."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/answerCallbackQuery",
                    json={"callback_query_id": callback_id, "text": text},
                    timeout=5,
                )
                return resp.json().get("ok", False)
            except httpx.HTTPError:
                return False

    async def delete_message(self, chat_id: str, message_id: str) -> bool:
        """Delete a message."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/deleteMessage",
                    json={"chat_id": chat_id, "message_id": message_id},
                    timeout=5,
                )
                return resp.json().get("ok", False)
            except httpx.HTTPError:
                return False
