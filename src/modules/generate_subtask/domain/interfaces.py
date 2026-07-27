from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from modules.generate_subtask.domain.models import Story, Subtask


class IStoryRepository(ABC):
    """
    Interface for persisting historical stories (RAG references).
    """

    @abstractmethod
    def save(self, story: Story, embedding: List[float]) -> None:
        pass

    @abstractmethod
    def get_all(self) -> List[Dict[str, Any]]:
        pass


class IMetricRepository(ABC):
    """
    Interface for performance logging and reporting statistics.
    """

    @abstractmethod
    def save_metric(
        self,
        epic_key: str,
        parent_key: str,
        total_story_points: float,
        subtasks_count: int,
        assignee_names: str,
    ) -> None:
        pass

    @abstractmethod
    def get_summary(self) -> List[Dict[str, Any]]:
        pass


class IJiraClient(ABC):
    """
    Interface for Atlassian Jira HTTP communications.
    """

    @abstractmethod
    def get_epic_issues(self, epic_key: str) -> List[Story]:
        pass

    @abstractmethod
    def find_user_by_name(self, display_name: str) -> Optional[str]:
        pass

    @abstractmethod
    def create_subtask_issue(
        self,
        parent_key: str,
        summary: str,
        description: str,
        story_points: float,
        assignee_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        pass


class ILlmClient(ABC):
    """
    Interface for LLM (Gemini) communications.
    """

    @abstractmethod
    def get_text_embedding(self, text: str) -> List[float]:
        pass

    @abstractmethod
    def generate_subtasks_from_ac(
        self,
        summary: str,
        description: str,
        parent_sp: float,
        examples: List[Dict[str, Any]],
    ) -> List[Subtask]:
        pass
