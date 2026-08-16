from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
import base64
import tempfile

from modules.reporting.infrastructure.excel_reporter import ExcelReporter
from modules.generate_subtask.infrastructure.jira_rest_client import JiraRestClient

router = APIRouter(prefix="/api/v1/reporting", tags=["Sprint & Squad Reporting"])

excel_reporter = ExcelReporter()
jira_client = JiraRestClient()


class ExportExcelRequest(BaseModel):
    root_key: str
    root_summary: Optional[str] = ""
    sprint_info: Optional[Dict[str, Any]] = None
    stories: Optional[List[Dict[str, Any]]] = []
    detailed_subtasks: Optional[List[Dict[str, Any]]] = []
    member_progress: Optional[List[Dict[str, Any]]] = []
    overall_status: Optional[Dict[str, Any]] = None
    total_epics_count: Optional[int] = 0
    return_base64: Optional[bool] = False


@router.post("/exportExcel")
@router.post("/export-excel")
def export_excel_report(req: ExportExcelRequest):
    """
    Generates professional, executive-ready Excel report (.xlsx)
    with native Bar & Pie Charts, KPI cards, Segoe UI theme, and clickable Jira links.
    """
    try:
        safe_key = "".join([c for c in req.root_key if c.isalnum() or c in ("-", "_")]).strip() or "Report"
        
        # 1. If detailed data is provided directly from Jira Web UI / Forge
        if req.detailed_subtasks or req.stories:
            subtasks = req.detailed_subtasks or []
            
            # If subtasks weren't flattened, extract them from stories
            if not subtasks and req.stories:
                for st in req.stories:
                    st_key = st.get("key", "")
                    st_sum = st.get("summary", "")
                    for sub in st.get("subtasks", []):
                        subtasks.append({
                            "key": sub.get("key", ""),
                            "summary": sub.get("summary", ""),
                            "status": sub.get("status", "To Do"),
                            "role": sub.get("role", "Backend"),
                            "assignee": sub.get("assignee", "Unassigned"),
                            "parent_key": st_key,
                            "parent_summary": st_sum,
                            "story_points": float(sub.get("story_points", 1.0)),
                        })

            # Calculate overall status if not provided
            todo_c = sum(1 for s in subtasks if str(s.get("status", "")).lower() in ("to do", "todo", "open", "backlog"))
            done_c = sum(1 for s in subtasks if str(s.get("status", "")).lower() in ("done", "closed", "resolved", "verified"))
            prog_c = len(subtasks) - todo_c - done_c
            pct_done = round((done_c / len(subtasks) * 100), 1) if subtasks else 0.0

            overall_status = req.overall_status or {
                "total": len(subtasks),
                "todo": todo_c,
                "in_progress": prog_c,
                "done": done_c,
                "percent_done": pct_done,
            }

            # Build member progress summary if not provided
            member_progress = req.member_progress or []
            if not member_progress and subtasks:
                mem_map = {}
                for s in subtasks:
                    assignee = (s.get("assignee") or "Unassigned").strip()
                    if assignee.lower() == "unassigned":
                        continue
                    if assignee not in mem_map:
                        mem_map[assignee] = {
                            "name": assignee,
                            "role": s.get("role", "Developer"),
                            "todo": 0,
                            "in_progress": 0,
                            "done": 0,
                            "total_subtasks": 0,
                            "percent_done": 0.0,
                        }
                    st_status = str(s.get("status", "")).lower()
                    if st_status in ("done", "closed", "resolved"):
                        mem_map[assignee]["done"] += 1
                    elif st_status in ("to do", "todo", "open"):
                        mem_map[assignee]["todo"] += 1
                    else:
                        mem_map[assignee]["in_progress"] += 1
                    mem_map[assignee]["total_subtasks"] += 1

                for m in mem_map.values():
                    tot = m["total_subtasks"]
                    m["percent_done"] = round((m["done"] / tot * 100), 1) if tot > 0 else 0.0
                member_progress = list(mem_map.values())

            # Build epic / stories progress
            stories_progress = []
            if req.stories:
                for st in req.stories:
                    st_key = st.get("key", "")
                    st_subs = [s for s in subtasks if s.get("parent_key") == st_key] or st.get("subtasks", [])
                    st_todo = sum(1 for s in st_subs if str(s.get("status", "")).lower() in ("to do", "todo", "open", "backlog"))
                    st_done = sum(1 for s in st_subs if str(s.get("status", "")).lower() in ("done", "closed", "resolved", "verified"))
                    st_prog = len(st_subs) - st_todo - st_done
                    st_tot = len(st_subs)
                    st_pct = round((st_done / st_tot * 100), 1) if st_tot > 0 else 0.0

                    stories_progress.append({
                        "key": st_key,
                        "summary": st.get("summary", ""),
                        "owner": st.get("owner") or st.get("assignee") or "-",
                        "status": st.get("status", "To Do"),
                        "todo": st_todo,
                        "in_progress": st_prog,
                        "done": st_done,
                        "total": st_tot,
                        "total_subtasks": st_tot,
                        "percent_done": st_pct,
                        "subtasks": st_subs,
                    })
            elif subtasks:
                # Auto-group from detailed_subtasks by parent_key
                parent_map = {}
                for s in subtasks:
                    p_key = s.get("parent_key") or "Parent Story"
                    p_sum = s.get("parent_summary") or p_key
                    if p_key not in parent_map:
                        parent_map[p_key] = {
                            "key": p_key,
                            "summary": p_sum,
                            "owner": s.get("parent_owner") or s.get("assignee") or "-",
                            "todo": 0,
                            "in_progress": 0,
                            "done": 0,
                            "total": 0,
                            "total_subtasks": 0,
                            "subtasks": [],
                        }
                    parent_map[p_key]["subtasks"].append(s)
                    s_stat = str(s.get("status", "")).lower()
                    if any(k in s_stat for k in ("done", "closed", "resolved", "complete")):
                        parent_map[p_key]["done"] += 1
                    elif any(k in s_stat for k in ("in progress", "progress", "review")):
                        parent_map[p_key]["in_progress"] += 1
                    else:
                        parent_map[p_key]["todo"] += 1

                for pm in parent_map.values():
                    tot = len(pm["subtasks"])
                    pm["total"] = tot
                    pm["total_subtasks"] = tot
                    pm["percent_done"] = round((pm["done"] / tot * 100), 1) if tot > 0 else 0.0
                    stories_progress.append(pm)

            report_data = {
                "root_key": req.root_key,
                "root_summary": req.root_summary or f"Laporan Progress {req.root_key}",
                "sprint_info": req.sprint_info or {},
                "overall_status": overall_status,
                "total_epics_count": req.total_epics_count or len(stories_progress),
                "member_progress": member_progress,
                "epic_progress": stories_progress,
                "story_progress": stories_progress,
                "stories": stories_progress,
                "parent_progress": stories_progress,
                "detailed_subtasks": subtasks,
            }
        else:
            # 2. Fallback: Fetch directly from Jira REST Client
            report_data = jira_client.get_progress_report_data(req.root_key)

        with tempfile.TemporaryDirectory() as tmp_dir:
            generated_filename = excel_reporter.generate_progress_report(
                report_data=report_data,
                safe_key=safe_key,
                output_path=tmp_dir,
            )
            full_file_path = os.path.join(tmp_dir, generated_filename)

            with open(full_file_path, "rb") as f:
                file_bytes = f.read()

        filename = f"Laporan_Progress_{safe_key}.xlsx"

        # Return Base64 JSON if requested (useful for Forge Resolvers)
        if req.return_base64:
            b64_str = base64.b64encode(file_bytes).decode("utf-8")
            return {
                "status": "success",
                "filename": filename,
                "base64": b64_str,
                "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }

        # Return raw downloadable stream
        return Response(
            content=file_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate Excel report: {str(e)}")
