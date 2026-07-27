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
        # Track workload allocations
        employee_loads = {
            emp.pn: {
                "employee": emp.to_dict(),
                "assigned_subtasks": [],
                "total_story_points": 0.0,
            }
            for emp in employees
        }

        # Index employee PNs by role
        employees_by_role = {}
        for emp in employees:
            role_norm = emp.role.strip().lower()
            if role_norm not in employees_by_role:
                employees_by_role[role_norm] = []
            employees_by_role[role_norm].append(emp.pn)

        unassigned_subtasks = []

        # Group subtasks by role key
        subtasks_by_role = {}
        for sub in subtasks:
            sub_role_key = sub.role.lower()
            mapped_role_name = settings.ROLE_MAPPINGS.get(sub_role_key, sub_role_key)
            mapped_role_norm = mapped_role_name.strip().lower()

            if mapped_role_norm not in subtasks_by_role:
                subtasks_by_role[mapped_role_norm] = []
            subtasks_by_role[mapped_role_norm].append(sub)

        # Distribute workloads role by role
        for role_norm, role_subs in subtasks_by_role.items():
            candidate_pns = employees_by_role.get(role_norm, [])

            # Fuzzy match if exact is missing
            if not candidate_pns:
                candidate_pns = []
                for emp_role_norm, pns in employees_by_role.items():
                    if role_norm in emp_role_norm or emp_role_norm in role_norm:
                        candidate_pns.extend(pns)

            if not candidate_pns:
                for sub in role_subs:
                    unassigned_subtasks.append(sub.to_dict())
                continue

            # Sort subtasks descending by effort (LPT heuristic)
            sorted_subs = sorted(role_subs, key=lambda x: x.story_points, reverse=True)

            for sub in sorted_subs:
                # Find candidate with the minimum total workload points
                selected_pn = min(
                    candidate_pns,
                    key=lambda pn: employee_loads[pn]["total_story_points"],
                )

                employee_loads[selected_pn]["assigned_subtasks"].append(sub.to_dict())
                employee_loads[selected_pn]["total_story_points"] += sub.story_points

        return {
            "assignments": list(employee_loads.values()),
            "unassigned_subtasks": unassigned_subtasks,
        }
