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

        # 4. Determine Smart Urgency Tier & Format Time/Header Strings
        due_info = f" (Due: {due_date_str})" if due_date_str else ""
        if real_days_remaining < 0:
            header_title = "❌ <b>SPRINT OVERDUE REPORT</b>"
            time_display = f"Status Waktu: ❌ <b>Overdue {abs(real_days_remaining)} Hari</b>{due_info}"
            pending_suffix = " ❌ <i>(Overdue!)</i>"
            footer_note = "<i>❌ PERHATIAN: Sprint ini telah melewati batas waktu (Overdue). Mohon tim segera menyelesaikan sisa subtask pending!</i>"
        elif real_days_remaining == 0:
            header_title = "🔥 <b>FINAL DAY ALERT: SPRINT DUE TODAY</b>"
            time_display = "Status Waktu: 🔥 <b>Hari Ini Terakhir (Due Today)!</b>"
            pending_suffix = " 🔥 <i>(Hari Terakhir!)</i>"
            footer_note = "<i>🔥 URGENT: Hari ini adalah hari terakhir sprint. Pastikan seluruh pekerjaan yang selesai segera di-update ke status Done di Jira!</i>"
        elif 1 <= real_days_remaining <= 3:
            header_title = f"🚨 <b>CRITICAL SPRINT ALERT (H-{real_days_remaining})</b>"
            time_display = f"Status Waktu: 🚨 <b>Sisa {real_days_remaining} Hari Kerja Lagi!</b>{due_info}"
            pending_suffix = f" 🚨 <i>(Kritis - Sisa H-{real_days_remaining})</i>"
            footer_note = f"<i>🚨 CRITICAL: Sprint deadline tersisa {real_days_remaining} hari kerja lagi. Mohon seluruh developer segera menindaklanjuti dan menyelesaikan blocker sebelum sprint berakhir!</i>"
        elif 4 <= real_days_remaining <= 5:
            header_title = f"⚠️ <b>SPRINT PROGRESS WARNING (H-{real_days_remaining})</b>"
            time_display = f"Status Waktu: ⚠️ <b>Sisa {real_days_remaining} Hari Kerja</b>{due_info}"
            pending_suffix = f" ⚠️ <i>(Sisa H-{real_days_remaining})</i>"
            footer_note = f"<i>⚠️ PERHATIAN: Sprint deadline tersisa {real_days_remaining} hari kerja. Mohon tim mulai memprioritaskan penyelesaian subtask pending.</i>"
        else:
            header_title = "<b>SPRINT PROGRESS REPORT</b>"
            time_display = f"Sisa Waktu: <b>{real_days_remaining} Hari Kerja</b>{due_info}"
            pending_suffix = ""
            footer_note = "<i>Mohon tim menindaklanjuti tugas pending sebelum akhir sprint.</i>"

        # 5. Construct Clean, Professional HTML Message
        pending_display = f"{pending_tasks}{pending_suffix}" if pending_tasks > 0 else "0"
        message = (
            f"{header_title}\n"
            f"Target: <b>{epic_key}</b> | {real_sprint_name}\n"
            f"{time_display}\n\n"
            f"<b>Ringkasan Sprint:</b>\n"
            f"- Total Subtask : {total_tasks}\n"
            f"- Selesai (Done): {done_tasks} ({pct_done}%)\n"
            f"- Pending       : {pending_display}\n\n"
        )

        if pending_tasks > 0:
            message += "<b>Rincian Progres per Epic & Story:</b>\n\n"

            # Structure tasks: Group by Epic -> Story -> List of subtasks
            tree = defaultdict(lambda: defaultdict(list))
            all_pending = []

            if report_data and report_data.get("detailed_subtasks"):
                for sub in report_data.get("detailed_subtasks", []):
                    if sub.get("status_category") != "Done":
                        all_pending.append(sub)
            else:
                for assignee, tasks in member_pending.items():
                    all_pending.extend(tasks)

            for t in all_pending:
                ek = t.get("epic_key", "")
                es = t.get("epic_summary", "")
                epic_label = f"[{ek}] {es}".strip() if (ek and es) else (f"[{ek}]" if ek else "Sprint Items")

                pk = t.get("parent_key") or "Story"
                ps = t.get("parent_summary") or ""
                story_label = f"[{pk}] {ps}".strip() if (ps and ps != "-") else f"[{pk}]"

                tree[epic_label][story_label].append(t)

            for epic_title, stories_dict in tree.items():
                message += f"<b>EPIC: {epic_title}</b>\n"
                for story_title, sub_list in stories_dict.items():
                    if len(sub_list) == 1 and sub_list[0].get("is_direct_story"):
                        st_item = sub_list[0]
                        st_stat = st_item.get("status", "To Do")
                        assignee = st_item.get("assignee", "Unassigned") or "Unassigned"
                        clean_name = assignee.strip().upper()
                        tag = emp_tag_map.get(clean_name, "")
                        assignee_display = f"{tag} ({assignee})" if tag else (assignee if assignee.lower() != "unassigned" else "<i>Belum Diambil</i>")
                        message += f"     <b>{story_title}</b>\n     ↳ <i>Status: {st_stat} | Assignee: {assignee_display}</i>\n"
                    else:
                        message += f"  📁 <b>{story_title}</b> (<i>{len(sub_list)} Subtask</i>)\n"
                        for idx, t in enumerate(sub_list[:8], 1):
                            t_key = t.get("key", "")
                            t_sum = t.get("summary", "")
                            t_stat = t.get("status", "To Do")
                            assignee = t.get("assignee", "Unassigned") or "Unassigned"
                            clean_name = assignee.strip().upper()
                            tag = emp_tag_map.get(clean_name, "")
                            assignee_display = f"{tag} ({assignee})" if tag else (assignee if assignee.lower() != "unassigned" else "<i>Belum Diambil</i>")

                            sub_role = str(t.get("role") or "").strip().lower()
                            if "front" in sub_role or "web" in sub_role:
                                role_badge = "[FE] "
                            elif "back" in sub_role:
                                role_badge = "[BE] "
                            elif "mob" in sub_role:
                                role_badge = "[Mobile] "
                            elif "qa" in sub_role:
                                role_badge = "[QA] "
                            else:
                                role_badge = ""

                            message += f"     {idx}. [{t_key}] {role_badge}{t_sum}\n        ↳ <i>Status: {t_stat} | Assignee: {assignee_display}</i>\n"
                        if len(sub_list) > 8:
                            message += f"     <i>...dan {len(sub_list) - 8} subtask lainnya</i>\n"
                    message += "\n"

            message += footer_note
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
