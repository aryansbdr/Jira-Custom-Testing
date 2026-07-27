import json
from typing import List, Dict, Any
from shared.database import get_db_connection
from modules.generate_subtask.domain.models import Story
from modules.generate_subtask.domain.interfaces import (
    IStoryRepository,
    IMetricRepository,
)


class SqliteStoryRepository(IStoryRepository):
    """
    SQLite implementation of IStoryRepository with mapping to new domain models.
    """

    def save(self, story: Story, embedding: List[float]) -> None:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # Map Story domain attributes to new SQLite column names
            cursor.execute(
                """
                INSERT OR REPLACE INTO historical_issues (issue_key, issue_type, issue_title, story_points, issue_description, embedding)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    story.key,
                    story.issue_type,
                    story.summary,
                    story.story_points,
                    story.description,
                    json.dumps(embedding),
                ),
            )

            cursor.execute(
                "SELECT id FROM historical_issues WHERE issue_key = ?", (story.key,)
            )

            issue_id = cursor.fetchone()[0]

            cursor.execute(
                "DELETE FROM historical_subtasks WHERE issue_id = ?", (issue_id,)
            )

            for sub in story.subtasks:
                cursor.execute(
                    """
                    INSERT INTO historical_subtasks (issue_id, title, role, story_points)
                    VALUES (?, ?, ?, ?)
                """,
                    (
                        issue_id,
                        sub.summary,
                        sub.role,
                        sub.story_points,
                    ),
                )
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def get_all(self) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, issue_key, issue_type, issue_title, story_points, issue_description, embedding FROM historical_issues"
        )
        rows = cursor.fetchall()

        issues = []
        for row in rows:
            cursor.execute(
                "SELECT title, role, story_points FROM historical_subtasks WHERE issue_id = ?",
                (row["id"],),
            )
            sub_rows = cursor.fetchall()

            # Map SQLite columns to Domain Model schema format
            subtasks = []
            for sub in sub_rows:
                subtasks.append(
                    {
                        "summary": sub["title"],
                        "description": "",
                        "role": sub["role"],
                        "story_points": sub["story_points"],
                    }
                )

            issues.append(
                {
                    "id": row["id"],
                    "issue_key": row["issue_key"],
                    "issue_type": row["issue_type"],
                    "summary": row["issue_title"],
                    "story_points": row["story_points"],
                    "description": row["issue_description"],
                    "embedding": json.loads(row["embedding"]),
                    "subtasks": subtasks,
                }
            )
        conn.close()
        return issues


class SqliteMetricRepository(IMetricRepository):
    """
    SQLite implementation of IMetricRepository.
    """

    def save_metric(
        self,
        epic_key: str,
        parent_key: str,
        total_story_points: float,
        subtasks_count: int,
        assignee_names: str,
    ) -> None:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO reports (epic_key, parent_key, total_story_points, subtasks_count, assignee_names)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    epic_key,
                    parent_key,
                    total_story_points,
                    subtasks_count,
                    assignee_names,
                ),
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def get_summary(self) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Retrieve all metrics logs to parse assignees
        cursor.execute("""
            SELECT timestamp, parent_key, total_story_points, subtasks_count, assignee_names 
            FROM reports
            ORDER BY timestamp DESC
        """)
        rows = cursor.fetchall()
        conn.close()

        # Aggregate by (date, member_name) in memory
        aggregation = {}

        for row in rows:
            timestamp = row["timestamp"]
            date_str = timestamp.split(" ")[0] if " " in timestamp else timestamp[:10]
            parent_key = row["parent_key"]
            total_sp = float(row["total_story_points"])

            assignee_str = row["assignee_names"] or ""
            names = [n.strip() for n in assignee_str.split(",") if n.strip()]
            if not names:
                continue

            # Distribute story points equally among active subtask assignees
            sp_per_subtask = total_sp / len(names)

            for name in names:
                agg_key = (date_str, name)
                if agg_key not in aggregation:
                    aggregation[agg_key] = {
                        "date": date_str,
                        "member": name,
                        "stories": set(),
                        "subtasks_count": 0,
                        "total_sp": 0.0,
                    }
                aggregation[agg_key]["stories"].add(parent_key)
                aggregation[agg_key]["subtasks_count"] += 1
                aggregation[agg_key]["total_sp"] += sp_per_subtask

        result = []
        for agg_key, data in aggregation.items():
            result.append(
                {
                    "date": data["date"],
                    "member": data["member"],
                    "stories_count": len(data["stories"]),
                    "subtasks_count": data["subtasks_count"],
                    "total_sp": round(data["total_sp"], 1),
                }
            )

        # Sort by date descending, then member name ascending
        result.sort(key=lambda x: (x["date"], x["member"]), reverse=True)
        return result
