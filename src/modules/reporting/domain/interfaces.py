from abc import ABC, abstractmethod
from typing import List, Dict, Any
from modules.reporting.domain.models import Employee


class IExcelParser(ABC):
    """
    Interface for parsing Excel files into domain models.
    """

    @abstractmethod
    def parse_employees(self, file_contents: bytes) -> List[Employee]:
        pass


class IWorkloadBalancer(ABC):
    """
    Interface for workload balancing domain service.
    """

    @abstractmethod
    def balance(
        self, employees: List[Employee], subtasks: List[Any]
    ) -> Dict[str, Any]:
        pass
