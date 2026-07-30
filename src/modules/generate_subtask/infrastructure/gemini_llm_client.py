import requests
import json
from typing import List, Dict, Any
from shared.config import settings
from modules.generate_subtask.domain.models import Subtask
from modules.generate_subtask.domain.interfaces import ILlmClient


class GeminiLlmClient(ILlmClient):
    """
    HTTP client for Google Gemini API.
    """

    def get_text_embedding(self, text: str) -> List[float]:
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not configured.")

        url = f"https://generativelanguage.googleapis.com/v1/models/{settings.EMBEDDING_MODEL}:embedContent?key={settings.GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        cleaned_text = str(text)[:4000]

        payload = {
            "model": f"models/{settings.EMBEDDING_MODEL}",
            "content": {"parts": [{"text": cleaned_text}]},
        }

        response = requests.post(url, json=payload, headers=headers, timeout=15)
        if response.status_code != 200:
            raise Exception(
                f"Gemini Embedding API error ({response.status_code}): {response.text}"
            )

        res_data = response.json()
        if "embedding" not in res_data or "values" not in res_data["embedding"]:
            raise Exception(f"Invalid response format from embedding API: {res_data}")

        return res_data["embedding"]["values"]

    def generate_subtasks_from_ac(
        self,
        summary: str,
        description: str,
        parent_sp: float,
        examples: List[Dict[str, Any]],
        db_patterns: Dict[str, Any] = None,
        mode: str = "free",
        max_subtasks: int = None,
    ) -> List[Subtask]:
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not configured.")

        # Strict AC Vocabulary prompt for BRI Scrum Master subtask decomposition
        prompt = (
            "BRI Scrum Master: Decompose User Story into subtasks strictly following the AC content.\n\n"
            "STRICT RULES:\n"
            "1. Prefixes: BE -, WEB -, Mobile -\n"
            "2. DO NOT invent specific endpoint paths (e.g. '/v1/createXxx'), service class names, or migration scripts unless those exact terms are explicitly written in the AC. NEVER use URL-style paths in subtask names. Use the AC's exact wording for BE tasks.\n"
            "3. Use the exact feature names, table names, and wording from the AC.\n"
            "4. Banned words in summary: Ensure/Handle/Verify/Validate/Make sure/Check that/schema\n"
            "5. SP: Fibonacci numbers only (0, 0.5, 1, 2, 3, 5, 8, 13)\n"
            "6. No generic review tasks (e.g. 'Review code')\n"
            "7. BE TASKS: If AC mentions backend services/functions → use the AC's exact wording (e.g. AC says 'Create service insert/update data proyek' → subtask is 'BE - Create service insert update data proyek'). If AC has NO BE detail → generate exactly 1 subtask: 'BE - Design Spec API for <story_name>'. NEVER invent endpoint paths, migration scripts, or class names not in the AC.\n"
            "8. SMART CONSOLIDATION: Group items by LOGICAL section, NOT by AC bullet points. Rules:\n"
            "   - All fields/inputs that belong to the SAME logical section or form → 1 subtask. E.g., all date, currency, payment method, and value fields within a 'Project Details' form → 'WEB - Create Project Details section'\n"
            "   - Each distinct popup/modal → 1 subtask\n"
            "   - Each standalone section (KUBL, TKBI, Approver, etc.) → 1 subtask\n"
            "   - Action buttons of the same page → 1 subtask\n"
            "   - NEVER create a subtask per individual field, date input, dropdown, or radio button.\n\n"
        )

        # Inject real naming patterns from DB (dynamic, no hard-coding)
        if db_patterns and (db_patterns.get("be") or db_patterns.get("web")):
            prompt += "STYLE PATTERNS FROM YOUR PROJECT:\n"
            if db_patterns.get("be"):
                prompt += "BE: " + " | ".join(db_patterns["be"]) + "\n"
            if db_patterns.get("web"):
                prompt += "WEB: " + " | ".join(db_patterns["web"]) + "\n"
            prompt += "\n"
        else:
            prompt += "BE: 'BE - Enhance X' | 'BE - Add X' | 'BE - Create X'\nWEB: 'WEB - Create component X' | 'WEB - Create Page X' | 'WEB - Mapping data X'\n\n"

        if examples:
            prompt += "REFERENCES (style only):\n"
            for eg in examples:
                ac_snippet = str(eg.get("description", ""))[:300]
                prompt += f"[{eg['summary']}] AC: {ac_snippet}\nSubtasks: "
                prompt += ", ".join(
                    f"{sub['summary']}({sub['role'][0].upper()})" for sub in eg["subtasks"]
                ) + "\n"
            prompt += "\n"

        prompt += (
            f"STORY: {summary} (SP:{parent_sp})\n"
            f"AC:\n{description}\n\n"
        )

        # Strict mode: enforce exact subtask count based on SP
        if mode == "strict" and max_subtasks:
            prompt += (
                f"STRICT MODE: You MUST generate EXACTLY {max_subtasks} subtask(s). No more, no less.\n"
                f"From all requirements in the AC, pick the {max_subtasks} most crucial task(s).\n"
                f"Priority order: core UI component > core backend > supporting tasks.\n"
                f"The JSON array MUST contain exactly {max_subtasks} item(s).\n\n"
            )

        # Free mode: cover all distinct sections/popups but consolidate fields within same section
        if mode != "strict":
            prompt += (
                "FREE MODE: Cover ALL distinct sections, popups, modals, and BE tasks from the AC. "
                "Apply SMART CONSOLIDATION: combine all fields/columns/buttons within the same section into 1 subtask. "
                "Do NOT skip major features, but do NOT create a separate subtask per individual field or column.\n\n"
            )

        prompt += '{"subtasks":[{"summary":"...","role":"backend|frontend|mobile","story_points":1.0}]}'

        # Multi-Model Automatic Fallback Chain with valid Google API model names
        fallback_models = [settings.GENERATION_MODEL, "gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-2.5-flash-lite", "gemini-flash-latest"]
        # Deduplicate while preserving order
        candidate_models = list(dict.fromkeys(fallback_models))

        last_exception = None
        text_content = None
        res_data = None

        import time

        for model_name in candidate_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={settings.GEMINI_API_KEY}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.0,
                }
            }

            try:
                response = requests.post(url, json=payload, headers=headers, timeout=15)
                if response.status_code == 200:
                    res_data = response.json()
                    candidate = res_data["candidates"][0]
                    text_content = candidate["content"]["parts"][0]["text"].strip()
                    break
                elif response.status_code in [429, 403]:
                    print(f"Quota limit for [{model_name}] (HTTP {response.status_code}). Waiting 8s & auto-switching model...")
                    last_exception = Exception(f"Gemini API limit (HTTP {response.status_code}): {response.text}")
                    time.sleep(8)
                    continue
                else:
                    last_exception = Exception(f"Gemini generation API failed ({response.status_code}): {response.text}")
                    continue
            except Exception as e:
                last_exception = e
                continue

        if not text_content:
            raise Exception(f"All fallback models failed. Last error: {str(last_exception)}")

        try:
            # Clean up potential markdown formatting block: ```json ... ```
            if text_content.startswith("```"):
                lines = text_content.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].startswith("```"):
                    lines = lines[:-1]
                text_content = "\n".join(lines).strip()

            result = json.loads(text_content)

            def _closest_fibonacci(val) -> float:
                fibs = [0.0, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 13.0, 21.0]
                try:
                    val_float = float(val)
                    return min(fibs, key=lambda x: abs(x - val_float))
                except (ValueError, TypeError):
                    return 1.0

            subtasks = []
            role_prefix_map = {
                "backend": "BE",
                "frontend": "WEB",
                "mobile": "Mobile",
            }

            subtasks_list = (
                result.get("subtasks", [])
                if isinstance(result, dict)
                else (result if isinstance(result, list) else [])
            )

            import re

            for sub in subtasks_list:
                raw_sp = sub.get("story_points", 1.0)
                summary_text = str(sub.get("summary", "")).strip()

                # Filter out generic noise tasks (Review Existing Code, Review Design Figma, Review MAB, etc.)
                summary_lower = summary_text.lower()
                if re.search(r'\breview\b.*(code|design|figma|existing|mab)', summary_lower) or summary_lower.startswith("review "):
                    continue
                
                # Normalize legacy FE - or WEBAPP - or fe - to WEB -
                summary_text = re.sub(r'^(fe|webapp)\s*-\s*', 'WEB - ', summary_text, flags=re.IGNORECASE)

                role_key = str(sub.get("role", "backend")).lower().strip()
                prefix = role_prefix_map.get(role_key, "BE")

                # Check if summary already starts with a known prefix tag or RAG template tag
                already_has_prefix = any(
                    summary_text.lower().startswith(p) or p in summary_text.lower()
                    for p in ["be -", "fe -", "qa -", "mobile", "[mobile", "app", "prescreening app", "pemrakarsa", "pemutus", "web -", "wlb -", "[web", "service -", "[mcs", "[las", "risk register", "risk management", "security review", "code review", "review", "audit", "compliance"]
                )

                if not already_has_prefix:
                    summary_text = f"{prefix} - {summary_text}"

                subtasks.append(
                    Subtask(
                        summary=summary_text,
                        description=sub.get("description", summary_text),
                        role=role_key,
                        story_points=_closest_fibonacci(raw_sp),
                    )
                )
            return subtasks

        except (KeyError, IndexError, ValueError) as e:
            raise Exception(
                f"Failed to parse structured output from Gemini: {res_data}. Error: {e}"
            )
