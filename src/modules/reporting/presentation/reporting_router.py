"""
Reporting Presentation Router.

Handles HTTP REST API endpoints for generating and exporting Sprint & Squad Progress
Excel reports (.xlsx) with clean, modular data processing and schema validation.
"""

import base64
import os
import re
import tempfile
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from modules.generate_subtask.infrastructure.jira_rest_client import JiraRestClient
from modules.reporting.infrastructure.excel_reporter import ExcelReporter

router = APIRouter(prefix="/api/v1/reporting", tags=["Sprint & Squad Reporting"])

excel_reporter = ExcelReporter()
jira_client = JiraRestClient()


class ExportExcelRequest(BaseModel):
    """Pydantic model representing an Excel export request payload."""

    root_key: str = Field(..., description="Target Jira Issue / Epic / Sprint key (e.g. JT-161)")
    root_summary: Optional[str] = Field(default="", description="Summary title of the target key")
    sprint_info: Optional[Dict[str, Any]] = Field(default=None, description="Active Sprint metadata")
    stories: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="List of parent stories")
    detailed_subtasks: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Flattened subtask list")
    member_progress: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Developer progress summaries")
    overall_status: Optional[Dict[str, Any]] = Field(default=None, description="Sprint-wide task counts")
    total_epics_count: Optional[int] = Field(default=0, description="Total count of active parent stories")
    return_base64: Optional[bool] = Field(default=False, description="Flag to return file as Base64 JSON")


# =============================================================================
# DATA NORMALIZATION HELPERS
# =============================================================================

def _normalize_subtask_role(summary: str, assignee: str, default_role: str = "Backend") -> str:
    """Infers and standardizes technical role (SAD, Frontend, Backend, Mobile) from summary and assignee."""
    summary_lower = str(summary or "").lower()
    assignee_lower = str(assignee or "").lower()

    if "fridolin" in assignee_lower or "adenito" in assignee_lower:
        return "SAD"

    sad_pattern = (
        r"\b(system design|design system|dokumen utama|product backlog|iad|bmc|sprint plan|"
        r"service dependency|security review|summary design|risk register|risk management|"
        r"user manual|user sign-off|architecture|sad|it control checklist|sprint retrospective|"
        r"dokumen pengembangan)\b"
    )
    if re.search(sad_pattern, summary_lower):
        return "SAD"

    if re.search(r"^(?:\[\s*fe\s*\]|\[\s*frontend\s*\]|\[\s*web\s*\]|fe\s*[-:]|web\s*[-:]|frontend\s*[-:])", summary_lower):
        return "Frontend"
    if re.search(r"\b(frontend|react|vue|angular|css|html|layout|modal|navbar|sidebar|screen|figma|ui/ux|view|page|halaman|tampilan)\b", summary_lower):
        return "Frontend"

    if re.search(r"^(?:\[\s*mobile\s*\]|\[\s*android\s*\]|\[\s*ios\s*\]|mobile\s*[-:]|android\s*[-:]|ios\s*[-:])", summary_lower):
        return "Mobile"
    if re.search(r"\b(mobile|android|ios|apk|flutter|react native|mcs)\b", summary_lower):
        return "Mobile"

    return default_role or "Backend"


def _compute_overall_status(subtasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculates sprint-wide task statistics (To Do, In Progress, Done, % Selesai)."""
    if not subtasks:
        return {"total": 0, "todo": 0, "in_progress": 0, "done": 0, "percent_done": 0.0}

    todo_count = sum(1 for s in subtasks if str(s.get("status", "")).lower() in ("to do", "todo", "open", "backlog"))
    done_count = sum(1 for s in subtasks if str(s.get("status", "")).lower() in ("done", "closed", "resolved", "verified", "complete", "selesai"))
    in_progress_count = len(subtasks) - todo_count - done_count
    percent_done = round((done_count / len(subtasks) * 100), 1)

    return {
        "total": len(subtasks),
        "todo": todo_count,
        "in_progress": in_progress_count,
        "done": done_count,
        "percent_done": percent_done,
    }


def _build_member_progress_summary(subtasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregates subtasks per developer into structured progress summaries."""
    member_map: Dict[str, Dict[str, Any]] = {}

    for sub in subtasks:
        assignee = (sub.get("assignee") or "Unassigned").strip()
        if assignee.lower() == "unassigned":
            continue

        if assignee not in member_map:
            member_map[assignee] = {
                "name": assignee,
                "role": sub.get("role", "Developer"),
                "todo": 0,
                "in_progress": 0,
                "done": 0,
                "total_subtasks": 0,
                "percent_done": 0.0,
            }

        status_lower = str(sub.get("status", "")).lower()
        if any(k in status_lower for k in ("done", "closed", "resolved", "complete", "selesai")):
            member_map[assignee]["done"] += 1
        elif any(k in status_lower for k in ("to do", "todo", "open", "backlog")):
            member_map[assignee]["todo"] += 1
        else:
            member_map[assignee]["in_progress"] += 1

        member_map[assignee]["total_subtasks"] += 1

    for item in member_map.values():
        total = item["total_subtasks"]
        item["percent_done"] = round((item["done"] / total * 100), 1) if total > 0 else 0.0

    return list(member_map.values())


def _build_story_progress_summary(
    stories: List[Dict[str, Any]], subtasks: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Builds progress breakdown per parent story / epic."""
    if stories:
        stories_progress = []
        for story in stories:
            story_key = story.get("key", "")
            story_subs = [s for s in subtasks if s.get("parent_key") == story_key] or story.get("subtasks", [])
            
            s_todo = sum(1 for s in story_subs if str(s.get("status", "")).lower() in ("to do", "todo", "open", "backlog"))
            s_done = sum(1 for s in story_subs if str(s.get("status", "")).lower() in ("done", "closed", "resolved", "verified", "complete", "selesai"))
            s_prog = len(story_subs) - s_todo - s_done
            s_total = len(story_subs)
            s_percent = round((s_done / s_total * 100), 1) if s_total > 0 else 0.0

            stories_progress.append({
                "key": story_key,
                "summary": story.get("summary", ""),
                "owner": story.get("owner") or story.get("assignee") or "-",
                "status": story.get("status", "To Do"),
                "todo": s_todo,
                "in_progress": s_prog,
                "done": s_done,
                "total": s_total,
                "total_subtasks": s_total,
                "percent_done": s_percent,
                "subtasks": story_subs,
            })
        return stories_progress

    # Auto-group from detailed_subtasks by parent_key if stories list is empty
    parent_map: Dict[str, Dict[str, Any]] = {}
    for sub in subtasks:
        parent_key = sub.get("parent_key") or "Parent Story"
        parent_summary = sub.get("parent_summary") or parent_key

        if parent_key not in parent_map:
            parent_map[parent_key] = {
                "key": parent_key,
                "summary": parent_summary,
                "owner": sub.get("parent_owner") or sub.get("assignee") or "-",
                "todo": 0,
                "in_progress": 0,
                "done": 0,
                "total": 0,
                "total_subtasks": 0,
                "subtasks": [],
            }

        parent_map[parent_key]["subtasks"].append(sub)
        status_lower = str(sub.get("status", "")).lower()
        if any(k in status_lower for k in ("done", "closed", "resolved", "complete", "selesai")):
            parent_map[parent_key]["done"] += 1
        elif any(k in status_lower for k in ("in progress", "progress", "review")):
            parent_map[parent_key]["in_progress"] += 1
        else:
            parent_map[parent_key]["todo"] += 1

    stories_progress = []
    for parent_item in parent_map.values():
        total_count = len(parent_item["subtasks"])
        parent_item["total"] = total_count
        parent_item["total_subtasks"] = total_count
        parent_item["percent_done"] = round((parent_item["done"] / total_count * 100), 1) if total_count > 0 else 0.0
        stories_progress.append(parent_item)

    return stories_progress


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/exportExcel")
@router.post("/export-excel")
def export_excel_report(req: ExportExcelRequest):
    """
    Generates professional, executive-ready Excel report (.xlsx)
    with native Bar & Pie Charts, KPI cards, Segoe UI theme, and clickable Jira links.
    """
    try:
        safe_key = "".join([c for c in req.root_key if c.isalnum() or c in ("-", "_")]).strip() or "Report"

        # 1. Process data from Jira Web UI / Forge
        if req.detailed_subtasks or req.stories:
            subtasks = req.detailed_subtasks or []

            # If subtasks weren't flattened, extract them from stories
            if not subtasks and req.stories:
                for story_item in req.stories:
                    st_key = story_item.get("key", "")
                    st_sum = story_item.get("summary", "")
                    for sub in story_item.get("subtasks", []):
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

            # Refine subtask roles (SAD, Frontend, Backend, Mobile)
            for sub in subtasks:
                sub["role"] = _normalize_subtask_role(
                    summary=sub.get("summary", ""),
                    assignee=sub.get("assignee", ""),
                    default_role=sub.get("role", "Backend"),
                )

            # Compute statistics and progress structures
            overall_status = req.overall_status or _compute_overall_status(subtasks)
            member_progress = req.member_progress or _build_member_progress_summary(subtasks)
            stories_progress = _build_story_progress_summary(req.stories or [], subtasks)

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

        # 3. Generate Excel file in temporary directory
        with tempfile.TemporaryDirectory() as tmp_dir:
            generated_filename = excel_reporter.generate_progress_report(
                report_data=report_data,
                safe_key=safe_key,
                output_path=tmp_dir,
            )
            full_file_path = os.path.join(tmp_dir, generated_filename)

            with open(full_file_path, "rb") as file_handle:
                file_bytes = file_handle.read()

        filename = f"Laporan_Progress_{safe_key}.xlsx"

        # 4. Return Base64 JSON if requested (for Forge Resolvers)
        if req.return_base64:
            base64_string = base64.b64encode(file_bytes).decode("utf-8")
            return {
                "status": "success",
                "filename": filename,
                "base64": base64_string,
                "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }

        # 5. Return binary stream directly for browser download
        return Response(
            content=file_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Gagal mengekspor laporan Excel: {str(exc)}",
        )
