import math
import re
from typing import List, Optional
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

    @staticmethod
    def chunk_ac_text(description: str) -> List[dict]:
        """
        Decomposes raw Acceptance Criteria (AC) text into discrete, structured AC chunks.
        Splits by line breaks, numbered items (1., 2.), lettered lists (a., b.), bullet points (- , *),
        and section headers (BE -, WEB -, Mobile -, Penambahan Sub Menu:).
        """
        if not description or not description.strip():
            return []

        raw_text = description.strip()

        # Split by newlines first to honor distinct AC lines, then by bullet/number markers
        lines = [ln.strip() for ln in re.split(r'[\r\n]+', raw_text) if ln and ln.strip()]
        raw_items = []
        split_pattern = r'(?=\b(?:\d+[\.\)]|[a-z][\.\)]|[\-\*•])\s+)|(?=\b(?:BE|WEB|Mobile)\s*-\s*)'
        for line in lines:
            sub_items = [item.strip() for item in re.split(split_pattern, line) if item and item.strip()]
            if sub_items:
                raw_items.extend(sub_items)
            else:
                raw_items.append(line)

        chunks = []
        for idx, item in enumerate(raw_items, start=1):
            clean_item = re.sub(r'^(?:\d+[\.\)]|[a-z][\.\)]|[\-\*•])\s*', '', item).strip()
            if not clean_item or len(clean_item) < 3:
                continue

            item_lower = clean_item.lower()

            # Accurate Frontend indicators
            has_web = any(kw in item_lower for kw in [
                "web", "tampilan", "ui ", " ui", "screen", "view", "form", "tab", "list",
                "menu", "component", "komponen", "modal", "page", "halaman", "button",
                "radio", "fe ", "monitoring", "tabel", "table", "menampilkan", "display"
            ])

            # Accurate Backend indicators (only flag as BE if explicit backend/DB terms appear)
            has_be = any(kw in item_lower for kw in [
                "be ", "backend", "endpoint", "api", "service", "query", "database",
                "insert", "inquiry", "function general", "cekdata", "mst_", "db ", " db"
            ]) or ("kolom" in item_lower and any(db_kw in item_lower for db_kw in ["mst_", "database", "db", "tabel "]))

            # Disambiguate: "menampilkan kolom pada monitoring" is 100% Frontend
            if has_web and ("menampilkan" in item_lower or "monitoring" in item_lower) and not any(db_kw in item_lower for db_kw in ["mst_", "endpoint", "api", "query"]):
                has_be = False

            has_mobile = any(kw in item_lower for kw in ["mobile", "brispot", "layout", "activity", "android", "ios", "prescreening", "prakarsa", "mikro", "kur", "slik"])

            role_hint = "backend" if has_be and not has_web else "frontend" if has_web and not has_be else "mobile" if has_mobile else "general"

            chunks.append({
                "chunk_id": idx,
                "raw_text": item,
                "clean_text": clean_item,
                "role_hint": role_hint,
                "has_be": has_be,
                "has_web": has_web,
                "has_mobile": has_mobile,
            })

        return chunks

    def execute(
        self,
        summary: str,
        description: str,
        parent_sp: float,
        mode: str = "free",
        existing_subtasks: List[str] = None,
        issue_key: Optional[str] = None,
        assignee: Optional[str] = None,
        assignee_role: Optional[str] = None,
    ) -> List[Subtask]:
        summary_lower = summary.lower()

        # Perform AC Chunking to break AC into structured items for precise RAG and LLM processing
        ac_chunks = self.chunk_ac_text(description)
        if ac_chunks:
            chunk_summary_text = "\n".join([f"- CHUNK {c['chunk_id']} [{c['role_hint'].upper()}]: {c['clean_text']}" for c in ac_chunks])
            formatted_description = f"{description}\n\nSTRUCTURED AC CHUNKS:\n{chunk_summary_text}"
        else:
            formatted_description = description

        # Inject Assignee Role Context if assigned engineer has specific role (especially Mobile/MCS)
        if assignee_role and "mob" in assignee_role.lower():
            formatted_description += f"\n\n[MOBILE ENGINEER ASSIGNED]: Story ini di-assign ke engineer mobile '{assignee or 'Mobile Dev'}'. Buat subtask 'MOBILE - <Title>' untuk UI Mobile App atau 'MSC - <Title>' untuk Mobile Channel Service / Backend API Mobile sesuai rincian AC."

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
                ),
                Subtask(
                    summary=f"Code Review - {clean_title}",
                    description=f"Eksekusi Code Review & Static Analysis untuk {clean_title}",
                    role="backend",

                ),
                Subtask(
                    summary=testing_subtask_title,
                    description=testing_desc,
                    role="backend",
                )
            ]

        # 1. Generate query embedding combining summary & description for accurate RAG match
        search_text = f"{summary}\n{formatted_description}".strip()
        target_embedding = self.llm_client.get_text_embedding(search_text)

        # 2. Retrieve all historical stories from SQLite RAG database
        historical_stories = self.story_repo.get_all()

        def _normalize_str(s: str) -> str:
            cleaned = str(s or '')
            cleaned = re.sub(r'^(?:\[.*?\]|\b(?:be|web|fe|mobile)\s*-\s*)', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'^\s*(?:\d+[\.\)]|[a-z][\.\)]|[\-\*•])\s*', '', cleaned, flags=re.MULTILINE)
            return re.sub(r'\s+', ' ', cleaned).strip().lower()

        req_title_norm = _normalize_str(summary)

        candidate_stories = []
        for s in historical_stories:
            if s.get("embedding"):
                s["similarity"] = self._cosine_similarity(target_embedding, s["embedding"])
                candidate_stories.append(s)
        candidate_stories.sort(key=lambda x: x["similarity"], reverse=True)

        # Priority 1: Check for 100% Full Issue Key Match in DB
        exact_key_match = None
        if issue_key:
            clean_ikey = issue_key.strip().upper()
            exact_key_match = next((s for s in historical_stories if s.get("issue_key") and s.get("issue_key").strip().upper() == clean_ikey), None)

        if not exact_key_match:
            exact_key_match = next(
                (s for s in historical_stories if s.get("issue_key") and (
                    s.get("issue_key").strip().upper() == summary.strip().upper() or
                    f"[{s.get('issue_key', '').strip().upper()}]" in summary.upper() or
                    f" {s.get('issue_key', '').strip().upper()} " in f" {summary.upper()} "
                )), None
            )
        exact_title_match = next((s for s in historical_stories if req_title_norm and req_title_norm == _normalize_str(s.get("summary"))), None)

        top_match = exact_key_match or exact_title_match

        # Priority 2: Fallback to vector similarity top match if no exact key/title match
        if not top_match:
            top_match = candidate_stories[0] if candidate_stories else None

        clean_req_title = _normalize_str(summary)
        clean_db_title = _normalize_str(top_match.get("summary", "")) if top_match else ""
        clean_req_desc = _normalize_str(description)
        clean_db_desc = _normalize_str(top_match.get("description", "")) if top_match else ""

        noise_regex = re.compile(
            r'(\banalyze requirements\b|\bidentify affected modules\b|\brequest payload structure\b|\bimplement request validation\b|\bmap request payload\b|\breview\b.*(code|design|figma|existing|mab)|^\s*review\s+|\bcode review\b|\bdesign review\b)',
            re.IGNORECASE
        )

        # Check if DB subtasks are genuinely valid (not empty or 100% boilerplate junk)
        db_subs = top_match.get("subtasks", []) if top_match else []
        valid_db_subs = [s for s in db_subs if not noise_regex.search(str(s.get("summary", "")).lower()) and s.get("role") not in ("qa", "tester")]
        has_sufficient_valid_subs = len(valid_db_subs) >= 2

        # Check similarity between descriptions (tolerant to whitespace/minor word differences)
        def _calc_overlap(text_a: str, text_b: str) -> float:
            if not text_a or not text_b:
                return 0.0
            words_a = set(text_a.split())
            words_b = set(text_b.split())
            if not words_a or not words_b:
                return 0.0
            intersection = words_a.intersection(words_b)
            return len(intersection) / max(len(words_a), len(words_b))

        desc_overlap = _calc_overlap(clean_req_desc, clean_db_desc)

        # Exact match occurs when AC description is identical (or title/key match when desc is empty/identical) and valid subtasks exist in DB
        is_exact_desc_match = bool(top_match and (clean_req_desc == clean_db_desc or desc_overlap >= 0.70) and has_sufficient_valid_subs)
        is_exact_title_match = bool(top_match and clean_req_title and clean_req_title == clean_db_title and has_sufficient_valid_subs)
        is_exact_key_match = bool(exact_key_match and has_sufficient_valid_subs)

        is_plek_ketiplek_match = is_exact_desc_match or is_exact_title_match or is_exact_key_match

        if top_match and is_plek_ketiplek_match:
            combined_text = f"{summary}\n{description or ''}".lower()
            has_web_or_corp = any(kw in combined_text for kw in ["korporasi", "mab", "web", "portal", "dashboard", "fe ", " fe", "ui", "tab ", "halaman", "browser"])
            has_mobile_keyword = any(kw in combined_text for kw in ["mobile", "brispot", "android", "ios", "mantri", "aplikasi mobile", "mobile app", "hanya untuk mobile", "untuk mobile", "camera brispot", "galeri brispot", "ots"])
            is_mobile_story = has_mobile_keyword and not has_web_or_corp
            is_pemutus = is_mobile_story and "pemutus" in combined_text
            is_pemrakarsa = is_mobile_story and ("pemrakarsa" in combined_text or "prescreening" in combined_text)
            is_bracket_mobile = is_pemrakarsa or is_pemutus
            role_tag = "[Mobile Pemutus]" if is_pemutus else ("[Mobile Pemrakarsa]" if is_pemrakarsa else "MOBILE -")
            msc_tag = "[MSC Pemutus]" if is_pemutus else ("[MSC Prakarsa]" if is_pemrakarsa else "MSC -")
            cloned_subtasks = []

            for sub in top_match["subtasks"]:
                summary_text = str(sub["summary"]).strip()
                sub_lower = summary_text.lower()
                
                # Filter out generic noise tasks (Review, Analyze requirements, Payload structure, etc.)
                if noise_regex.search(sub_lower):
                    continue

                # Clean all leading role prefixes (BE -, WEB -, FE -, WEBAPP -, Mobile -, MSC -, MCS -, etc.) completely
                clean_body = re.sub(r'^((be|web|fe|webapp|mobile|msc|mcs)\s*-\s*)+', '', summary_text, flags=re.IGNORECASE).strip()
                clean_body_lower = clean_body.lower()
            
                raw_role = str(sub.get("role", "backend")).lower()

                # Robust detection of Backend vs Frontend:
                # 1. Any task with /v1/, /v2/, create service, endpoint, queue, migration, database -> Backend
                _is_backend_service = any(kw in clean_body_lower for kw in [
                    "/v1/", "/v2/", "create new service", "create service",
                    "queue ", "migrate", "endpoint", "api ", "backend", "db schema",
                    "migration", "repository", "controller", "stored procedure"
                ])

                _ui_kw = [
                    "pop up", "popup", "wording", "halaman", "redirect",
                    "button", "tombol", "screen", "layout", "tampilan",
                    "dropdown", "autofill", "checkbox", "radio", "figma",
                    "camera", "geotagging", "input"
                ]
                is_ui_task = any(kw in clean_body_lower for kw in _ui_kw)

                if clean_body_lower.startswith("[mobile") or clean_body_lower.startswith("mobile -"):
                    normalized_role = "mobile" if is_mobile_story else "frontend"
                elif clean_body_lower.startswith("[msc") or clean_body_lower.startswith("msc -") or clean_body_lower.startswith("[mcs") or clean_body_lower.startswith("mcs -"):
                    normalized_role = "backend"
                elif _is_backend_service:
                    normalized_role = "backend"
                elif is_ui_task:
                    normalized_role = "mobile" if is_mobile_story else "frontend"
                elif raw_role in ("developer", "backend", "be"):
                    normalized_role = "backend"
                elif raw_role in ("frontend", "web", "fe", "mobile"):
                    normalized_role = "mobile" if is_mobile_story else "frontend"
                else:
                    normalized_role = "frontend" if summary_text.upper().startswith("WEB -") else "backend"

                # Build final summary text:
                if clean_body.startswith("["):
                    # Auto-normalize [MCS ...] to [MSC ...]
                    if clean_body.upper().startswith("[MCS"):
                        clean_body = re.sub(r'^\[MCS', '[MSC', clean_body, flags=re.IGNORECASE)
                    summary_text = clean_body
                else:
                    if normalized_role in ("frontend", "mobile"):
                        if is_mobile_story:
                            summary_text = f"{role_tag} {clean_body}" if is_bracket_mobile else f"MOBILE - {clean_body}"
                            normalized_role = "mobile"
                        else:
                            summary_text = f"WEB - {clean_body}"
                    else:
                        if is_mobile_story:
                            summary_text = f"{msc_tag} {clean_body}" if is_bracket_mobile else f"MSC - {clean_body}"
                        else:
                            summary_text = f"BE - {clean_body}"

                cloned_subtasks.append(
                    Subtask(
                        summary=self._standardize_subtask_title(summary_text),
                        description="",
                        role=normalized_role,
                        story_points=sub["story_points"],
                    )
                )
            if cloned_subtasks:
                # If existing_subtasks already exist in Jira, filter them out so we return only the missing subtasks!
                if existing_subtasks and len(existing_subtasks) > 0:
                    existing_norm = {re.sub(r'^((be|web|fe|webapp|mobile)\s*-\s*)+', '', s, flags=re.IGNORECASE).strip().lower() for s in existing_subtasks}
                    cloned_subtasks = [
                        s for s in cloned_subtasks
                        if re.sub(r'^((be|web|fe|webapp|mobile)\s*-\s*)+', '', s.summary, flags=re.IGNORECASE).strip().lower() not in existing_norm
                    ]

                db_naming_patterns = self._extract_naming_patterns(candidate_stories[:10])
                
                # Check for any remaining custom AC not covered yet
                all_known_subs = cloned_subtasks + ([Subtask(summary=s, description="", role="backend", story_points=1.0) for s in existing_subtasks] if existing_subtasks else [])
                gap_subtasks = self.llm_client.fill_gaps_from_ac(
                    summary=summary,
                    description=formatted_description,
                    cloned_subtasks=all_known_subs,
                    db_patterns=db_naming_patterns,
                )
                if gap_subtasks:
                    for g in gap_subtasks:
                        g.summary = self._standardize_subtask_title(g.summary)
                    cloned_subtasks.extend(gap_subtasks)

                # Mobile subtasks are valid when the story mentions BRISpot mobile roles
                _mobile_kw = [
                    "pemrakarsa", "prakarsa", "pemutus", "prescreening",
                    "mikro", "kur", "slik", "mobile", "mobile app", "brispot", "android", "ios", "aplikasi",
                ]
                has_mobile_ctx = any(
                    kw in (summary + " " + (description or "")).lower() for kw in _mobile_kw
                )
                if not has_mobile_ctx:
                    cloned_subtasks = [s for s in cloned_subtasks if s.role != "mobile"]
                
                # Standardize all titles before return
                for s in cloned_subtasks:
                    s.summary = self._standardize_subtask_title(s.summary)

                return cloned_subtasks
            # All cloned subtasks were filtered as noise — fallback to AI synthesis
            print("   [INFO] Semua subtask dari DB adalah noise, fallback ke AI synthesis...")

        selected_references = candidate_stories[:2]

        # Extract real naming patterns from DB to guide AI style dynamically
        db_naming_patterns = self._extract_naming_patterns(candidate_stories[:10])

        # Resolve target subtask count for strict mode from SP table
        target_subtasks = None
        if mode == "strict":
            effective_sp = parent_sp if (parent_sp and parent_sp > 0) else 3.0
            sp_key = min(self.SP_SUBTASK_LIMIT.keys(), key=lambda k: abs(k - effective_sp))
            target_subtasks = self.SP_SUBTASK_LIMIT[sp_key]

        # 4. Generate structured subtasks using LLM Client
        if existing_subtasks and len(existing_subtasks) > 0:
            existing_objs = [Subtask(summary=s, description="", role="backend", story_points=1.0) for s in existing_subtasks]
            generated_subtasks = self.llm_client.fill_gaps_from_ac(
                summary=summary,
                description=formatted_description,
                cloned_subtasks=existing_objs,
                db_patterns=db_naming_patterns,
            )
        else:
            generated_subtasks = self.llm_client.generate_subtasks_from_ac(
                summary=summary,
                description=formatted_description,
                parent_sp=parent_sp,
                examples=selected_references,
                db_patterns=db_naming_patterns,
                mode=mode,
                max_subtasks=target_subtasks,
            )

        # Enforce exact count for strict mode — trim to exactly target_subtasks
        if mode == "strict" and target_subtasks:
            generated_subtasks = generated_subtasks[:target_subtasks]

        # Post-process: mobile context guard + general sanitization
        ac_text = (summary + " " + (description or "")).lower()
        has_web_or_corp = any(kw in ac_text for kw in ["korporasi", "mab", "web", "portal", "dashboard", "fe ", " fe", "ui", "tab ", "halaman", "browser"])
        mobile_context_keywords = [
            "mobile", "mobile app", "brispot", "android", "ios", "aplikasi mobile", "ots", "prescreening",
            "mantri", "hanya untuk mobile", "untuk mobile", "camera brispot", "galeri brispot"
        ]
        has_mobile_context = (any(kw in ac_text for kw in mobile_context_keywords) and not has_web_or_corp) or (bool(assignee_role) and "mob" in assignee_role.lower())
        is_pemutus = has_mobile_context and "pemutus" in ac_text
        is_pemrakarsa = has_mobile_context and ("pemrakarsa" in ac_text or "prescreening" in ac_text)
        is_bracket_mobile = is_pemrakarsa or is_pemutus

        filtered_subtasks = []
        for sub in generated_subtasks:
            # Drop QA tasks as requested (QA does not need generated subtasks)
            if sub.role == "qa" or sub.summary.lower().startswith("qa -") or sub.summary.lower().startswith("testing -"):
                continue
            # Drop hallucinated Mobile subtasks when the story has no mobile context and no mobile assignee
            if sub.role == "mobile" and not has_mobile_context:
                continue

            # In mobile stories, ensure standard prefix formatting based directly on sub.role
            if has_mobile_context:
                sub_sum = sub.summary.strip()
                clean_body = re.sub(r'^((be|web|fe|webapp|mobile|msc|mcs|qa)\s*-\s*)+', '', sub_sum, flags=re.IGNORECASE).strip()
                clean_body = re.sub(r'^\[(Mobile|WEB|FE|MSC|MCS|BE)[^\]]*\]\s*', '', clean_body, flags=re.IGNORECASE).strip()

                if sub.role == "backend":
                    if is_pemutus:
                        sub.summary = f"[MSC Pemutus] {clean_body}"
                    elif is_pemrakarsa:
                        sub.summary = f"[MSC Prakarsa] {clean_body}"
                    else:
                        sub.summary = f"MSC - {clean_body}"
                else:
                    sub.role = "mobile"
                    if is_pemutus:
                        sub.summary = f"[Mobile Pemutus] {clean_body}"
                    elif is_pemrakarsa:
                        sub.summary = f"[Mobile Pemrakarsa] {clean_body}"
                    else:
                        sub.summary = f"MOBILE - {clean_body}"

            filtered_subtasks.append(sub)

        # Post-process: button consolidation & save progress clarity
        consolidated = []
        dl_button_merged = False
        dl_subtasks = [s for s in filtered_subtasks if "download" in s.summary.lower() and "button" in s.summary.lower()]

        for sub in filtered_subtasks:
            summary_lower = sub.summary.lower()
            # 1. Consolidate multiple download button states into ONE unified subtask
            if sub in dl_subtasks:
                if not dl_button_merged:
                    role_prefix = "[Mobile Pemrakarsa] " if sub.summary.startswith("[Mobile") else ("MOBILE - " if sub.summary.startswith("MOBILE") else "WEB - ")
                    doc_name = "Risalah RKK" if ("rkk" in summary_lower or "risalah" in summary_lower) else ""
                    title_suffix = f" {doc_name}" if doc_name else ""
                    new_summary = f"{role_prefix}Create Button Download PDF{title_suffix} with State Validation (Visible & Enabled after Save, Disabled if not saved)".strip()
                    consolidated.append(Subtask(
                        summary=new_summary,
                        description=sub.description,
                        role=sub.role,
                        story_points=sub.story_points
                    ))
                    dl_button_merged = True
                continue
            # 2. Enhance save progress button clarity
            elif ("button simpan" in summary_lower or "save button" in summary_lower) and "progress" not in summary_lower:
                role_prefix = "WEB - " if sub.summary.startswith("WEB - ") else ("[Mobile Pemrakarsa] " if sub.summary.startswith("[Mobile") else "")
                doc_name = "Risalah RKK" if ("rkk" in summary_lower or "risalah" in summary_lower) else ""
                title_suffix = f" {doc_name}" if doc_name else ""
                new_summary = f"{role_prefix}Create Button Simpan for Save Progress{title_suffix}".strip()
                consolidated.append(Subtask(
                    summary=new_summary,
                    description=sub.description,
                    role=sub.role,
                    story_points=sub.story_points
                ))
            else:
                consolidated.append(sub)

        final_list = consolidated if consolidated else (filtered_subtasks if filtered_subtasks else generated_subtasks)
        for s in final_list:
            s.summary = self._standardize_subtask_title(s.summary)
        return final_list

    @staticmethod
    def _standardize_subtask_title(summary: str) -> str:
        """Standardizes subtask title casing, spelling, grammar, and prefixes."""
        s = str(summary or '').strip()

        # 1. Extract prefix
        prefix_match = re.match(r'^((?:\[(?:Mobile|WEB|FE|MSC|MCS|BE)[^\]]*\]|(?:BE|WEB|FE|WEBAPP|MOBILE|MSC|MCS))\s*-\s*)', s, re.IGNORECASE)
        prefix = ""
        body = s
        if prefix_match:
            prefix = prefix_match.group(1).strip()
            body = s[len(prefix_match.group(1)):].strip()
        elif s.startswith("["):
            bracket_match = re.match(r'^(\[[^\]]+\])\s*', s)
            if bracket_match:
                prefix = bracket_match.group(1).strip()
                body = s[len(bracket_match.group(0)):].strip()

        # Standardize prefix formatting
        if prefix:
            if prefix.upper().startswith("WEB -") or prefix.upper().startswith("FE -"):
                prefix = "WEB -"
            elif prefix.upper().startswith("BE -"):
                prefix = "BE -"
            elif prefix.upper().startswith("MSC -") or prefix.upper().startswith("MCS -"):
                prefix = "MSC -"
            elif prefix.upper().startswith("MOBILE -"):
                prefix = "MOBILE -"
            elif prefix.upper().startswith("[MSC"):
                prefix = re.sub(r'^\[MCS', '[MSC', prefix, flags=re.IGNORECASE)

        # 2. Fix common dataset typos (including within camelCase identifiers like inquirtLimit -> inquiryLimit)
        body = re.sub(r'inquirt', 'inquiry', body, flags=re.IGNORECASE)
        body = re.sub(r'\bIMplement\b', 'Implement', body)
        body = re.sub(r'\bimplement\b', 'Implement', body)
        body = re.sub(r'\bcreating\b', 'Create', body, flags=re.IGNORECASE)
        body = re.sub(r'\bcreate\b', 'Create', body, flags=re.IGNORECASE)
        body = re.sub(r'\bhandling\b', 'Handle', body, flags=re.IGNORECASE)
        body = re.sub(r'\bhandle\b', 'Handle', body, flags=re.IGNORECASE)
        body = re.sub(r'\bmapping data\b', 'Mapping Data', body, flags=re.IGNORECASE)
        body = re.sub(r'\bmapping\b', 'Mapping Data', body, flags=re.IGNORECASE)
        body = re.sub(r'\bendpoint\s*/', 'Endpoint /', body, flags=re.IGNORECASE)
        body = re.sub(r'\bendpoint\b', 'Endpoint', body, flags=re.IGNORECASE)
        body = re.sub(r'\bservice\b', 'Service', body, flags=re.IGNORECASE)
        body = re.sub(r'\bcomponent\b', 'Component', body, flags=re.IGNORECASE)
        body = re.sub(r'\badd\b', 'Add', body, flags=re.IGNORECASE)
        body = re.sub(r'\benhance\b', 'Enhance', body, flags=re.IGNORECASE)
        body = re.sub(r'\bperhitungan\b', 'Perhitungan', body, flags=re.IGNORECASE)
        body = re.sub(r'\bidentification\b', 'Identification', body, flags=re.IGNORECASE)
        body = re.sub(r'\blogic\b', 'Logic', body, flags=re.IGNORECASE)

        # Specific database SOP pattern
        if "sop database" in body.lower() and "column" in body.lower():
            tbl_match = re.search(r'database\s+([a-zA-Z0-9_]+)', body, re.IGNORECASE)
            col_match = re.search(r'column\s+([a-zA-Z0-9_]+)', body, re.IGNORECASE)
            tbl_name = tbl_match.group(1) if tbl_match else "mst_nore_fasilitas"
            col_name = col_match.group(1) if col_match else "tanggal_akad"
            body = f"Add Column {col_name} to Database Table {tbl_name}"

        # Specific 'Implement tipe perusahaan identification logic'
        if "tipe perusahaan" in body.lower() and "identification" in body.lower():
            body = "Implement Tipe Perusahaan Identification Logic"

        if body.lower() == "add tanggal akad dan jangka waktu":
            body = "Add Field Tanggal Akad dan Jangka Waktu"

        body = re.sub(r'^Create component\b', 'Create Component', body, flags=re.IGNORECASE)
        body = re.sub(r'^Create endpoint\b', 'Create Endpoint', body, flags=re.IGNORECASE)
        body = re.sub(r'^Create service\b', 'Create Service', body, flags=re.IGNORECASE)
        body = re.sub(r'^Mapping Data Data\b', 'Mapping Data', body, flags=re.IGNORECASE)
        body = re.sub(r'\s+', ' ', body).strip()

        if prefix:
            return f"{prefix} {body}".strip()
        return body

    def _extract_naming_patterns(self, stories: list) -> dict:
        """Extract real naming patterns from historical subtasks to use as dynamic style guide."""
        be_patterns = set()
        web_patterns = set()
        mobile_patterns = set()

        noise_pattern = re.compile(
            r'\b(review|ensure|handle|verify|validate|check that|make sure|analyze requirements|payload structure|request validation)\b',
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
                if title_lower.startswith("be -") or title_lower.startswith("msc -") or title_lower.startswith("[msc"):
                    be_patterns.add(pattern)
                elif title_lower.startswith("web -") or title_lower.startswith("fe -"):
                    web_patterns.add(re.sub(r'^fe\s*-', 'WEB -', pattern, flags=re.IGNORECASE))
                elif title_lower.startswith("mobile -") or title_lower.startswith("[mobile"):
                    mobile_patterns.add(pattern)

        return {
            "be": sorted(be_patterns)[:8],
            "web": sorted(web_patterns)[:8],
            "mobile": sorted(mobile_patterns)[:8],
        }
