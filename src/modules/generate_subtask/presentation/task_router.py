from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

# Shared & Core Domain Imports
from modules.reporting.domain.models import Employee
from modules.reporting.domain.balancer_service import WorkloadBalancerService

# Infrastructure & Repository Imports
from modules.generate_subtask.infrastructure.sqlite_story_repository import SqliteStoryRepository, SqliteMetricRepository
from modules.generate_subtask.infrastructure.gemini_llm_client import GeminiLlmClient
from modules.generate_subtask.infrastructure.jira_rest_client import JiraRestClient
from modules.reporting.infrastructure.pandas_excel_parser import PandasExcelParser

# Application Use Case Imports
from modules.generate_subtask.application.generate_subtasks_use_case import GenerateSubtasksUseCase
from modules.reporting.application.balance_workload_use_case import BalanceWorkloadUseCase

router = APIRouter(prefix="/api/v1")

# Instantiate infrastructure and application services (Dependency Injection)
story_repo = SqliteStoryRepository()
metric_repo = SqliteMetricRepository()
llm_client = GeminiLlmClient()
jira_client = JiraRestClient()
excel_parser = PandasExcelParser()

generate_subtasks_uc = GenerateSubtasksUseCase(story_repo, llm_client)
balance_workload_uc = BalanceWorkloadUseCase(WorkloadBalancerService())

# Pydantic Schemas for Requests
class EmployeeSchema(BaseModel):
    pn: str
    name: str
    role: str

class PredictRequest(BaseModel):
    ac_text: str
    title: str
    parent_sp: float
    members: List[EmployeeSchema]
    selected_role: Optional[str] = "all"
    parent_type: Optional[str] = None


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
    Generates and load-balances subtasks for a given AC.
    """
    try:
        # 1. Generate subtasks from use case (incorporates SQLite RAG + Gemini)
        subtask_objs = generate_subtasks_uc.execute(
            summary=req.title,
            description=req.ac_text,
            parent_sp=req.parent_sp
        )
        for sub in subtask_objs:
            sub.parent_type = req.parent_type

        
        if req.selected_role and req.selected_role.lower() != "all":
            target_role = req.selected_role.lower()
            subtask_objs = [s for s in subtask_objs if s.role == target_role]
            
        # 3. Parse employee list schema into Employee entities
        emp_entities = [
            Employee(pn=emp.pn, name=emp.name, role=emp.role)
            for emp in req.members
        ]
        
        # 4. Run load balancer use case
        balanced_result = balance_workload_uc.execute(emp_entities, subtask_objs)
        
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
