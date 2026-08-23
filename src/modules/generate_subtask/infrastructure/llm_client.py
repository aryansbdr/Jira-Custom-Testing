import requests
import json
import re
import time
from typing import List, Dict, Any
from shared.config import settings
from modules.generate_subtask.domain.models import Subtask
from modules.generate_subtask.domain.interfaces import ILlmClient


def _closest_fibonacci(val: float) -> float:
    fibs = [0.0, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 13.0]
    try:
        f_val = float(val)
    except (ValueError, TypeError):
        return 1.0
    return min(fibs, key=lambda x: abs(x - f_val))


class LlmClient(ILlmClient):

    _SYSTEM_PROMPT = (
        "Role: BRI Scrum Master. Decompose User Story into granular subtasks strictly matching AC and RAG dataset patterns.\n\n"
        "RULES:\n"
        "1. ROLE ASSIGNMENT & BACKEND / FRONTEND DECOMPOSITION:\n"
        "   - Assign role 'frontend' (or 'mobile' for mobile context) for UI screens, layouts, input fields, cascading dropdowns, camera/gallery UI, and client-side form validations.\n"
        "   - Assign role 'backend' for data queries, filter processing, business logic calculations, database storage, and external integrations.\n"
        "   - If a feature requires backend processing (e.g. data filtering, search query, calculations) but NO specific endpoint path is written in the AC/Todo, create a functional BE task like 'Implement Query Filtering by <Criteria>' or 'Handle Data Filtering for <Feature>'. NEVER fabricate/invent imaginary URL paths (e.g. do NOT guess '/v1/fake_endpoint'). Only use 'Create Endpoint <path>' if the exact path or endpoint name is explicitly provided in the text.\n"
        "2. NAMING CONVENTIONS & DETAIL PRESERVATION:\n"
        "   - Use standard technical verbs: 'Create Layout', 'Create Component <Name>', 'Create Dropdown <Name>', 'Create Datepicker <Name>', 'Implement <Logic Name> Logic', 'Implement Query Filtering by <Criteria>', 'Save <Data> to <Table>'.\n"
        "   - PRESERVE SPECIFIC OPTIONS / VALUES: When the AC/Description explicitly lists options, choices, or values for dropdowns, radios, or badges (e.g. 'Draft, Review, Disetujui, Ditolak'), INCLUDE them in parentheses in the title, e.g. 'Create Dropdown for Status Pengajuan (Draft, Review, Disetujui, Ditolak)'.\n"
        "   - Preserve domain terms ('Debitur', 'PTK', 'Pengajuan Kredit', 'Risalah RKK', 'KUBL', 'Pencairan', 'MAB', etc.).\n"
        "3. CONSOLIDATION: Sibling fields in the same section may merge with 'and'/'/'. Merge button states (visible/disabled) into ONE single task with state validation.\n\n"
        'Output JSON (Clean titles without role prefix; role is "frontend", "backend", or "mobile"):\n'
        '{"subtasks":[{"summary":"Create Layout for Risalah RKK","role":"frontend","story_points":1.0},{"summary":"Create Dropdown for Status Pengajuan (Draft, Review, Disetujui, Ditolak)","role":"frontend","story_points":1.0},{"summary":"Save KUBL Data to content_data_kbli","role":"backend","story_points":1.0}]}\n\n'
    )

    def _get_gemini_api_keys(self) -> List[str]:
        raw = settings.GEMINI_API_KEY or ""
        return [k.strip() for k in raw.split(",") if k.strip()]

    def get_text_embedding(self, text: str) -> List[float]:
        cleaned_text = str(text)[:4000]

        # 1. Try Gemini Embedding first to match 3072-dim vectors stored in subtasks.db
        gemini_keys = self._get_gemini_api_keys()
        if gemini_keys:
            for key in gemini_keys:
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
                except Exception:
                    pass

        # 2. Fallback to OpenAI Embedding if Gemini fails or key not set
        if settings.OPENAI_API_KEY:
            try:
                url = "https://api.openai.com/v1/embeddings"
                headers = {
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY.strip()}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": "text-embedding-3-small",
                    "input": cleaned_text,
                }
                response = requests.post(url, json=payload, headers=headers, timeout=8)
                if response.status_code == 200:
                    return response.json()["data"][0]["embedding"]
            except Exception as e:
                print(f"[LLM Client] OpenAI Embedding failed: {e}")

        raise Exception("Failed to generate embedding with all configured providers.")

    def _clean_ac_text(self, text: str) -> str:
        """Sanitize and compress AC text to eliminate unnecessary tokens (HTML tags, wiki markup, excess whitespace)."""
        if not text:
            return ""
        # Remove HTML tags
        cleaned = re.sub(r'<[^>]+>', ' ', text)
        # Remove Jira wiki markup ({*}, {*}, *}, headers, panels, etc.)
        cleaned = re.sub(r'\{\*?\}|\{\*|\*\}|\{color:[^\}]*\}|\{panel:[^\}]*\}', '', cleaned)
        cleaned = re.sub(r'h[1-6]\.\s*', '', cleaned)
        # Normalize multiple spaces/newlines to single linebreaks
        cleaned = re.sub(r'[ \t]+', ' ', cleaned)
        cleaned = re.sub(r'\n\s*\n+', '\n', cleaned)
        return cleaned.strip()

  
    _MOBILE_CONTEXT_KEYWORDS = [
        "mobile",
        "mobile app",
        "brispot",
        "android",
        "ios",
        "aplikasi mobile",
        "ots",
        "prescreening",
        "camera brispot",
        "galeri brispot",
        "layout mobile",
        "activity android",
    ]

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
        # Use shared class-level prompt (same prompt for both generation and gap-fill)
        system_prompt = self._SYSTEM_PROMPT

        # Pre-check: does this story have any mobile context?
        # Used below to filter out hallucinated Mobile subtasks.
        combined_text = (summary + " " + (description or "")).lower()
        has_mobile_context = any(kw in combined_text for kw in self._MOBILE_CONTEXT_KEYWORDS)

        user_content = ""
        if db_patterns and (db_patterns.get("be") or db_patterns.get("web")):
            be_p = " | ".join(db_patterns["be"]) if db_patterns.get("be") else ""
            web_p = " | ".join(db_patterns["web"]) if db_patterns.get("web") else ""
            user_content += f"PATTERNS: BE: {be_p} | WEB: {web_p}\n\n"

        if examples:
            user_content += "EXAMPLES:\n"
            for eg in examples:
                subs = ", ".join(f"{s['summary']}" for s in eg.get("subtasks", []))
                user_content += f"[{eg.get('summary', '')}] -> {subs}\n"
            user_content += "\n"

        safe_summary = (summary or "").strip()
        cleaned_desc = self._clean_ac_text(description)
        safe_desc = cleaned_desc[:20000] + ("..." if len(cleaned_desc) > 20000 else "")
        user_content += f"STORY: {safe_summary} (SP:{parent_sp})\nAC:\n{safe_desc}\n\n"

        if mode == "strict" and max_subtasks:
            user_content += f"STRICT MODE: Output EXACTLY {max_subtasks} subtask(s).\n\n"
        else:
            user_content += "FREE MODE: Cover all sections/modals/BE tasks.\n\n"

        last_exception = None


        if settings.OPENAI_API_KEY and settings.LLM_PROVIDER.lower() in ["openai", "auto"]:
            try:
                url = "https://api.openai.com/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY.strip()}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": settings.OPENAI_MODEL or "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    "temperature": 0.0,
                    "seed": 42,
                    "response_format": {"type": "json_object"},
                    "max_tokens": 1500,
                }
                for attempt in range(2):
                    try:
                        response = requests.post(url, json=payload, headers=headers, timeout=20)
                        if response.status_code == 200:
                            res_data = response.json()
                            raw_text = res_data["choices"][0]["message"]["content"].strip()
                            parsed = json.loads(raw_text)
                            result = self._parse_subtasks(parsed, safe_summary, safe_desc)
                            # Strip hallucinated Mobile subtasks when the story has no mobile context
                            if not has_mobile_context:
                                result = [s for s in result if s.role != "mobile"]
                            return result
                        else:
                            last_exception = Exception(f"OpenAI API error ({response.status_code}): {response.text}")
                    except Exception as req_err:
                        last_exception = req_err
                        if attempt == 0:
                            time.sleep(1)
                            continue
                    print(f"\n[LLM Client] OpenAI failed ({response.status_code}). Trying Gemini...")
            except Exception as e:
                last_exception = e
                print(f"\n[LLM Client] OpenAI error: {e}. Trying Gemini...")

      
        gemini_keys = self._get_gemini_api_keys()
        if not gemini_keys and not settings.OPENAI_API_KEY:
            raise ValueError("Neither OPENAI_API_KEY nor GEMINI_API_KEY is configured.")

        fallback_models = ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash-lite"]
        candidate_models = list(dict.fromkeys(fallback_models))
        gemini_prompt = f"{system_prompt}\n\n{user_content}"

        for attempt in range(2):
            for api_key in gemini_keys:
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
                        "contents": [{"parts": [{"text": gemini_prompt}]}],
                        "generationConfig": gen_config
                    }

                    try:
                        response = requests.post(url, json=payload, headers=headers, timeout=6)
                        if response.status_code == 200:
                            res_data = response.json()
                            candidate = res_data["candidates"][0]
                            text_content = candidate["content"]["parts"][0]["text"].strip()
                            parsed = json.loads(text_content)
                            result = self._parse_subtasks(parsed, safe_summary, safe_desc)
                            # Strip hallucinated Mobile subtasks when the story has no mobile context
                            if not has_mobile_context:
                                result = [s for s in result if s.role != "mobile"]
                            return result
                        elif response.status_code in [429, 403]:
                            last_exception = Exception(f"Gemini API limit (HTTP {response.status_code}): {response.text}")
                            continue
                        else:
                            last_exception = Exception(f"Gemini API error ({response.status_code}): {response.text}")
                            continue
                    except Exception as e:
                        last_exception = e
                        continue

            if attempt < 1 and "429" in str(last_exception):
                print("\n[LLM Client] Gemini Quota limit 429. Fast retry in 3s...")
                time.sleep(3)

        raise Exception(f"All LLM providers failed. Last error: {str(last_exception)}")

 
    _BACKEND_OVERRIDE_KEYWORDS = [
        "migration", "database migration",
        "db schema", "tabel database", "kolom database",
        "repository", "controller",
        "stored procedure", "cekdata", "function general",
        "insert into", "select from",
    ]

    def _parse_subtasks(self, parsed: dict, safe_summary: str, safe_desc: str = "") -> List[Subtask]:
        subtasks = []
        combined_text = (safe_summary + " " + (safe_desc or "")).lower()
        has_web_or_corp = any(
            kw in combined_text
            for kw in ["korporasi", "mab", "web", "portal", "dashboard", "fe ", " fe", "ui", "tab ", "halaman", "browser"]
        )
        has_mobile_keyword = any(
            kw in combined_text
            for kw in [
                "mobile", "brispot", "android", "ios", "mantri", "aplikasi mobile", "mobile app",
                "hanya untuk mobile", "untuk mobile", "camera brispot", "galeri brispot", "ots"
            ]
        )
        has_mobile_story = has_mobile_keyword and not has_web_or_corp
        is_pemutus = has_mobile_story and "pemutus" in combined_text
        is_pemrakarsa = has_mobile_story and ("pemrakarsa" in combined_text or "prescreening" in combined_text)
        is_bracket_mobile = is_pemrakarsa or is_pemutus

        mobile_tag = "[Mobile Pemutus]" if is_pemutus else "[Mobile Pemrakarsa]"
        msc_tag = "[MSC Pemutus]" if is_pemutus else "[MSC Prakarsa]"

        for sub in parsed.get("subtasks", []):
            summary_text = sub.get("summary", "").strip()
            # Clean Jira markup symbols ({*}, {*}, *}, and single asterisks *) from title
            summary_text = re.sub(r'\{\*?\}|\{\*|\*\}|\*', '', summary_text).strip()
            role_val = str(sub.get("role", "backend")).lower()
            raw_sp = sub.get("story_points", 1.0)

            # Drop QA/Testing and SDLC boilerplate noise in code
            if role_val in ("qa", "tester", "testing") or re.search(r'(\bqa\b|\btesting\b|\buat\b|\banalyze requirements\b|\bpayload structure\b|\brequest validation\b|\bmap request payload\b|\bcode review\b|\bdesign review\b)', summary_text, flags=re.IGNORECASE):
                continue

            # Strip all leading role prefixes (BE -, WEB -, FE -, WEBAPP -, Mobile -, MSC -, MCS -, etc.)
            clean_body = re.sub(r'^((be|web|fe|webapp|mobile|msc|mcs|qa)\s*-\s*)+', '', summary_text, flags=re.IGNORECASE).strip()

            # Auto-standardize [MCS ...] to [MSC ...]
            if clean_body.upper().startswith("[MCS"):
                clean_body = re.sub(r'^\[MCS', '[MSC', clean_body, flags=re.IGNORECASE)

            # Determine role: respect AI role_val or bracket tag
            if clean_body.startswith("[MSC") or clean_body.startswith("MSC -") or clean_body.startswith("BE -") or role_val == "backend":
                role_key = "backend"
                clean_body_no_bracket = re.sub(r'^\[(MSC|MCS|BE)[^\]]*\]\s*', '', clean_body, flags=re.IGNORECASE).strip()
                if has_mobile_story:
                    final_summary = f"{msc_tag} {clean_body_no_bracket}" if is_bracket_mobile else f"MSC - {clean_body_no_bracket}"
                else:
                    final_summary = f"BE - {clean_body_no_bracket}"
            elif clean_body.startswith("[Mobile") or clean_body.startswith("MOBILE -") or role_val in ("mobile", "frontend", "fe", "web"):
                clean_body_no_bracket = re.sub(r'^\[(Mobile|WEB|FE)[^\]]*\]\s*', '', clean_body, flags=re.IGNORECASE).strip()
                if has_mobile_story or role_val == "mobile":
                    role_key = "mobile"
                    final_summary = f"{mobile_tag} {clean_body_no_bracket}" if is_bracket_mobile else f"MOBILE - {clean_body_no_bracket}"
                else:
                    role_key = "frontend"
                    final_summary = f"WEB - {clean_body_no_bracket}"
            else:
                role_key = "backend"
                if has_mobile_story:
                    final_summary = f"{msc_tag} {clean_body}" if is_bracket_mobile else f"MSC - {clean_body}"
                else:
                    final_summary = f"BE - {clean_body}"

            subtasks.append(
                Subtask(
                    summary=final_summary,
                    description=sub.get("description", final_summary),
                    role=role_key,
                    story_points=_closest_fibonacci(raw_sp),
                )
            )
        return subtasks

    def fill_gaps_from_ac(
        self,
        summary: str,
        description: str,
        cloned_subtasks: List[Subtask],
        db_patterns: Dict[str, Any] = None,
    ) -> List[Subtask]:
        """
        After cloning subtasks from the RAG dataset, ask the LLM to verify
        whether all items in the AC are already covered by the cloned list.
        If there are gaps, the LLM returns only the missing subtasks.
        This prevents the dataset clone from being incomplete.
        """

        existing_summaries = "\n".join(
            f"- {s.summary}" for s in cloned_subtasks
        )

        # Build naming pattern hint from DB so new subtasks follow convention
        pattern_hint = ""
        if db_patterns and (db_patterns.get("be") or db_patterns.get("web")):
            be_p = " | ".join(db_patterns["be"]) if db_patterns.get("be") else ""
            web_p = " | ".join(db_patterns["web"]) if db_patterns.get("web") else ""
            pattern_hint = f"PATTERNS: BE: {be_p} | WEB: {web_p}\n\n"

        # Reuse the shared _SYSTEM_PROMPT — gap context is injected into user_content below
        cleaned_desc = self._clean_ac_text(description)
        gap_user_content = (
            f"{pattern_hint}"
            f"STORY: {summary}\n"
            f"AC:\n{cleaned_desc[:20000]}\n\n"
            f"EXISTING SUBTASKS IN JIRA:\n{existing_summaries}\n\n"
            "GAP FILL MODE INSTRUCTIONS:\n"
            "1. Carefully audit every explicit endpoint (e.g., /insert..., /inquiry..., /api/...), service, function (e.g., cekData), column, modal, and feature in the AC against the EXISTING SUBTASKS list above.\n"
            "2. If ANY explicit endpoint, function, or feature mentioned in the AC is NOT explicitly covered by the existing subtasks, YOU MUST GENERATE A SUBTASK FOR IT!\n"
            "3. Output ONLY the missing subtasks.\n"
            "4. Only return {\"subtasks\": []} if EVERY single endpoint, service, function, and UI component in the AC is 100% matched by an existing subtask."
        )

        last_exception = None

        # Try OpenAI first
        if settings.OPENAI_API_KEY and settings.LLM_PROVIDER.lower() in ["openai", "auto"]:
            try:
                url = "https://api.openai.com/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY.strip()}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": settings.OPENAI_MODEL or "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": self._SYSTEM_PROMPT},
                        {"role": "user", "content": gap_user_content},
                    ],
                    "temperature": 0.0,
                    "seed": 42,
                    "response_format": {"type": "json_object"},
                    "max_tokens": 800,
                }
                response = requests.post(url, json=payload, headers=headers, timeout=20)
                if response.status_code == 200:
                    raw_text = response.json()["choices"][0]["message"]["content"].strip()
                    parsed = json.loads(raw_text)
                    gap_subtasks = self._filter_gap_subtasks(self._parse_subtasks(parsed, summary))
                    # Deduplicate against existing cloned subtasks in code (not via prompt instruction)
                    gap_subtasks = self._deduplicate_gap_subtasks(gap_subtasks, cloned_subtasks)
                    return gap_subtasks
                else:
                    last_exception = Exception(f"OpenAI gap fill error ({response.status_code})")
            except Exception as e:
                last_exception = e

        # Fallback to Gemini
        try:
            from modules.generate_subtask.infrastructure.gemini_llm_client import GeminiLlmClient
            gemini = GeminiLlmClient()
            gap_subtasks = self._filter_gap_subtasks(
                gemini.fill_gaps_from_ac_raw(self._SYSTEM_PROMPT, gap_user_content, summary)
            )
            # Deduplicate against existing cloned subtasks in code (not via prompt instruction)
            gap_subtasks = self._deduplicate_gap_subtasks(gap_subtasks, cloned_subtasks)
            return gap_subtasks
        except Exception as e:
            return []

    _BANNED_GAP_VERBS = re.compile(
        r'(\b(test|tests|testing|unit test|integration test)\b|'
        r'^(BE|WEB|Mobile)\s*-\s*(Ensure|Test|Document|Verify|Validate|Handle|Check|Make sure|Review|'
        r'Implement logic to|Update UI to reflect|Differentiate|Monitor|Confirm|Track)\b)',
        re.IGNORECASE,
    )

    def _normalize_summary(self, summary: str) -> str:
        normalized = re.sub(r'^((be|web|fe|webapp|mobile)\s*-\s*)+', '', summary, flags=re.IGNORECASE)
        return normalized.strip().lower()

    def _deduplicate_gap_subtasks(
        self,
        gap_subtasks: List[Subtask],
        existing_subtasks: List[Subtask],
    ) -> List[Subtask]:
        """
        Remove any subtask returned by the LLM gap-fill that already exists
        in the cloned subtask list. Comparison is done by normalizing both
        summaries (strip prefix + lowercase) so minor casing/prefix differences
        are ignored. This replaces the 'do NOT duplicate' instruction in the prompt.
        """
        # Build a set of normalized existing summaries for O(1) lookup
        existing_normalized = {
            self._normalize_summary(s.summary) for s in existing_subtasks
        }

        unique = []
        for sub in gap_subtasks:
            normalized = self._normalize_summary(sub.summary)
            if normalized in existing_normalized:
                # Skip — this subtask already exists in the cloned list
                print(f"[Dedup] Skipping duplicate gap subtask: '{sub.summary}'")
                continue
            existing_normalized.add(normalized)
            unique.append(sub)
        return unique

    def _filter_gap_subtasks(self, subtasks: List[Subtask]) -> List[Subtask]:
        """Remove gap-fill subtasks that start with banned generic verbs not present in the RAG dataset."""
        filtered = []
        for sub in subtasks:
            if self._BANNED_GAP_VERBS.match(sub.summary):
                continue
            filtered.append(sub)
        return filtered
