import datetime
from typing import Optional, Dict, Any, List
from collections import defaultdict
from modules.generate_subtask.domain.interfaces import IJiraClient
from modules.notification.domain.interfaces import INotificationClient
from modules.reporting.domain.models import Employee
from shared.config import settings


class SendSprintReminderUseCase:
    """
    Application use case for building and triggering Sprint Reminder notifications
    with Auto-Detected Sprint Due Date, Global Summary + Per-Member Task Breakdown & Auto-Tags.
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
        sprint_name: Optional[str] = None,
        days_remaining: Optional[int] = None,
        chat_id: Optional[str] = None,
        employees: Optional[List[Employee]] = None,
    ) -> Dict[str, Any]:
        epic_key = epic_key.strip()
        base_jira_url = settings.JIRA_URL.rstrip("/")

        # 1. Map employee names to their Telegram Username & Role
        emp_tag_map = {}
        emp_role_map = {}
        if employees:
            for emp in employees:
                clean_name = emp.name.strip().upper()
                if emp.telegram_username:
                    emp_tag_map[clean_name] = emp.telegram_username
                emp_role_map[clean_name] = emp.role

        # 2. Auto-detect active Sprint details & Due Date from Jira if not provided
        real_sprint_name = sprint_name or "Active Sprint"
        real_days_remaining = days_remaining
        due_date_str = ""

        if hasattr(self.jira_client, "get_active_sprint_info"):
            try:
                sprint_info = self.jira_client.get_active_sprint_info(epic_key)
                if sprint_info:
                    if not sprint_name or sprint_name == "Active Sprint":
                        real_sprint_name = sprint_info.get("name", "Active Sprint")
                    if days_remaining is None:
                        real_days_remaining = sprint_info.get("days_remaining")
                    end_date_val = sprint_info.get("end_date")
                    if end_date_val:
                        try:
                            dt = datetime.datetime.fromisoformat(end_date_val.replace("Z", "+00:00"))
                            due_date_str = dt.strftime("%d %b %Y")
                        except Exception:
                            pass
            except Exception:
                pass

        if real_days_remaining is None:
            real_days_remaining = 2

        # 3. Fetch Jira Progress Data (Supports whole project/sprint)
        report_data = None
        if hasattr(self.jira_client, "get_progress_report_data"):
            try:
                report_data = self.jira_client.get_progress_report_data(epic_key, employees or [])
            except Exception:
                report_data = None

        if report_data and report_data.get("detailed_subtasks"):
            detailed = report_data.get("detailed_subtasks", [])
            overall = report_data.get("overall_status", {})
            total_tasks = overall.get("total", len(detailed))
            done_tasks = overall.get("done", 0)
            pending_tasks = total_tasks - done_tasks
            pct_done = overall.get("percent_done", 0.0)

            # Group unfinished tasks by assignee
            member_pending = defaultdict(list)
            for sub in detailed:
                status_cat = sub.get("status_category", "To Do")
                if status_cat != "Done":
                    assignee = sub.get("assignee", "Unassigned")
                    member_pending[assignee].append(sub)

        else:
            # Fallback to get_epic_issues
            stories = self.jira_client.get_epic_issues(epic_key)
            total_tasks = len(stories)
            done_tasks = 0
            member_pending = defaultdict(list)

            for st in stories:
                status_lower = st.status.lower()
                if status_lower in ["done", "closed", "resolved", "completed"]:
                    done_tasks += 1
                else:
                    assignee = getattr(st, "assignee", "Unassigned") or "Unassigned"
                    member_pending[assignee].append({
                        "key": st.key,
                        "summary": st.summary,
                        "status": st.status,
                        "story_points": st.story_points,
                        "role": "",
                    })
            pending_tasks = total_tasks - done_tasks
            pct_done = round((done_tasks / total_tasks * 100), 1) if total_tasks > 0 else 0.0

        # 4. Format Sisa Waktu string
        if real_days_remaining > 0:
            due_info = f" (Due: {due_date_str})" if due_date_str else ""
            time_display = f"⏳ <b>Sisa Waktu:</b> {real_days_remaining} Hari Lagi{due_info}"
        elif real_days_remaining == 0:
            time_display = "🚨 <b>Sisa Waktu:</b> <b>Hari Ini Terakhir (Due Today)!</b> ⏳"
        else:
            time_display = f"⚠️ <b>Status Waktu:</b> <b>Overdue {abs(real_days_remaining)} Hari!</b>"

        # 5. Construct Rich HTML Message
        message = (
            f"🚨 <b>SPRINT REMINDER & ACTION ITEMS</b> 🚨\n"
            f"------------------------------------------------\n"
            f"🎯 <b>Target:</b> {epic_key} ({real_sprint_name})\n"
            f"{time_display}\n\n"
            f"📊 <b>RANGKUMAN UTAMA SPRINT:</b>\n"
            f"• Total Subtask: {total_tasks} task\n"
            f"• Selesai (Done): {done_tasks} task ({pct_done}%)\n"
            f"• Sisa Pending: {pending_tasks} task\n"
            f"------------------------------------------------\n"
        )

        if pending_tasks > 0:
            message += "👥 <b>DAFTAR TUGAS PENDING PER DEVELOPER:</b>\n\n"

            # Sort members: active with tasks first, unassigned last
            sorted_assignees = sorted(
                [a for a in member_pending.keys() if a.lower() != "unassigned"],
                key=lambda x: len(member_pending[x]),
                reverse=True
            )
            if "Unassigned" in member_pending:
                sorted_assignees.append("Unassigned")

            for assignee in sorted_assignees:
                tasks = member_pending[assignee]
                clean_name = assignee.strip().upper()
                tag = emp_tag_map.get(clean_name, "")
                role = emp_role_map.get(clean_name, "")
                
                # Header per developer with auto-tag
                if assignee.lower() == "unassigned":
                    dev_header = f"⚠️ <b>Unassigned Tasks</b> (<i>{len(tasks)} Task Belum Diambil</i>):"
                else:
                    tag_str = f"<b>{tag}</b> " if tag else ""
                    role_str = f" - {role}" if role else ""
                    dev_header = f"👤 {tag_str}<b>{assignee}</b>{role_str} (<i>{len(tasks)} Task Pending</i>):"

                message += f"{dev_header}\n"

                # List tasks under this developer (max 5 shown, rest summarized)
                for t in tasks[:5]:
                    t_key = t.get("key", "")
                    t_sum = t.get("summary", "")
                    t_stat = t.get("status", "To Do")
                    message += f"  • <code>[{t_key}]</code> {t_sum} — <i>({t_stat})</i>\n"

                if len(tasks) > 5:
                    message += f"  <i>...dan {len(tasks) - 5} task lainnya</i>\n"
                message += "\n"

            message += "<i>Mohon tim dapat mengejar penyelesaian sebelum Sprint Review! 🚀</i>"
        else:
            message += "🎉 <b>LUAR BIASA! Seluruh task pada Sprint/Epic ini telah Selesai (100% Done)!</b> 🚀"

        # Send via configured notification client
        success = self.notification_client.send_message(
            message=message, parse_mode="HTML", chat_id=chat_id
        )

        return {
            "status": "success" if success else "failed",
            "epic_key": epic_key,
            "sprint_name": real_sprint_name,
            "days_remaining": real_days_remaining,
            "due_date": due_date_str,
            "total_tasks": total_tasks,
            "done_tasks": done_tasks,
            "pending_tasks": pending_tasks,
            "message_sent": success,
        }
