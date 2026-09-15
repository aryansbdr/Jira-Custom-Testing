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
        "Role: BRI Scrum Master. Decompose User Story into granular subtasks strictly matching AC intent and RAG dataset patterns on Database rag_store.db.\n\n"
        "RULES:\n"
        "1. DYNAMIC ACTION VERB MATCHING: Extract and reflect the exact primary action verb written in AC (e.g., 'Migrate' for 'Migrasi', 'Move' for 'Pindahkan', 'Update/Change' for 'Ganti', 'Create/Add' for new items, 'Add Validation' for validation rules). Inherit parent section verbs (e.g., 'BE: Migrasi endpoint...') for all child endpoints listed under that section.\n"
        "2. RAG PATTERN MIMICKING: Strictly imitate squad prefixes ([MSC ...], [Mobile ...]), technical terminology, and naming structures retrieved from RAG Dataset without forcing rigid hardcoded verb rules.\n"
        "3. EXCLUSIONS: NEVER generate QA/testing tasks or SDLC boilerplate (no 'Analyze requirements', 'Payload structure', 'Request validation', 'Review').\n"
        "4. CONSOLIDATION: Sibling fields in the same section may merge with 'and'/'/'. Merge button states (visible/disabled) into ONE single task with state validation.\n\n"
        'Output JSON (Clean titles without role prefix; role is "frontend" or "backend"):\n'
        '{"subtasks":[{"summary":"Migrate Endpoint /v1/detailRiwayatOtsPemutusMikro","role":"backend","story_points":1.0},{"summary":"Move trigger Endpoint validateOTS","role":"frontend","story_points":1.0}]}\n\n'
    )

    def _get_gemini_api_keys(self) -> List[str]:
        raw = settings.GEMINI_API_KEY or ""
        return [k.strip() for k in raw.split(",") if k.strip()]

    def get_text_embedding(self, text: str) -> List[float]:
        cleaned_text = str(text)[:4000]

        # 1. Try OpenAI Embedding if key exists
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
                print(f"[LLM Client] OpenAI Embedding failed: {e}. Falling back to Gemini...")

        # 2. Fallback to Gemini Embedding
        gemini_keys = self._get_gemini_api_keys()
        if not gemini_keys:
            raise ValueError("Neither OPENAI_API_KEY nor GEMINI_API_KEY is configured.")

        last_err = None
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
                last_err = f"Gemini Embedding API error ({response.status_code}): {response.text}"
            except Exception as e:
                last_err = str(e)

        raise Exception(f"All embedding providers failed. Last error: {last_err}")

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
        "pemrakarsa",
        "prakarsa",
        "pemutus",
        "prescreening",
        "mikro",
        "kur",
        "slik",
        "ots",
        "mobile",
        "mobile app",
        "android",
        "ios",
        "aplikasi",
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
            user_content += f"STRICT MODE: Output {max_subtasks} subtask(s).\n\n"
        else:
            user_content += "FREE MODE: Cover all sections AC.\n\n"

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
        has_mobile_story = any(
            kw in combined_text
            for kw in [
                "mobile", "brispot", "android", "ios", "mantri", "aplikasi mobile", "mobile app",
                "hanya untuk mobile", "untuk mobile", "camera brispot", "galeri brispot",
                "pemrakarsa", "pemutus", "prescreening", "prakarsa"
            ]
        )
        is_pemutus = "pemutus" in combined_text
        is_pemrakarsa = "pemrakarsa" in combined_text or "prakarsa" in combined_text or "prescreening" in combined_text
        is_bracket_mobile = is_pemrakarsa or is_pemutus

        mobile_tag = "[Mobile Pemutus]" if is_pemutus else "[Mobile Pemrakarsa]"
        msc_tag = "[MSC Pemutus]" if is_pemutus else "[MSC Prakarsa]"

        for sub in parsed.get("subtasks", []):
            summary_text = sub.get("summary", "").strip()
            # Clean Jira markup symbols ({*}, {*}, *}, and single asterisks *) from title
            summary_text = re.sub(r'\{\*?\}|\{\*|\*\}|\*', '', summary_text).strip()
            role_val = str(sub.get("role", "backend")).lower()
            raw_sp = sub.get("story_points", 1.0)

            # Strip all leading role prefixes (BE -, WEB -, FE -, WEBAPP -, Mobile -, MSC -, MCS -, etc.)
            clean_body = re.sub(r'^((be|web|fe|webapp|mobile|msc|mcs|qa)\s*-\s*)+', '', summary_text, flags=re.IGNORECASE).strip()
            clean_body_lower = clean_body.lower()

            # Auto-standardize [MCS ...] to [MSC ...]
            if clean_body.upper().startswith("[MCS"):
                clean_body = re.sub(r'^\[MCS', '[MSC', clean_body, flags=re.IGNORECASE)
                clean_body_lower = clean_body.lower()

            _is_backend_service = any(kw in clean_body_lower for kw in [
                "/v1/", "/v2/", "create new service", "create service",
                "queue ", "migrate", "endpoint", "api", "backend", "db schema",
                "migration", "repository", "controller", "stored procedure", "fds",
                "simpan lat long", "save lat long", "send geotagging", "kirimkan pada fds",
                "geotagging data"
            ])

            # If clean_body already starts with a bracket tag like [Mobile ...] or [MSC ...]
            if clean_body.startswith("["):
                if clean_body_lower.startswith("[msc") or clean_body_lower.startswith("[mcs") or _is_backend_service:
                    role_key = "backend"
                    if clean_body_lower.startswith("[mobile") and _is_backend_service:
                        clean_body = re.sub(r'^\[mobile\s*[^\]]*\]\s*', '', clean_body, flags=re.IGNORECASE).strip()
                        clean_body = f"{msc_tag} {clean_body}" if is_bracket_mobile else f"MSC - {clean_body}"
                elif clean_body_lower.startswith("[mobile"):
                    role_key = "mobile"
                else:
                    role_key = "backend" if _is_backend_service else "mobile"
                final_summary = clean_body
            else:
                # Determine role & prefix
                # Backend tasks get MSC - prefix for Mobile stories, and BE - prefix for Web stories
                if _is_backend_service:
                    role_key = "backend"
                    if has_mobile_story:
                        final_summary = f"{msc_tag} {clean_body}" if is_bracket_mobile else f"MSC - {clean_body}"
                    else:
                        final_summary = f"BE - {clean_body}"
                elif any(kw in clean_body_lower for kw in ["pop up", "popup", "wording", "halaman", "button", "tombol", "screen", "layout", "figma", "tampilan", "dropdown", "autofill", "checkbox", "radio"]):
                    if has_mobile_story:
                        role_key = "mobile"
                        final_summary = f"{mobile_tag} {clean_body}" if is_bracket_mobile else f"MOBILE - {clean_body}"
                    else:
                        role_key = "frontend"
                        final_summary = f"WEB - {clean_body}"
                elif "frontend" in role_val or "web" in role_val or "fe" == role_val:
                    if has_mobile_story:
                        role_key = "mobile"
                        final_summary = f"{mobile_tag} {clean_body}" if is_bracket_mobile else f"MOBILE - {clean_body}"
                    else:
                        role_key = "frontend"
                        final_summary = f"WEB - {clean_body}"
                elif "mobile" in role_val:
                    if any(kw in clean_body_lower for kw in ["service", "api", "endpoint", "channel", "backend", "inquiry", "integrasi", "fds"]):
                        role_key = "backend"
                        if has_mobile_story:
                            final_summary = f"{msc_tag} {clean_body}" if is_bracket_mobile else f"MSC - {clean_body}"
                        else:
                            final_summary = f"BE - {clean_body}"
                    else:
                        role_key = "mobile"
                        final_summary = f"{mobile_tag} {clean_body}" if is_bracket_mobile else f"MOBILE - {clean_body}"
                elif "qa" in role_val or "tester" in role_val:
                    continue
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
            "1. Audit every explicit action, service, endpoint, persistence/save process, and UI component in the AC against the EXISTING SUBTASKS list.\n"
            "2. Distinct technical responsibilities mentioned in the AC MUST NOT be merged into a single existing subtask. For example, data saving/persistence (e.g., storing data/coordinates) and external transmission/API endpoints (e.g., sending data to external/3rd party services) are SEPARATE responsibilities. If any distinct action in the AC is not explicitly covered by an existing subtask, YOU MUST GENERATE A SUBTASK FOR IT.\n"
            "3. Output ONLY the missing subtasks using appropriate role prefixes (MSC - for backend/channel services, WEB - for web frontend, MOBILE - for mobile frontend).\n"
            "4. Only return {\"subtasks\": []} if EVERY single distinct action, service, endpoint, and UI component in the AC is 100% covered by an existing subtask.\n"
            "5. MANDATORY TODO LIST AUDIT: Pay special attention to any explicit 'Todo:' or 'To Do:' bullet/numbered list in the story description. You MUST audit EVERY single TODO item item-by-item against the EXISTING SUBTASKS list. If any item from the TODO list (e.g., 'Web Enhance modal pop search debitur by ptk dan nama') does NOT have a corresponding subtask in EXISTING SUBTASKS, YOU MUST GENERATE A SUBTASK FOR IT."
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
            gap_subtasks = self._filter_gap_subtasks(self._fill_gaps_gemini(gap_user_content, summary))
            gap_subtasks = self._deduplicate_gap_subtasks(gap_subtasks, cloned_subtasks)
            return gap_subtasks
        except Exception as e:
            return []

    def _fill_gaps_gemini(self, gap_user_content: str, summary: str) -> List[Subtask]:
        combined_prompt = f"{self._SYSTEM_PROMPT}\n\n{gap_user_content}"
        fallback_models = ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
        api_keys = self._get_gemini_api_keys()
        if not api_keys:
            return []

        text_content = None
        for api_key in api_keys:
            for model_name in fallback_models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                headers = {"Content-Type": "application/json"}
                gen_config = {
                    "temperature": 0.0,
                    "seed": 42,
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
                except Exception:
                    continue
            if text_content:
                break

        if not text_content:
            return []

        try:
            parsed = json.loads(text_content)
            return self._parse_subtasks(parsed, summary)
        except Exception:
            return []

    _BANNED_GAP_VERBS = re.compile(
        r'(\b(test|tests|testing|unit test|integration test)\b|'
        r'^(BE|WEB|Mobile)\s*-\s*(Ensure|Test|Document|Verify|Validate|Handle|Check|Make sure|Review|'
        r'Implement logic to|Update UI to reflect|Differentiate|Monitor|Confirm|Track)\b)',
        re.IGNORECASE,
    )

    _STOP_WORDS = {
        "for", "in", "to", "by", "of", "and", "or", "the", "a", "an", "on", "with", "data", "subtask", "task"
    }

    _ACTION_KEYWORDS = {
        "reset", "cari", "search", "batal", "cancel", "tambah", "add", "detail", "delete", "remove",
        "edit", "update", "inquiry", "save", "simpan", "send", "kirim", "enhance", "popup", "modal", "layout"
    }

    def _normalize_tokens(self, summary: str) -> set:
        clean = re.sub(r'^((be|web|fe|webapp|mobile|msc|mcs|qa)\s*-\s*)+', '', summary, flags=re.IGNORECASE).strip()
        clean = re.sub(r'^\[[^\]]+\]\s*', '', clean, flags=re.IGNORECASE).strip()
        words = re.findall(r'[a-zA-Z0-9]+', clean.lower())
        return {w for w in words if w not in self._STOP_WORDS}

    def _is_similar_subtask(self, sub1_summary: str, sub2_summary: str) -> bool:
        tokens1 = self._normalize_tokens(sub1_summary)
        tokens2 = self._normalize_tokens(sub2_summary)
        if not tokens1 or not tokens2:
            return False
        
        # Check for conflicting action keywords (e.g., reset vs cari)
        actions1 = tokens1 & self._ACTION_KEYWORDS
        actions2 = tokens2 & self._ACTION_KEYWORDS
        if actions1 and actions2 and not (actions1 & actions2):
            return False

        if tokens1 == tokens2:
            return True
        
        intersection = tokens1 & tokens2
        min_len = min(len(tokens1), len(tokens2))
        overlap_ratio = len(intersection) / float(min_len) if min_len > 0 else 0.0
        return overlap_ratio >= 0.8 or tokens1.issubset(tokens2) or tokens2.issubset(tokens1)

    def _deduplicate_gap_subtasks(
        self,
        gap_subtasks: List[Subtask],
        existing_subtasks: List[Subtask],
    ) -> List[Subtask]:
        """
        Remove any subtask returned by the LLM gap-fill that already exists
        in the cloned subtask list. Uses token similarity and action keyword matching
        so minor casing, prefix, or suffix variations are safely recognized as duplicates.
        """
        unique = []
        for sub in gap_subtasks:
            is_dup = False
            for ex in existing_subtasks:
                if self._is_similar_subtask(sub.summary, ex.summary):
                    print(f"[Dedup] Skipping duplicate gap subtask: '{sub.summary}' (matches existing '{ex.summary}')")
                    is_dup = True
                    break
            if not is_dup:
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
