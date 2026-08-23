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
    epic_key: str = Field(default="JT", example="BL", description="Project Key, Epic Key, or Filter ID")
    sprint_name: Optional[str] = Field(default="Active Sprint", example="Sprint 9572")
    days_remaining: Optional[int] = Field(default=2, example=2, description="Days remaining in sprint")


class CustomTelegramMessageRequest(BaseModel):
    message: str = Field(
        default="<b>Notification Test</b>",
        example="<b>System Status:</b> All services operational.",
        description="HTML formatted Telegram message text"
    )


class CriticalAlertTestRequest(BaseModel):
    target_info: str = Field(
        default="26953",
        example="26953",
        description="Dashboard ID, Filter ID, Project Key, or JQL query"
    )
    days_remaining: int = Field(
        default=3,
        example=3,
        description="3 for H-3 Critical Alert, 5 for H-5 Warning, 0 for Due Today, -1 for Overdue"
    )
    sprint_name: Optional[str] = Field(default="Squad Korporasi - Critical Test Sprint", example="Korporasi 1 - Active Sprint")


@router.post("/testCriticalAlert")
def test_critical_alert_notification(req: CriticalAlertTestRequest) -> Dict[str, Any]:
    """
    Directly tests sending a Critical (H-3/H-5/Overdue) Telegram alert with live Jira data.
    """
    try:
        sent = send_reminder_uc.execute(
            project_or_epic=req.target_info,
            days_remaining=req.days_remaining,
            sprint_name=req.sprint_name,
        )
        return {
            "status": "success",
            "message": f"Critical notification (H-{req.days_remaining}) successfully sent to Telegram!",
            "telegram_sent": sent,
            "target": req.target_info,
            "days_remaining": req.days_remaining,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to send Critical Telegram Alert: {str(e)}"
        )


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
