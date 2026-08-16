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
            time_display = f"Sisa Waktu: <b>{real_days_remaining} Hari Kerja</b>{due_info}"
        elif real_days_remaining == 0:
            time_display = "Sisa Waktu: <b>Hari Ini Terakhir (Due Today)</b>"
        else:
            time_display = f"Status Waktu: <b>Overdue {abs(real_days_remaining)} Hari</b>"

        # 5. Construct Clean, Professional HTML Message
        message = (
            f"<b>SPRINT PROGRESS REPORT</b>\n"
            f"Target: <b>{epic_key}</b> | {real_sprint_name}\n"
            f"{time_display}\n\n"
            f"<b>Ringkasan Sprint:</b>\n"
            f"• Total Subtask : {total_tasks}\n"
            f"• Selesai (Done): {done_tasks} ({pct_done}%)\n"
            f"• Pending       : {pending_tasks}\n\n"
        )

        if pending_tasks > 0:
            message += "<b>Rincian Tugas Pending per Role & Anggota Tim:</b>\n\n"

            # 1. Structure tasks: role -> developer -> parent_story -> list of subtasks
            role_order = ["Frontend", "Backend", "Mobile", "QA", "General", "Unassigned"]
            grouped_by_role = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

            for assignee, tasks in member_pending.items():
                clean_name = assignee.strip().upper()
                tag = emp_tag_map.get(clean_name, "")
                emp_role = emp_role_map.get(clean_name, "")

                for t in tasks:
                    sub_role = str(t.get("role") or "").strip().title()
                    if not sub_role or sub_role == "-":
                        sub_role = emp_role.title() if emp_role else "General"
                    if assignee.lower() == "unassigned":
                        sub_role = "Unassigned"

                    # Normalize role name
                    if "Front" in sub_role or "Web" in sub_role:
                        canonical_role = "Frontend"
                    elif "Back" in sub_role:
                        canonical_role = "Backend"
                    elif "Mob" in sub_role or "Android" in sub_role or "Ios" in sub_role:
                        canonical_role = "Mobile"
                    elif "Qa" in sub_role or "Test" in sub_role:
                        canonical_role = "QA"
                    elif sub_role == "Unassigned":
                        canonical_role = "Unassigned"
                    else:
                        canonical_role = "General"

                    p_key = t.get("parent_key") or "Parent Story"
                    p_sum = t.get("parent_summary") or ""
                    parent_label = f"[{p_key}] {p_sum}" if p_sum else f"[{p_key}]"

                    grouped_by_role[canonical_role][assignee][parent_label].append(t)

            # 2. Render structured blocks per role
            sorted_roles = sorted(
                grouped_by_role.keys(),
                key=lambda r: role_order.index(r) if r in role_order else 99
            )

            for role_name in sorted_roles:
                devs_dict = grouped_by_role[role_name]
                if not devs_dict:
                    continue

                role_header = f"<b>━━━ 🔹 {role_name.upper()} ━━━</b>\n"
                message += role_header

                for assignee, parents_dict in devs_dict.items():
                    clean_name = assignee.strip().upper()
                    tag = emp_tag_map.get(clean_name, "")
                    tag_str = f"{tag} " if tag else ""

                    tot_dev_tasks = sum(len(ts) for ts in parents_dict.values())
                    if assignee.lower() == "unassigned":
                        dev_header = f"👤 <b>Belum Diambil (Unassigned)</b> — <i>{tot_dev_tasks} Task</i>\n"
                    else:
                        dev_header = f"👤 <b>{tag_str}{assignee}</b> — <i>{tot_dev_tasks} Task</i>\n"
                    message += dev_header

                    for parent_title, t_list in parents_dict.items():
                        message += f"  📦 <b>{parent_title}</b>\n"
                        for t in t_list[:4]:
                            t_key = t.get("key", "")
                            t_sum = t.get("summary", "")
                            t_stat = t.get("status", "To Do")
                            message += f"     • <code>[{t_key}]</code> {t_sum} <i>({t_stat})</i>\n"
                        if len(t_list) > 4:
                            message += f"     <i>...dan {len(t_list) - 4} subtask lainnya</i>\n"
                    message += "\n"

            message += "<i>Mohon tim menindaklanjuti tugas pending sebelum akhir sprint.</i>"
        else:
            message += "<i>Seluruh subtask pada sprint ini telah selesai (100% Done).</i>"

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
