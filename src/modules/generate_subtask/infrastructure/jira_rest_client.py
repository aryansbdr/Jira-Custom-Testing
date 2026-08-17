import requests
import re
import datetime
import time
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

    def _clean_key(self, raw_key: str) -> str:
        if not raw_key:
            return ""
        raw_key = raw_key.strip()
        # Extract issue key if full URL is passed (e.g. https://domain.atlassian.net/browse/SCRUM-15)
        if "/browse/" in raw_key:
            raw_key = raw_key.split("/browse/")[-1].split("?")[0].split("#")[0].strip()
        return raw_key

    def _is_issue_key(self, text: str) -> bool:
        import re
        if not text:
            return False
        cleaned = self._clean_key(text)
        return bool(re.match(r"^[A-Za-z0-9_]+-\d+$", cleaned))

    def _extract_story_points(self, fields: dict) -> float:
        if not isinstance(fields, dict):
            return 0.0
        val = fields.get(settings.JIRA_STORY_POINTS_FIELD)
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                pass
        for candidate in ["customfield_10106", "customfield_10016", "customfield_10006", "customfield_10004", "customfield_10008", "storyPoints"]:
            v = fields.get(candidate)
            if v is not None:
                try:
                    return float(v)
                except (ValueError, TypeError):
                    pass
        return 0.0

    def _execute_jql_search(
        self, jql: str, fields: List[str], max_results: int = 100
    ) -> List[dict]:
        """Unified JQL search executing POST on Jira Cloud /rest/api/3/search/jql and GET on Jira Server /rest/api/2/search."""
        try:
            headers = self._get_headers()
            auth = self._get_auth()
        except Exception as auth_err:
            print(f"Warning: Jira authentication skipped: {auth_err}")
            return []

        base_url = settings.JIRA_URL.rstrip("/")
        if self._is_cloud():
            # Jira Cloud: GET /rest/api/3/search/jql
            url = f"{base_url}/rest/api/3/search/jql"
            params = {
                "jql": jql,
                "fields": ",".join(fields) if isinstance(fields, list) else fields,
                "maxResults": max_results,
            }
            try:
                res = requests.get(url, headers=headers, params=params, auth=auth, timeout=35)
                if res.status_code == 200:
                    return res.json().get("issues", [])
                else:
                    print(f"Warning: Jira Cloud search failed ({res.status_code}): {res.text[:200]}")
            except Exception as e:
                print(f"Warning: Jira Cloud search exception: {e}")
        else:
            # Jira Server / DC: GET /rest/api/2/search
            url = f"{base_url}/rest/api/2/search"
            params = {
                "jql": jql,
                "fields": ",".join(fields) if isinstance(fields, list) else fields,
                "maxResults": max_results,
            }
            try:
                res = requests.get(url, headers=headers, params=params, auth=auth, timeout=35)
                if res.status_code == 200:
                    return res.json().get("issues", [])
                else:
                    print(f"Warning: Jira Server search failed ({res.status_code}): {res.text[:200]}")
            except Exception as e:
                print(f"Warning: Jira Server search exception: {e}")

        return []

    def get_epic_issues(self, epic_key: str) -> List[Story]:
        epic_key = self._clean_key(epic_key)
        if not epic_key or not self._is_issue_key(epic_key):
            return []

        jql = f'parent = "{epic_key}" OR "Epic Link" = "{epic_key}" ORDER BY rank ASC'
        fields = ["summary", "description", settings.JIRA_STORY_POINTS_FIELD, "issuetype", "status"]
        issues_raw = self._execute_jql_search(jql, fields, max_results=100)

        stories = []
        for item in issues_raw:
                fields = item.get("fields", {})

                description_text = ""
                desc_obj = fields.get("description")
                if isinstance(desc_obj, str):
                    description_text = desc_obj
                elif isinstance(desc_obj, dict):
                    description_text = self._parse_adf_to_text(desc_obj)

                sp_val = self._extract_story_points(fields)

                if description_text:
                    description_text = description_text.replace("\r", "")

                issuetype_obj = fields.get("issuetype") or {}
                issuetype_name = (
                    issuetype_obj.get("name", "Story")
                    if isinstance(issuetype_obj, dict)
                    else "Story"
                )
                is_subtask = (
                    issuetype_obj.get("subtask", False)
                    if isinstance(issuetype_obj, dict)
                    else False
                )

                # Skip subtasks when querying Epic children — Epic children must be Stories, Tasks, Bugs, etc.
                if is_subtask or issuetype_name.lower() in ["sub-task", "subtask", "sub task"]:
                    continue

                status_obj = fields.get("status") or {}
                status_name = (
                    status_obj.get("name", "To Do")
                    if isinstance(status_obj, dict)
                    else "To Do"
                )

                summary_text = fields.get("summary") or ""
                stories.append(
                    Story(
                        key=item.get("key") or "",
                        summary=summary_text,
                        story_points=sp_val,
                        description=description_text or "",
                        issue_type=issuetype_name,
                        status=status_name,
                    )
                )

        # Fallback for Jira Cloud if JQL returns no children: check parent issue directly
        if not stories and self._is_cloud():
            try:
                single_url = f"{settings.JIRA_URL.rstrip('/')}/rest/api/3/issue/{epic_key}"
                single_res = requests.get(single_url, headers=headers, auth=auth, timeout=5)
                if single_res.status_code == 200:
                    p_data = single_res.json()
                    sub_items = p_data.get("fields", {}).get("subtasks", []) or p_data.get("fields", {}).get("issuelinks", [])
                    for child_item in sub_items:
                        c_key = child_item.get("key") or child_item.get("outwardIssue", {}).get("key") or child_item.get("inwardIssue", {}).get("key")
                        if c_key:
                            child_story = self.get_single_issue(c_key)
                            if child_story:
                                stories.append(child_story)
            except Exception:
                pass

        return stories

    def get_existing_subtask_summaries(self, parent_key: str) -> set:
        """Fetch all existing subtask summary titles for a given parent issue key (for deduplication)."""
        parent_key = self._clean_key(parent_key)
        if not parent_key:
            return set()

        try:
            headers = self._get_headers()
            auth = self._get_auth()

            # Cloud uses API v3, Server uses v2
            version = "3" if self._is_cloud() else "2"
            url = f"{settings.JIRA_URL.rstrip('/')}/rest/api/{version}/issue/{parent_key}?fields=subtasks"

            response = requests.get(url, headers=headers, auth=auth, timeout=5)
            if response.status_code == 200:
                data = response.json()
                subtasks = data.get("fields", {}).get("subtasks", [])
                return {st.get("fields", {}).get("summary", "").strip().lower() for st in subtasks if st.get("fields", {}).get("summary")}
        except Exception as e:
            print(f"Warning: Failed to fetch existing subtasks for {parent_key}: {e}")

        return set()

    def get_single_issue(self, issue_key: str) -> Optional[Story]:
        """Fetch a single Story/Task by its key (for single-ticket subtask generation)."""
        issue_key = self._clean_key(issue_key)
        if not issue_key or not self._is_issue_key(issue_key):
            return None
        url = f"{settings.JIRA_URL.rstrip('/')}/rest/api/2/issue/{issue_key}"
        try:
            headers = self._get_headers()
            auth = self._get_auth()
        except Exception as auth_err:
            print(f"Warning: Jira authentication skipped: {auth_err}")
            return None

        params = {"fields": f"summary,description,{settings.JIRA_STORY_POINTS_FIELD},issuetype,status,parent"}

        response = None
        for attempt in range(2):
            try:
                response = requests.get(url, headers=headers, params=params, auth=auth, timeout=25)
                if response.status_code == 200:
                    break
            except Exception as req_err:
                if attempt == 1:
                    print(f"Warning: Failed to fetch issue {issue_key}: {req_err}")
                    return None
                time.sleep(1)
        if not response or response.status_code != 200:
            print(f"Warning: Failed to fetch issue {issue_key}: {response.status_code if response else 'No response'}")
            return None

        item = response.json()
        fields = item.get("fields", {})

        issuetype_obj = fields.get("issuetype") or {}
        issuetype_name = issuetype_obj.get("name", "Story") if isinstance(issuetype_obj, dict) else "Story"
        is_subtask = issuetype_obj.get("subtask", False) if isinstance(issuetype_obj, dict) else False

        # If user passed a subtask key directly, automatically switch to its parent Story/Task
        if is_subtask or issuetype_name.lower() in ["sub-task", "subtask", "sub task"]:
            parent_obj = fields.get("parent") or {}
            parent_key = parent_obj.get("key")
            if parent_key and parent_key != issue_key:
                print(f"  ℹ️ [{issue_key}] adalah Subtask. Otomatis beralih ke parent Story/Task [{parent_key}]...")
                return self.get_single_issue(parent_key)

        description_text = ""
        desc_obj = fields.get("description")
        if isinstance(desc_obj, str):
            description_text = desc_obj
        elif isinstance(desc_obj, dict):
            description_text = self._parse_adf_to_text(desc_obj)

        if description_text:
            description_text = description_text.replace("\r", "")

        sp_val = self._extract_story_points(fields)

        issuetype_obj = fields.get("issuetype") or {}
        issuetype_name = issuetype_obj.get("name", "Story") if isinstance(issuetype_obj, dict) else "Story"

        status_obj = fields.get("status") or {}
        status_name = status_obj.get("name", "To Do") if isinstance(status_obj, dict) else "To Do"

        summary_text = fields.get("summary") or ""
        return Story(
            key=item.get("key") or "",
            summary=summary_text,
            story_points=sp_val,
            description=description_text or "",
            issue_type=issuetype_name,
            status=status_name,
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
            candidate_type_names = ["Subtask", "Sub-task", "Sub Bug", "Sub-Bug", "Sub-bug", "sub bug"]
        elif "documentation" in parent_type_lower:
            candidate_type_names = ["Subtask", "Sub-task", "Sub Documentation", "Sub-Documentation", "sub documentation"]
        else:
            candidate_type_names = ["Subtask", "Sub-task", "Sub-Task", "Sub task", "Task", "Story"]

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

            # Fallback 1: If story points customfield is rejected, retry without it
            if response.status_code == 400 and settings.JIRA_STORY_POINTS_FIELD in response.text:
                payload["fields"].pop(settings.JIRA_STORY_POINTS_FIELD, None)
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
        extract_text(adf_obj)
        return " ".join(text_parts).strip()

    def _resolve_target_info(self, root_key: str) -> Dict[str, Any]:
        """
        Dynamically analyzes root_key to determine if it is:
        1. A Dashboard ID / URL (e.g. 26953, 20893, selectPageId=26953)
        2. An Agile Board ID / RapidView ID (e.g. 2342, 2735)
        3. An Agile Sprint ID (e.g. 10588, 9911)
        4. A Filter ID (e.g. 27735, 40101)
        5. An Epic or Issue Key (e.g. BL-38812, JT-146)
        6. A Project Key (e.g. JT, BL)
        """
        key = str(root_key or "").strip()
        auth = self._get_auth()
        headers = self._get_headers()
        base_url = settings.JIRA_URL.rstrip("/")
        
        # Check for numeric ID in URL or raw digits
        num_id = None
        if "selectPageId=" in key:
            m = re.search(r'selectPageId=(\d+)', key)
            if m: num_id = m.group(1)
        elif "pageId=" in key or "id=" in key:
            m = re.search(r'(?:pageId|id)=(\d+)', key)
            if m: num_id = m.group(1)
        elif key.isdigit():
            num_id = key

        if num_id:
            # 1. Try as Dashboard ID (Jira Server/DC & Cloud)
            try:
                d_res = requests.get(f"{base_url}/rest/dashboards/1.0/{num_id}", headers=headers, auth=auth, timeout=8)
                if d_res.status_code != 200:
                    d_res = requests.get(f"{base_url}/rest/api/2/dashboard/{num_id}", headers=headers, auth=auth, timeout=8)

                if d_res.status_code == 200:
                    d_data = d_res.json()
                    dash_title = d_data.get("title") or d_data.get("name") or f"Dashboard {num_id}"
                    gadgets = d_data.get("gadgets", []) or d_data.get("items", [])
                    found_board = None
                    found_sprint = None
                    found_filters = []
                    found_projects = []

                    def _extract_id_from_text(text: str, key_name: str) -> Optional[str]:
                        if not text:
                            return None
                        m = re.search(rf'{key_name}=(\d+)', str(text))
                        return m.group(1) if m else None
                    
                    for g in gadgets:
                        gid = g.get("id")
                        # Check direct gadget object in list first
                        g_url = g.get("gadgetUrl") or g.get("uri") or ""
                        rendered_url = g.get("renderedGadgetUrl") or ""
                        
                        # Inspect params/userPrefs inside g
                        direct_prefs = g.get("userPrefs") or {}
                        if isinstance(direct_prefs, list):
                            direct_prefs = {f.get("name"): f.get("value") for f in direct_prefs if isinstance(f, dict)}

                        rv_id = direct_prefs.get("rapidViewId") or direct_prefs.get("boardId") or _extract_id_from_text(rendered_url, "rapidViewId")
                        sp_id = direct_prefs.get("sprintId") or _extract_id_from_text(rendered_url, "sprintId")
                        fid = direct_prefs.get("filterId") or direct_prefs.get("searchId") or _extract_id_from_text(rendered_url, "filterId") or _extract_id_from_text(rendered_url, "id")

                        # If not found directly, fetch gadget details
                        if gid and (not rv_id and not sp_id and not fid):
                            try:
                                g_res = requests.get(f"{base_url}/rest/dashboards/1.0/{num_id}/gadget/{gid}", headers=headers, auth=auth, timeout=4)
                                if g_res.status_code == 200:
                                    gd = g_res.json()
                                    props = gd.get("context", {}).get("dashboardItem", {}).get("properties", {})
                                    up_fields = gd.get("userPrefs", {})
                                    if isinstance(up_fields, dict) and "fields" in up_fields:
                                        user_prefs = {f.get("name"): f.get("value") for f in up_fields.get("fields", []) if isinstance(f, dict)}
                                    elif isinstance(up_fields, dict):
                                        user_prefs = up_fields
                                    else:
                                        user_prefs = {}

                                    r_url = gd.get("renderedGadgetUrl") or gd.get("gadgetUrl") or ""
                                    rv_id = props.get("rapidViewId") or user_prefs.get("rapidViewId") or props.get("boardId") or user_prefs.get("boardId") or _extract_id_from_text(r_url, "rapidViewId")
                                    sp_id = props.get("sprintId") or user_prefs.get("sprintId") or _extract_id_from_text(r_url, "sprintId")
                                    fid = props.get("filterId") or user_prefs.get("filterId") or props.get("searchId") or user_prefs.get("searchId") or _extract_id_from_text(r_url, "filterId") or _extract_id_from_text(r_url, "id")
                            except Exception:
                                pass

                        if rv_id and str(rv_id).isdigit() and not found_board:
                            found_board = str(rv_id)
                        if sp_id and str(sp_id).isdigit() and sp_id != "auto" and not found_sprint:
                            found_sprint = str(sp_id)
                        if fid and str(fid).isdigit() and str(fid) not in found_filters:
                            found_filters.append(str(fid))

                    return {
                        "type": "dashboard",
                        "id": num_id,
                        "title": dash_title,
                        "board_id": found_board,
                        "sprint_id": found_sprint,
                        "filter_ids": found_filters,
                    }
            except Exception as e:
                print(f"Warning: Dashboard resolution for {num_id} error: {e}")

            # 2. Try as Agile Board ID
            try:
                b_res = requests.get(f"{base_url}/rest/agile/1.0/board/{num_id}", headers=headers, auth=auth, timeout=5)
                if b_res.status_code == 200:
                    b_data = b_res.json()
                    return {
                        "type": "board",
                        "id": num_id,
                        "title": f"Board {b_data.get('name')}",
                        "board_id": num_id,
                        "sprint_id": None,
                    }
            except Exception:
                pass

            # 3. Try as Agile Sprint ID
            try:
                sp_res = requests.get(f"{base_url}/rest/agile/1.0/sprint/{num_id}", headers=headers, auth=auth, timeout=5)
                if sp_res.status_code == 200:
                    sp_data = sp_res.json()
                    return {
                        "type": "sprint",
                        "id": num_id,
                        "title": f"Sprint {sp_data.get('name')}",
                        "board_id": None,
                        "sprint_id": num_id,
                        "sprint_name": sp_data.get("name"),
                    }
            except Exception:
                pass

            # 4. Try as Filter ID
            try:
                f_res = requests.get(f"{base_url}/rest/api/2/filter/{num_id}", headers=headers, auth=auth, timeout=5)
                if f_res.status_code == 200:
                    f_data = f_res.json()
                    return {
                        "type": "filter",
                        "id": num_id,
                        "title": f"Filter {f_data.get('name')}",
                        "jql": f_data.get("jql"),
                    }
            except Exception:
                pass

        # Text-based identifier
        if "-" in key:
            return {
                "type": "epic_or_issue",
                "key": key,
                "title": f"Issue / Epic {key}",
            }
        else:
            return {
                "type": "project",
                "key": key,
                "title": f"Project {key}",
            }

    def get_progress_report_data(
        self, root_key: str, active_employees: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        """
        Fetch real-time Jira progress metrics (To Do, In Progress, Done)
        broken down per Member and per Parent Story for rich Excel reporting.
        Supports Project Key (e.g. 'JT' for entire sprint/project), Epic Key, or Story Key.
        """
        root_key = self._clean_key(root_key) if root_key else "JT"
        headers = self._get_headers()
        auth = self._get_auth()
        api_ver = "3" if self._is_cloud() else "2"
        base_jira_url = settings.JIRA_URL.rstrip("/")

        # Build employee role lookup dictionary (by lower name and PN)
        emp_role_map = {}
        if active_employees:
            for emp in active_employees:
                name = getattr(emp, "name", None) or (emp.get("name") if isinstance(emp, dict) else "")
                role = getattr(emp, "role", None) or (emp.get("role") if isinstance(emp, dict) else "")
                pn = getattr(emp, "pn", None) or (emp.get("pn") if isinstance(emp, dict) else "")
                if name:
                    emp_role_map[name.strip().lower()] = role
                if pn:
                    emp_role_map[str(pn).strip()] = role

        # Status categorization helper
        def _categorize_status(status_raw: str, cat_key: str = "") -> str:
            raw = str(status_raw or "").strip().lower()
            cat = str(cat_key or "").strip().lower()
            if cat == "done" or raw in ("done", "resolved", "closed", "complete", "completed", "verified"):
                return "Done"
            if cat in ("indeterminate", "inprogress") or raw in ("in progress", "in development", "in review", "in testing", "testing", "in qa", "active", "ready for testing"):
                return "In Progress"
            return "To Do"

        # 1. Dynamically resolve target type and parameters
        target_info = self._resolve_target_info(root_key)
        target_type = target_info.get("type", "general")
        root_summary = target_info.get("title") or root_key
        is_dashboard = (target_type == "dashboard")
        is_project_level = (target_type == "project")
        project_name = root_key if is_project_level else root_key.split("-")[0]

        issues_raw = []
        sprint_info = self.get_active_sprint_info(root_key, target_info=target_info)
        resolved_sprint_id = target_info.get("sprint_id") or (sprint_info.get("sprint_id") if sprint_info else None)
        resolved_board_id = target_info.get("board_id")

      
        if resolved_sprint_id:
            try:
                iss_res = requests.get(
                    f"{base_jira_url}/rest/agile/1.0/sprint/{resolved_sprint_id}/issue",
                    headers=headers,
                    auth=auth,
                    params={"fields": f"summary,status,assignee,parent,issuetype,{settings.JIRA_STORY_POINTS_FIELD}", "maxResults": 200},
                    timeout=30,
                )
                if iss_res.status_code == 200:
                    issues_raw = iss_res.json().get("issues", [])
                    sprint_name = target_info.get("sprint_name") or f"Sprint {resolved_sprint_id}"
                    root_summary = f"{target_info.get('title', 'Sprint')} - {sprint_name}"
            except Exception as e:
                print(f"Warning: Fetching issues by sprint ID {resolved_sprint_id} failed: {e}")

        elif resolved_board_id or is_dashboard or target_type == "board":
            board_id = resolved_board_id
            if not board_id and is_dashboard:
                board_search_name = target_info.get("title") or root_key
                try:
                    b_res = requests.get(
                        f"{base_jira_url}/rest/agile/1.0/board",
                        headers=headers,
                        auth=auth,
                        params={"name": board_search_name},
                        timeout=15,
                    )
                    if b_res.status_code == 200:
                        boards = b_res.json().get("values", [])
                        scrum_board = next((b for b in boards if b.get("type") == "scrum"), boards[0] if boards else None)
                        if scrum_board:
                            board_id = scrum_board.get("id")
                except Exception as e:
                    print(f"Warning: Board search by name '{board_search_name}' failed: {e}")

            if board_id:
                try:
                    sp_res = requests.get(
                        f"{base_jira_url}/rest/agile/1.0/board/{board_id}/sprint?state=active",
                        headers=headers,
                        auth=auth,
                        timeout=15,
                    )
                    if sp_res.status_code == 200:
                        sprints = sp_res.json().get("values", [])
                        if sprints:
                            active_sprint = sprints[0]
                            sprint_id = active_sprint.get("id")
                            sprint_name = active_sprint.get("name")
                            target_info["sprint_id"] = sprint_id
                            target_info["board_id"] = board_id
                            root_summary = f"{target_info.get('title', 'Board')} - {sprint_name}"
                            
                            iss_res = requests.get(
                                f"{base_jira_url}/rest/agile/1.0/sprint/{sprint_id}/issue",
                                headers=headers,
                                auth=auth,
                                params={"fields": f"summary,status,assignee,parent,issuetype,{settings.JIRA_STORY_POINTS_FIELD}", "maxResults": 200},
                                timeout=30,
                            )
                            if iss_res.status_code == 200:
                                issues_raw = iss_res.json().get("issues", [])
                except Exception as e:
                    print(f"Warning: Dynamic Agile Sprint fetch for board {board_id} failed: {e}")

        # If Filter IDs were found in Dashboard gadgets (e.g. Filter Results Gadget)
        if not issues_raw and (target_info.get("filter_ids") or (target_type == "filter" and target_info.get("jql"))):
            filter_ids = target_info.get("filter_ids", [])
            if target_type == "filter" and target_info.get("id"):
                filter_ids = [target_info["id"]]

            for fid in filter_ids:
                try:
                    f_res = requests.get(f"{base_jira_url}/rest/api/2/filter/{fid}", headers=headers, auth=auth, timeout=8)
                    if f_res.status_code == 200:
                        f_data = f_res.json()
                        filter_jql = f_data.get("jql")
                        if filter_jql:
                            fields_to_fetch = f"summary,status,assignee,parent,issuetype,{settings.JIRA_STORY_POINTS_FIELD}"
                            search_url = f"{base_jira_url}/rest/api/{api_ver}/search" if self._is_cloud() else f"{base_jira_url}/rest/api/2/search"
                            res = requests.get(
                                search_url,
                                headers=headers,
                                auth=auth,
                                params={"jql": filter_jql, "fields": fields_to_fetch, "maxResults": 250},
                                timeout=45,
                            )
                            if res.status_code == 200:
                                issues_raw = res.json().get("issues", [])
                                if issues_raw:
                                    root_summary = f"{target_info.get('title', 'Dashboard')} - Filter: {f_data.get('name')}"
                                    break
                except Exception as e:
                    print(f"Warning: Fetching issues by filter {fid} failed: {e}")

        # Fallback to JQL Search API if issues_raw not populated by Agile API
        if not issues_raw:
            fields_to_fetch = f"summary,status,assignee,parent,issuetype,{settings.JIRA_STORY_POINTS_FIELD}"
            if is_dashboard:
                # Scope to dashboard title if it contains project/board identifier
                dash_clean_title = re.sub(r'[^\w\s-]', '', target_info.get("title", "")).strip()
                if dash_clean_title and dash_clean_title.lower() not in ("dashboard", f"dashboard {root_key}"):
                    jql = f'(project = "{dash_clean_title}" OR summary ~ "{dash_clean_title}") AND sprint in openSprints() AND issuetype in subTaskIssueTypes() ORDER BY assignee ASC, status ASC'
                else:
                    jql = 'sprint in openSprints() AND issuetype in subTaskIssueTypes() ORDER BY assignee ASC, status ASC'
            elif is_project_level:
                fields_list = ["summary", "status", "assignee", "parent", "issuetype", settings.JIRA_STORY_POINTS_FIELD]
                # 1. Prioritize active sprint in this project
                jql = f'project = "{root_key}" AND sprint in openSprints() ORDER BY parent ASC, created DESC'
                issues_raw = self._execute_jql_search(jql, fields_list, max_results=250)

                # 2. If no open sprint issues found, query all subtasks
                if not issues_raw:
                    jql = f'project = "{root_key}" AND issuetype in subTaskIssueTypes() ORDER BY parent ASC'
                    issues_raw = self._execute_jql_search(jql, fields_list, max_results=250)

                # 3. Fallback to all project issues
                if not issues_raw:
                    jql = f'project = "{root_key}" ORDER BY created DESC'
                    issues_raw = self._execute_jql_search(jql, fields_list, max_results=250)

                root_summary = f"Seluruh Subtask & Sprint Project {root_key}"
            else:
                jql = f'parent = "{root_key}" OR "Epic Link" = "{root_key}" OR id = "{root_key}" ORDER BY parent ASC'
                root_summary = root_key
                fields_list = ["summary", "status", "assignee", "parent", "issuetype", settings.JIRA_STORY_POINTS_FIELD]
                issues_raw = self._execute_jql_search(jql, fields_list, max_results=250)

        # Fallback if single issue passed and JQL didn't catch subtasks directly
        if not issues_raw and not is_project_level:
            try:
                single_url = f"{base_jira_url}/rest/api/{api_ver}/issue/{root_key}?fields=subtasks,summary,status"
                s_res = requests.get(single_url, headers=headers, auth=auth, timeout=10)
                if s_res.status_code == 200:
                    s_data = s_res.json()
                    root_summary = s_data.get("fields", {}).get("summary", root_key)
                    for st_item in s_data.get("fields", {}).get("subtasks", []):
                        issues_raw.append(st_item)
            except Exception:
                pass

        # Helper for subtask role inference
        def _infer_task_role(summary_str: str) -> str:
            s = summary_str.strip().lower()
            # 1. SAD / System Design / Documentation check first
            if re.search(r'\b(system design|design system|dokumen utama|product backlog|iad|bmc|sprint plan|service dependency|security review|summary design|risk register|risk management|user manual|user sign-off|architecture|sad|it control checklist|sprint retrospective|dokumen pengembangan|fsd|brd)\b', s):
                return "SAD"
            if re.search(r'^(?:\[\s*sad\s*\]|sad\s*[-:]|system design\s*[-:]|dokumen\s*[-:])', s):
                return "SAD"
            # 2. Frontend check
            if re.search(r'^(?:\[\s*fe\s*\]|\[\s*frontend\s*\]|\[\s*web\s*\]|fe\s*[-:]|web\s*[-:]|frontend\s*[-:])', s):
                return "Frontend"
            if re.search(r'\b(frontend|react|vue|angular|css|html|layout|modal|navbar|sidebar|screen|figma|ui/ux|view|page|halaman|tampilan)\b', s):
                return "Frontend"
            # 3. QA check
            if re.search(r'^(?:\[\s*qa\s*\]|\[\s*qc\s*\]|\[\s*test\s*\]|qa\s*[-:]|qc\s*[-:]|test\s*[-:]|testing\s*[-:])', s):
                return "QA"
            if re.search(r'\b(qa|qc|sit|uat|dast|sast|pentest|testing|test requirement|test plan|test case)\b', s):
                return "QA"
            # 4. Mobile check
            if re.search(r'^(?:\[\s*mobile\s*\]|\[\s*android\s*\]|\[\s*ios\s*\]|mobile\s*[-:]|android\s*[-:]|ios\s*[-:])', s):
                return "Mobile"
            if re.search(r'\b(mobile|android|ios|apk|flutter|react native|mcs)\b', s):
                return "Mobile"
            # 5. Backend check
            if re.search(r'^(?:\[\s*be\s*\]|\[\s*backend\s*\]|\[\s*job\s*\]|\[\s*las\s*\]|be\s*[-:]|backend\s*[-:]|api\s*[-:])', s):
                return "Backend"
            if re.search(r'\b(backend|api|endpoint|database|query|service|controller|model|repository|cron|job|kafka|redis|sql|table)\b', s):
                return "Backend"
            return "Backend"

        # Pre-pass: calculate predominant role per assignee
        assignee_role_counts = {}
        for item in issues_raw:
            f = item.get("fields", {})
            assignee_obj = f.get("assignee") or {}
            assignee_name = assignee_obj.get("displayName") or "Unassigned"
            if assignee_name != "Unassigned":
                st_summary = f.get("summary", "")
                r_inferred = _infer_task_role(st_summary)
                if assignee_name not in assignee_role_counts:
                    assignee_role_counts[assignee_name] = {}
                assignee_role_counts[assignee_name][r_inferred] = assignee_role_counts[assignee_name].get(r_inferred, 0) + 1

        developer_final_roles = {}
        for dev_name, counts in assignee_role_counts.items():
            dev_lower = dev_name.strip().lower()
            if "fridolin" in dev_lower or "adenito" in dev_lower:
                developer_final_roles[dev_name] = "SAD"
            elif dev_lower in emp_role_map:
                developer_final_roles[dev_name] = emp_role_map[dev_lower]
            else:
                best_role = max(counts.items(), key=lambda x: x[1])[0]
                developer_final_roles[dev_name] = best_role

        member_map = {}
        story_map = {}
        detailed_subtasks = []

        total_todo = 0
        total_in_progress = 0
        total_done = 0

        # 2. Process all retrieved issues & subtasks
        for item in issues_raw:
            issue_key = item.get("key", "")
            fields = item.get("fields", {})
            issue_summary = fields.get("summary", "")
            issue_type_obj = fields.get("issuetype") or {}
            is_subtask = issue_type_obj.get("subtask", False) or bool(fields.get("parent"))

            # Assignee
            assignee_obj = fields.get("assignee") or {}
            assignee_name = assignee_obj.get("displayName") or "Unassigned"

            # Status
            status_obj = fields.get("status") or {}
            status_name = status_obj.get("name", "To Do")
            status_cat_key = (status_obj.get("statusCategory") or {}).get("key", "")
            normalized_status = _categorize_status(status_name, status_cat_key)

            # Role lookup: Developer overall role -> fallback task inference
            if assignee_name == "Unassigned":
                resolved_role = "-"
            elif "fridolin" in assignee_name.strip().lower() or "adenito" in assignee_name.strip().lower():
                resolved_role = "SAD"
            else:
                task_role = _infer_task_role(issue_summary)
                if task_role == "SAD":
                    resolved_role = "SAD"
                else:
                    resolved_role = developer_final_roles.get(assignee_name) or task_role

            if not is_subtask:
                # Parent Story / Epic in the sprint
                if issue_key not in story_map:
                    story_map[issue_key] = {
                        "key": issue_key,
                        "summary": issue_summary,
                        "owner": assignee_name if assignee_name != "Unassigned" else "-",
                        "todo": 0,
                        "in_progress": 0,
                        "done": 0,
                        "total_subtasks": 0,
                    }
                continue

            # It's a subtask
            if normalized_status == "Done":
                total_done += 1
            elif normalized_status == "In Progress":
                total_in_progress += 1
            else:
                total_todo += 1

            # Parent tracking
            parent_key = (fields.get("parent") or {}).get("key", "")
            parent_summary = (fields.get("parent") or {}).get("fields", {}).get("summary", "")
            if parent_key and parent_key not in story_map:
                story_map[parent_key] = {
                    "key": parent_key,
                    "summary": parent_summary or f"Parent {parent_key}",
                    "owner": "-",
                    "todo": 0,
                    "in_progress": 0,
                    "done": 0,
                    "total_subtasks": 0,
                }
            if parent_key in story_map:
                story_map[parent_key]["total_subtasks"] += 1
                if normalized_status == "Done":
                    story_map[parent_key]["done"] += 1
                elif normalized_status == "In Progress":
                    story_map[parent_key]["in_progress"] += 1
                else:
                    story_map[parent_key]["todo"] += 1

            # Member progress tracking
            if assignee_name != "Unassigned":
                if assignee_name not in member_map:
                    member_map[assignee_name] = {
                        "name": assignee_name,
                        "role": developer_final_roles.get(assignee_name, resolved_role),
                        "todo": 0,
                        "in_progress": 0,
                        "done": 0,
                        "total_subtasks": 0,
                    }
                member_map[assignee_name]["total_subtasks"] += 1
                if normalized_status == "Done":
                    member_map[assignee_name]["done"] += 1
                elif normalized_status == "In Progress":
                    member_map[assignee_name]["in_progress"] += 1
                else:
                    member_map[assignee_name]["todo"] += 1

            # Detailed subtask entry
            detailed_subtasks.append({
                "key": issue_key,
                "summary": issue_summary,
                "assignee": assignee_name,
                "role": resolved_role,
                "status": normalized_status,
                "parent_key": parent_key,
                "parent_summary": parent_summary,
                "story_points": 1.0,
                "url": f"{base_jira_url}/browse/{issue_key}",
            })

        # If no subtasks exist under sprint items, treat all sprint stories/tasks as reportable work items
        if not detailed_subtasks and issues_raw:
            for item in issues_raw:
                issue_key = item.get("key", "")
                fields = item.get("fields", {})
                issue_summary = fields.get("summary", "")
                assignee_obj = fields.get("assignee") or {}
                assignee_name = assignee_obj.get("displayName") or "Unassigned"
                status_obj = fields.get("status") or {}
                status_name = status_obj.get("name", "To Do")
                status_cat_key = (status_obj.get("statusCategory") or {}).get("key", "")
                normalized_status = _categorize_status(status_name, status_cat_key)

                if assignee_name == "Unassigned":
                    resolved_role = "-"
                elif "fridolin" in assignee_name.strip().lower() or "adenito" in assignee_name.strip().lower():
                    resolved_role = "SAD"
                else:
                    task_role = _infer_task_role(issue_summary)
                    resolved_role = developer_final_roles.get(assignee_name) or task_role

                if normalized_status == "Done":
                    total_done += 1
                elif normalized_status == "In Progress":
                    total_in_progress += 1
                else:
                    total_todo += 1

                detailed_subtasks.append({
                    "key": issue_key,
                    "summary": issue_summary,
                    "assignee": assignee_name,
                    "role": resolved_role,
                    "status": normalized_status,
                    "parent_key": "-",
                    "parent_summary": "-",
                    "story_points": 1.0,
                    "url": f"{base_jira_url}/browse/{issue_key}",
                })

        # Ensure all active team members from Members.xlsx appear (only in project mode, not dashboard mode)
        if active_employees and not is_dashboard:
            for emp in active_employees:
                name = getattr(emp, "name", None) or (emp.get("name") if isinstance(emp, dict) else "")
                role = getattr(emp, "role", None) or (emp.get("role") if isinstance(emp, dict) else "")
                if name and name not in member_map:
                    member_map[name] = {
                        "name": name,
                        "role": role,
                        "todo": 0,
                        "in_progress": 0,
                        "done": 0,
                        "total_subtasks": 0,
                    }

        # Calculate percent done per member
        member_progress_list = []
        for m in member_map.values():
            tot = m["total_subtasks"]
            m["percent_done"] = round((m["done"] / tot * 100), 1) if tot > 0 else 0.0
            member_progress_list.append(m)

        # Sort members by active tasks count (descending) then name
        member_progress_list.sort(key=lambda x: (x["total_subtasks"] > 0, x["total_subtasks"], x["name"]), reverse=True)

        # Calculate percent done per story
        story_progress_list = []
        for s in story_map.values():
            tot = s["total_subtasks"]
            s["percent_done"] = round((s["done"] / tot * 100), 1) if tot > 0 else 0.0
            story_progress_list.append(s)
        story_progress_list.sort(key=lambda x: x["key"])

        grand_total = total_todo + total_in_progress + total_done
        sprint_info = self.get_active_sprint_info(root_key, target_info=target_info)

        return {
            "root_key": root_key,
            "root_summary": root_summary,
            "sprint_info": sprint_info,
            "total_epics_count": len(story_progress_list),
            "overall_status": {
                "todo": total_todo,
                "in_progress": total_in_progress,
                "done": total_done,
                "total": grand_total,
                "percent_done": round((total_done / grand_total * 100), 1) if grand_total > 0 else 0.0,
            },
            "member_progress": member_progress_list,
            "story_progress": story_progress_list,
            "detailed_subtasks": detailed_subtasks,
        }

    def get_active_sprint_info(
        self, project_or_epic: str = "JT", target_info: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Fetches the active Sprint details (Name, Start Date, End Date, Days Remaining)
        100% dynamically from Jira Agile REST API and Jira Greenhopper API.
        """
        if not target_info:
            target_info = self._resolve_target_info(project_or_epic)

        auth = self._get_auth()
        headers = self._get_headers()
        base_jira_url = settings.JIRA_URL.rstrip("/")

        candidate_board_ids = []
        if target_info.get("board_id"):
            candidate_board_ids.append(target_info["board_id"])

        # If direct sprint ID is known
        if target_info.get("sprint_id"):
            try:
                sp_url = f"{base_jira_url}/rest/agile/1.0/sprint/{target_info['sprint_id']}"
                sp_res = requests.get(sp_url, headers=headers, auth=auth, timeout=10)
                if sp_res.status_code == 200:
                    sp = sp_res.json()
                    name = sp.get("name", "Active Sprint")
                    end_date_str = sp.get("endDate")
                    days_remaining = None
                    if end_date_str:
                        try:
                            end_dt = datetime.datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                            now_dt = datetime.datetime.now(datetime.timezone.utc)
                            curr = now_dt.date()
                            target = end_dt.date()
                            w_days = 0
                            while curr < target:
                                curr += datetime.timedelta(days=1)
                                if curr.weekday() < 5:
                                    w_days += 1
                            days_remaining = w_days
                        except Exception:
                            pass
                    return {
                        "sprint_id": sp.get("id"),
                        "name": name,
                        "start_date": sp.get("startDate"),
                        "end_date": end_date_str,
                        "days_remaining": days_remaining,
                        "goal": sp.get("goal", ""),
                    }
            except Exception:
                pass

        # If board ID not directly known, search boards dynamically
        if not candidate_board_ids:
            search_params = {}
            if target_info.get("type") == "dashboard":
                search_params = {"name": target_info.get("title") or project_or_epic}
            elif target_info.get("type") == "project":
                search_params = {"projectKeyOrId": target_info.get("key") or project_or_epic}
            elif "-" in project_or_epic:
                search_params = {"projectKeyOrId": project_or_epic.split("-")[0]}

            try:
                res = requests.get(f"{base_jira_url}/rest/agile/1.0/board", headers=headers, auth=auth, params=search_params, timeout=10)
                if res.status_code == 200:
                    boards = res.json().get("values", [])
                    scrum_boards = [b for b in boards if b.get("type") == "scrum"] or boards
                    for b in scrum_boards:
                        if b.get("id") not in candidate_board_ids:
                            candidate_board_ids.append(b.get("id"))
            except Exception:
                pass

        # Query active sprint and greenhopper data for candidate boards
        for b_id in candidate_board_ids:
            # 1. Direct native fetch from Jira Greenhopper API (Exact Jira Days Remaining)
            try:
                gh_res = requests.get(
                    f"{base_jira_url}/rest/greenhopper/1.0/xboard/work/allData/?rapidViewId={b_id}",
                    headers=headers,
                    auth=auth,
                    timeout=12,
                )
                if gh_res.status_code == 200:
                    s_list = gh_res.json().get("sprintsData", {}).get("sprints", [])
                    active_gh = next((s for s in s_list if s.get("state") == "ACTIVE"), None)
                    if active_gh:
                        return {
                            "sprint_id": active_gh.get("id"),
                            "name": active_gh.get("name", "Active Sprint"),
                            "start_date": active_gh.get("startDate"),
                            "end_date": active_gh.get("endDate"),
                            "days_remaining": active_gh.get("daysRemaining"),
                            "goal": active_gh.get("goal", ""),
                        }
            except Exception:
                pass

            # 2. Fallback to standard Agile Sprint API
            try:
                sprint_url = f"{base_jira_url}/rest/agile/1.0/board/{b_id}/sprint?state=active"
                s_res = requests.get(sprint_url, headers=headers, auth=auth, timeout=10)
                if s_res.status_code == 200:
                    active_sprints = s_res.json().get("values", [])
                    if active_sprints:
                        sp = active_sprints[0]
                        name = sp.get("name", "Active Sprint")
                        end_date_str = sp.get("endDate")
                        days_remaining = None
                        if end_date_str:
                            try:
                                end_dt = datetime.datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                                now_dt = datetime.datetime.now(datetime.timezone.utc)
                                curr = now_dt.date()
                                target = end_dt.date()
                                w_days = 0
                                while curr < target:
                                    curr += datetime.timedelta(days=1)
                                    if curr.weekday() < 5:
                                        w_days += 1
                                days_remaining = w_days
                            except Exception:
                                pass
                        return {
                            "sprint_id": sp.get("id"),
                            "name": name,
                            "start_date": sp.get("startDate"),
                            "end_date": end_date_str,
                            "days_remaining": days_remaining,
                            "goal": sp.get("goal", ""),
                        }
            except Exception:
                pass

        return None
