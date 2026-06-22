"""
Telegram Bot API service — the bot's ears and mouth.

Python concepts:
    1.  CLASS — TelegramService bundles related functions (poll, send, etc.)
        together with shared state (token, base_url, _offset).  Each method
        receives `self` as its first parameter, giving it access to the instance.
    2.  ASYNC / AWAIT — `async def` declares a coroutine (a function that can
        pause and resume).  `await` pauses until the operation completes.
        This lets the bot do other things while waiting for HTTP responses.
    3.  HTTPX — a modern async HTTP client.  Each `async with httpx.AsyncClient()`
        creates a connection pool, sends the request, and cleans up after.

Long-polling explained:
    Telegram's getUpdates supports a `timeout` parameter.  Instead of
    returning immediately with whatever updates are available, the server
    holds the connection open for up to `timeout` seconds.  If a new
    message arrives during that window, it returns immediately.  This
    gives us near-instant response without hammering the API.
"""

import httpx

from config.settings import TELEGRAM_BOT_TOKEN
from models.content import IncomingMessage
from utils.logger import get_logger

logger = get_logger(__name__)


class TelegramService:
    """
    Wraps the Telegram Bot API for long-polling and message dispatch.

    The Bot API is a simple REST API.  Every method is an HTTP call to:
        https://api.telegram.org/bot<TOKEN>/<method>

    No SDK needed — just HTTP requests.  We use httpx for async support.

    Attributes:
        token:    The bot token from @BotFather
        base_url: Pre-computed API base URL
        _offset:  Tracks which updates we've already processed.  Telegram
                  returns only updates with update_id > offset.  We increment
                  it after processing each update so we never see the same
                  message twice.
    """

    def __init__(self, token: str | None = None) -> None:
        """
        Initialize the Telegram service.

        Args:
            token: Bot token.  If None, reads from TELEGRAM_BOT_TOKEN env var.
        """
        self.token = token or TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self._offset: int = 0  # Last processed update_id + 1

    # ── Polling (receiving messages) ──────────────────────────

    async def poll(self) -> list[IncomingMessage]:
        """
        Fetch new messages since the last poll.

        Returns a list of IncomingMessage objects.  Empty list if nothing new.
        Each message includes the text, sender info, and chat ID.

        The offset-based system means:
            - First call: offset=0 → gets the latest updates
            - After processing: offset = last_update_id + 1
            - Next call: only gets updates newer than that offset

        Callback queries (inline keyboard presses) are parsed and returned
        as regular IncomingMessage objects with callback_data set.
        """
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self.base_url}/getUpdates",
                    params={"offset": self._offset, "timeout": 30},
                    timeout=35,  # httpx timeout (slightly > Telegram's 30s)
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
            # ALWAYS advance the offset — even if we skip this update —
            # so we never see it again
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
                continue  # Skip non-text updates (photos, joins, etc.)
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

    # ── Sending messages ──────────────────────────────────────

    async def send(
        self, chat_id: str, text: str, parse_mode: str | None = "Markdown"
    ) -> bool:
        """
        Send a text message to a chat.

        Args:
            chat_id:    Target chat ID (from IncomingMessage.chat_id)
            text:       Message body (max 4096 chars — we truncate)
            parse_mode: "Markdown" for formatting, None for plain text.
                        Notion content uses None because # and * in the
                        text break Telegram's Markdown parser.

        Returns True if the message was sent successfully.
        """
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
        """
        Send or edit a message with inline keyboard buttons.

        Currently unused in the text-command flow, but kept for future use
        if we switch back to inline keyboards.

        Args:
            buttons: List of rows, each row is a list of (label, callback_data).
                     Example: [[("Accept", "accept"), ("Quit", "quit")]]
            edit_message_id: If provided, edits an existing message instead of
                             sending a new one.  Used to remove keyboard after
                             the user makes a choice.
        """
        keyboard = [
            [{"text": label, "callback_data": data} for label, data in row]
            for row in buttons
        ]
        reply_markup = {"inline_keyboard": keyboard}

        payload: dict = {"text": text[:4096], "reply_markup": reply_markup}
        if parse_mode:
            payload["parse_mode"] = parse_mode

        async with httpx.AsyncClient() as client:
            try:
                if edit_message_id:
                    payload["chat_id"] = chat_id
                    payload["message_id"] = edit_message_id
                    resp = await client.post(
                        f"{self.base_url}/editMessageText", json=payload, timeout=10,
                    )
                else:
                    payload["chat_id"] = chat_id
                    resp = await client.post(
                        f"{self.base_url}/sendMessage", json=payload, timeout=10,
                    )
                resp.raise_for_status()
                ok: bool = resp.json().get("ok", False)
            except httpx.HTTPError as exc:
                logger.error("Keyboard send failed: %s", exc)
                return False

        logger.info("Keyboard %s to %s",
                     "edited" if edit_message_id else "sent", chat_id)
        return ok

    async def answer_callback(self, callback_id: str, text: str = "") -> bool:
        """
        Acknowledge a callback query (removes the loading spinner on the
        user's button).  Call this before doing any slow work in response
        to a button press.
        """
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
