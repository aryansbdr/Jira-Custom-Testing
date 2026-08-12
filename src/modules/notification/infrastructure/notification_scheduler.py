import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from modules.generate_subtask.infrastructure.jira_rest_client import JiraRestClient
from modules.notification.infrastructure.telegram_client import TelegramBotClient
from modules.notification.application.send_sprint_reminder_use_case import (
    SendSprintReminderUseCase,
)
from modules.reporting.infrastructure.pandas_excel_parser import PandasExcelParser


class NotificationSchedulerService:
    """
    Automated Background Time Scheduler for Sprint Reminders & Standup Alerts.
    Powered by APScheduler to trigger daily morning & afternoon updates to Telegram/Teams.
    """

    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.jira_client = JiraRestClient()
        self.telegram_client = TelegramBotClient()
        self.use_case = SendSprintReminderUseCase(
            self.jira_client, self.telegram_client
        )
        self.excel_parser = PandasExcelParser()
        self.is_running = False

    def _get_employees(self):
        """Helper to load employees with Telegram tags from Members.xlsx if available."""
        if os.path.exists("Members.xlsx"):
            try:
                with open("Members.xlsx", "rb") as f:
                    return self.excel_parser.parse_employees(f.read())
            except Exception as e:
                print(f"[Scheduler] Warning: Failed to parse Members.xlsx: {e}")
        return []

    def run_morning_reminder(self, project_key: str = "JT"):
        """Job triggered every weekday morning at 08:45 WIB before Daily Standup."""
        print(f"[Scheduler] [CLOCK] Running Morning Standup Reminder for {project_key}...")
        try:
            employees = self._get_employees()
            result = self.use_case.execute(
                epic_key=project_key,
                sprint_name="Active Sprint",
                days_remaining=2,
                employees=employees,
            )
            print(f"[Scheduler] [OK] Morning reminder sent successfully: {result}")
        except Exception as e:
            print(f"[Scheduler] [ERROR] Error sending morning reminder: {e}")

    def run_afternoon_reminder(self, project_key: str = "JT"):
        """Job triggered every weekday afternoon at 16:30 WIB for daily wrap-up."""
        print(f"[Scheduler] [CLOCK] Running Afternoon Progress Update for {project_key}...")
        try:
            employees = self._get_employees()
            result = self.use_case.execute(
                epic_key=project_key,
                sprint_name="Active Sprint",
                days_remaining=2,
                employees=employees,
            )
            print(f"[Scheduler] [OK] Afternoon reminder sent successfully: {result}")
        except Exception as e:
            print(f"[Scheduler] [ERROR] Error sending afternoon reminder: {e}")

    def start(self):
        """Starts the background scheduler with configured cron triggers."""
        if not self.is_running:
            # 1. Morning Standup Reminder: Senin - Jumat pukul 08:45 WIB
            self.scheduler.add_job(
                func=self.run_morning_reminder,
                trigger=CronTrigger(day_of_week="mon-fri", hour=8, minute=45),
                id="morning_standup_reminder",
                name="Daily Morning Standup Reminder (08:45 WIB)",
                replace_existing=True,
            )

            # 2. Afternoon Progress Wrap-up: Senin - Jumat pukul 16:30 WIB
            self.scheduler.add_job(
                func=self.run_afternoon_reminder,
                trigger=CronTrigger(day_of_week="mon-fri", hour=16, minute=30),
                id="afternoon_wrapup_reminder",
                name="Daily Afternoon Wrap-up (16:30 WIB)",
                replace_existing=True,
            )

            self.scheduler.start()
            self.is_running = True
            print("[Scheduler] Automated Notification Scheduler started.")

    def shutdown(self):
        """Gracefully shuts down the background scheduler."""
        if self.is_running:
            self.scheduler.shutdown(wait=False)
            self.is_running = False
            print("[Scheduler] Automated Notification Scheduler stopped.")

    def get_status(self) -> dict:
        """Returns the current scheduler status and next scheduled run times."""
        jobs_info = []
        for job in self.scheduler.get_jobs():
            next_run = job.next_run_time.strftime("%d-%m-%Y %H:%M:%S WIB") if job.next_run_time else "N/A"
            jobs_info.append({
                "job_id": job.id,
                "name": job.name,
                "next_run_time": next_run,
            })

        return {
            "is_running": self.is_running,
            "total_active_jobs": len(jobs_info),
            "jobs": jobs_info,
        }

    def trigger_now(self, project_key: str = "JT", sprint_name: str = "Active Sprint", days_remaining: int = 2) -> dict:
        """Manually trigger the reminder immediately on-demand."""
        employees = self._get_employees()
        return self.use_case.execute(
            epic_key=project_key,
            sprint_name=sprint_name,
            days_remaining=days_remaining,
            employees=employees,
        )


# Singleton instance for application-wide use
notification_scheduler = NotificationSchedulerService()
