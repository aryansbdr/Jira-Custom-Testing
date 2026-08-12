from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Shared Imports
from shared.database import init_db

# Presentation Routers
from modules.generate_subtask.presentation.task_router import router as task_router
from modules.reporting.presentation.team_router import router as team_router
from modules.reporting.presentation.reporting_router import router as reporting_router
from modules.notification.presentation.notification_router import router as notification_router
from modules.notification.infrastructure.notification_scheduler import notification_scheduler

app = FastAPI(
    title="Backend Jira dan Workload Balance",
    description="API contract for jira automation PKL-BRI",
    version="2.0.0"
)

# Enable CORS for Forge custom UI requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(task_router)
app.include_router(team_router)
app.include_router(reporting_router)
app.include_router(notification_router)


@app.on_event("startup")
def startup_event():
    print("[Main] Initializing SQLite database...")
    init_db()
    
    # Start background notification scheduler (08:45 WIB & 16:30 WIB)
    print("[Main] Starting automated notification scheduler...")
    notification_scheduler.start()


@app.on_event("shutdown")
def shutdown_event():
    print("[Main] Stopping automated notification scheduler...")
    notification_scheduler.shutdown()


if __name__ == "__main__":
    print("Starting FastAPI server in development mode")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
