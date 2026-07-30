import requests
from typing import Optional
from shared.config import settings
from modules.notification.domain.interfaces import INotificationClient


class MSTeamsWebhookClient(INotificationClient):
    """
    HTTP REST Client implementation for sending notification cards via Microsoft Teams Incoming Webhook.
    """

    def send_message(
        self,
        message: str,
        parse_mode: str = "HTML",
        chat_id: Optional[str] = None,
    ) -> bool:
        webhook_url = chat_id or getattr(settings, "TEAMS_WEBHOOK_URL", "")

        if not webhook_url:
            raise ValueError(
                "TEAMS_WEBHOOK_URL is not configured in environment or .env file."
            )

        # MS Teams MessageCard payload format
        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": "0076D7",
            "summary": "Sprint Ending Reminder",
            "sections": [
                {
                    "activityTitle": "🚨 <b>SPRINT ENDING REMINDER</b> 🚨",
                    "activitySubtitle": "BRI Agile Scrum Notification",
                    "text": message.replace("\n", "<br>"),
                    "markdown": True,
                }
            ],
        }

        response = requests.post(webhook_url, json=payload, timeout=15)
        if response.status_code in (200, 202):
            return True

        raise Exception(
            f"Failed to send MS Teams message ({response.status_code}): {response.text}"
        )
