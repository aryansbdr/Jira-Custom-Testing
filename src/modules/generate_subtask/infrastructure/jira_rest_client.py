import requests
from typing import List, Dict, Any, Optional
from shared.config import settings
from modules.generate_subtask.domain.models import Story
from modules.generate_subtask.domain.interfaces import IJiraClient


class JiraRestClient(IJiraClient):
    """
    HTTP REST Client implementation supporting both Jira Server (PAT Bearer Auth)
    and Jira Cloud (Basic Auth) dynamically.
    """

    def _is_cloud(self) -> bool:
        return "atlassian.net" in settings.JIRA_URL.lower()

    def _get_headers(
        self, custom_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if custom_headers:
            headers.update(custom_headers)

        # Determine authentication method based on Jira type
        if self._is_cloud():
            # Cloud expects Basic authentication (Base64 of email:token handled by requests.auth)
            # We will use the requests 'auth' parameter for Cloud.
            pass
        else:
            # Jira Server/Data Center (e.g. jira.bri.co.id) expects Bearer token PAT auth
            headers["Authorization"] = f"Bearer {settings.JIRA_API_TOKEN}"

        return headers

    def _get_auth(self) -> Optional[requests.auth.HTTPBasicAuth]:
        if self._is_cloud():
            if not settings.JIRA_EMAIL or not settings.JIRA_API_TOKEN:
                raise ValueError(
                    "For Jira Cloud, JIRA_EMAIL and JIRA_API_TOKEN must be configured."
                )
            return requests.auth.HTTPBasicAuth(
                settings.JIRA_EMAIL, settings.JIRA_API_TOKEN
            )
        # Server PAT does not use Basic Auth parameters
        return None

    def get_epic_issues(self, epic_key: str) -> List[Story]:
        epic_key = epic_key.strip()
        # Jira Cloud has migrated search to /rest/api/3/search/jql, Server remains on /rest/api/2/search
        if self._is_cloud():
            url = f"{settings.JIRA_URL.rstrip('/')}/rest/api/3/search/jql"
        else:
            url = f"{settings.JIRA_URL.rstrip('/')}/rest/api/2/search"

        headers = self._get_headers()
        auth = self._get_auth()

        jql = f'parent = "{epic_key}" OR "Epic Link" = "{epic_key}" ORDER BY rank ASC'


        params = {
            "jql": jql,
            "fields": f"summary,description,{settings.JIRA_STORY_POINTS_FIELD},issuetype,status",
            "maxResults": 100,
        }

        response = requests.get(
            url, headers=headers, params=params, auth=auth, timeout=20
        )

        if response.status_code != 200:
            raise Exception(
                f"Failed to fetch issues from Jira ({response.status_code}): {response.text}"
            )

        data = response.json()
        stories = []

        for item in data.get("issues", []):
            fields = item.get("fields", {})

            description_text = ""
            desc_obj = fields.get("description")
            if isinstance(desc_obj, str):
                description_text = desc_obj
            elif isinstance(desc_obj, dict):
                description_text = self._parse_adf_to_text(desc_obj)

            sp_val = fields.get(settings.JIRA_STORY_POINTS_FIELD)
            try:
                sp_val = float(sp_val) if sp_val is not None else 0.0
            except ValueError:
                sp_val = 0.0

            if description_text:
                description_text = description_text.replace("\r", "")

            status_name = fields.get("status", {}).get("name", "To Do")

            stories.append(
                Story(
                    key=item.get("key"),
                    summary=fields.get("summary", ""),
                    story_points=sp_val,
                    description=description_text,
                    issue_type=fields.get("issuetype", {}).get("name", "Story"),
                    status=status_name,
                )
            )

        return stories

    def get_single_issue(self, issue_key: str) -> Optional[Story]:
        """Fetch a single Story/Task by its key (for single-ticket subtask generation)."""
        issue_key = issue_key.strip()
        url = f"{settings.JIRA_URL.rstrip('/')}/rest/api/2/issue/{issue_key}"
        headers = self._get_headers()
        auth = self._get_auth()
        params = {"fields": f"summary,description,{settings.JIRA_STORY_POINTS_FIELD},issuetype,status"}

        response = requests.get(url, headers=headers, params=params, auth=auth, timeout=20)
        if response.status_code != 200:
            raise Exception(
                f"Failed to fetch issue {issue_key} from Jira ({response.status_code}): {response.text}"
            )

        item = response.json()
        fields = item.get("fields", {})

        description_text = ""
        desc_obj = fields.get("description")
        if isinstance(desc_obj, str):
            description_text = desc_obj
        elif isinstance(desc_obj, dict):
            description_text = self._parse_adf_to_text(desc_obj)

        if description_text:
            description_text = description_text.replace("\r", "")

        sp_val = fields.get(settings.JIRA_STORY_POINTS_FIELD)
        try:
            sp_val = float(sp_val) if sp_val is not None else 0.0
        except ValueError:
            sp_val = 0.0

        return Story(
            key=item.get("key"),
            summary=fields.get("summary", ""),
            story_points=sp_val,
            description=description_text,
            issue_type=fields.get("issuetype", {}).get("name", "Story"),
            status=fields.get("status", {}).get("name", "To Do"),
        )

    def find_user_by_name(
        self, display_name: str, pn: Optional[str] = None
    ) -> Optional[str]:
        url = f"{settings.JIRA_URL.rstrip('/')}/rest/api/2/user/search"
        headers = self._get_headers()
        auth = self._get_auth()

        # 1. Try search by PN first if provided (Corporate Standard)
        if pn:
            params = {"username": pn, "maxResults": 1}
            response = requests.get(
                url, headers=headers, params=params, auth=auth, timeout=10
            )
            if response.status_code != 200:
                params = {"query": pn, "maxResults": 1}
                response = requests.get(
                    url, headers=headers, params=params, auth=auth, timeout=10
                )

            if response.status_code == 200:
                users = response.json()
                if users:
                    return (
                        users[0].get("name")
                        or users[0].get("key")
                        or users[0].get("accountId")
                    )

        # 2. Fallback to search by Display Name if PN not found/provided
        params = {"username": display_name, "maxResults": 1}
        response = requests.get(
            url, headers=headers, params=params, auth=auth, timeout=10
        )
        if response.status_code != 200:
            params = {"query": display_name, "maxResults": 1}
            response = requests.get(
                url, headers=headers, params=params, auth=auth, timeout=10
            )

        if response.status_code == 200:
            users = response.json()
            if users:
                return (
                    users[0].get("name")
                    or users[0].get("key")
                    or users[0].get("accountId")
                )
        return None

    def create_subtask_issue(
        self,
        parent_key: str,
        summary: str,
        description: str,
        story_points: float,
        assignee_id: Optional[str] = None,
        parent_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{settings.JIRA_URL.rstrip('/')}/rest/api/2/issue"
        headers = self._get_headers({"Content-Type": "application/json"})
        auth = self._get_auth()

        # Determine candidate subtask issue type names (case-sensitive in Jira Server)
        parent_type_lower = parent_type.lower() if parent_type else "task"
        if "bug" in parent_type_lower:
            candidate_type_names = ["Sub Bug", "Sub-Bug", "Sub-bug", "sub bug"]
        elif "documentation" in parent_type_lower:
            candidate_type_names = ["Sub Documentation", "Sub-Documentation", "sub documentation"]
        else:
            candidate_type_names = ["Sub-Task", "Sub-task", "Subtask", "Sub task", "sub task"]

        last_response = None
        for type_name in candidate_type_names:
            payload = {
                "fields": {
                    "project": {"key": parent_key.split("-")[0]},
                    "parent": {"key": parent_key},
                    "summary": summary,
                    "description": description if description else "Subtask generated by AI.",
                    "issuetype": {"name": type_name},
                }
            }

            if assignee_id:
                if self._is_cloud():
                    payload["fields"]["assignee"] = {"accountId": assignee_id}
                else:
                    payload["fields"]["assignee"] = {"name": assignee_id}

            if story_points > 0:
                payload["fields"][settings.JIRA_STORY_POINTS_FIELD] = story_points

            response = requests.post(
                url, headers=headers, json=payload, auth=auth, timeout=15
            )
            if response.status_code in (200, 201):
                return response.json()

            if assignee_id and not self._is_cloud():
                # Fallback to try accountId if Server setup uses cloud format
                payload["fields"]["assignee"] = {"accountId": assignee_id}
                response = requests.post(
                    url, headers=headers, json=payload, auth=auth, timeout=15
                )
                if response.status_code in (200, 201):
                    return response.json()

            last_response = response

        raise Exception(
            f"Failed to create subtask in Jira ({last_response.status_code}): {last_response.text}"
        )

        return response.json()

    def _parse_adf_to_text(self, adf_obj: Dict[str, Any]) -> str:
        text_parts = []

        def extract_text(node):
            if not isinstance(node, dict):
                return
            if node.get("type") == "text":
                text_parts.append(node.get("text", ""))
            elif "content" in node:
                for child in node["content"]:
                    extract_text(child)

        extract_text(adf_obj)
