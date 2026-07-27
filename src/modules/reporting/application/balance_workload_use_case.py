from typing import List, Dict, Any
from modules.reporting.domain.models import Employee
from modules.reporting.domain.balancer_service import WorkloadBalancerService
from modules.generate_subtask.domain.models import Subtask


class BalanceWorkloadUseCase:
    """
    Application Use Case that coordinates workload balancing.
    """

    def __init__(self, balancer_service: WorkloadBalancerService):
        self.balancer_service = balancer_service

    def execute(
        self, employees: List[Employee], subtasks: List[Subtask]
    ) -> Dict[str, Any]:
        return self.balancer_service.balance(employees, subtasks)
