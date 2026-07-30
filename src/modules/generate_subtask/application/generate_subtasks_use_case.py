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

    # SP → max subtask count mapping for Strict Mode
    SP_SUBTASK_LIMIT = {
        0.0: 1, 0.5: 1, 1.0: 1, 2.0: 1,
        3.0: 2,
        5.0: 3,
        8.0: 3,
        13.0: 4,
    }

    def execute(
        self, summary: str, description: str, parent_sp: float, mode: str = "free"
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

        # Ultra-Strict 1-to-1 Exact Match Cloning ("Plek Ketiplek Sama" Judul & AC)
        def _normalize_str(s: str) -> str:
            return re.sub(r'\s+', ' ', str(s or '')).strip().lower()

        is_exact_title_match = (
            top_match and _normalize_str(summary) == _normalize_str(top_match["summary"])
        )
        is_exact_desc_match = (
            top_match and _normalize_str(description) == _normalize_str(top_match["description"])
        )

        is_plek_ketiplek_match = is_exact_title_match and is_exact_desc_match

        if top_match and is_plek_ketiplek_match:
            cloned_subtasks = []
            for sub in top_match["subtasks"]:
                summary_text = str(sub["summary"]).strip()
                summary_lower = summary_text.lower()
                
                # Filter out generic noise tasks (Review Existing Code, Review Design Figma, Review MAB, etc.)
                if re.search(r'\breview\b.*(code|design|figma|existing|mab)', summary_lower) or summary_lower.startswith("review "):
                    continue

                # Normalize legacy FE - or WEBAPP - to WEB -
                summary_text = re.sub(r'^(fe|webapp)\s*-\s*', 'WEB - ', summary_text, flags=re.IGNORECASE)

                cloned_subtasks.append(
                    Subtask(
                        summary=summary_text,
                        description="",
                        role=sub["role"],
                        story_points=sub["story_points"],
                    )
                )
            if cloned_subtasks:
                return cloned_subtasks
            # All cloned subtasks were filtered as noise — fallback to AI synthesis
            print("   [INFO] Semua subtask dari DB adalah noise, fallback ke Gemini AI...")

        selected_references = candidate_stories[:5]

        # Extract real naming patterns from DB to guide AI style dynamically
        db_naming_patterns = self._extract_naming_patterns(candidate_stories[:10])

        # Resolve target subtask count for strict mode from SP table
        target_subtasks = None
        if mode == "strict":
            # Find closest SP key in table
            sp_key = min(self.SP_SUBTASK_LIMIT.keys(), key=lambda k: abs(k - parent_sp))
            target_subtasks = self.SP_SUBTASK_LIMIT[sp_key]

        # 4. Generate structured subtasks using Gemini LLM Client
        generated_subtasks = self.llm_client.generate_subtasks_from_ac(
            summary=summary,
            description=description,
            parent_sp=parent_sp,
            examples=selected_references,
            db_patterns=db_naming_patterns,
            mode=mode,
            max_subtasks=target_subtasks,
        )

        # Enforce exact count for strict mode — trim to exactly target_subtasks
        if mode == "strict" and target_subtasks:
            generated_subtasks = generated_subtasks[:target_subtasks]

        # Post-process: sanitize BE subtask names and enforce 'Enhance endpoint' rule when AC has no BE details
        ac_text = (summary + " " + (description or "")).lower()
        be_keywords = ["backend", "be ", "database", "db ", "tabel database", "kolom", "endpoint", "api", "query", "migration", "payload", "controller"]
        has_be_in_ac = any(kw in ac_text for kw in be_keywords)

        filtered_subtasks = []
        be_generic_added = False

        for sub in generated_subtasks:
            sub_role = sub.role.lower()
            is_be = sub_role in ["be", "backend"]

            if is_be and not has_be_in_ac:
                # AC has no BE detail — only allow 1 generic 'Enhance endpoint' subtask; drop all invented specifics
                if not be_generic_added:
                    sub.summary = f"BE - Design Spec API for {summary}"
                    sub.story_points = 2.0
                    filtered_subtasks.append(sub)
                    be_generic_added = True
                # skip any additional invented BE subtasks
                continue

            filtered_subtasks.append(sub)

        return filtered_subtasks if filtered_subtasks else generated_subtasks

    def _extract_naming_patterns(self, stories: list) -> dict:
        """Extract real naming patterns from historical subtasks to use as dynamic style guide."""
        be_patterns = set()
        web_patterns = set()

        noise_pattern = re.compile(
            r'\b(review|ensure|handle|verify|validate|check that|make sure)\b',
            re.IGNORECASE
        )

        for story in stories:
            for sub in story.get("subtasks", []):
                title = str(sub.get("summary", "")).strip()
                if not title or noise_pattern.search(title):
                    continue
                title_lower = title.lower()
                # Extract first 6 words as the pattern template
                words = title.split()
                pattern = " ".join(words[:6]) if len(words) >= 3 else title
                if title_lower.startswith("be -") or title_lower.startswith("be -"):
                    be_patterns.add(pattern)
                elif title_lower.startswith("web -") or title_lower.startswith("fe -"):
                    web_patterns.add(re.sub(r'^fe\s*-', 'WEB -', pattern, flags=re.IGNORECASE))

        return {
            "be": sorted(be_patterns)[:8],
            "web": sorted(web_patterns)[:8],
        }
