import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Gemini Configuration
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    GENERATION_MODEL: str = "gemini-2.5-flash"



    JIRA_URL: str = os.getenv("JIRA_URL", "https://your-domain.atlassian.net")
    JIRA_EMAIL: str = os.getenv("JIRA_EMAIL", "")
    JIRA_API_TOKEN: str = os.getenv("JIRA_API_TOKEN", "")
    JIRA_STORY_POINTS_FIELD: str = os.getenv(
        "JIRA_STORY_POINTS_FIELD", "customfield_10016"
    )

    # Database
    # SQLite DB stored relative to the project root directory
    DATABASE_PATH: str = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "rag_store.db")
    )

    # Role Mappings
    ROLE_MAPPINGS: dict = {
        "backend": "Backend",
        "frontend": "Frontend",
        "qa": "QA Engineer",
        "sad": "SAD",
        "po": "Product Owner",
        "project officer": "Project Officer",
    }

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
