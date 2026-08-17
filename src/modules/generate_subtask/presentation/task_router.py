from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
import uuid
import os

# Shared & Core Domain Imports
from modules.reporting.domain.models import Employee
from modules.reporting.domain.balancer_service import WorkloadBalancerService

# Infrastructure & Repository Imports
from modules.generate_subtask.infrastructure.sqlite_story_repository import SqliteStoryRepository, SqliteMetricRepository
from modules.generate_subtask.infrastructure.llm_client import LlmClient
from modules.generate_subtask.infrastructure.jira_rest_client import JiraRestClient
from modules.reporting.infrastructure.pandas_excel_parser import PandasExcelParser

# Application Use Case Imports
from modules.generate_subtask.application.generate_subtasks_use_case import GenerateSubtasksUseCase
from modules.reporting.application.balance_workload_use_case import BalanceWorkloadUseCase

router = APIRouter(prefix="/api/v1")

# Instantiate infrastructure and application services (Dependency Injection)
story_repo = SqliteStoryRepository()
metric_repo = SqliteMetricRepository()
llm_client = LlmClient()
jira_client = JiraRestClient()
excel_parser = PandasExcelParser()

generate_subtasks_uc = GenerateSubtasksUseCase(story_repo, llm_client)
balance_workload_uc = BalanceWorkloadUseCase(WorkloadBalancerService())

# High-performance parallel workers (5 workers) for fast subtask generation (<6s)
executor = ThreadPoolExecutor(max_workers=5)

# In-memory store for tracking async job statuses
job_status_store: Dict[str, Dict[str, Any]] = {}

# Pydantic Schemas for Requests
class EmployeeSchema(BaseModel):
    pn: str
    name: str
    role: str

class PredictRequest(BaseModel):
    issue_key: Optional[str] = None
    ac_text: str
    title: str
    parent_sp: float
    members: List[EmployeeSchema]
    selected_role: Optional[str] = "all"
    parent_type: Optional[str] = None
    is_epic: Optional[bool] = False
    stories: Optional[List[Dict[str, Any]]] = []
    # List of existing subtask summaries (titles) from Jira.
    # When provided, the AI will only generate subtasks that cover AC items
    # not already handled by existing subtasks (gap-fill mode).
    existing_subtask_summaries: Optional[List[str]] = []


class EstimateSPRequest(BaseModel):
    subtasks: List[Dict[str, Any]]

class MetricSaveRequest(BaseModel):
    epic_key: str
    parent_key: str
    total_story_points: float
    subtasks_count: int
    assignee_names: str

# Endpoints API

@router.get("/health", tags=["System Health"])
def health_check():
    """
    Verify backend status.
    """
    return {
        "status": "active",
        "message": "Backend aman.!"
    }

def _run_async_prediction(job_id: str, req: PredictRequest):
    """Background task handler for async subtask generation and workload balancing."""
    try:
        job_status_store[job_id]["progress"] = "Fetching issue info from Jira..."
        
        # 1. Direct stories list provided (e.g. from Jira Cloud / Forge Bulk Epic)
        if req.stories and len(req.stories) > 0:
            def process_story_dict(s_dict):
                st_key = s_dict.get("key") or s_dict.get("issue_key") or req.issue_key
                st_summary = s_dict.get("summary") or s_dict.get("title") or ""
                st_desc = s_dict.get("ac_text") or s_dict.get("description") or st_summary
                st_sp = float(s_dict.get("parent_sp") or s_dict.get("story_points") or 3.0)
                st_existing = s_dict.get("existing_subtask_summaries") or s_dict.get("existing_subtasks") or []
                st_ptype = s_dict.get("parent_type") or "Story"
                
                subs = generate_subtasks_uc.execute(
                    summary=st_summary,
                    description=st_desc,
                    parent_sp=st_sp,
                    existing_subtasks=st_existing,
                    issue_key=st_key,
                )
                for sub in subs:
                    sub.parent_key = st_key
                    sub.parent_summary = st_summary
                    sub.parent_type = st_ptype
                return subs

            nested_results = list(executor.map(process_story_dict, req.stories))
            all_generated = [sub for sub_list in nested_results for sub in sub_list]

        else:
            # Check if issue_key or title is a Single Issue or Epic
            lookup_key = req.issue_key or req.title
            issues = []
            try:
                single = jira_client.get_single_issue(lookup_key)
                if single and single.issue_type.lower() == "epic":
                    issues = jira_client.get_epic_issues(single.key)
                elif single:
                    issues = [single]
                else:
                    issues = jira_client.get_epic_issues(lookup_key)
            except Exception as err:
                print(f"Warning: Jira issue lookup skipped for '{lookup_key}': {err}")
                issues = []

            if not issues:
                # Fallback to direct text input
                jira_existing = list(jira_client.get_existing_subtask_summaries(req.issue_key)) if req.issue_key else []
                combined_existing = list(set(jira_existing + (req.existing_subtask_summaries or [])))
                subtask_objs = generate_subtasks_uc.execute(
                    summary=req.title,
                    description=req.ac_text,
                    parent_sp=req.parent_sp,
                    existing_subtasks=combined_existing,
                    issue_key=req.issue_key,
                )
                for sub in subtask_objs:
                    sub.parent_key = req.issue_key
                    sub.parent_summary = req.title
                    sub.parent_type = req.parent_type
                all_generated = subtask_objs
            else:
                job_status_store[job_id]["progress"] = f"Generating subtasks with AI ({len(issues)} stories)..."
                
                def process_story(story_item):
                    desc = story_item.description or req.ac_text or story_item.summary
                    jira_existing = list(jira_client.get_existing_subtask_summaries(story_item.key))
                    extra_from_req = req.existing_subtask_summaries or []
                    combined_existing = list(set(jira_existing + extra_from_req))
                    subs = generate_subtasks_uc.execute(
                        summary=story_item.summary,
                        description=desc,
                        parent_sp=story_item.story_points,
                        existing_subtasks=combined_existing,
                        issue_key=story_item.key,
                    )
                    for sub in subs:
                        sub.parent_key = story_item.key
                        sub.parent_summary = story_item.summary
                        sub.parent_type = story_item.issue_type
                    return subs

                nested_results = list(executor.map(process_story, issues))
                all_generated = [sub for sub_list in nested_results for sub in sub_list]

        if req.selected_role and req.selected_role.lower() != "all":
            target_role = req.selected_role.lower()
            all_generated = [s for s in all_generated if s.role == target_role]

        job_status_store[job_id]["progress"] = "Balancing workload across team..."
        emp_entities = [Employee(pn=e.pn, name=e.name, role=e.role) for e in req.members]
        balanced_result = balance_workload_uc.execute(emp_entities, all_generated)

        job_status_store[job_id] = {
            "status": "completed",
            "progress": "Subtask generation & balancing complete 100%",
            "results": balanced_result
        }
    except Exception as e:
        job_status_store[job_id] = {
            "status": "failed",
            "progress": "Failed",
            "error": str(e)
        }

@router.post("/predict-async", tags=["Subtask Generation"])
def predict_subtasks_async(req: PredictRequest, background_tasks: BackgroundTasks):
    """
    Asynchronously generates subtasks in background.
    Returns HTTP 202 Accepted in <100ms to eliminate Atlassian Forge 25s timeout risk.
    """
    job_id = f"job-{uuid.uuid4().hex[:8]}"
    job_status_store[job_id] = {
        "status": "processing",
        "progress": "Queued for processing...",
        "results": None
    }
    background_tasks.add_task(_run_async_prediction, job_id, req)
    return {
        "status": "accepted",
        "job_id": job_id,
        "message": "Subtask generation started in background."
    }

@router.get("/job-status/{job_id}", tags=["Subtask Generation"])
def get_job_status(job_id: str):
    """
    Polls the progress status of an async subtask generation job.
    """
    job_info = job_status_store.get(job_id)
    if not job_info:
        raise HTTPException(status_code=404, detail=f"Job ID '{job_id}' not found.")
    return job_info

@router.get("/epicInfo", tags=["Jira Integration"])
def get_epic_info(ticket: str):
    """
    Fetches all issues under an Epic and returns a dynamic summary of issue counts and statuses.
    """
    try:
        issues = jira_client.get_epic_issues(ticket)
        if not issues:
            return {
                "status": "success",
                "epic_key": ticket,
                "total_issues": 0,
                "issue_counts": {},
                "status_counts": {},
                "issues": []
            }
            
        # Group and count issue types and statuses dynamically
        counts = {}
        status_counts = {}
        for issue in issues:
            itype = issue.issue_type.title()
            counts[itype] = counts.get(itype, 0) + 1
            
            istatus = issue.status.title()
            status_counts[istatus] = status_counts.get(istatus, 0) + 1
            
        return {
            "status": "success",
            "epic_key": ticket,
            "total_issues": len(issues),
            "issue_counts": counts,
            "status_counts": status_counts,
            "issues": [
                {
                    "issue_key": issue.key,
                    "summary": issue.summary,
                    "story_points": issue.story_points,
                    "description": issue.description,
                    "issue_type": issue.issue_type,
                    "status": issue.status
                }
                for issue in issues
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch Epic info: {str(e)}")



@router.post("/predict", tags=["Subtask Generation"])
def predict_subtasks(req: PredictRequest):
    """
    Enhanced endpoint: Auto-detects Epic or Single Issue/AC text, 
    executes subtask generation in parallel (2 workers), and balances workload.
    """
    try:
        # 1. Parse employee list schema into Employee entities, fallback to Members.xlsx if dummy or empty
        dummy_names = {"Developer Backend", "Developer Frontend", "QA Engineer"}
        emp_entities = [
            Employee(pn=emp.pn, name=emp.name, role=emp.role)
            for emp in req.members
            if emp.name not in dummy_names
        ]
        if not emp_entities and os.path.exists("Members.xlsx"):
            try:
                with open("Members.xlsx", "rb") as f:
                    emp_entities = excel_parser.parse_employees(f.read())
            except Exception as e:
                print(f"Warning: Failed to load Members.xlsx in predict: {e}")

        if not emp_entities:
            emp_entities = [
                Employee(pn=emp.pn, name=emp.name, role=emp.role)
                for emp in req.members
            ]

        # Build mapping of employee names to their mapped roles (e.g. 'surya' -> 'mobile')
        emp_role_map = {}
        for emp in emp_entities:
            if emp.name:
                emp_role_map[emp.name.strip().lower()] = emp.role.strip().lower()

        # 2. Direct stories list provided (e.g. from Jira Cloud / Forge Bulk Epic)
        if req.stories and len(req.stories) > 0:
            def process_story_dict(s_dict):
                st_key = s_dict.get("key") or s_dict.get("issue_key") or req.issue_key
                st_summary = s_dict.get("summary") or s_dict.get("title") or ""
                st_desc = s_dict.get("ac_text") or s_dict.get("description") or st_summary
                st_sp = float(s_dict.get("parent_sp") or s_dict.get("story_points") or 3.0)
                st_existing = s_dict.get("existing_subtask_summaries") or s_dict.get("existing_subtasks") or []
                st_ptype = s_dict.get("parent_type") or "Story"
                st_assignee = s_dict.get("assignee") or s_dict.get("owner") or ""
                st_assignee_role = emp_role_map.get(st_assignee.strip().lower(), "")
                
                subs = generate_subtasks_uc.execute(
                    summary=st_summary,
                    description=st_desc,
                    parent_sp=st_sp,
                    existing_subtasks=st_existing,
                    issue_key=st_key,
                    assignee=st_assignee,
                    assignee_role=st_assignee_role,
                )
                for sub in subs:
                    sub.parent_key = st_key
                    sub.parent_summary = st_summary
                    sub.parent_type = st_ptype
                return subs

            nested_results = list(executor.map(process_story_dict, req.stories))
            all_generated = [sub for sub_list in nested_results for sub in sub_list]

        else:
            # 3. If direct AC text and title are provided in payload (from Forge UI), process directly without redundant Jira API roundtrips
            if req.title and req.ac_text and not req.is_epic:
                combined_existing = req.existing_subtask_summaries or []
                req_assignee = getattr(req, "assignee", "") or ""
                req_assignee_role = emp_role_map.get(req_assignee.strip().lower(), "")
                subtask_objs = generate_subtasks_uc.execute(
                    summary=req.title,
                    description=req.ac_text,
                    parent_sp=req.parent_sp,
                    existing_subtasks=combined_existing,
                    issue_key=req.issue_key,
                    assignee=req_assignee,
                    assignee_role=req_assignee_role,
                )
                for sub in subtask_objs:
                    sub.parent_key = req.issue_key
                    sub.parent_summary = req.title
                    sub.parent_type = req.parent_type
                all_generated = subtask_objs
            else:
                # Fallback to Jira lookup if text was omitted
                lookup_key = req.issue_key or req.title
                issues = []
                try:
                    single = jira_client.get_single_issue(lookup_key)
                    if single and single.issue_type.lower() == "epic":
                        issues = jira_client.get_epic_issues(single.key)
                    elif single:
                        issues = [single]
                    else:
                        issues = jira_client.get_epic_issues(lookup_key)
                except Exception as err:
                    print(f"Warning: Jira issue lookup skipped for '{lookup_key}': {err}")
                    issues = []

                if not issues:
                    combined_existing = req.existing_subtask_summaries or []
                    req_assignee = getattr(req, "assignee", "") or ""
                    req_assignee_role = emp_role_map.get(req_assignee.strip().lower(), "")
                    subtask_objs = generate_subtasks_uc.execute(
                        summary=req.title,
                        description=req.ac_text,
                        parent_sp=req.parent_sp,
                        existing_subtasks=combined_existing,
                        issue_key=req.issue_key,
                        assignee=req_assignee,
                        assignee_role=req_assignee_role,
                    )
                    for sub in subtask_objs:
                        sub.parent_key = req.issue_key
                        sub.parent_summary = req.title
                        sub.parent_type = req.parent_type
                    all_generated = subtask_objs
                else:
                    # Process all child stories using controlled parallel workers (2 workers max).
                    def process_story(story_item):
                        desc = story_item.description or req.ac_text or story_item.summary
                        jira_existing = list(jira_client.get_existing_subtask_summaries(story_item.key))
                        extra_from_req = req.existing_subtask_summaries or []
                        combined_existing = list(set(jira_existing + extra_from_req))
                        st_assignee = getattr(story_item, "assignee", "") or getattr(story_item, "owner", "") or ""
                        st_assignee_role = emp_role_map.get(st_assignee.strip().lower(), "")
                        subs = generate_subtasks_uc.execute(
                            summary=story_item.summary,
                            description=desc,
                            parent_sp=story_item.story_points,
                            existing_subtasks=combined_existing,
                            issue_key=story_item.key,
                            assignee=st_assignee,
                            assignee_role=st_assignee_role,
                        )
                        for sub in subs:
                            sub.parent_key = story_item.key
                            sub.parent_summary = story_item.summary
                            sub.parent_type = story_item.issue_type
                        return subs

                    nested_results = list(executor.map(process_story, issues))
                    all_generated = [sub for sub_list in nested_results for sub in sub_list]

        # 4. Filter by role if requested
        if req.selected_role and req.selected_role.lower() != "all":
            target_role = req.selected_role.lower()
            all_generated = [s for s in all_generated if s.role == target_role]
        # 5. Run load balancer use case
        balanced_result = balance_workload_uc.execute(emp_entities, all_generated)
        
        return {
            "status": "success",
            "results": balanced_result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")

@router.post("/predictFromExcel", tags=["Subtask Generation"])
async def predict_from_excel(
    members_file: UploadFile = File(...),
    stories_file: UploadFile = File(...),
    selected_role: Optional[str] = Form("all")
):
    """
    Parses active members and stories from uploaded Excel sheets,
    generates subtasks using RAG/Gemini, and returns balanced assignments.
    """
    try:
        # 1. Parse members Excel
        members_content = await members_file.read()
        employees = excel_parser.parse_employees(members_content)
        if not employees:
            raise ValueError("Employee list in Excel is empty.")
            
        # 2. Parse target stories Excel
        stories_content = await stories_file.read()
        target_stories = excel_parser.parse_stories(stories_content)
        if not target_stories:
            raise ValueError("Stories list in Excel is empty.")
            
        all_generated_subtasks = []
        
        # 3. Generate subtasks for each story in Excel
        for story in target_stories:
            desc = story.description or story.summary
            subtask_objs = generate_subtasks_uc.execute(
                summary=story.summary,
                description=desc,
                parent_sp=story.story_points
            )
            for sub in subtask_objs:
                sub.parent_key = story.key
                sub.parent_summary = story.summary
                all_generated_subtasks.append(sub)

                
        # 4. Filter by role if requested
        if selected_role and selected_role.lower() != "all":
            target_role = selected_role.lower()
            all_generated_subtasks = [s for s in all_generated_subtasks if s.role == target_role]
            
        # 5. Run load balancer
        balanced_result = balance_workload_uc.execute(employees, all_generated_subtasks)
        
        # 6. Lookup Jira account IDs
        for assignment in balanced_result["assignments"]:
            emp_data = assignment["employee"]
            if assignment["assigned_subtasks"]:
                jira_id = jira_client.find_user_by_name(emp_data["name"], pn=emp_data.get("pn"))
                emp_data["jira_account_id"] = jira_id
                
        return {
            "status": "success",
            "results": balanced_result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction from Excel failed: {str(e)}")

@router.post("/estimateStoryPoints", tags=["Subtask Generation"])
def estimate_story_points(req: EstimateSPRequest):
    """
    Calculates total story points of active subtasks.
    """
    try:
        total_sp = sum(float(sub.get("story_points", 0.0)) for sub in req.subtasks)
        return {
            "status": "success",
            "total_story_points": total_sp
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to calculate story points: {str(e)}")

@router.post("/metrics/save", tags=["Metrics Reporting"])
def save_metrics(req: MetricSaveRequest):
    """
    Saves performance metrics to database.
    """
    try:
        metric_repo.save_metric(
            epic_key=req.epic_key,
            parent_key=req.parent_key,
            total_story_points=req.total_story_points,
            subtasks_count=req.subtasks_count,
            assignee_names=req.assignee_names
        )
        return {
            "status": "success",
            "message": "Metric log saved successfully."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save metrics: {str(e)}")

@router.get("/metrics/summary", tags=["Metrics Reporting"])
def get_metrics():
    """
    Fetches statistical reports summary.
    """
    try:
        summary = metric_repo.get_summary()
        return {
            "status": "success",
            "summary": summary
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch metrics summary: {str(e)}")

@router.post("/ingestHistorical", tags=["RAG Ingestion"])
async def ingest_historical(file: UploadFile = File(...)):
    """
    Ingests Excel story/subtask reference documents.
    """
    try:
        contents = await file.read()
        stories = excel_parser.parse_historical_import(contents)
        
        success_count = 0
        for story in stories:
            text_to_embed = f"{story.summary}\n{story.description}"
            embedding = llm_client.get_text_embedding(text_to_embed)
            story_repo.save(story, embedding)
            success_count += 1
            
        return {
            "status": "success",
            "message": f"Successfully ingested {success_count} historical stories.",
            "stories_processed": success_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")
