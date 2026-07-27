from typing import Optional, Dict, Any


class Employee:
    """
    Domain Entity representing a development team member.
    """

    def __init__(
        self, pn: str, name: str, role: str, jira_account_id: Optional[str] = None
    ):
        self.pn = pn.strip()
        self.name = name.strip()
        self.role = role.strip()
        self.jira_account_id = jira_account_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pn": self.pn,
            "name": self.name,
            "role": self.role,
            "jira_account_id": self.jira_account_id,
        }
