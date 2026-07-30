import requests
from typing import Optional
from shared.config import settings
from modules.notification.domain.interfaces import INotificationClient


class TelegramBotClient(INotificationClient):
    """
    HTTP REST Client implementation for sending messages via Telegram Bot API.
    """

    def send_message(
        self,
        message: str,
        parse_mode: str = "HTML",
        chat_id: Optional[str] = None,
    ) -> bool:
        bot_token = settings.TELEGRAM_BOT_TOKEN
        target_chat_id = chat_id or settings.TELEGRAM_CHAT_ID

        if not bot_token:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN is not configured in environment or .env file."
            )
        if not target_chat_id:
            raise ValueError(
                "TELEGRAM_CHAT_ID is not configured in environment or .env file."
            )

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": target_chat_id,
            "text": message,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 200:
            return True

        raise Exception(
            f"Failed to send Telegram message ({response.status_code}): {response.text}"
        )
