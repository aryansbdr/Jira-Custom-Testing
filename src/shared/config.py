import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Gemini Configuration
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    GENERATION_MODEL: str = "gemini-2.5-flash"

    # OpenAI Configuration
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini")



    JIRA_URL: str = os.getenv("JIRA_URL", "https://your-domain.atlassian.net")
    JIRA_EMAIL: str = os.getenv("JIRA_EMAIL", "")
    JIRA_API_TOKEN: str = os.getenv("JIRA_API_TOKEN", "")
    JIRA_STORY_POINTS_FIELD: str = os.getenv(
        "JIRA_STORY_POINTS_FIELD", "customfield_10016"
    )

    # Telegram & MS Teams Configuration
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
    TEAMS_WEBHOOK_URL: str = os.getenv("TEAMS_WEBHOOK_URL", "")

    # Database
    # SQLite DB stored relative to the project root directory
    DATABASE_PATH: str = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "rag_store.db")
    )

    # Role Mappings (Core active BRI roles: BE, WEB, Mobile)
    ROLE_MAPPINGS: dict = {
        "backend": "BE",
        "frontend": "WEB",
        "mobile": "Mobile",
    }

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
