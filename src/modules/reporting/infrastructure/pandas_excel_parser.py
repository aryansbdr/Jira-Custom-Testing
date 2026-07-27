import pandas as pd
import io
import re
from typing import List
from modules.reporting.domain.models import Employee
from modules.generate_subtask.domain.models import Story, Subtask


class PandasExcelParser:
    """
    Pandas implementation for parsing Excel files.
    """

    def parse_employees(self, file_contents: bytes) -> List[Employee]:
        # Read strictly ONLY the first sheet (Index 0)
        df = pd.read_excel(io.BytesIO(file_contents), sheet_name=0)
        df.columns = [str(c).strip().lower() for c in df.columns]

        pn_col = next(
            (c for c in df.columns if "personal_number" in c or "pn" in c), None
        )
        name_col = next(
            (c for c in df.columns if "nama" in c or "name" in c or "pegawai" in c),
            None,
        )
        role_col = next((c for c in df.columns if "role" in c or "jabatan" in c), None)

        if not pn_col or not name_col or not role_col:
            raise ValueError(
                f"Excel columns must contain variations of 'PN', 'Nama/Name', and 'Role'. Found: {list(df.columns)}"
            )

        employees = []
        for _, row in df.iterrows():
            if pd.isna(row[pn_col]) or pd.isna(row[name_col]):
                continue
            pn_str = (
                str(int(row[pn_col]))
                if isinstance(row[pn_col], (int, float))
                else str(row[pn_col]).strip()
            )
            employees.append(
                Employee(
                    pn=pn_str,
                    name=str(row[name_col]).strip(),
                    role=str(row[role_col]).strip(),
                )
            )
        return employees

    def parse_stories(self, file_contents: bytes) -> List[Story]:
        # Read strictly ONLY the first sheet (Index 0)
        df = pd.read_excel(io.BytesIO(file_contents), sheet_name=0)
        df.columns = [str(c).strip().lower() for c in df.columns]

        code_col = next(
            (
                c
                for c in df.columns
                if "code" in c or "key" in c or "id" in c or "story" in c
            ),
            None,
        )
        title_col = next(
            (c for c in df.columns if "title" in c or "summary" in c or "judul" in c),
            None,
        )
        sp_col = next((c for c in df.columns if "point" in c or "sp" in c), None)
        desc_col = next(
            (c for c in df.columns if "desc" in c or "ac" in c or "kriteria" in c), None
        )

        if not title_col or not desc_col:
            raise ValueError(
                f"Excel must contain Title Story and Description Story columns. Found: {list(df.columns)}"
            )

        stories = []
        for _, row in df.iterrows():
            if pd.isna(row[title_col]) or pd.isna(row[desc_col]):
                continue
            sp_val = row[sp_col] if sp_col and not pd.isna(row[sp_col]) else 0.0
            try:
                sp_val = float(sp_val)
            except ValueError:
                sp_val = 0.0

            stories.append(
                Story(
                    key=str(row[code_col]).strip()
                    if code_col and not pd.isna(row[code_col])
                    else "STORY-GEN",
                    summary=str(row[title_col]).strip(),
                    story_points=sp_val,
                    description=str(row[desc_col]).strip(),
                )
            )
        return stories

    def parse_historical_import(self, file_contents: bytes) -> List[Story]:
        # Read strictly ONLY the first sheet (Index 0)
        sheet_df = pd.read_excel(io.BytesIO(file_contents), sheet_name=0)
        if sheet_df.empty:
            return []

        # Standardize header names for the first sheet
        new_cols = []
        seen_canonical = set()
        for c in sheet_df.columns:
            c_str = str(c).strip().lower()
            if "sub" in c_str and ("task" in c_str or "title" in c_str or "judul" in c_str) and "subtask_title" not in seen_canonical:
                new_cols.append("subtask_title")
                seen_canonical.add("subtask_title")
            elif ("code" in c_str or "key" in c_str or "id" in c_str) and "code_story" not in seen_canonical:
                new_cols.append("code_story")
                seen_canonical.add("code_story")
            elif ("title" in c_str or "summary" in c_str or "judul" in c_str or "issues" in c_str) and "title_story" not in seen_canonical:
                new_cols.append("title_story")
                seen_canonical.add("title_story")
            elif ("desc" in c_str or "ac" in c_str or "kriteria" in c_str) and "description_story" not in seen_canonical:
                new_cols.append("description_story")
                seen_canonical.add("description_story")
            elif ("type" in c_str or "jenis" in c_str or "tipe" in c_str) and "issue_type" not in seen_canonical:
                new_cols.append("issue_type")
                seen_canonical.add("issue_type")
            elif ("point" in c_str or "sp" in c_str) and "story_point" not in seen_canonical:
                new_cols.append("story_point")
                seen_canonical.add("story_point")
            elif "role" in c_str and "role" not in seen_canonical:
                new_cols.append("role")
                seen_canonical.add("role")
            else:
                new_cols.append(c_str)
        
        sheet_df.columns = new_cols
        df = sheet_df

        code_col = "code_story" if "code_story" in df.columns else None
        title_col = "title_story" if "title_story" in df.columns else None
        desc_col = "description_story" if "description_story" in df.columns else None
        sp_col = "story_point" if "story_point" in df.columns else None
        type_col = "issue_type" if "issue_type" in df.columns else None
        sub_title_col = "subtask_title" if "subtask_title" in df.columns else None
        sub_role_col = "role" if "role" in df.columns else None
        sub_sp_col = None

        if not title_col or not desc_col:
            raise ValueError("Missing required Title Story or Description Story columns.")

        def _detect_issue_type(title_text: str, key_text: str) -> str:
            t_lower = (title_text + " " + key_text).lower()
            if "bug" in t_lower or "error" in t_lower or "fix" in t_lower:
                return "Bug"
            elif "task" in t_lower:
                return "Task"
            elif "security" in t_lower or "review" in t_lower or "audit" in t_lower or "arsitektur" in t_lower:
                return "Architecture"
            elif "doc" in t_lower or "dokumentasi" in t_lower:
                return "Documentation"
            return "Story"

        stories_dict = {}
        for _, row in df.iterrows():
            key = (
                str(row[code_col]).strip()
                if code_col and not pd.isna(row[code_col])
                else str(row[title_col]).strip()
            )
            if not key or pd.isna(row[title_col]):
                continue

            raw_title = str(row[title_col]).strip()
            if not raw_title or raw_title.lower() == "nan":
                continue

            raw_desc = (
                str(row[desc_col]).strip()
                if desc_col and not pd.isna(row[desc_col]) and str(row[desc_col]).strip().lower() != "nan"
                else raw_title
            )

            if key not in stories_dict:
                sp_val = (
                    row[sp_col]
                    if sp_col and not pd.isna(row[sp_col])
                    else 0.0
                )
                try:
                    sp_val = float(sp_val)
                except ValueError:
                    sp_val = 0.0

                detected_type = (
                    str(row[type_col]).strip()
                    if type_col and not pd.isna(row[type_col])
                    else _detect_issue_type(raw_title, key)
                )

                stories_dict[key] = Story(
                    key=str(row[code_col]).strip()
                    if code_col and not pd.isna(row[code_col])
                    else key,
                    summary=raw_title,
                    story_points=sp_val,
                    description=raw_desc,
                    issue_type=detected_type,
                )

            if sub_title_col and sub_title_col in df.columns and not pd.isna(row[sub_title_col]):
                raw_sub_text = str(row[sub_title_col]).strip()
                if raw_sub_text and raw_sub_text.lower() != "nan":
                    # Smart split by numbered pattern (1., 2., 3.) or newlines
                    if re.search(r'\d+\.\s*', raw_sub_text):
                        sub_chunks = re.split(r'\n?\s*\d+\.\s*', raw_sub_text)
                    else:
                        sub_chunks = raw_sub_text.split('\n')

                    for chunk in sub_chunks:
                        # Extract first meaningful line in chunk, ignoring noise like 'Actions'
                        lines = [line_str.strip() for line_str in chunk.split('\n') if line_str.strip()]
                        for line_item in lines:
                            cleaned_item = line_item.strip()
                            item_lower = cleaned_item.lower()

                            # Filter out noise words and extremely short items
                            if not cleaned_item or item_lower in ["actions", "action", "subtask", "subtasks", "nan", "none"] or len(cleaned_item) < 3:
                                continue

                            sub_sp = (
                                row[sub_sp_col]
                                if sub_sp_col and sub_sp_col in df.columns and not pd.isna(row[sub_sp_col])
                                else 0.0
                            )
                            try:
                                sub_sp = float(sub_sp)
                            except ValueError:
                                sub_sp = 0.0

                            # Auto-detect role from title prefix and system tags
                            detected_role = "Developer"
                            if any(kw in item_lower for kw in ["mobile", "[mobile", "app", "prescreening app", "pemrakarsa", "pemutus"]):
                                detected_role = "mobile"
                            elif item_lower.startswith("fe -") or item_lower.startswith("web -") or item_lower.startswith("wlb -") or item_lower.startswith("[web"):
                                detected_role = "frontend"
                            elif item_lower.startswith("be -") or item_lower.startswith("service -") or "[mcs" in item_lower or "[las" in item_lower or "mcs core" in item_lower:
                                detected_role = "backend"
                            elif item_lower.startswith("qa -") or "review" in item_lower:
                                detected_role = "qa"

                            if sub_role_col and sub_role_col in df.columns and not pd.isna(row[sub_role_col]):
                                detected_role = str(row[sub_role_col]).strip()

                            stories_dict[key].add_subtask(
                                Subtask(
                                    summary=cleaned_item,
                                    description="",
                                    role=detected_role,
                                    story_points=sub_sp if sub_sp > 0 else 1.0,
                                )
                            )

        # Filter: Only return quality reference stories that have Description AND at least 1 Subtask
        quality_stories = [s for s in stories_dict.values() if s.subtasks and len(s.subtasks) > 0]
        return quality_stories
