from typing import List, Dict, Any
from shared.config import settings
from modules.reporting.domain.models import Employee
from modules.generate_subtask.domain.models import Subtask


class WorkloadBalancerService:
    """
    Domain service executing Greedy LPT workload balancing.
    """

    def balance(
        self, employees: List[Employee], subtasks: List[Subtask]
    ) -> Dict[str, Any]:
        def _normalize_role(r_str: str) -> str:
            s = str(r_str or "").strip().lower()
            if "back" in s or s == "be":
                return "be"
            if "front" in s or "web" in s or s == "fe":
                return "web"
            if "mob" in s or "android" in s or "ios" in s or "app" in s:
                return "mobile"
            return settings.ROLE_MAPPINGS.get(s, s).strip().lower()

        active_roles_lower = {"be", "web", "mobile"}

        # Track workload allocations only for active engineering roles (BE, WEB, Mobile)
        employee_loads = {
            emp.pn: {
                "employee": emp.to_dict(),
                "assigned_subtasks": [],
                "total_story_points": 0.0,
            }
            for emp in employees
            if _normalize_role(emp.role) in active_roles_lower
        }
        
        employees_by_role = {}
        for emp in employees:
            mapped_norm = _normalize_role(emp.role)
            if mapped_norm not in active_roles_lower:
                continue
            if mapped_norm not in employees_by_role:
                employees_by_role[mapped_norm] = []
            employees_by_role[mapped_norm].append(emp.pn)

        unassigned_subtasks = []

        # Group subtasks by (role_norm, parent_key) block
        # Guarantees that ALL subtasks under 1 Story for 1 role go to the SAME person
        role_parent_blocks = {}
        for sub in subtasks:
            mapped_role_norm = _normalize_role(sub.role)
            pkey = getattr(sub, "parent_key", None) or "GENERAL"
            
            key = (mapped_role_norm, pkey)
            if key not in role_parent_blocks:
                role_parent_blocks[key] = []
            role_parent_blocks[key].append(sub)

        # Group blocks by role_norm
        blocks_by_role = {}
        for (role_norm, pkey), block_subs in role_parent_blocks.items():
            if role_norm not in blocks_by_role:
                blocks_by_role[role_norm] = []
            blocks_by_role[role_norm].append(block_subs)

        # Distribute workloads role by role (Story block by Story block)
        for role_norm, blocks in blocks_by_role.items():
            candidate_pns = employees_by_role.get(role_norm, [])

            # Fuzzy match if exact is missing
            if not candidate_pns:
                candidate_pns = []
                for emp_role_norm, pns in employees_by_role.items():
                    if role_norm in emp_role_norm or emp_role_norm in role_norm:
                        candidate_pns.extend(pns)

            if not candidate_pns:
                for block in blocks:
                    for sub in block:
                        unassigned_subtasks.append(sub.to_dict())
                continue

            # Sort blocks descending by total SP (LPT heuristic per story block)
            sorted_blocks = sorted(
                blocks,
                key=lambda blk: sum(s.story_points for s in blk),
                reverse=True
            )

            for blk in sorted_blocks:
                # Find candidate with the minimum total workload points
                selected_pn = min(
                    candidate_pns,
                    key=lambda pn: employee_loads[pn]["total_story_points"],
                )

                blk_sp = sum(s.story_points for s in blk)
                for sub in blk:
                    employee_loads[selected_pn]["assigned_subtasks"].append(sub.to_dict())
                employee_loads[selected_pn]["total_story_points"] += blk_sp

        return {
            "assignments": list(employee_loads.values()),
            "unassigned_subtasks": unassigned_subtasks,
        }
