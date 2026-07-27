from fastapi import APIRouter, UploadFile, File, HTTPException
from modules.reporting.infrastructure.pandas_excel_parser import PandasExcelParser
from modules.reporting.application.parse_members_use_case import ParseMembersUseCase

router = APIRouter(prefix="/api/v1")

# Instantiate parser & use case
excel_parser = PandasExcelParser()
parse_members_uc = ParseMembersUseCase(excel_parser)


@router.post("/parse-members", tags=["Team Workload Management"])
async def parse_members(file: UploadFile = File(...)):
    """
    Parses employee Excel list and returns JSON.
    """
    try:
        contents = await file.read()
        employees = parse_members_uc.execute(contents)

        # Serialize entities to dict for output
        return {"status": "success", "employees": [emp.to_dict() for emp in employees]}
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to parse employee Excel: {str(e)}"
        )
