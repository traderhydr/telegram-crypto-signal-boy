"""Telegram Bot API poster with dry-run support."""

from __future__ import annotations

import logging
from typing import Optional

import requests

from .models import Signal

logger = logging.getLogger(__name__)


class TelegramClient:
    def __init__(
        self,
        bot_token: str = "",
        channel_id: str = "",
        dry_run: bool = True,
        timeout: float = 15.0,
    ):
        self.bot_token = bot_token
        self.channel_id = channel_id
        self.dry_run = dry_run or not bot_token or not channel_id
        self.timeout = timeout

    def send_signal(self, signal: Signal) -> bool:
        text = signal.format_message()
        return self.send_message(text)

    def send_message(self, text: str) -> bool:
        if self.dry_run:
            print("========== DRY RUN (Telegram) ==========")
            print(text)
            print("========================================")
            logger.info("Dry-run: message printed instead of posting")
            return True

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.channel_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                logger.error("Telegram API error: %s", data)
                return False
            logger.info("Posted signal to Telegram channel %s", self.channel_id)
            return True
        except requests.RequestException:
            logger.exception("Failed to post to Telegram")
            return False
