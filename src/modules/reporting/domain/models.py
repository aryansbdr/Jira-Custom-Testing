from typing import Optional, Dict, Any


class Employee:
    """
    Domain Entity representing a development team member with optional Telegram username for auto-tagging.
    """

    def __init__(
        self,
        pn: str,
        name: str,
        role: str,
        jira_account_id: Optional[str] = None,
        telegram_username: Optional[str] = None,
    ):
        self.pn = pn.strip()
        self.name = name.strip()
        self.role = role.strip()
        self.jira_account_id = jira_account_id
        
        # Clean telegram username (ensure leading @ if present)
        if telegram_username and str(telegram_username).strip():
            u = str(telegram_username).strip()
            self.telegram_username = u if u.startswith("@") else f"@{u}"
        else:
            self.telegram_username = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pn": self.pn,
            "name": self.name,
            "role": self.role,
            "jira_account_id": self.jira_account_id,
            "telegram_username": self.telegram_username,
        }
