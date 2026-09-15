import requests
import re
import datetime
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

    def get_epic_issues(self, epic_key: str) -> List[Story]:
        epic_key = self._clean_key(epic_key)
        if not epic_key or not self._is_issue_key(epic_key):
            return []
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

        response = None
        for attempt in range(2):
            try:
                response = requests.get(
                    url, headers=headers, params=params, auth=auth, timeout=25
                )
                if response.status_code == 200:
                    break
            except Exception as req_err:
                if attempt == 1:
                    raise req_err
                time.sleep(1)

        stories = []

        if response.status_code == 200:
            data = response.json()
            for item in data.get("issues", []):
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
                issuetype_name = issuetype_obj.get("name", "Story") if isinstance(issuetype_obj, dict) else "Story"
                is_subtask = issuetype_obj.get("subtask", False) if isinstance(issuetype_obj, dict) else False

                # Skip subtasks when querying Epic children 
                if is_subtask or issuetype_name.lower() in ["sub-task", "subtask", "sub task"]:
                    continue

                status_obj = fields.get("status") or {}
                status_name = status_obj.get("name", "To Do") if isinstance(status_obj, dict) else "To Do"

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
        
        headers = self._get_headers()
        auth = self._get_auth()
        
        # Cloud uses API v3, Server uses v2
        version = "3" if self._is_cloud() else "2"
        url = f"{settings.JIRA_URL.rstrip('/')}/rest/api/{version}/issue/{parent_key}?fields=subtasks"
        
        try:
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
        headers = self._get_headers()
        auth = self._get_auth()
        params = {"fields": f"summary,description,{settings.JIRA_STORY_POINTS_FIELD},issuetype,status,parent"}

        response = None
        for attempt in range(2):
            try:
                response = requests.get(url, headers=headers, params=params, auth=auth, timeout=25)
                if response.status_code == 200:
                    break
            except Exception as req_err:
                if attempt == 1:
                    raise req_err
                time.sleep(1)
        if response.status_code != 200:
            raise Exception(
                f"Failed to fetch issue {issue_key} from Jira ({response.status_code}): {response.text}"
            )

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
                print(f" [{issue_key}] adalah Subtask. Otomatis beralih ke parent Story/Task [{parent_key}]...")
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

        # Check if input is a Dashboard URL or Page ID (e.g. selectPageId=26953 or 23001)
        dashboard_id = None
        if "selectPageId=" in root_key:
            m = re.search(r'selectPageId=(\d+)', root_key)
            if m:
                dashboard_id = m.group(1)
        elif "ConfigurePortalPages" in root_key or "Dashboard" in root_key:
            m = re.search(r'(?:id|pageId|selectPageId)=(\d+)', root_key)
            if m:
                dashboard_id = m.group(1)
        elif root_key.isdigit():
            dashboard_id = root_key

        is_dashboard = bool(dashboard_id) in root_key.lower()
        is_project_level = (not is_dashboard) and (("-" not in root_key) or root_key.upper() in ("ALL", "PROJECT"))
        project_name = root_key if is_project_level else root_key.split("-")[0]

        issues_raw = []
        root_summary = root_key

        if is_dashboard:
            dashboard_title = f"Dashboard Korporasi 1 (ID: {dashboard_id or '26953'})"
            root_summary = f"Inquiry Live Jira Dashboard: {dashboard_title}"
            
            # Dynamically query Agile Boards for the dashboard / squad
            board_query = "Korporasi 1"
            try:
                b_res = requests.get(
                    f"{base_jira_url}/rest/agile/1.0/board",
                    headers=headers,
                    auth=auth,
                    params={"name": board_query},
                    timeout=15,
                )
                if b_res.status_code == 200:
                    boards = b_res.json().get("values", [])
                    scrum_board = next((b for b in boards if b.get("type") == "scrum"), boards[0] if boards else None)
                    if scrum_board:
                        board_id = scrum_board.get("id")
                        # Query active sprint for this board dynamically
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
                                root_summary = f"Dashboard Korporasi 1 - {sprint_name}"
                                
                                # Fetch all issues directly from the active sprint
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
                print(f"Warning: Dynamic Agile Sprint fetch failed: {e}")

        # Fallback to JQL Search API if issues_raw not populated by Agile API
        if not issues_raw:
            fields_to_fetch = f"summary,status,assignee,parent,issuetype,{settings.JIRA_STORY_POINTS_FIELD}"
            if is_dashboard:
                jql = 'sprint in openSprints() AND issuetype in subTaskIssueTypes() ORDER BY assignee ASC, status ASC'
            elif is_project_level:
                jql = f'project = "{root_key}" AND issuetype in subTaskIssueTypes() ORDER BY parent ASC'
                root_summary = f"Seluruh Subtask & Epic Sprint Project {root_key}"
            else:
                jql = f'parent = "{root_key}" OR "Epic Link" = "{root_key}" OR id = "{root_key}" ORDER BY parent ASC'
                root_summary = root_key

            search_url = f"{base_jira_url}/rest/api/{api_ver}/search/jql" if self._is_cloud() else f"{base_jira_url}/rest/api/2/search"
            try:
                res = requests.get(
                    search_url,
                    headers=headers,
                    auth=auth,
                    params={"jql": jql, "fields": fields_to_fetch, "maxResults": 250},
                    timeout=45,
                )
                if res.status_code == 200:
                    issues_raw = res.json().get("issues", [])
            except Exception as e:
                print(f"Warning: JQL search failed: {e}")

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

        member_map = {}
        story_map = {}
        detailed_subtasks = []

        total_todo = 0
        total_in_progress = 0
        total_done = 0

        # 2. Process all retrieved subtasks
        for item in issues_raw:
            st_key = item.get("key", "")
            f = item.get("fields", {})
            st_summary = f.get("summary", "")

            # Parent issue info
            parent_obj = f.get("parent") or {}
            p_key = parent_obj.get("key") or root_key
            p_fields = parent_obj.get("fields") or {}
            p_summary = p_fields.get("summary") or p_key

            # Status
            st_status_obj = f.get("status") or {}
            st_status_name = st_status_obj.get("name", "To Do")
            st_status_cat = (st_status_obj.get("statusCategory") or {}).get("key", "")
            normalized_status = _categorize_status(st_status_name, st_status_cat)

            # Assignee
            assignee_obj = f.get("assignee") or {}
            assignee_name = assignee_obj.get("displayName") or "Unassigned"

            # Story Points
            st_sp = self._extract_story_points(f)

            # Role lookup / inference
            role_val = emp_role_map.get(assignee_name.strip().lower(), "")
            if not role_val:
                sum_lower = st_summary.lower()
                if sum_lower.startswith("web -") or sum_lower.startswith("fe -"):
                    role_val = "Frontend"
                elif sum_lower.startswith("be -"):
                    role_val = "Backend"
                elif sum_lower.startswith("mobile -"):
                    role_val = "Mobile"
                else:
                    role_val = "Engineer"

            # Update overall counts
            if normalized_status == "Done":
                total_done += 1
            elif normalized_status == "In Progress":
                total_in_progress += 1
            else:
                total_todo += 1

            # Update Story Map
            if p_key not in story_map:
                story_map[p_key] = {
                    "key": p_key,
                    "summary": p_summary,
                    "todo": 0,
                    "in_progress": 0,
                    "done": 0,
                    "total_subtasks": 0,
                    "total_sp": 0.0,
                }
            story_map[p_key]["total_subtasks"] += 1
            if normalized_status == "Done":
                story_map[p_key]["done"] += 1
            elif normalized_status == "In Progress":
                story_map[p_key]["in_progress"] += 1
            else:
                story_map[p_key]["todo"] += 1

            # Update Member Map
            if assignee_name not in member_map:
                member_map[assignee_name] = {
                    "name": assignee_name,
                    "role": role_val,
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

            detailed_subtasks.append({
                "key": st_key,
                "summary": st_summary,
                "parent_key": p_key,
                "parent_summary": p_summary,
                "assignee": assignee_name,
                "role": role_val,
                "status": st_status_name,
                "status_category": normalized_status,
                "story_points": st_sp,
                "url": f"{base_jira_url}/browse/{st_key}" if st_key else "",
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
                        "total_sp": 0.0,
                    }

        # Calculate percent done per member
        member_progress_list = []
        for m in member_map.values():
            tot = m["total_subtasks"]
            m["percent_done"] = round((m["done"] / tot * 100), 1) if tot > 0 else 0.0
            member_progress_list.append(m)

        # Sort members by role then name
        member_progress_list.sort(key=lambda x: (x["role"], x["name"]))

        # Calculate percent done per story
        story_progress_list = []
        for s in story_map.values():
            tot = s["total_subtasks"]
            s["percent_done"] = round((s["done"] / tot * 100), 1) if tot > 0 else 0.0
            story_progress_list.append(s)
        story_progress_list.sort(key=lambda x: x["key"])

        grand_total = total_todo + total_in_progress + total_done

        return {
            "root_key": root_key,
            "root_summary": root_summary,
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

    def get_active_sprint_info(self, project_or_epic: str = "JT") -> Optional[Dict[str, Any]]:
        """
        Fetches the active Sprint details (Name, Start Date, End Date, Days Remaining)
        directly from Jira Agile REST API.
        """
        import datetime
        project_key = project_or_epic.split("-")[0] if "-" in project_or_epic else project_or_epic
        auth = self._get_auth()
        headers = self._get_headers()
        base_url = settings.JIRA_URL.rstrip("/")

        # 1. Search Agile Boards for the project
        try:
            boards_url = f"{base_url}/rest/agile/1.0/board?projectKeyOrId={project_key}"
            res = requests.get(boards_url, headers=headers, auth=auth, timeout=10)
            if res.status_code == 200:
                boards = res.json().get("values", [])
                for b in boards:
                    b_id = b.get("id")
                    sprint_url = f"{base_url}/rest/agile/1.0/board/{b_id}/sprint?state=active"
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
                                    days_remaining = (end_dt.date() - now_dt.date()).days
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

        # 2. Fallback: Search across all agile boards in Jira
        try:
            boards_url = f"{base_url}/rest/agile/1.0/board"
            res = requests.get(boards_url, headers=headers, auth=auth, timeout=10)
            if res.status_code == 200:
                boards = res.json().get("values", [])
                for b in boards:
                    b_id = b.get("id")
                    sprint_url = f"{base_url}/rest/agile/1.0/board/{b_id}/sprint?state=active"
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
                                    days_remaining = (end_dt.date() - now_dt.date()).days
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
