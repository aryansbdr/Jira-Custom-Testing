import math
import re
from typing import List
from modules.generate_subtask.domain.models import Subtask
from modules.generate_subtask.domain.interfaces import IStoryRepository, ILlmClient


class GenerateSubtasksUseCase:
    """
    Application use case for fetching context, querying RAG, and generating subtasks.
    """

    def __init__(self, story_repo: IStoryRepository, llm_client: ILlmClient):
        self.story_repo = story_repo
        self.llm_client = llm_client

    def _cosine_similarity(self, vector_a: List[float], vector_b: List[float]) -> float:
        if len(vector_a) != len(vector_b):
            return 0.0
        dot_product = sum(x * y for x, y in zip(vector_a, vector_b))
        norm_a = math.sqrt(sum(x * x for x in vector_a))
        norm_b = math.sqrt(sum(y * y for y in vector_b))
        if norm_a * norm_b == 0.0:
            return 0.0
        return dot_product / (norm_a * norm_b)

    def execute(
        self, summary: str, description: str, parent_sp: float
    ) -> List[Subtask]:
        summary_lower = summary.lower()

        # Exception Rule: Exclude Test & Deployment tickets from subtask generation as requested
        skip_test_keywords = [
            "test plan",
            "test execution",
            "deployment test",
            "automation & performance test",
            "performance test",
            "automation test",
            "test deployment",
        ]
        if any(kw in summary_lower for kw in skip_test_keywords):
            return []

        # Hybrid Rule-Based Pattern Bypass for static operational tasks (Instant, 100% consistent, 0 quota)
        if "risk management" in summary_lower or "risk register" in summary_lower:
            clean_title = summary.replace("Risk Management -", "").replace("Risk Management", "").strip(" -")
            return [
                Subtask(
                    summary=f"Risk Register - {clean_title}",
                    description=f"Eksekusi pembuatan & pendaftaran Risk Register untuk {clean_title}",
                    role="backend",
                    story_points=1.0,
                )
            ]
        elif "security review" in summary_lower:
            clean_title = summary.replace("[REVIEW]", "").replace("[Review]", "").replace("Security Review -", "").replace("Security Review", "").strip(" -")
            full_text = f"{summary} {description}".lower()
            
            # Inspect Endpoint URLs, HTTP Methods, and Action Keywords
            has_write_or_inject = bool(re.search(r'\b(post|put|patch|delete|insert|create|update|save|submit|inject|pembentukan|penyesuaian|tambah|edit|hapus)\b', full_text)) or any(ep in full_text for ep in ["/insert", "/create", "/update", "/save", "/submit", "/delete", "/inject", "/add", "/post"])
            has_read_or_inquiry = bool(re.search(r'\b(get|inquiry|fetch|monitoring|dashboard|view|list|search|report|laporan|detail)\b', full_text)) or any(ep in full_text for ep in ["/inquiry", "/get", "/fetch", "/search", "/list", "/detail", "/find", "/view", "/monitoring"])

            if has_write_or_inject and not (has_read_or_inquiry and "inquiry" in clean_title.lower()):
                testing_subtask_title = f"Pentest - {clean_title}"
                testing_desc = f"Eksekusi Penetration Testing & Vulnerability Assessment untuk {clean_title}"
            elif has_read_or_inquiry:
                testing_subtask_title = f"DAST - {clean_title}"
                testing_desc = f"Eksekusi Dynamic Application Security Testing (DAST) untuk {clean_title}"
            else:
                testing_subtask_title = f"Pentest - {clean_title}"
                testing_desc = f"Eksekusi Penetration Testing & Vulnerability Assessment untuk {clean_title}"

            return [
                Subtask(
                    summary=f"Design Security Review - {clean_title}",
                    description=f"Eksekusi Design Security Review untuk {clean_title}",
                    role="backend",
                    story_points=1.0,
                ),
                Subtask(
                    summary=f"Code Review - {clean_title}",
                    description=f"Eksekusi Code Review & Static Analysis untuk {clean_title}",
                    role="backend",
                    story_points=1.0,
                ),
                Subtask(
                    summary=testing_subtask_title,
                    description=testing_desc,
                    role="backend",
                    story_points=1.0,
                ),
            ]

        # 1. Generate query embedding combining summary & description for accurate RAG match
        search_text = f"{summary}\n{description}".strip()
        target_embedding = self.llm_client.get_text_embedding(search_text)

        # 2. Retrieve all historical stories from SQLite RAG database
        historical_stories = self.story_repo.get_all()

        # 3. Calculate similarities to find closest reference matches
        candidate_stories = []
        for story in historical_stories:
            similarity_score = self._cosine_similarity(
                target_embedding, story["embedding"]
            )
            reference_candidate = story.copy()
            reference_candidate["similarity"] = similarity_score
            candidate_stories.append(reference_candidate)

        # Sort descending by similarity score
        candidate_stories.sort(key=lambda x: x["similarity"], reverse=True)
        top_match = candidate_stories[0] if candidate_stories else None

        # Ultra-Strict RAG Direct Cloning (Only for exact same title or >= 95% identical content)
        is_exact_title_match = (
            top_match and summary.strip().lower() == top_match["summary"].strip().lower()
        )
        is_near_identical = top_match and top_match["similarity"] >= 0.95

        if top_match and (is_exact_title_match or is_near_identical):
            cloned_subtasks = []
            for sub in top_match["subtasks"]:
                cloned_subtasks.append(
                    Subtask(
                        summary=sub["summary"],
                        description="",
                        role=sub["role"],
                        story_points=sub["story_points"],
                    )
                )
            if cloned_subtasks:
                return cloned_subtasks

        selected_references = candidate_stories[:2]

        # 4. Generate structured subtasks using Gemini LLM Client
        generated_subtasks = self.llm_client.generate_subtasks_from_ac(
            summary=summary,
            description=description,
            parent_sp=parent_sp,
            examples=selected_references,
        )

        return generated_subtasks
