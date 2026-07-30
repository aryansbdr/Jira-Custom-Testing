from abc import ABC, abstractmethod
from typing import Optional


class INotificationClient(ABC):
    """
    Interface for sending messages/reminders to external messaging channels (e.g. Telegram).
    """

    @abstractmethod
    def send_message(
        self,
        message: str,
        parse_mode: str = "HTML",
        chat_id: Optional[str] = None,
    ) -> bool:
        pass
