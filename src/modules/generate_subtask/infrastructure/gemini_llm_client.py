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

    def _get_api_keys(self) -> List[str]:
        raw = settings.GEMINI_API_KEY or ""
        keys = [k.strip() for k in raw.split(",") if k.strip()]
        if not keys:
            raise ValueError("GEMINI_API_KEY is not configured.")
        return keys

    def get_text_embedding(self, text: str) -> List[float]:
        api_keys = self._get_api_keys()
        cleaned_text = str(text)[:4000]

        last_err = None
        for key in api_keys:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.EMBEDDING_MODEL}:embedContent?key={key}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "model": f"models/{settings.EMBEDDING_MODEL}",
                "content": {"parts": [{"text": cleaned_text}]},
            }

            try:
                response = requests.post(url, json=payload, headers=headers, timeout=5)
                if response.status_code == 200:
                    res_data = response.json()
                    if "embedding" in res_data and "values" in res_data["embedding"]:
                        return res_data["embedding"]["values"]
                last_err = f"Gemini Embedding API error ({response.status_code}): {response.text}"
            except Exception as e:
                last_err = str(e)

        raise Exception(f"All API keys failed for embedding: {last_err}")

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
            "Role: BRI Scrum Master. Decompose User Story into subtasks strictly using AC terms.\n\n"
            "RULES:\n"
            "1. Prefix: 'BE -', 'WEB -', or 'Mobile -'\n"
            "2. Task Titles: Use exact AC wording for BOTH BE and WEB/Mobile subtasks. If AC mentions 'Modul' or 'Komponen', output 'WEB - Create Component <name>'. If AC specifies 'Enhance...', output 'WEB - Enhance...'. If AC specifies 'Nambah/Add/Create...', output 'WEB - Create...'. If explicit 'To do list' or backend endpoints are provided in AC, use those exact items for BE subtasks. NEVER create 'BE -' tasks from document chapter/section/tab names (e.g. do NOT create 'BE - 1 Analisa Operasional Bisnis', 'BE - Bab 5' — section headers belong to WEB/UI forms, NOT backend). If no BE details in AC, output exactly 1 subtask: 'BE - Design Spec API for <story_name>'. NEVER invent URL paths (/v1/...), class names, or migration scripts.\n"
            "3. ROLE SEPARATION (FE vs BE): NEVER merge Frontend (WEB/Mobile) and Backend (BE) into one subtask. If an AC has both UI display (e.g. 'Menampilkan kolom pada monitoring / page / tabel') and Backend/Database changes (e.g. 'tambah kolom mst_* / endpoint / query'), they MUST ALWAYS be split into separate subtasks: 1 for 'WEB - ...' and 1 for 'BE - ...'.\n"
            "4. CONSOLIDATION: Group by LOGICAL section/component/modal/page within the SAME role. "
            "Merge sibling items that share the same action verb and component type into ONE subtask using 'and' or '/'. "
            "Example: 'Create Sub Menu for Prakarsa Baru' + 'Create Sub Menu for Prakarsa Perubahan Syarat' → 'Create Sub Menu for Prakarsa Baru and Perubahan Syarat'. "
            "Only split into separate subtasks if items are functionally different (different component type, role, or significantly different complexity). "
            "NEVER create separate subtasks per field or bullet point.\n"
            "5. Banned words: Ensure/Handle/Verify/Validate/Make sure/Check that/schema/Review code\n"
            "6. PRESERVE DOMAIN TERMS: Do NOT translate Indonesian business/domain terms to English. Keep words like 'debitur', 'prakarsa', 'pemrakarsa', 'pemutus', 'pencairan', 'korporasi', 'perubahan syarat', 'pengajuan', 'fasilitas', 'termin', 'rekening' exactly as written in the AC.\n"
            "7. SP: Fibonacci only (0, 0.5, 1, 2, 3, 5, 8, 13)\n\n"
        )

        # --- Detect Mobile app context from summary + description ---
        # Determines whether subtasks should use [Mobile Pemrakarsa] or [Mobile Pemutus] prefix.
        # This matches the naming convention observed in the RAG database (rag_store.db):
        #   - Stories about 'pemrakarsa' / 'prakarsa' flow → [Mobile Pemrakarsa] prefix
        #   - Stories about 'pemutus' / 'putusan' flow   → [Mobile Pemutus] prefix
        # Mobile context requires explicit mobile app keywords (mobile, brispot, android, ios)
        # Business terms like 'prakarsa', 'pemrakarsa', 'pemutus' alone do NOT imply mobile as they exist on Web too.
        has_mobile_keyword = any(
            kw in combined_text for kw in ["mobile", "brispot", "aplikasi mobile", "mobile app", "app mobile", "brispot app", "android", "ios"]
        )

        is_mobile_pemrakarsa = has_mobile_keyword and (
            "pemrakarsa" in combined_text
            or "prakarsa" in combined_text
            or "prescreening" in combined_text
        )
        is_mobile_pemutus = has_mobile_keyword and (
            "pemutus" in combined_text
            or "putusan kredit" in combined_text
            or "rekomendasi kredit" in combined_text
        )

        # Inject specific Mobile prefix instruction into prompt so AI names subtasks correctly
        # NOTE: Pemrakarsa/Pemutus prefix normalization is handled entirely by post-processing code below.
        # No prompt injection needed for mobile context — this saves prompt tokens while keeping results accurate.


        # Inject real naming patterns from DB
        if db_patterns and (db_patterns.get("be") or db_patterns.get("web")):
            be_p = " | ".join(db_patterns["be"]) if db_patterns.get("be") else ""
            web_p = " | ".join(db_patterns["web"]) if db_patterns.get("web") else ""
            prompt += f"PATTERNS: BE: {be_p} | WEB: {web_p}\n\n"

        if examples:
            prompt += "EXAMPLES:\n"
            for eg in examples:
                subs = ", ".join(f"{s['summary']}" for s in eg["subtasks"])
                prompt += f"[{eg['summary']}] -> {subs}\n"
            prompt += "\n"

        safe_summary = (summary or "").strip()
        # Pass full AC description (up to 20,000 chars) to ensure no sections, modals, or BE details are missed
        raw_desc = (description or "").strip()
        safe_desc = raw_desc[:20000] + ("..." if len(raw_desc) > 20000 else "")
        prompt += f"STORY: {safe_summary} (SP:{parent_sp})\nAC:\n{safe_desc}\n\n"

        if mode == "strict" and max_subtasks:
            prompt += f"STRICT MODE: Output EXACTLY {max_subtasks} subtask(s).\n\n"
        else:
            prompt += "FREE MODE: Cover all sections/modals/BE tasks with section-level consolidation.\n\n"

        prompt += 'Output JSON: {"subtasks":[{"summary":"...","role":"backend|frontend|mobile","story_points":1.0}]}'

        # Multi-Model Automatic Fallback Chain (prioritizing 1.5-flash & 2.0-flash for maximum free tier quota & speed)
        fallback_models = ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash-lite"]
        candidate_models = list(dict.fromkeys(fallback_models))
        last_exception = None
        text_content = None
        res_data = None

        import time

        api_keys = self._get_api_keys()

        # Fast Multi-pass retry loop with 3s backoff to respect Forge 25s timeout limit
        for attempt in range(2):
            for api_key in api_keys:
                for model_name in candidate_models:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                    headers = {"Content-Type": "application/json"}
                    gen_config = {
                        "temperature": 0.0,
                        "maxOutputTokens": 1500,
                        "responseMimeType": "application/json"
                    }
                    if "2.5" in model_name:
                        gen_config["thinkingConfig"] = {"thinkingBudget": 0}

                    payload = {
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": gen_config
                    }

                    try:
                        response = requests.post(url, json=payload, headers=headers, timeout=6)
                        if response.status_code == 200:
                            res_data = response.json()
                            candidate = res_data["candidates"][0]
                            text_content = candidate["content"]["parts"][0]["text"].strip()
                            break
                        elif response.status_code in [429, 403]:
                            last_exception = Exception(f"Gemini API limit (HTTP {response.status_code}): {response.text}")
                            continue
                        else:
                            last_exception = Exception(f"Gemini generation API failed ({response.status_code}): {response.text}")
                            continue
                    except Exception as e:
                        last_exception = e
                        continue

                if text_content:
                    break

            if text_content:
                break

            # If rate limited across all keys and models, short 3s backoff before 2nd attempt
            if attempt < 1 and "429" in str(last_exception):
                print("\n[Gemini API] Quota limit 429. Fast retry in 3s...")
                time.sleep(3)

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
                # Strip trailing role markers like (M), (B), (F) copied from prompt examples
                summary_text = re.sub(r'\s*\([MBFmbf]\)$', '', summary_text).strip()
                role_key = str(sub.get("role", "backend")).lower().strip()

                # Filter out generic noise tasks (Review Existing Code, Review Design Figma, etc.)
                summary_lower = summary_text.lower()
                if re.search(r'\breview\b.*(code|design|figma|existing|mab)', summary_lower) or summary_lower.startswith("review "):
                    continue

                # --- Pemrakarsa / Pemutus context: special prefix rules ---
                # In this mobile app context:
                #   - 'frontend' / WEB subtasks are NOT needed — skip them entirely
                #   - 'backend' subtasks get [MCS Prakarsa] or [MCS Pemutus] prefix
                #   - 'mobile' subtasks get [Mobile Pemrakarsa] or [Mobile Pemutus] prefix
                is_mobile_context = is_mobile_pemrakarsa or is_mobile_pemutus
                mcs_label = "Prakarsa" if (is_mobile_pemrakarsa and not is_mobile_pemutus) else "Pemutus"

                if is_mobile_context:
                    # Skip WEB/frontend subtasks entirely in this context
                    if role_key == "frontend":
                        continue

                    if role_key == "backend":
                        # Strip any existing [MCS ...] bracket prefix first
                        summary_text = re.sub(r'^\[MCS[^\]]*\]\s*', '', summary_text, flags=re.IGNORECASE).strip()
                        # Strip any unbracketed prefix with or without dash: BE -, MCS Prakarsa -, MCS Pemutus, etc.
                        summary_text = re.sub(r'^(BE|MCS(\s+Prakarsa|\s+Pemutus)?)\s*(-|\s+)?', '', summary_text, flags=re.IGNORECASE).strip()
                        # Apply correct [MCS Prakarsa] or [MCS Pemutus] prefix
                        summary_text = f"[MCS {mcs_label}] {summary_text}"

                    elif role_key == "mobile":
                        # Strip any existing [Mobile ...] bracket prefix first
                        summary_text = re.sub(r'^\[Mobile[^\]]*\]\s*', '', summary_text, flags=re.IGNORECASE).strip()
                        # Strip any unbracketed prefix with or without dash: Mobile Pemrakarsa -, Mobile Pemrakarsa, Mobile -, etc.
                        summary_text = re.sub(r'^Mobile(\s+Pemrakarsa|\s+Pemutus)?\s*(-|\s+)?', '', summary_text, flags=re.IGNORECASE).strip()
                        # Apply the contextually correct bracketed prefix
                        if is_mobile_pemrakarsa and not is_mobile_pemutus:
                            summary_text = f"[Mobile Pemrakarsa] {summary_text}"
                        else:
                            summary_text = f"[Mobile Pemutus] {summary_text}"

                else:
                    # --- Standard (non-mobile-context) prefix normalization ---

                    # Normalize legacy FE - or WEBAPP - or fe - to WEB -
                    summary_text = re.sub(r'^(fe|webapp)\s*-\s*', 'WEB - ', summary_text, flags=re.IGNORECASE)

                    prefix = role_prefix_map.get(role_key, "BE")

                    # Normalize Mobile subtask prefix for generic context (no pemrakarsa/pemutus)
                    if role_key == "mobile":
                        summary_text = re.sub(r'^Mobile\s*-\s*', '', summary_text, flags=re.IGNORECASE)
                        summary_text = re.sub(r'^\[Mobile[^\]]*\]\s*', '', summary_text).strip()
                        summary_text = f"Mobile - {summary_text}"

                    # Check if summary already starts with a known prefix tag or RAG template tag
                    already_has_prefix = any(
                        summary_text.lower().startswith(p) or p in summary_text.lower()
                        for p in ["be -", "fe -", "qa -", "mobile", "[mobile", "app", "prescreening app",
                                  "pemrakarsa", "pemutus", "web -", "wlb -", "[web", "service -",
                                  "[mcs", "[las", "risk register", "risk management",
                                  "security review", "code review", "review", "audit", "compliance"]
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

    def fill_gaps_from_ac_raw(
        self,
        system_prompt: str,
        user_content: str,
        summary: str,
    ) -> List["Subtask"]:
        """
        Thin Gemini wrapper specifically for gap-fill calls.
        Takes pre-built system_prompt + user_content (from LlmClient.fill_gaps_from_ac)
        and calls Gemini to get any missing subtasks not covered by the cloned set.
        Returns a list of Subtask objects (may be empty if nothing is missing).
        """
        import re
        from modules.generate_subtask.domain.models import Subtask

        # Combine system + user into a single Gemini-style prompt
        combined_prompt = f"{system_prompt}\n\n{user_content}"

        fallback_models = ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
        api_keys = self._get_api_keys()
        last_exception = None
        text_content = None

        for api_key in api_keys:
            for model_name in fallback_models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                headers = {"Content-Type": "application/json"}
                gen_config = {
                    "temperature": 0.0,
                    "maxOutputTokens": 800,
                    "responseMimeType": "application/json",
                }
                if "2.5" in model_name:
                    gen_config["thinkingConfig"] = {"thinkingBudget": 0}

                payload = {
                    "contents": [{"parts": [{"text": combined_prompt}]}],
                    "generationConfig": gen_config,
                }
                try:
                    response = requests.post(url, json=payload, headers=headers, timeout=10)
                    if response.status_code == 200:
                        res_data = response.json()
                        text_content = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
                        break
                    elif response.status_code in [429, 403]:
                        last_exception = Exception(f"Gemini quota limit ({response.status_code})")
                        continue
                    else:
                        last_exception = Exception(f"Gemini gap fill failed ({response.status_code})")
                except Exception as e:
                    last_exception = e
            if text_content:
                break

        if not text_content:
            raise Exception(f"Gemini gap fill: all models failed. Last: {last_exception}")

        # Parse JSON response into Subtask objects
        parsed = json.loads(text_content)
        subtasks = []
        for sub in parsed.get("subtasks", []):
            summary_text = sub.get("summary", "").strip()
            # Clean Jira markup symbols ({*}, {*}, *}, and single asterisks *) from title
            summary_text = re.sub(r'\{\*?\}|\{\*|\*\}|\*', '', summary_text).strip()
            role_val = str(sub.get("role", "backend")).lower()
            raw_sp = sub.get("story_points", 1.0)

            # Clean all leading role prefixes (BE -, WEB -, FE -, WEBAPP -, Mobile -, etc.) completely
            clean_body = re.sub(r'^((be|web|fe|webapp|mobile)\s*-\s*)+', '', summary_text, flags=re.IGNORECASE).strip()
            prefix = "WEB - " if ("frontend" in role_val or "web" in role_val) else "Mobile - " if "mobile" in role_val else "BE - "
            summary_text = f"{prefix}{clean_body}"

            role_key = (
                "frontend" if ("frontend" in role_val or "web" in role_val)
                else "mobile" if "mobile" in role_val
                else "backend"
            )

            # Fibonacci SP
            fib = [0, 0.5, 1, 2, 3, 5, 8, 13]
            sp = min(fib, key=lambda x: abs(x - float(raw_sp)))

            subtasks.append(Subtask(
                summary=summary_text,
                description="",
                role=role_key,
                story_points=sp,
            ))
        return subtasks
