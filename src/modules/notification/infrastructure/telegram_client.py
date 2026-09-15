import requests
from typing import Optional
from shared.config import settings
from modules.notification.domain.interfaces import INotificationClient


class TelegramBotClient(INotificationClient):
    """
    HTTP REST Client implementation for sending messages via Telegram Bot API.
    """

    def _split_message(self, text: str, max_length: int = 3800) -> list:
        if len(text) <= max_length:
            return [text]

        chunks = []
        current = ""
        paragraphs = text.split("\n\n")
        for p in paragraphs:
            if len(current) + len(p) + 2 <= max_length:
                current += ("\n\n" if current else "") + p
            else:
                if current:
                    chunks.append(current)
                    current = ""
                if len(p) > max_length:
                    lines = p.split("\n")
                    for line in lines:
                        if len(current) + len(line) + 1 <= max_length:
                            current += ("\n" if current else "") + line
                        else:
                            if current:
                                chunks.append(current)
                            current = line
                else:
                    current = p
        if current:
            chunks.append(current)
        return chunks

    def send_message(
        self,
        message: str,
        parse_mode: str = "HTML",
        chat_id: Optional[str] = None,
    ) -> bool:
        bot_token = str(settings.TELEGRAM_BOT_TOKEN or "").strip().strip('"').strip("'")
        if bot_token.lower().startswith("bot"):
            bot_token = bot_token[3:]

        target_chat_id = str(chat_id or settings.TELEGRAM_CHAT_ID or "").strip().strip('"').strip("'")

        if not bot_token or not target_chat_id:
            safe_preview = message.encode("ascii", errors="ignore").decode("ascii")
            print("[Telegram Client Warning] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not configured in .env file.")
            print(f"[Generated Notification Preview]:\n{safe_preview}\n")
            return False

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        chunks = self._split_message(message, max_length=3800)

        for chunk in chunks:
            payload = {
                "chat_id": target_chat_id,
                "text": chunk,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }
            response = requests.post(url, json=payload, timeout=15)
            if response.status_code != 200:
                raise Exception(
                    f"Failed to send Telegram message ({response.status_code}): {response.text}"
                )
        return True
