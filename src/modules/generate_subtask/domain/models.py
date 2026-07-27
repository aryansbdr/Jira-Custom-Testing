from typing import List, Dict, Any, Optional


class Subtask:
    """
    Value Object representing a subtask to be created in Jira.
    """

    def __init__(
        self,
        summary: str,
        description: str,
        role: str,
        story_points: float,
        parent_key: Optional[str] = None,
        parent_summary: Optional[str] = None,
        parent_type: Optional[str] = None,
    ):
        self.summary = summary.strip()
        self.description = description.strip()
        self.role = role.lower().strip()
        self.story_points = story_points
        self.parent_key = parent_key
        self.parent_summary = parent_summary
        self.parent_type = parent_type

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary,
            "description": self.description,
            "role": self.role,
            "story_points": self.story_points,
            "parent_key": self.parent_key,
            "parent_summary": self.parent_summary,
            "parent_type": self.parent_type,
        }


class Story:
    """
    Aggregate Root representing a parent Jira User Story/Task.
    """

    def __init__(
        self,
        key: str,
        summary: str,
        story_points: float,
        description: str,
        issue_type: str = "Story",
        status: str = "To Do",
        subtasks: Optional[List[Subtask]] = None,
    ):
        self.key = key.strip()
        self.summary = summary.strip()
        self.story_points = story_points
        self.description = description.strip()
        self.issue_type = issue_type.strip()
        self.status = status.strip()
        self.subtasks = subtasks if subtasks is not None else []

    def add_subtask(self, subtask: Subtask):
        subtask.parent_key = self.key
        subtask.parent_summary = self.summary
        self.subtasks.append(subtask)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "summary": self.summary,
            "story_points": self.story_points,
            "description": self.description,
            "issue_type": self.issue_type,
            "status": self.status,
            "subtasks": [sub.to_dict() for sub in self.subtasks],
        }
