"""Minimal Telegram Bot API client used by teltail.

Only exposes the operations we need: ``send_message`` and ``edit_message``.
All network errors are raised as ``TelegramError``.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional


class TelegramError(Exception):
    pass


class TelegramRateLimitError(TelegramError):
    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


@dataclass
class TelegramMessage:
    chat_id: str
    message_id: int


class TelegramClient:
    def __init__(self, bot_token: str, timeout: float = 10.0) -> None:
        self._bot_token = bot_token
        self._timeout = timeout

    @property
    def base_url(self) -> str:
        return f"https://api.telegram.org/bot{self._bot_token}"

    def _post(self, method: str, data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/{method}"
        body = urllib.parse.urlencode(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                try:
                    err_raw = exc.read().decode("utf-8", errors="replace")
                    err_payload = json.loads(err_raw)
                    retry_after = err_payload.get("parameters", {}).get("retry_after")
                    msg = f"Too Many Requests: retry after {retry_after}"
                    raise TelegramRateLimitError(msg, retry_after=retry_after) from exc
                except (json.JSONDecodeError, AttributeError):
                    pass
            raise TelegramError(f"network error calling {method}: {exc}") from exc
        except urllib.error.URLError as exc:  # pragma: no cover - network
            raise TelegramError(f"network error calling {method}: {exc}") from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TelegramError(f"invalid JSON from Telegram for {method}: {raw[:200]}") from exc

        if not payload.get("ok"):
            description = payload.get("description", "unknown error")
            raise TelegramError(f"Telegram API error for {method}: {description}")

        assert isinstance(payload, dict)
        return payload

    def send_message(self, chat_id: str, text: str, parse_mode: Optional[str] = None) -> TelegramMessage:
        data: Dict[str, Any] = {"chat_id": chat_id, "text": text}
        if parse_mode is not None:
            data["parse_mode"] = parse_mode
        payload = self._post("sendMessage", data)
        result = payload.get("result") or {}
        mid = result.get("message_id")
        if mid is None:
            raise TelegramError("Telegram response missing message_id")
        message_id = int(mid)
        chat = result.get("chat", {}) or {}
        chat_identifier = chat.get("id", chat_id)
        return TelegramMessage(chat_id=str(chat_identifier), message_id=message_id)

    def edit_message(self, message: TelegramMessage, text: str, parse_mode: Optional[str] = None) -> None:
        data: Dict[str, Any] = {
            "chat_id": message.chat_id,
            "message_id": message.message_id,
            "text": text,
        }
        if parse_mode is not None:
            data["parse_mode"] = parse_mode
        self._post("editMessageText", data)
