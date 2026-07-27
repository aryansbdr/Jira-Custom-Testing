from typing import List
from modules.reporting.domain.models import Employee
from modules.reporting.infrastructure.pandas_excel_parser import PandasExcelParser


class ParseMembersUseCase:
    """
    Application use case for converting Excel files to Employee domain entities.
    """

    def __init__(self, excel_parser: PandasExcelParser):
        self.excel_parser = excel_parser

    def execute(self, file_contents: bytes) -> List[Employee]:
        return self.excel_parser.parse_employees(file_contents)
