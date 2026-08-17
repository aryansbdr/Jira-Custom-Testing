"""
Automated Notification Scheduler Service with Catch-Up Mechanism.

Powered by APScheduler to trigger daily morning standup alerts (08:45 WIB)
and afternoon wrap-up updates (16:30 WIB) to Telegram.
Includes a Catch-up Mechanism that automatically detects and sends missed
morning reports if the computer/backend was offline at 08:45 WIB.
"""

import datetime
import json
import os
import threading
import zoneinfo
from typing import Any, Dict, List

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from modules.generate_subtask.infrastructure.jira_rest_client import JiraRestClient
from modules.notification.application.send_sprint_reminder_use_case import (
    SendSprintReminderUseCase,
)
from modules.notification.infrastructure.telegram_client import TelegramBotClient
from modules.reporting.infrastructure.pandas_excel_parser import PandasExcelParser


class NotificationSchedulerService:
    """
    Automated Background Time Scheduler for Sprint Reminders & Standup Alerts.
    Features:
    - Daily Morning Standup Reminder at 08:45 WIB (Mon - Fri)
    - Daily Afternoon Progress Wrap-up at 16:30 WIB (Mon - Fri)
    - Automatic Catch-up: Sends missed reminders immediately upon startup if machine was offline.
    """

    HISTORY_FILE = "notification_history.json"
    TIMEZONE = zoneinfo.ZoneInfo("Asia/Jakarta")

    def __init__(self):
        # Explicitly configure Asia/Jakarta (WIB) timezone for accurate execution
        self.scheduler = BackgroundScheduler(timezone="Asia/Jakarta")
        self.jira_client = JiraRestClient()
        self.telegram_client = TelegramBotClient()
        self.use_case = SendSprintReminderUseCase(
            self.jira_client, self.telegram_client
        )
        self.excel_parser = PandasExcelParser()
        self.is_running = False

    def _load_history(self) -> Dict[str, str]:
        """Loads last notification sent dates from disk."""
        if os.path.exists(self.HISTORY_FILE):
            try:
                with open(self.HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_history(self, key: str, date_str: str) -> None:
        """Saves last notification sent date to disk to avoid duplicate messages."""
        history = self._load_history()
        history[key] = date_str
        try:
            with open(self.HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            print(f"[Scheduler] Warning: Failed to write {self.HISTORY_FILE}: {e}")

    def _get_employees(self) -> List[Any]:
        """Helper to load employees with Telegram tags from Members.xlsx if available."""
        if os.path.exists("Members.xlsx"):
            try:
                with open("Members.xlsx", "rb") as f:
                    return self.excel_parser.parse_employees(f.read())
            except Exception as e:
                print(f"[Scheduler] Warning: Failed to parse Members.xlsx: {e}")
        return []

    def run_morning_reminder(self, project_key: str = "JT") -> None:
        """Job triggered every weekday morning at 08:45 WIB before Daily Standup."""
        now_wib = datetime.datetime.now(self.TIMEZONE)
        today_str = now_wib.strftime("%d-%m-%Y")
        print(f"[Scheduler] [CLOCK] Running Morning Standup Reminder for {project_key} at 08:45 WIB...")
        try:
            employees = self._get_employees()
            result = self.use_case.execute(
                epic_key=project_key,
                sprint_name=None,
                days_remaining=None,
                employees=employees,
            )
            self._save_history("last_morning_date", today_str)
            print(f"[Scheduler] [OK] Morning reminder sent successfully: {result}")
        except Exception as e:
            print(f"[Scheduler] [ERROR] Error sending morning reminder: {e}")

    def run_afternoon_reminder(self, project_key: str = "JT") -> None:
        """Job triggered every weekday afternoon at 16:30 WIB for daily wrap-up."""
        now_wib = datetime.datetime.now(self.TIMEZONE)
        today_str = now_wib.strftime("%d-%m-%Y")
        print(f"[Scheduler] [CLOCK] Running Afternoon Progress Update for {project_key} at 16:30 WIB...")
        try:
            employees = self._get_employees()
            result = self.use_case.execute(
                epic_key=project_key,
                sprint_name=None,
                days_remaining=None,
                employees=employees,
            )
            self._save_history("last_afternoon_date", today_str)
            print(f"[Scheduler] [OK] Afternoon reminder sent successfully: {result}")
        except Exception as e:
            print(f"[Scheduler] [ERROR] Error sending afternoon reminder: {e}")

    def _check_and_catchup_missed_reminders(self, project_key: str = "JT") -> None:
        """
        Catch-Up Mechanism:
        If backend is started after 08:45 WIB on a weekday and the morning reminder
        was not sent today, automatically trigger it immediately upon startup.
        """
        now_wib = datetime.datetime.now(self.TIMEZONE)
        today_str = now_wib.strftime("%d-%m-%Y")
        history = self._load_history()

        # Check if today is a weekday (Monday = 0 ... Friday = 4)
        if now_wib.weekday() < 5:
            last_morning = history.get("last_morning_date")
            is_past_morning_cutoff = (now_wib.hour > 8) or (now_wib.hour == 8 and now_wib.minute >= 45)

            if is_past_morning_cutoff and last_morning != today_str:
                print(f"[Scheduler] [CATCHUP] Morning reminder for today ({today_str}) was missed while offline. Sending catch-up report now...")
                self.run_morning_reminder(project_key)

    def start(self) -> None:
        """Starts the background scheduler with configured cron triggers and runs catch-up if needed."""
        if not self.is_running:
            # 1. Morning Standup Reminder: Senin - Jumat pukul 08:45 WIB (Asia/Jakarta)
            self.scheduler.add_job(
                func=self.run_morning_reminder,
                trigger=CronTrigger(day_of_week="mon-fri", hour=8, minute=45, timezone="Asia/Jakarta"),
                id="morning_standup_reminder",
                name="Daily Morning Standup Reminder (08:45 WIB)",
                replace_existing=True,
            )

            # 2. Afternoon Progress Wrap-up: Senin - Jumat pukul 16:30 WIB (Asia/Jakarta)
            self.scheduler.add_job(
                func=self.run_afternoon_reminder,
                trigger=CronTrigger(day_of_week="mon-fri", hour=16, minute=30, timezone="Asia/Jakarta"),
                id="afternoon_wrapup_reminder",
                name="Daily Afternoon Wrap-up (16:30 WIB)",
                replace_existing=True,
            )

            self.scheduler.start()
            self.is_running = True
            print("[Scheduler] Automated Notification Scheduler started with Asia/Jakarta (WIB) timezone.")

            # Run catch-up in a non-blocking background thread on startup
            threading.Thread(
                target=self._check_and_catchup_missed_reminders,
                daemon=True,
                name="SchedulerCatchUpThread",
            ).start()

    def shutdown(self) -> None:
        """Gracefully shuts down the background scheduler."""
        if self.is_running:
            self.scheduler.shutdown(wait=False)
            self.is_running = False
            print("[Scheduler] Automated Notification Scheduler stopped.")

    def get_status(self) -> Dict[str, Any]:
        """Returns the current scheduler status and next scheduled run times."""
        jobs_info = []
        for job in self.scheduler.get_jobs():
            next_run = job.next_run_time.strftime("%d-%m-%Y %H:%M:%S WIB") if job.next_run_time else "N/A"
            jobs_info.append({
                "job_id": job.id,
                "name": job.name,
                "next_run_time": next_run,
            })

        history = self._load_history()
        return {
            "is_running": self.is_running,
            "total_active_jobs": len(jobs_info),
            "jobs": jobs_info,
            "last_morning_sent_date": history.get("last_morning_date", "-"),
            "last_afternoon_sent_date": history.get("last_afternoon_date", "-"),
        }

    def trigger_now(
        self,
        project_key: str = "JT",
        sprint_name: str = "Active Sprint",
        days_remaining: int = 2,
    ) -> Dict[str, Any]:
        """Manually triggers the reminder immediately on-demand."""
        employees = self._get_employees()
        return self.use_case.execute(
            epic_key=project_key,
            sprint_name=sprint_name,
            days_remaining=days_remaining,
            employees=employees,
        )


# Singleton instance for application-wide use
notification_scheduler = NotificationSchedulerService()
