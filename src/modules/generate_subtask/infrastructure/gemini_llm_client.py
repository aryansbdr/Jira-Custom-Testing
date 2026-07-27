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
    ) -> List[Subtask]:
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not configured.")

        # Streamlined high-performance prompt with BRI naming conventions
        prompt = (
            "You are an expert Agile Scrum Master for BRI Bank project. Break down the new User Story into subtasks strictly mimicking the Historical References and Acceptance Criteria (AC).\n\n"
            "STRICT BRI NAMING PATTERN CONVENTIONS:\n"
            "1. Allowed Roles: ONLY 'backend', 'frontend' (uses WEB prefix), or 'mobile'.\n"
            "2. Frontend (WEB) Naming Style:\n"
            "   - 'WEB - Creating <component_name> component' (e.g. 'WEB - Creating pencarian nasabah component')\n"
            "   - 'WEB - Handling <feature_name> with API' (e.g. 'WEB - Handling pencarian nasabah with API')\n"
            "   - 'WEB - Creating pagination for <component_name>'\n"
            "3. Backend (BE) Naming Style:\n"
            "   - 'BE - Create Endpoint <ServiceName>' (e.g. 'BE - Create Endpoint InquiryListDataDebiturKorporasi')\n"
            "   - 'BE - Enhance /<endpoint_path>' (e.g. 'BE - Enhance /mcseksternal/inquiryVcfByCif')\n"
            "   - 'BE - Sync <sync_job_name>'\n"
            "4. If Description contains a 'Todo:' block, extract those items first as foundational subtasks.\n"
            "5. Subtask Story Points MUST choose from Fibonacci numbers: 0, 0.5, 1, 2, 3, 5, 8, 13.\n\n"
        )

        if examples:
            prompt += "### HISTORICAL REFERENCES (Mimic Style & Scope):\n"
            for i, eg in enumerate(examples):
                prompt += f"\n--- Reference {i + 1} ---\n"
                prompt += f"Parent Title: {eg['summary']}\n"
                prompt += f"Parent SP: {eg['story_points']}\n"
                prompt += f"Parent AC:\n{eg['description']}\n"
                prompt += "Subtasks:\n"
                for sub in eg["subtasks"]:
                    prompt += f" - [Role: {sub['role']}] {sub['summary']} ({sub['story_points']} SP)\n"
            prompt += "\n=====================================\n\n"

        prompt += (
            "### NEW USER STORY TO BREAK DOWN:\n"
            f"Title: {summary}\n"
            f"Parent SP: {parent_sp}\n"
            f"Description & AC:\n{description}\n\n"
            'Output STRICTLY a raw JSON object with key "subtasks": '
            '{"subtasks": [{"summary": "...", "description": "...", "role": "backend|frontend|mobile", "story_points": 1.0}]}. '
            "Do NOT wrap in ```json or add any extra text.\n"
        )

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
            payload = {"contents": [{"parts": [{"text": prompt}]}]}

            try:
                response = requests.post(url, json=payload, headers=headers, timeout=30)
                if response.status_code == 200:
                    res_data = response.json()
                    candidate = res_data["candidates"][0]
                    text_content = candidate["content"]["parts"][0]["text"].strip()
                    break
                elif response.status_code in [429, 403]:
                    print(f"Quota limit for [{model_name}] (HTTP {response.status_code}). Waiting 2s & auto-switching model...")
                    last_exception = Exception(f"Gemini API limit (HTTP {response.status_code}): {response.text}")
                    time.sleep(2)
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
                # Remove first line (e.g. ```json) and last line (```)
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

            for sub in subtasks_list:
                raw_sp = sub.get("story_points", 1.0)
                summary_text = str(sub.get("summary", "")).strip()
                
                # Normalize legacy FE - or WEBAPP - to WEB -
                if summary_text.upper().startswith("FE - "):
                    summary_text = "WEB - " + summary_text[5:]
                elif summary_text.upper().startswith("WEBAPP - "):
                    summary_text = "WEB - " + summary_text[9:]

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
