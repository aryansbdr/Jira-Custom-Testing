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

        prompt = (
            "Role: BRI Scrum Master. Decompose User Story into granular subtasks strictly matching AC and RAG dataset patterns.\n\n"
            "RULES:\n"
            "1. STRICT AC GROUNDING & ROLE ASSIGNMENT:\n"
            "   - Assign role 'frontend' (or 'mobile' for mobile context) for UI screens, layouts, input fields, cascading dropdowns, camera/gallery UI, and form validations.\n"
            "   - Assign role 'backend' for database storage/tables, APIs, microservices, external service integrations (e.g. FDS, external core), and data sync/offline persistence services.\n"
            "   - NEVER invent unmentioned features/endpoints (use 'Create API Endpoint' ONLY if 'endpoint/API' is explicitly in AC; use 'Save <Data> to <Table>' for database storage).\n"
            "2. NAMING: English technical verbs ('Create Layout', 'Create Input Field', 'Create Dropdown', 'Create Button <Name>', 'Save <Data> to <Table>') + preserve Indonesian domain terms ('Risalah RKK', 'KUBL', 'Debitur', 'Pencairan', 'MAB', etc.).\n"
            "3. CONSOLIDATION: Sibling fields in the same section may merge with 'and'/'/'. Merge button states (visible/disabled) into ONE single task with state validation.\n\n"
            'Output JSON (Clean titles without role prefix; role is "frontend", "backend", or "mobile"):\n'
            '{"subtasks":[{"summary":"Create Layout for Risalah RKK","role":"frontend","story_points":1.0},{"summary":"Save KUBL Data to content_data_kbli","role":"backend","story_points":1.0}]}\n\n'
        )

        # --- Detect Mobile app context from summary + description ---
        combined_text = f"{summary}\n{description}".lower()
        has_mobile_keyword = any(
            kw in combined_text for kw in [
                "mobile", "brispot", "aplikasi mobile", "mobile app", "app mobile",
                "brispot app", "android", "ios", "mantri", "hanya untuk mobile",
                "untuk mobile", "camera brispot", "galeri brispot"
            ]
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
        is_general_mobile = has_mobile_keyword and not (is_mobile_pemrakarsa or is_mobile_pemutus)

        # Inject specific Mobile prefix instruction into prompt so AI names subtasks correctly
        # NOTE: Pemrakarsa/Pemutus prefix normalization is handled entirely by post-processing code below.
        # No prompt injection needed for mobile context — this saves prompt tokens while keeping results accurate.


        # Inject real naming patterns from DB
        if db_patterns and (db_patterns.get("be") or db_patterns.get("web") or db_patterns.get("mobile")):
            be_p = " | ".join(db_patterns["be"]) if db_patterns.get("be") else ""
            web_p = " | ".join(db_patterns["web"]) if db_patterns.get("web") else ""
            mob_p = " | ".join(db_patterns["mobile"]) if db_patterns.get("mobile") else ""
            prompt += f"PATTERNS FROM RAG DB: BE: {be_p} | WEB: {web_p}" + (f" | MOBILE: {mob_p}" if mob_p else "") + "\n\n"

        if examples:
            prompt += "EXAMPLES FROM RAG DB:\n"
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
                        "seed": 42,
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

                # Drop QA/Testing and SDLC boilerplate noise in code
                summary_lower = summary_text.lower()
                if role_key in ("qa", "tester", "testing") or re.search(r'(\bqa\b|\btesting\b|\buat\b|\banalyze requirements\b|\bpayload structure\b|\brequest validation\b|\bmap request payload\b|\bcode review\b|\bdesign review\b|^\s*review\s+)', summary_lower):
                    continue

                # --- Pemrakarsa / Pemutus context: special prefix rules ---
                # In this mobile app context:
                #   - 'frontend' / WEB subtasks are NOT needed — skip them entirely
                #   - 'backend' subtasks get [MSC Prakarsa] or [MSC Pemutus] prefix
                #   - 'mobile' subtasks get [Mobile Pemrakarsa] or [Mobile Pemutus] prefix
                is_mobile_context = is_mobile_pemrakarsa or is_mobile_pemutus
                msc_label = "Prakarsa" if (is_mobile_pemrakarsa and not is_mobile_pemutus) else "Pemutus"

                if is_mobile_context:
                    if role_key == "backend":
                        clean = re.sub(r'^\[(MSC|MCS|BE)[^\]]*\]\s*', '', summary_text, flags=re.IGNORECASE).strip()
                        clean = re.sub(r'^(BE|(MSC|MCS)(\s+Prakarsa|\s+Pemutus)?)\s*(-|\s+)?', '', clean, flags=re.IGNORECASE).strip()
                        summary_text = f"[MSC {msc_label}] {clean}"
                    else:
                        role_key = "mobile"
                        clean = re.sub(r'^\[(Mobile|WEB|FE)[^\]]*\]\s*', '', summary_text, flags=re.IGNORECASE).strip()
                        clean = re.sub(r'^(Mobile|WEB|FE)(\s+Pemrakarsa|\s+Pemutus)?\s*(-|\s+)?', '', clean, flags=re.IGNORECASE).strip()
                        summary_text = f"[Mobile {msc_label}] {clean}"

                elif is_general_mobile:
                    if role_key == "backend":
                        clean = re.sub(r'^\[(MSC|MCS|BE)[^\]]*\]\s*', '', summary_text, flags=re.IGNORECASE).strip()
                        clean = re.sub(r'^(BE|MSC|MCS)\s*-\s*', '', clean, flags=re.IGNORECASE).strip()
                        summary_text = f"MSC - {clean}"
                    else:
                        role_key = "mobile"
                        clean = re.sub(r'^\[(Mobile|WEB|FE)[^\]]*\]\s*', '', summary_text, flags=re.IGNORECASE).strip()
                        clean = re.sub(r'^(Mobile|WEB|FE)\s*-\s*', '', clean, flags=re.IGNORECASE).strip()
                        summary_text = f"MOBILE - {clean}"

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
                                  "[msc", "[mcs", "[las", "risk register", "risk management",
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
        combined_context = f"{summary}\n{user_content}".lower()
        has_mobile_kw = any(
            kw in combined_context
            for kw in [
                "mobile", "brispot", "android", "ios", "mantri", "aplikasi mobile", "mobile app",
                "hanya untuk mobile", "untuk mobile", "camera brispot", "galeri brispot",
                "pemrakarsa", "pemutus", "prescreening", "prakarsa"
            ]
        )
        is_pemutus = "pemutus" in combined_context
        is_pemrakarsa = "pemrakarsa" in combined_context or "prakarsa" in combined_context or "prescreening" in combined_context
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
                "queue ", "migrate", "endpoint", "api ", "backend", "db schema",
                "migration", "repository", "controller", "stored procedure"
            ])

            if clean_body.startswith("["):
                if clean_body_lower.startswith("[msc") or clean_body_lower.startswith("[mcs") or _is_backend_service:
                    role_key = "backend"
                elif clean_body_lower.startswith("[mobile"):
                    role_key = "mobile"
                else:
                    role_key = "backend" if _is_backend_service else "mobile"
                final_summary = clean_body
            else:
                if "frontend" in role_val or "web" in role_val or "fe" == role_val or any(kw in clean_body_lower for kw in ["pop up", "popup", "wording", "halaman", "button", "tombol", "screen", "layout", "figma", "camera", "geotagging", "input"]):
                    if has_mobile_kw:
                        role_key = "mobile"
                        final_summary = f"{mobile_tag} {clean_body}" if is_bracket_mobile else f"MOBILE - {clean_body}"
                    else:
                        role_key = "frontend"
                        final_summary = f"WEB - {clean_body}"
                elif "mobile" in role_val:
                    if any(kw in clean_body_lower for kw in ["service", "api", "endpoint", "channel", "backend", "inquiry", "integrasi"]):
                        role_key = "backend"
                        final_summary = f"{msc_tag} {clean_body}" if is_bracket_mobile else f"MSC - {clean_body}"
                    else:
                        role_key = "mobile"
                        final_summary = f"{mobile_tag} {clean_body}" if is_bracket_mobile else f"MOBILE - {clean_body}"
                elif "qa" in role_val or "tester" in role_val:
                    continue
                else:
                    role_key = "backend"
                    if has_mobile_kw:
                        final_summary = f"{msc_tag} {clean_body}" if is_bracket_mobile else f"MSC - {clean_body}"
                    else:
                        final_summary = f"BE - {clean_body}"

            # Fibonacci SP
            fib = [0, 0.5, 1, 2, 3, 5, 8, 13]
            sp = min(fib, key=lambda x: abs(x - float(raw_sp)))

            subtasks.append(Subtask(
                summary=final_summary,
                description="",
                role=role_key,
                story_points=sp,
            ))
        return subtasks
