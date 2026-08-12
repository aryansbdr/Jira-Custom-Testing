from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

from modules.generate_subtask.infrastructure.jira_rest_client import JiraRestClient
from modules.notification.infrastructure.telegram_client import TelegramBotClient
from modules.notification.infrastructure.notification_scheduler import notification_scheduler
from modules.notification.application.send_sprint_reminder_use_case import (
    SendSprintReminderUseCase,
)

router = APIRouter(prefix="/api/v1/notification", tags=["Telegram Notification"])

jira_client = JiraRestClient()
telegram_client = TelegramBotClient()
send_reminder_uc = SendSprintReminderUseCase(jira_client, telegram_client)


class SprintReminderRequest(BaseModel):
    epic_key: str = Field(default="JT", example="JT")
    sprint_name: Optional[str] = Field(default="Active Sprint", example="Korp 2 - Sprint 3")
    days_remaining: Optional[int] = Field(default=2, example=2)


class CustomTelegramMessageRequest(BaseModel):
    message: str = Field(..., example="<b>PERHATIAN:</b> Rapat Daily Standup 10 menit lagi!")


@router.post("/sprintReminder")
def trigger_sprint_reminder(req: SprintReminderRequest) -> Dict[str, Any]:
    """
    Triggers a Sprint Ending Reminder Telegram notification with per-member auto-tag.
    """
    try:
        result = notification_scheduler.trigger_now(
            project_key=req.epic_key,
            sprint_name=req.sprint_name or "Active Sprint",
            days_remaining=req.days_remaining or 2,
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to send Telegram Sprint Reminder: {str(e)}"
        )


@router.post("/sendMessage")
def send_custom_telegram_message(req: CustomTelegramMessageRequest) -> Dict[str, Any]:
    """
    Sends a custom HTML-formatted Telegram notification on-demand.
    """
    try:
        success = telegram_client.send_message(
            message=req.message,
            parse_mode="HTML",
        )
        return {"status": "success", "message_sent": success}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to send custom Telegram message: {str(e)}"
        )


@router.get("/scheduler/status")
def get_scheduler_status() -> Dict[str, Any]:
    """
    Returns background notification scheduler status and next scheduled run times.
    """
    return notification_scheduler.get_status()


@router.post("/scheduler/triggerNow")
def trigger_scheduler_now(project_key: str = "JT") -> Dict[str, Any]:
    """
    Immediately triggers the scheduled notification on-demand.
    """
    try:
        result = notification_scheduler.trigger_now(project_key=project_key)
        return {"status": "success", "result": result}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to trigger scheduled notification: {str(e)}"
        )
