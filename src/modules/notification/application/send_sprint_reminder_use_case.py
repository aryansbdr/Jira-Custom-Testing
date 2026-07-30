from typing import Optional, Dict, Any
from modules.generate_subtask.domain.interfaces import IJiraClient
from modules.notification.domain.interfaces import INotificationClient


class SendSprintReminderUseCase:
    """
    Application use case for building and triggering Sprint Ending Telegram reminders.
    """

    def __init__(
        self,
        jira_client: IJiraClient,
        notification_client: INotificationClient,
    ):
        self.jira_client = jira_client
        self.notification_client = notification_client

    def execute(
        self,
        epic_key: str,
        sprint_name: str = "Active Sprint",
        days_remaining: int = 2,
        chat_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        epic_key = epic_key.strip()
        stories = self.jira_client.get_epic_issues(epic_key)

        total_sp = 0.0
        done_sp = 0.0
        unfinished_tasks = []

        for story in stories:
            total_sp += story.story_points
            status_lower = story.status.lower()

            if status_lower in ["done", "closed", "resolved", "completed"]:
                done_sp += story.story_points
            else:
                unfinished_tasks.append(
                    {
                        "key": story.key,
                        "summary": story.summary,
                        "sp": story.story_points,
                        "status": story.status,
                        "type": story.issue_type,
                    }
                )

        remaining_sp = max(0.0, total_sp - done_sp)
        progress_pct = (done_sp / total_sp * 100) if total_sp > 0 else 0.0

        # Construct clean, HTML-formatted Telegram Message
        message = (
            f"🚨 <b>SPRINT ENDING REMINDER</b> 🚨\n"
            f"------------------------------------------------\n"
            f"<b>Epic / Target:</b> {epic_key}\n"
            f"<b>Sprint:</b> {sprint_name}\n"
            f"<b>Sisa Waktu:</b> {days_remaining} Hari Lagi ⏳\n\n"
            f"📊 <b>RINGKASAN PROGRESS:</b>\n"
            f"• Total Story Points: {total_sp:.1f} SP\n"
            f"• Selesai (Done): {done_sp:.1f} SP ({progress_pct:.0f}%)\n"
            f"• Belum Selesai: {remaining_sp:.1f} SP\n\n"
        )

        if unfinished_tasks:
            message += f"⚠️ <b>DAFTAR SUBTASK / STORY UNFINISHED ({len(unfinished_tasks)}):</b>\n"
            for idx, task in enumerate(unfinished_tasks[:10], 1):
                message += f"  {idx}. [{task['key']}] {task['summary']} ({task['sp']} SP) - <i>{task['status']}</i>\n"

            if len(unfinished_tasks) > 10:
                message += f"  <i>...dan {len(unfinished_tasks) - 10} task lainnya</i>\n"

            message += "\n<i>Mohon tim dapat mengejar penyelesaian sebelum Sprint Review! 🚀</i>"
        else:
            message += "🎉 <b>SELAMAT! Seluruh task pada Epic ini telah Selesai (100% Done)!</b>"

        success = self.notification_client.send_message(
            message=message, parse_mode="HTML", chat_id=chat_id
        )

        return {
            "status": "success" if success else "failed",
            "epic_key": epic_key,
            "sprint_name": sprint_name,
            "days_remaining": days_remaining,
            "total_sp": total_sp,
            "done_sp": done_sp,
            "unfinished_count": len(unfinished_tasks),
            "message_sent": success,
        }
