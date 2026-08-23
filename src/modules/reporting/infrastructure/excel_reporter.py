"""
Excel Reporter Infrastructure Service.

Generates executive-ready Excel reports (.xlsx) for Sprint & Squad Progress,
featuring multi-date snapshots, developer donut charts, horizontal burndown bars,
and grouped hierarchical subtask tables with native openpyxl formatting.
"""

import os
import re
import datetime
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
from openpyxl.chart import BarChart, DoughnutChart, Reference
from openpyxl.chart.data_source import AxDataSource, StrRef, StrData, StrVal
from openpyxl.chart.label import DataLabelList
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.worksheet import Worksheet

from shared.config import settings


class ReportTheme:
    """Centralized typography, color palettes, and borders for Excel reports."""

    # Typography
    FONT_MAIN_TITLE = Font(name="Segoe UI", size=15, bold=True, color="1F4E79")
    FONT_SECTION_TITLE = Font(name="Segoe UI", size=12, bold=True, color="1F4E79")
    FONT_SUBTITLE = Font(name="Segoe UI", size=10, italic=True, color="595959")
    FONT_HEADER = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
    FONT_DATA = Font(name="Segoe UI", size=10)
    FONT_BOLD = Font(name="Segoe UI", size=10, bold=True)
    FONT_LINK = Font(name="Segoe UI", size=10, color="0563C1", underline="single")
    FONT_PARENT_BOLD = Font(name="Segoe UI", size=10, bold=True, color="1F4E79")
    FONT_SUBTASK_INDENT = Font(name="Segoe UI", size=9, color="333333")
    FONT_SUBTASK_LINK = Font(name="Segoe UI", size=9, color="0563C1", underline="single")
    FONT_SUBTASK_ROLE = Font(name="Segoe UI", size=9, italic=True, color="595959")
    FONT_MUTED = Font(name="Segoe UI", size=9, italic=True, color="595959")
    FONT_KPI_LABEL = Font(name="Segoe UI", size=9, bold=True, color="595959")
    FONT_KPI_VALUE = Font(name="Segoe UI", size=11, bold=True, color="1F4E79")

    # Status Badges
    FONT_STATUS_DONE = Font(name="Segoe UI", size=10, bold=True, color="276A3C")
    FONT_STATUS_PROG = Font(name="Segoe UI", size=10, bold=True, color="1F4E79")
    FONT_STATUS_TODO = Font(name="Segoe UI", size=10, bold=True, color="595959")

    FILL_STATUS_DONE = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    FILL_STATUS_PROG = PatternFill(start_color="DDEBF7", end_color="DDEBF7", fill_type="solid")
    FILL_STATUS_TODO = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")

    # Table Fills
    FILL_HEADER = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    FILL_SUB_HEADER = PatternFill(start_color="2E75B6", end_color="2E75B6", fill_type="solid")
    FILL_TOTAL = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    FILL_ZEBRA = PatternFill(start_color="F9FAFC", end_color="F9FAFC", fill_type="solid")
    FILL_PARENT_STORY = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    FILL_PARENT_GROUP = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    # Borders
    THIN_BORDER = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )
    TOTAL_TOP_BOTTOM_BORDER = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="1F4E79"),
        bottom=Side(style="double", color="1F4E79"),
    )


class ExcelReporter:
    """
    Generates structured, executive-ready Excel reports (.xlsx) with native openpyxl charts,
    collapsible hierarchies, and multi-date historical snapshots.
    """

    @staticmethod
    def _get_professional_filename(safe_key: str, report_data: Dict[str, Any] = None) -> str:
        raw_key = str((report_data or {}).get("root_key") or safe_key or "").strip()
        
        # 1. Extract Squad / Component name if present
        comp_match = re.search(r"component\s*(?:=|\bIN\b)\s*\(?['\"]?([^'\")]*)['\"]?\)?", raw_key, re.IGNORECASE)
        if comp_match:
            comp_name = comp_match.group(1).strip()
            clean_comp = re.sub(r'[^\w\s-]', '', comp_name).strip()
            clean_comp = re.sub(r'[\s-]+', '_', clean_comp)
            if clean_comp:
                return clean_comp

        # 2. Extract Project name if JQL specifies project
        proj_match = re.search(r"project\s*=\s*['\"]?([A-Za-z0-9_]+)['\"]?", raw_key, re.IGNORECASE)
        if proj_match and len(raw_key) > 25:
            p_val = proj_match.group(1).strip()
            return f"Project_{p_val}"

        # 3. Check for Dashboard title in report_data
        if report_data and report_data.get("root_summary"):
            summary = str(report_data.get("root_summary")).strip()
            clean_sum = re.sub(r'[^\w\s-]', '', summary).strip()
            clean_sum = re.sub(r'[\s-]+', '_', clean_sum)
            if 2 <= len(clean_sum) <= 35 and "custom" not in clean_sum.lower():
                return clean_sum

        # 4. Numeric Dashboard / Filter ID
        if raw_key.isdigit():
            return f"Dashboard_{raw_key}"

        # 5. Clean short key (e.g. "BL-38812", "BL", "JT")
        if len(raw_key) <= 25 and not (" " in raw_key or "=" in raw_key):
            clean_raw = re.sub(r'[^\w\s-]', '', raw_key).strip()
            clean_raw = re.sub(r'[\s-]+', '_', clean_raw)
            if clean_raw:
                return clean_raw

        return "Squad_Progress"

    def generate_progress_report(
        self, report_data: Dict[str, Any], safe_key: str, output_path: str = "."
    ) -> str:
        """
        Main entrypoint to generate or update the Sprint & Squad Progress Excel report (.xlsx).
        Creates a dedicated sheet per date for multi-date sprint tracking.

        Output folder structure:
            Laporan/{PROJECT}/{YYYY}/{MM-MMMM}/{DD-MM-YYYY}_{SQUAD_NAME}.xlsx

        Example:
            Laporan/BL/2026/08-Agustus/Laporan_Progress_Squad_Korporasi_23-08-2026.xlsx
        """
        base_jira_url = settings.JIRA_URL.rstrip("/")
        root_key = report_data.get("root_key", safe_key)
        root_summary = report_data.get("root_summary", "")

        today_date_str = datetime.datetime.now().strftime("%d-%m-%Y")
        sheet_title = today_date_str

        prof_name = self._get_professional_filename(safe_key, report_data)
        filename = f"Laporan_Progress_{prof_name}_{today_date_str}.xlsx"

        # ---------------------------------------------------------------
        # Build structured output folder: Laporan/{PROJECT}/{YYYY}/{MM-NamaBulan}/
        # ---------------------------------------------------------------
        # Extract project code from root_key (e.g. "BL" from "BL-38812", or "JT" from "JT-161")
        project_code = "Umum"
        raw_key_for_proj = str(root_key or safe_key or "").strip()
        proj_prefix_match = re.match(r'^([A-Za-z]{1,8})(?:-\d+)?$', raw_key_for_proj)
        if proj_prefix_match:
            project_code = proj_prefix_match.group(1).upper()
        else:
            # Try to extract from JQL: project = BL or project = "BL"
            jql_proj = re.search(r'project\s*=\s*[\'"]?([A-Za-z0-9_]+)[\'"]?', raw_key_for_proj, re.IGNORECASE)
            if jql_proj:
                project_code = jql_proj.group(1).upper()

        # Build YYYY and MM-NamaBulan folder names
        now = datetime.datetime.now()
        year_folder = now.strftime("%Y")
        bulan_id = [
            "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
            "Juli", "Agustus", "September", "Oktober", "November", "Desember"
        ]
        month_folder = f"{now.strftime('%m')}-{bulan_id[now.month]}"

        # Compose final folder path (relative to output_path base)
        structured_folder = os.path.join(output_path, "Laporan", project_code, year_folder, month_folder)
        os.makedirs(structured_folder, exist_ok=True)

        full_path = os.path.join(structured_folder, filename)

        # 1. Initialize Workbook & Worksheet
        workbook, worksheet, chart_worksheet = self._initialize_workbook(full_path, sheet_title)
        theme = ReportTheme()

        # 2. Render Header Block & Top KPI Cards
        self._render_header_and_kpis(
            worksheet=worksheet,
            report_data=report_data,
            root_key=root_key,
            root_summary=root_summary,
            today_date_str=today_date_str,
            theme=theme,
        )

        # 3. Render Section 1: Developer Summary Table & Donut Charts
        member_progress = report_data.get("member_progress", [])
        overall_status = report_data.get("overall_status", {})
        total_member_row, active_members = self._render_developer_summary(
            worksheet=worksheet,
            member_progress=member_progress,
            overall_status=overall_status,
            theme=theme,
        )
        max_chart_bottom_row = self._render_developer_donut_charts(
            worksheet=worksheet,
            chart_worksheet=chart_worksheet,
            active_members=active_members,
            overall_status=overall_status,
            total_member_row=total_member_row,
        )

        # 4. Render Section 2: Progress per Parent Story / Epic (placed below BOTH table and charts)
        section_2_start_row = max(total_member_row + 4, max_chart_bottom_row + 3, 27)
        section_2_end_row, active_chart_stories = self._render_story_progress_section(
            worksheet=worksheet,
            report_data=report_data,
            start_row=section_2_start_row,
            base_jira_url=base_jira_url,
            theme=theme,
        )
        self._render_story_progress_chart(
            worksheet=worksheet,
            chart_worksheet=chart_worksheet,
            active_chart_stories=active_chart_stories,
            chart_start_row=section_2_start_row,
        )

        # 5. Render Section 3: Detailed Subtask Table with Vertically Merged Parent Stories
        adaptive_chart_height = max(11, len(active_chart_stories) * 3.2 + 2)
        section_3_start_row = max(section_2_end_row + 4, section_2_start_row + int(adaptive_chart_height) + 4)
        detailed_subtasks = report_data.get("detailed_subtasks", [])
        
        self._render_subtask_details_section(
            worksheet=worksheet,
            detailed_subtasks=detailed_subtasks,
            start_row=section_3_start_row,
            base_jira_url=base_jira_url,
            theme=theme,
        )
        self._render_role_distribution_chart(
            worksheet=worksheet,
            chart_worksheet=chart_worksheet,
            detailed_subtasks=detailed_subtasks,
            start_row=section_3_start_row,
        )

        # 6. Apply Optimal Column Widths
        self._apply_column_dimensions(worksheet)

        # 7. Save Workbook Safely
        return self._save_workbook(workbook, full_path, safe_key, output_path, filename)

    # =========================================================================
    # INTERNAL HELPER METHODS (MODULAR DECOMPOSITION)
    # =========================================================================

    def _initialize_workbook(
        self, full_path: str, sheet_title: str
    ) -> Tuple[openpyxl.Workbook, Worksheet, Worksheet]:
        """Initializes or loads an existing workbook, setting up a fresh sheet for today's snapshot and a hidden chart data sheet."""
        chart_sheet_title = f"_ChartData_{sheet_title}"
        if os.path.exists(full_path):
            try:
                workbook = openpyxl.load_workbook(full_path)
                if sheet_title in workbook.sheetnames:
                    workbook.remove(workbook[sheet_title])
                if chart_sheet_title in workbook.sheetnames:
                    workbook.remove(workbook[chart_sheet_title])
                worksheet = workbook.create_sheet(title=sheet_title)
                chart_worksheet = workbook.create_sheet(title=chart_sheet_title)
            except Exception:
                workbook = openpyxl.Workbook()
                worksheet = workbook.active
                worksheet.title = sheet_title
                chart_worksheet = workbook.create_sheet(title=chart_sheet_title)
        else:
            workbook = openpyxl.Workbook()
            worksheet = workbook.active
            worksheet.title = sheet_title
            chart_worksheet = workbook.create_sheet(title=chart_sheet_title)

        chart_worksheet.sheet_state = "hidden"
        workbook.active = worksheet
        worksheet.views.sheetView[0].showGridLines = True
        return workbook, worksheet, chart_worksheet

    def _format_sprint_date(self, date_value: Any) -> str:
        """Formats ISO or slash-separated date strings into readable Indonesian/Standard format."""
        if not date_value:
            return "-"
        date_str = str(date_value).strip()
        try:
            if "/" in date_str:
                parts = date_str.split()[0].split("/")
                if len(parts) == 3:
                    day, month, yr = parts
                    if len(yr) == 2:
                        yr = "20" + yr
                    return f"{int(day):02d} {month.capitalize()} {yr}"
            elif "-" in date_str:
                parts = date_str[:10].split("-")
                if len(parts) == 3:
                    yr, month, day = parts
                    import calendar
                    month_name = calendar.month_abbr[int(month)]
                    return f"{int(day):02d} {month_name} {yr}"
        except Exception:
            pass
        return date_str[:11]

    def _render_header_and_kpis(
        self,
        worksheet: Worksheet,
        report_data: Dict[str, Any],
        root_key: str,
        root_summary: str,
        today_date_str: str,
        theme: ReportTheme,
    ) -> None:
        """Renders the top banner and KPI summary cards."""
        now_str = datetime.datetime.now().strftime("%d %B %Y, %H:%M WIB")
        sprint_info = report_data.get("sprint_info") or {}
        sprint_name = sprint_info.get("name") or sprint_info.get("sprintName") or "Active Sprint"
        days_remaining = sprint_info.get("days_remaining") if sprint_info.get("days_remaining") is not None else sprint_info.get("daysRemaining")
        start_date_fmt = sprint_info.get("startDateStr") or self._format_sprint_date(sprint_info.get("start_date"))
        end_date_fmt = sprint_info.get("dueDateStr") or self._format_sprint_date(sprint_info.get("end_date"))

        # 1. Main Title & Subtitle
        worksheet["A1"] = f"LAPORAN PROGRESS SQUAD & SPRINT: {root_key} ({today_date_str})"
        worksheet["A1"].font = theme.FONT_MAIN_TITLE
        
        if days_remaining is not None:
            sprint_sub = f"{root_summary} | Periode: {start_date_fmt} s/d {end_date_fmt} | Sisa Waktu: {days_remaining} Hari Kerja | Diekspor: {now_str}"
        else:
            sprint_sub = f"{root_summary} | Diekspor pada: {now_str}"
        
        worksheet["A2"] = sprint_sub
        worksheet["A2"].font = theme.FONT_SUBTITLE
        worksheet.row_dimensions[1].height = 24
        worksheet.row_dimensions[2].height = 18

        # 2. KPI Summary Cards (Rows 4-5)
        overall = report_data.get("overall_status", {})
        epics_count = report_data.get("total_epics_count", 0)
        kpi_labels = [
            "Sprint Aktif",
            "Start Date",
            "End Date (Due)",
            "Sisa Waktu Sprint",
            "Total Story",
            "Total Subtask",
            "To Do",
            "In Progress",
            "Done (Selesai)",
            "% Penyelesaian",
        ]
        kpi_values = [
            sprint_name,
            start_date_fmt,
            end_date_fmt,
            f"{days_remaining} Hari Kerja" if days_remaining is not None else "-",
            epics_count,
            overall.get("total", 0),
            overall.get("todo", 0),
            overall.get("in_progress", 0),
            overall.get("done", 0),
            f"{overall.get('percent_done', 0.0)}%",
        ]

        for col_idx, (lbl, val) in enumerate(zip(kpi_labels, kpi_values), 1):
            cell_lbl = worksheet.cell(row=4, column=col_idx, value=lbl)
            cell_lbl.font = theme.FONT_KPI_LABEL
            cell_lbl.alignment = Alignment(horizontal="center", vertical="center")
            cell_lbl.fill = theme.FILL_ZEBRA
            cell_lbl.border = theme.THIN_BORDER

            cell_val = worksheet.cell(row=5, column=col_idx, value=val)
            cell_val.font = theme.FONT_KPI_VALUE
            cell_val.alignment = Alignment(horizontal="center", vertical="center")
            cell_val.fill = theme.FILL_TOTAL
            cell_val.border = theme.THIN_BORDER

        worksheet.row_dimensions[4].height = 18
        worksheet.row_dimensions[5].height = 24

    def _render_developer_summary(
        self,
        worksheet: Worksheet,
        member_progress: List[Dict[str, Any]],
        overall_status: Optional[Dict[str, Any]] = None,
        theme: ReportTheme = ReportTheme(),
    ) -> Tuple[int, List[Dict[str, Any]]]:
        """Renders Section 1 table: Developer progress summary and Total row."""
        worksheet["A7"] = "1. RINGKASAN PROGRESS PER DEVELOPER"
        worksheet["A7"].font = theme.FONT_SECTION_TITLE
        worksheet.row_dimensions[7].height = 22

        member_headers = [
            "Nama Developer",
            "Role",
            "To Do",
            "In Progress",
            "Done",
            "Total Subtask",
            "% Selesai",
        ]
        for col_idx, header_text in enumerate(member_headers, 1):
            cell = worksheet.cell(row=8, column=col_idx, value=header_text)
            cell.font = theme.FONT_HEADER
            cell.fill = theme.FILL_HEADER
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = theme.THIN_BORDER
        worksheet.row_dimensions[8].height = 22

        # Separate real members vs unassigned
        real_members = [
            m for m in member_progress 
            if not m.get("is_unassigned") and "unassigned" not in str(m.get("name", "")).lower()
        ]
        unassigned_entry = next(
            (m for m in member_progress if m.get("is_unassigned") or "unassigned" in str(m.get("name", "")).lower()), 
            None
        )

        active_members = [m for m in real_members if m.get("total_subtasks", 0) > 0]
        active_members.sort(key=lambda x: x.get("total_subtasks", 0), reverse=True)
        idle_members = [m for m in real_members if m.get("total_subtasks", 0) == 0]
        idle_members.sort(key=lambda x: x.get("name", ""))

        sorted_members = list(active_members)

        if unassigned_entry:
            sorted_members.append(unassigned_entry)
        elif overall_status:
            # Fallback calculate unassigned if not present in member_progress
            assigned_todo = sum(m.get("todo", 0) for m in real_members)
            assigned_prog = sum(m.get("in_progress", 0) for m in real_members)
            assigned_done = sum(m.get("done", 0) for m in real_members)

            unassigned_todo = max(0, overall_status.get("todo", 0) - assigned_todo)
            unassigned_prog = max(0, overall_status.get("in_progress", 0) - assigned_prog)
            unassigned_done = max(0, overall_status.get("done", 0) - assigned_done)
            unassigned_total = unassigned_todo + unassigned_prog + unassigned_done
            if unassigned_total > 0:
                sorted_members.append({
                    "name": "Belum Diambil (Unassigned)",
                    "role": "-",
                    "todo": unassigned_todo,
                    "in_progress": unassigned_prog,
                    "done": unassigned_done,
                    "total_subtasks": unassigned_total,
                    "is_unassigned": True,
                })

        sorted_members.extend(idle_members)

        current_row = 9
        for idx, member in enumerate(sorted_members):
            row_fill = theme.FILL_ZEBRA if idx % 2 == 1 else PatternFill(fill_type=None)
            
            cell_name = worksheet.cell(row=current_row, column=1, value=member.get("name", ""))
            cell_role = worksheet.cell(row=current_row, column=2, value=member.get("role", ""))
            cell_todo = worksheet.cell(row=current_row, column=3, value=member.get("todo", 0))
            cell_prog = worksheet.cell(row=current_row, column=4, value=member.get("in_progress", 0))
            cell_done = worksheet.cell(row=current_row, column=5, value=member.get("done", 0))
            cell_tot  = worksheet.cell(row=current_row, column=6, value=f"=SUM(C{current_row}:E{current_row})")
            cell_pct  = worksheet.cell(row=current_row, column=7, value=f'=IF(F{current_row}=0, 0, E{current_row}/F{current_row})')

            is_bold = member.get("total_subtasks", 0) > 0 and not member.get("is_unassigned")
            cell_name.font = theme.FONT_BOLD if is_bold else (theme.FONT_MUTED if member.get("is_unassigned") else theme.FONT_DATA)
            cell_role.font = theme.FONT_DATA
            cell_todo.font = theme.FONT_DATA
            cell_prog.font = theme.FONT_DATA
            cell_done.font = theme.FONT_DATA
            cell_tot.font = theme.FONT_BOLD
            cell_pct.font = theme.FONT_BOLD

            cell_name.alignment = Alignment(horizontal="left", vertical="center")
            cell_role.alignment = Alignment(horizontal="center", vertical="center")
            cell_todo.alignment = Alignment(horizontal="right", vertical="center")
            cell_prog.alignment = Alignment(horizontal="right", vertical="center")
            cell_done.alignment = Alignment(horizontal="right", vertical="center")
            cell_tot.alignment  = Alignment(horizontal="right", vertical="center")
            cell_pct.alignment  = Alignment(horizontal="right", vertical="center")
            cell_pct.number_format = "0.0%"

            for col_idx in range(1, 8):
                cell_obj = worksheet.cell(row=current_row, column=col_idx)
                cell_obj.border = theme.THIN_BORDER
                if row_fill.fill_type:
                    cell_obj.fill = row_fill

            worksheet.row_dimensions[current_row].height = 20
            current_row += 1

        # Total Row
        total_member_row = current_row
        worksheet.cell(row=total_member_row, column=1, value="Total Akumulasi Tim").font = theme.FONT_BOLD
        worksheet.cell(row=total_member_row, column=2, value="").font = theme.FONT_BOLD
        worksheet.cell(row=total_member_row, column=3, value=f"=SUM(C9:C{total_member_row-1})").font = theme.FONT_BOLD
        worksheet.cell(row=total_member_row, column=4, value=f"=SUM(D9:D{total_member_row-1})").font = theme.FONT_BOLD
        worksheet.cell(row=total_member_row, column=5, value=f"=SUM(E9:E{total_member_row-1})").font = theme.FONT_BOLD
        worksheet.cell(row=total_member_row, column=6, value=f"=SUM(F9:F{total_member_row-1})").font = theme.FONT_BOLD

        cell_pct_total = worksheet.cell(row=total_member_row, column=7, value=f'=IF(F{total_member_row}=0, 0, E{total_member_row}/F{total_member_row})')
        cell_pct_total.font = theme.FONT_BOLD
        cell_pct_total.number_format = "0.0%"

        for col_idx in range(1, 8):
            cell_obj = worksheet.cell(row=total_member_row, column=col_idx)
            cell_obj.fill = theme.FILL_TOTAL
            cell_obj.border = theme.TOTAL_TOP_BOTTOM_BORDER
            if col_idx >= 3:
                cell_obj.alignment = Alignment(horizontal="right", vertical="center")
        
        worksheet.row_dimensions[total_member_row].height = 22
        return total_member_row, active_members

    def _render_developer_donut_charts(
        self,
        worksheet: Worksheet,
        chart_worksheet: Worksheet,
        active_members: List[Dict[str, Any]],
        overall_status: Dict[str, Any],
        total_member_row: int,
    ) -> int:
        """Renders clean Donut Charts per active developer + Overall Sprint status in a multi-row grid layout."""
        chart_columns = ["J", "Q", "X", "AE"]
        eligible_devs = [
            m for m in active_members 
            if str(m.get("name", "")).strip().lower() not in ("unassigned", "belum diambil (unassigned)", "total", "total akumulasi tim", "-", "")
            and m.get("total_subtasks", 0) > 0
        ]

        # 1. Slot 0: Overall Sprint Status Donut
        todo_total = int(overall_status.get("todo", 0))
        prog_total = int(overall_status.get("in_progress", 0))
        done_total = int(overall_status.get("done", 0))

        overall_slices = []
        if todo_total > 0:
            overall_slices.append(("To Do", todo_total))
        if prog_total > 0:
            overall_slices.append(("In Progress", prog_total))
        if done_total > 0:
            overall_slices.append(("Done", done_total))

        if not overall_slices:
            overall_slices.append(("To Do", 0))

        chart_worksheet.cell(row=1, column=1, value="Status")
        chart_worksheet.cell(row=1, column=2, value="Jumlah")

        for os_idx, (os_label, os_val) in enumerate(overall_slices, 2):
            chart_worksheet.cell(row=os_idx, column=1, value=os_label)
            chart_worksheet.cell(row=os_idx, column=2, value=os_val)

        chart_pie = DoughnutChart()
        chart_pie.title = "Proporsi Status Sprint Keseluruhan"
        chart_pie.dataLabels = DataLabelList()
        chart_pie.dataLabels.showPercent = True
        chart_pie.dataLabels.showVal = False
        chart_pie.dataLabels.showCatName = False
        chart_pie.dataLabels.showSerName = False
        chart_pie.dataLabels.showLegendKey = False
        chart_pie.dataLabels.numFmt = "0%"
        chart_pie.legend.legendPos = "b"

        data_ref_pie = Reference(chart_worksheet, min_col=2, min_row=1, max_row=1 + len(overall_slices))
        cats_ref_pie = Reference(chart_worksheet, min_col=1, min_row=2, max_row=1 + len(overall_slices))
        chart_pie.add_data(data_ref_pie, titles_from_data=True)
        chart_pie.set_categories(cats_ref_pie)
        # Overall sprint chart placed at AE6 - far right after all developer donut charts, no overlap with any table
        chart_pie.height = 11
        chart_pie.width = 10
        worksheet.add_chart(chart_pie, "AE6")

        max_chart_bottom_row = 20

        # HYBRID CHART SELECTION:
        # Case A: If 1 <= len(eligible_devs) <= 6 -> Generate clean Pie/Donut Charts per Developer!
        if 1 <= len(eligible_devs) <= 6:
            # Each chart is ~10 cols wide. Layout: Row 1 → J6, Q6, X6 | Row 2 → J22, Q22, X22
            # Column J=10, Q=17, X=24 → 7 columns apart → no overlap for width=10
            chart_columns = ["J", "Q", "X", "J", "Q", "X"]
            for dev_idx, dev in enumerate(eligible_devs):
                grid_col_letter = chart_columns[dev_idx % len(chart_columns)]
                grid_row_start = 6 if dev_idx < 3 else 22

                dev_name = dev.get("name", f"Developer {dev_idx+1}")
                dev_role = dev.get("role", "")

                col_cat = (dev_idx + 1) * 3 + 1
                col_val = (dev_idx + 1) * 3 + 2

                todo_count = int(dev.get("todo", 0))
                prog_count = int(dev.get("in_progress", 0))
                done_count = int(dev.get("done", 0))

                status_slices = []
                if todo_count > 0:
                    status_slices.append(("To Do", todo_count))
                if prog_count > 0:
                    status_slices.append(("In Progress", prog_count))
                if done_count > 0:
                    status_slices.append(("Done", done_count))

                if not status_slices:
                    status_slices.append(("To Do", 0))

                chart_worksheet.cell(row=1, column=col_cat, value="Status")
                chart_worksheet.cell(row=1, column=col_val, value="Jumlah")

                for s_idx, (s_label, s_val) in enumerate(status_slices, 2):
                    chart_worksheet.cell(row=s_idx, column=col_cat, value=s_label)
                    chart_worksheet.cell(row=s_idx, column=col_val, value=s_val)

                chart_dev = DoughnutChart()
                chart_dev.title = f"{dev_name} ({dev_role})" if dev_role else dev_name
                chart_dev.dataLabels = DataLabelList()
                chart_dev.dataLabels.showPercent = True
                chart_dev.dataLabels.showVal = False
                chart_dev.dataLabels.showCatName = False
                chart_dev.dataLabels.showSerName = False
                chart_dev.dataLabels.showLegendKey = False
                chart_dev.dataLabels.numFmt = "0%"
                chart_dev.legend.legendPos = "b"

                data_ref = Reference(chart_worksheet, min_col=col_val, min_row=1, max_row=1 + len(status_slices))
                cats_ref = Reference(chart_worksheet, min_col=col_cat, min_row=2, max_row=1 + len(status_slices))
                chart_dev.add_data(data_ref, titles_from_data=True)
                chart_dev.set_categories(cats_ref)
                chart_dev.height = 11
                chart_dev.width = 10  # 10 units wide, 7-column gap prevents overlap

                worksheet.add_chart(chart_dev, f"{grid_col_letter}{grid_row_start}")
                max_chart_bottom_row = max(max_chart_bottom_row, grid_row_start + 14)

        # Case B: If len(eligible_devs) > 6 -> Generate 1 Vertical Stacked Column Chart (type="col")
        # Populate chart_worksheet starting at Col 5 to ensure openpyxl binds ONLY active developers (no 0-task clutter)!
        elif len(eligible_devs) > 6:
            chart_worksheet.cell(row=1, column=5, value="Developer")
            chart_worksheet.cell(row=1, column=6, value="To Do")
            chart_worksheet.cell(row=1, column=7, value="In Progress")
            chart_worksheet.cell(row=1, column=8, value="Done")

            str_vals = []
            for d_idx, dev in enumerate(eligible_devs, 2):
                dev_name = str(dev.get("name", f"Dev {d_idx-1}")).strip()
                chart_worksheet.cell(row=d_idx, column=5, value=dev_name)
                chart_worksheet.cell(row=d_idx, column=6, value=int(dev.get("todo", 0)))
                chart_worksheet.cell(row=d_idx, column=7, value=int(dev.get("in_progress", 0)))
                chart_worksheet.cell(row=d_idx, column=8, value=int(dev.get("done", 0)))
                str_vals.append(StrVal(d_idx - 2, v=dev_name))

            num_devs = len(eligible_devs)
            data_ref_bar = Reference(chart_worksheet, min_col=6, min_row=1, max_col=8, max_row=1 + num_devs)

            chart_bar = BarChart()
            chart_bar.type = "col"  # Vertical column chart as explicitly requested by user!
            chart_bar.style = 10
            chart_bar.grouping = "stacked"
            chart_bar.overlap = 100
            chart_bar.title = "Perbandingan Progres Subtask per Developer"
            chart_bar.y_axis.title = "Jumlah Subtask"

            chart_bar.add_data(data_ref_bar, titles_from_data=True)

            # Build strCache explicitly so Excel immediately renders every developer name!
            str_cache = StrData(pt=str_vals)
            sqref_str = f"'{chart_worksheet.title}'!$E$2:$E${1 + num_devs}"
            for s in chart_bar.series:
                s.cat = AxDataSource(strRef=StrRef(f=sqref_str, strCache=str_cache))

            # Rotate X-axis labels diagonally -45 deg and force display of every label
            chart_bar.x_axis.tickLblSkip = 1
            chart_bar.x_axis.textRotation = -45

            chart_bar.height = 14
            chart_bar.width = max(28, int(num_devs * 2.2))
            worksheet.add_chart(chart_bar, "Q6")
            max_chart_bottom_row = max(max_chart_bottom_row, 22)

        return max_chart_bottom_row

    def _render_story_progress_section(
        self,
        worksheet: Worksheet,
        report_data: Dict[str, Any],
        start_row: int,
        base_jira_url: str,
        theme: ReportTheme,
    ) -> Tuple[int, List[Dict[str, Any]]]:
        """Renders Section 2 table: Progress per Parent Story / Epic with merged 'Belum ada subtask' cells."""
        worksheet.cell(row=start_row, column=1, value="2. PROGRESS PER PARENT STORY / EPIC").font = theme.FONT_SECTION_TITLE
        worksheet.row_dimensions[start_row].height = 22

        story_headers = [
            "Key Story (Link)",
            "Judul Story Induk",
            "Owner",
            "To Do",
            "In Progress",
            "Done",
            "Total Subtask",
            "% Selesai",
        ]
        header_row = start_row + 1
        for col_idx, header_text in enumerate(story_headers, 1):
            cell = worksheet.cell(row=header_row, column=col_idx, value=header_text)
            cell.font = theme.FONT_HEADER
            cell.fill = theme.FILL_SUB_HEADER
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = theme.THIN_BORDER
        worksheet.row_dimensions[header_row].height = 22

        # Auto-aggregate stories if missing
        raw_stories = report_data.get("story_progress") or report_data.get("stories") or report_data.get("parent_progress") or report_data.get("epic_progress") or []
        detailed_subtasks = report_data.get("detailed_subtasks", [])

        if not raw_stories and detailed_subtasks:
            parent_map = {}
            for sub in detailed_subtasks:
                parent_key = sub.get("parent_key") or "Parent Story"
                parent_summary = sub.get("parent_summary") or parent_key
                if parent_key not in parent_map:
                    parent_map[parent_key] = {
                        "key": parent_key,
                        "summary": parent_summary,
                        "owner": sub.get("parent_owner") or sub.get("assignee") or "-",
                        "todo": 0,
                        "in_progress": 0,
                        "done": 0,
                        "subtasks": []
                    }
                parent_map[parent_key]["subtasks"].append(sub)
                status_clean = str(sub.get("status", "")).lower()
                if any(k in status_clean for k in ("done", "closed", "resolved", "complete", "selesai")):
                    parent_map[parent_key]["done"] += 1
                elif any(k in status_clean for k in ("in progress", "in development", "in review", "progress")):
                    parent_map[parent_key]["in_progress"] += 1
                else:
                    parent_map[parent_key]["todo"] += 1
            raw_stories = list(parent_map.values())

        stories_data = []
        for story_item in raw_stories:
            if "todo" in story_item or "in_progress" in story_item:
                stories_data.append(story_item)
            else:
                story_subs = story_item.get("subtasks", [])
                s_todo = sum(1 for s in story_subs if not any(k in str(s.get("status", "")).lower() for k in ("done", "closed", "resolved", "complete", "selesai", "in progress", "in development", "in review", "progress")))
                s_done = sum(1 for s in story_subs if any(k in str(s.get("status", "")).lower() for k in ("done", "closed", "resolved", "complete", "selesai")))
                s_prog = len(story_subs) - s_todo - s_done
                stories_data.append({
                    "key": story_item.get("key", ""),
                    "summary": story_item.get("summary", ""),
                    "owner": story_item.get("owner") or story_item.get("assignee") or "-",
                    "todo": s_todo,
                    "in_progress": s_prog,
                    "done": s_done,
                    "total_subtasks": len(story_subs)
                })

        active_parent_rows = []
        current_row = header_row + 1

        for idx, story in enumerate(stories_data):
            parent_key = story.get("key", "")
            parent_summary = story.get("summary", "")
            jira_link = f"{base_jira_url}/browse/{parent_key}"

            matching_subs = [
                sub for sub in detailed_subtasks
                if (parent_key and sub.get("parent_key") == parent_key) or (parent_summary and sub.get("parent_summary") == parent_summary)
            ]
            has_child_subtasks = len(matching_subs) > 0 or (int(story.get("todo", 0)) + int(story.get("in_progress", 0)) + int(story.get("done", 0))) > 0

            # 1. PARENT STORY ROW
            cell_key = worksheet.cell(row=current_row, column=1)
            cell_key.value = f'=HYPERLINK("{jira_link}", "{parent_key}")' if parent_key else "-"
            cell_key.font = theme.FONT_LINK
            cell_key.alignment = Alignment(horizontal="center", vertical="center")

            cell_summary = worksheet.cell(row=current_row, column=2, value=parent_summary)
            cell_summary.font = theme.FONT_PARENT_BOLD if has_child_subtasks else theme.FONT_DATA
            cell_summary.alignment = Alignment(horizontal="left", vertical="center")

            cell_owner = worksheet.cell(row=current_row, column=3, value=story.get("owner", "-"))
            cell_owner.font = theme.FONT_BOLD if story.get("owner") not in ("-", "Unassigned") else theme.FONT_DATA
            cell_owner.alignment = Alignment(horizontal="center", vertical="center")

            story_fill = theme.FILL_PARENT_STORY if has_child_subtasks else (theme.FILL_ZEBRA if idx % 2 == 1 else PatternFill(fill_type=None))

            if has_child_subtasks:
                active_parent_rows.append(current_row)
                cell_todo = worksheet.cell(row=current_row, column=4, value=story.get("todo", 0))
                cell_prog = worksheet.cell(row=current_row, column=5, value=story.get("in_progress", 0))
                cell_done = worksheet.cell(row=current_row, column=6, value=story.get("done", 0))
                cell_tot  = worksheet.cell(row=current_row, column=7, value=f"=SUM(D{current_row}:F{current_row})")
                cell_pct  = worksheet.cell(row=current_row, column=8, value=f'=IF(G{current_row}=0, 0, F{current_row}/G{current_row})')

                cell_todo.font = theme.FONT_BOLD
                cell_prog.font = theme.FONT_BOLD
                cell_done.font = theme.FONT_BOLD
                cell_tot.font = theme.FONT_BOLD
                cell_pct.font = theme.FONT_BOLD

                cell_todo.alignment = Alignment(horizontal="right", vertical="center")
                cell_prog.alignment = Alignment(horizontal="right", vertical="center")
                cell_done.alignment = Alignment(horizontal="right", vertical="center")
                cell_tot.alignment  = Alignment(horizontal="right", vertical="center")
                cell_pct.alignment  = Alignment(horizontal="right", vertical="center")
                cell_pct.number_format = "0.0%"
            else:
                # Merge columns 4 to 8 (To Do s/d % Selesai) with centered italic text
                worksheet.merge_cells(start_row=current_row, start_column=4, end_row=current_row, end_column=8)
                merged_cell = worksheet.cell(row=current_row, column=4, value="Belum ada subtask")
                merged_cell.font = theme.FONT_MUTED
                merged_cell.alignment = Alignment(horizontal="center", vertical="center")

            for col_idx in range(1, 9):
                cell_obj = worksheet.cell(row=current_row, column=col_idx)
                cell_obj.border = theme.THIN_BORDER
                cell_obj.fill = story_fill

            worksheet.row_dimensions[current_row].height = 22
            current_row += 1

            # 2. NESTED SUBTASKS (Indented)
            for sub_idx, sub in enumerate(matching_subs):
                sub_key = sub.get("key", "")
                sub_url = sub.get("url") or f"{base_jira_url}/browse/{sub_key}"
                sub_summary = sub.get("summary", "")
                sub_assignee = sub.get("assignee", "Unassigned")
                sub_role = sub.get("role", "-")
                status_lower = str(sub.get("status") or sub.get("status_category") or "To Do").strip().lower()

                cell_sub_key = worksheet.cell(row=current_row, column=1)
                cell_sub_key.value = f'=HYPERLINK("{sub_url}", "  ↳ {sub_key}")' if sub_key else "  ↳ -"
                cell_sub_key.font = theme.FONT_SUBTASK_LINK
                cell_sub_key.alignment = Alignment(horizontal="left", vertical="center")

                cell_sub_summary = worksheet.cell(row=current_row, column=2, value=f"  ↳ {sub_summary}")
                cell_sub_summary.font = theme.FONT_SUBTASK_INDENT
                cell_sub_summary.alignment = Alignment(horizontal="left", vertical="center")

                cell_sub_assignee = worksheet.cell(row=current_row, column=3, value=sub_assignee)
                cell_sub_assignee.font = theme.FONT_SUBTASK_INDENT
                cell_sub_assignee.alignment = Alignment(horizontal="center", vertical="center")

                worksheet.cell(row=current_row, column=4, value="-").alignment = Alignment(horizontal="center", vertical="center")
                worksheet.cell(row=current_row, column=5, value="-").alignment = Alignment(horizontal="center", vertical="center")

                cell_sub_role = worksheet.cell(row=current_row, column=6, value=f"Role: {sub_role}" if sub_role != "-" else "-")
                cell_sub_role.font = theme.FONT_SUBTASK_ROLE
                cell_sub_role.alignment = Alignment(horizontal="center", vertical="center")

                cell_sub_sp = worksheet.cell(row=current_row, column=7, value="-")
                cell_sub_sp.font = theme.FONT_SUBTASK_INDENT
                cell_sub_sp.alignment = Alignment(horizontal="center", vertical="center")

                cell_sub_status = worksheet.cell(row=current_row, column=8)
                cell_sub_status.alignment = Alignment(horizontal="center", vertical="center")

                if any(k in status_lower for k in ("done", "closed", "resolved", "complete", "selesai")):
                    cell_sub_status.value = "Done"
                    cell_sub_status.fill = theme.FILL_STATUS_DONE
                    cell_sub_status.font = theme.FONT_STATUS_DONE
                elif any(k in status_lower for k in ("in progress", "in development", "in review", "progress", "sedang")):
                    cell_sub_status.value = "In Progress"
                    cell_sub_status.fill = theme.FILL_STATUS_PROG
                    cell_sub_status.font = theme.FONT_STATUS_PROG
                else:
                    cell_sub_status.value = "To Do"
                    cell_sub_status.fill = theme.FILL_STATUS_TODO
                    cell_sub_status.font = theme.FONT_STATUS_TODO

                for col_idx in range(1, 9):
                    cell_obj = worksheet.cell(row=current_row, column=col_idx)
                    cell_obj.border = theme.THIN_BORDER
                    if col_idx < 8 and sub_idx % 2 == 1:
                        cell_obj.fill = theme.FILL_ZEBRA

                worksheet.row_dimensions[current_row].outlineLevel = 1
                worksheet.row_dimensions[current_row].height = 19
                current_row += 1

        # Story Total Row
        story_total_row = current_row
        worksheet.cell(row=story_total_row, column=1, value="Total").font = theme.FONT_BOLD
        worksheet.cell(row=story_total_row, column=2, value="").font = theme.FONT_BOLD
        worksheet.cell(row=story_total_row, column=3, value="").font = theme.FONT_BOLD

        if active_parent_rows:
            sum_d = ",".join([f"D{r}" for r in active_parent_rows])
            sum_e = ",".join([f"E{r}" for r in active_parent_rows])
            sum_f = ",".join([f"F{r}" for r in active_parent_rows])
            sum_g = ",".join([f"G{r}" for r in active_parent_rows])
            worksheet.cell(row=story_total_row, column=4, value=f"=SUM({sum_d})").font = theme.FONT_BOLD
            worksheet.cell(row=story_total_row, column=5, value=f"=SUM({sum_e})").font = theme.FONT_BOLD
            worksheet.cell(row=story_total_row, column=6, value=f"=SUM({sum_f})").font = theme.FONT_BOLD
            worksheet.cell(row=story_total_row, column=7, value=f"=SUM({sum_g})").font = theme.FONT_BOLD
        else:
            for col_idx in range(4, 8):
                worksheet.cell(row=story_total_row, column=col_idx, value=0).font = theme.FONT_BOLD

        cell_pct_story_total = worksheet.cell(row=story_total_row, column=8, value=f'=IF(G{story_total_row}=0, 0, F{story_total_row}/G{story_total_row})')
        cell_pct_story_total.font = theme.FONT_BOLD
        cell_pct_story_total.number_format = "0.0%"

        for col_idx in range(1, 9):
            cell_obj = worksheet.cell(row=story_total_row, column=col_idx)
            cell_obj.fill = theme.FILL_TOTAL
            cell_obj.border = theme.TOTAL_TOP_BOTTOM_BORDER
            if col_idx >= 4:
                cell_obj.alignment = Alignment(horizontal="right", vertical="center")

        worksheet.row_dimensions[story_total_row].height = 22

        active_chart_stories = [
            st for st in stories_data 
            if (st.get("todo", 0) + st.get("in_progress", 0) + st.get("done", 0)) > 0
        ][:12]
        if not active_chart_stories:
            active_chart_stories = stories_data[:8]

        return story_total_row, active_chart_stories

    def _render_story_progress_chart(
        self,
        worksheet: Worksheet,
        chart_worksheet: Worksheet,
        active_chart_stories: List[Dict[str, Any]],
        chart_start_row: int,
    ) -> None:
        """Renders the Adaptive Horizontal Stacked Bar Chart for Story Completion using chart_worksheet."""
        if not active_chart_stories:
            return

        # Write story data in chart_worksheet columns 13..16 (M..P)
        chart_worksheet.cell(row=1, column=13, value="Story Induk")
        chart_worksheet.cell(row=1, column=14, value="Done")
        chart_worksheet.cell(row=1, column=15, value="In Progress")
        chart_worksheet.cell(row=1, column=16, value="To Do")

        for story_idx, story_item in enumerate(active_chart_stories, 1):
            target_row = 1 + story_idx
            story_key = str(story_item.get("key") or "").strip()
            story_summary = str(story_item.get("summary") or "").strip()
            
            # Multi-line label: Key on line 1, Full Summary on line 2
            label_text = f"[{story_key}]\n{story_summary}" if story_summary else (story_key or f"Story {story_idx}")

            cell_lbl = chart_worksheet.cell(row=target_row, column=13, value=label_text)
            cell_lbl.number_format = '@'
            chart_worksheet.cell(row=target_row, column=14, value=int(story_item.get("done", 0)))
            chart_worksheet.cell(row=target_row, column=15, value=int(story_item.get("in_progress", 0)))
            chart_worksheet.cell(row=target_row, column=16, value=int(story_item.get("todo", 0)))

        chart_story = BarChart()
        chart_story.type = "bar"
        chart_story.grouping = "stacked"
        chart_story.overlap = 100
        chart_story.gapWidth = 80
        chart_story.title = "Progres Penyelesaian per Story Induk"
        
        # Left Category Axis
        chart_story.x_axis.axPos = "l"
        chart_story.x_axis.tickLblPos = "nextTo"
        chart_story.x_axis.tickLblSkip = 1
        chart_story.x_axis.tickMarkSkip = 1
        chart_story.x_axis.delete = False
        chart_story.x_axis.title = None
        # Reverse category axis: Excel horizontal bar charts render items bottom-to-top by default.
        # Setting orientation="maxMin" flips this so the FIRST story in data appears at TOP,
        # matching the same order as the "Progress Per Parent Story/EPIC" table above.
        chart_story.x_axis.scaling.orientation = "maxMin"

        # Bottom Value Axis (also cross at max to keep labels on left when axis is reversed)
        chart_story.y_axis.axPos = "b"
        chart_story.y_axis.title = "Jumlah Subtask"
        chart_story.y_axis.delete = False
        chart_story.y_axis.crosses = "max"

        chart_story.legend.legendPos = "r"

        chart_story.dataLabels = DataLabelList()
        chart_story.dataLabels.showVal = True
        chart_story.dataLabels.showCatName = False
        chart_story.dataLabels.showSerName = False
        chart_story.dataLabels.showPercent = False
        chart_story.dataLabels.showLegendKey = False

        data_ref = Reference(chart_worksheet, min_col=14, max_col=16, min_row=1, max_row=1 + len(active_chart_stories))
        cats_ref = Reference(chart_worksheet, min_col=13, min_row=2, max_row=1 + len(active_chart_stories))

        chart_story.add_data(data_ref, titles_from_data=True)
        chart_story.set_categories(cats_ref)

        # Semantic Colors: Done (Green), In Progress (Blue), To Do (Gray)
        if len(chart_story.series) >= 3:
            chart_story.series[0].graphicalProperties.solidFill = "548235"
            chart_story.series[1].graphicalProperties.solidFill = "2E75B6"
            chart_story.series[2].graphicalProperties.solidFill = "A6A6A6"

        chart_story.height = max(11, len(active_chart_stories) * 3.2 + 2)
        chart_story.width = 34

        worksheet.add_chart(chart_story, f"J{chart_start_row}")

    def _render_subtask_details_section(
        self,
        worksheet: Worksheet,
        detailed_subtasks: List[Dict[str, Any]],
        start_row: int,
        base_jira_url: str,
        theme: ReportTheme,
    ) -> None:
        """Renders Section 3 table with Assignee & Role next to Subtask Title and vertically merged Parent blocks."""
        worksheet.cell(row=start_row, column=1, value="3. RINCIAN LENGKAP SELURUH SUBTASK JIRA").font = theme.FONT_SECTION_TITLE
        worksheet.row_dimensions[start_row].height = 22

        subtask_headers = [
            "No",
            "Key Subtask (Link)",
            "Judul Subtask",
            "Assignee",
            "Role",
            "Key Parent",
            "Story Induk",
            "Status",
        ]
        header_row = start_row + 1
        for col_idx, header_text in enumerate(subtask_headers, 1):
            cell = worksheet.cell(row=header_row, column=col_idx, value=header_text)
            cell.font = theme.FONT_HEADER
            cell.fill = theme.FILL_HEADER
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = theme.THIN_BORDER
        worksheet.row_dimensions[header_row].height = 22

        # Group subtasks by Parent Story to prevent repetitive 1-row-parent duplication
        parent_subtask_groups = OrderedDict()
        for sub in detailed_subtasks:
            parent_key = sub.get("parent_key") or "Other"
            if parent_key not in parent_subtask_groups:
                parent_subtask_groups[parent_key] = []
            parent_subtask_groups[parent_key].append(sub)

        current_row = header_row + 1
        global_sub_idx = 1

        for parent_key, group_subtasks in parent_subtask_groups.items():
            start_group_row = current_row
            end_group_row = current_row + len(group_subtasks) - 1
            parent_summary = group_subtasks[0].get("parent_summary", "")
            parent_url = f"{base_jira_url}/browse/{parent_key}"

            for sub in group_subtasks:
                row_fill = theme.FILL_ZEBRA if global_sub_idx % 2 == 0 else PatternFill(fill_type=None)
                sub_key = sub.get("key", "")
                sub_url = sub.get("url") or f"{base_jira_url}/browse/{sub_key}"

                # Col 1: No
                cell_no = worksheet.cell(row=current_row, column=1, value=global_sub_idx)
                cell_no.alignment = Alignment(horizontal="center", vertical="center")
                cell_no.font = theme.FONT_DATA

                # Col 2: Key Subtask
                cell_skey = worksheet.cell(row=current_row, column=2)
                cell_skey.value = f'=HYPERLINK("{sub_url}", "{sub_key}")' if sub_key else "-"
                cell_skey.font = theme.FONT_LINK
                cell_skey.alignment = Alignment(horizontal="center", vertical="center")

                # Col 3: Judul Subtask
                cell_ssum = worksheet.cell(row=current_row, column=3, value=sub.get("summary", ""))
                cell_ssum.font = theme.FONT_DATA
                cell_ssum.alignment = Alignment(horizontal="left", vertical="center")

                # Col 4: Assignee (Right next to Judul Subtask)
                cell_ass = worksheet.cell(row=current_row, column=4, value=sub.get("assignee", "Unassigned"))
                cell_ass.font = theme.FONT_BOLD if sub.get("assignee") != "Unassigned" else theme.FONT_DATA
                cell_ass.alignment = Alignment(horizontal="center", vertical="center")

                # Col 5: Role (Right next to Assignee)
                cell_role = worksheet.cell(row=current_row, column=5, value=sub.get("role", ""))
                cell_role.font = theme.FONT_DATA
                cell_role.alignment = Alignment(horizontal="center", vertical="center")

                # Col 8: Status Badge
                status_raw = str(sub.get("status") or sub.get("status_category") or "To Do").strip()
                status_lower = status_raw.lower()

                cell_status = worksheet.cell(row=current_row, column=8)
                cell_status.alignment = Alignment(horizontal="center", vertical="center")

                if any(k in status_lower for k in ("done", "closed", "resolved", "complete", "selesai")):
                    cell_status.value = "Done"
                    cell_status.fill = theme.FILL_STATUS_DONE
                    cell_status.font = theme.FONT_STATUS_DONE
                elif any(k in status_lower for k in ("in progress", "in development", "in review", "progress", "sedang")):
                    cell_status.value = "In Progress"
                    cell_status.fill = theme.FILL_STATUS_PROG
                    cell_status.font = theme.FONT_STATUS_PROG
                else:
                    cell_status.value = "To Do"
                    cell_status.fill = theme.FILL_STATUS_TODO
                    cell_status.font = theme.FONT_STATUS_TODO

                for col_idx in range(1, 9):
                    cell_obj = worksheet.cell(row=current_row, column=col_idx)
                    cell_obj.border = theme.THIN_BORDER
                    if col_idx not in (6, 7) and col_idx != 8 and row_fill.fill_type:
                        cell_obj.fill = row_fill

                worksheet.row_dimensions[current_row].height = 20
                current_row += 1
                global_sub_idx += 1

            # Vertically merge Key Parent (Col 6) and Story Induk (Col 7)
            if len(group_subtasks) > 1:
                worksheet.merge_cells(start_row=start_group_row, start_column=6, end_row=end_group_row, end_column=6)
                worksheet.merge_cells(start_row=start_group_row, start_column=7, end_row=end_group_row, end_column=7)
            else:
                # If only 1 subtask, adjust row height so long Story Induk title doesn't overlap
                max_text_len = max(len(group_subtasks[0].get("summary", "")), len(parent_summary))
                est_lines = max(1, (max_text_len + 35) // 40)
                worksheet.row_dimensions[start_group_row].height = max(26, est_lines * 18)

            cell_parent_key = worksheet.cell(row=start_group_row, column=6)
            cell_parent_key.value = f'=HYPERLINK("{parent_url}", "{parent_key}")' if parent_key and parent_key != "Other" else "-"
            cell_parent_key.font = theme.FONT_LINK
            cell_parent_key.alignment = Alignment(horizontal="center", vertical="center")

            cell_parent_sum = worksheet.cell(row=start_group_row, column=7, value=parent_summary)
            cell_parent_sum.font = theme.FONT_BOLD
            cell_parent_sum.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)

            for group_row_idx in range(start_group_row, end_group_row + 1):
                for group_col_idx in (6, 7):
                    worksheet.cell(row=group_row_idx, column=group_col_idx).border = theme.THIN_BORDER
                    worksheet.cell(row=group_row_idx, column=group_col_idx).fill = theme.FILL_PARENT_GROUP

    def _render_role_distribution_chart(
        self,
        worksheet: Worksheet,
        chart_worksheet: Worksheet,
        detailed_subtasks: List[Dict[str, Any]],
        start_row: int,
    ) -> None:
        """Renders the Role Breakdown Doughnut Chart using chart_worksheet."""
        if not detailed_subtasks:
            return

        role_counts = {}
        for sub in detailed_subtasks:
            role_name = str(sub.get("role") or "General").strip().title()
            if not role_name or role_name == "-":
                role_name = "General / Other"
            role_counts[role_name] = role_counts.get(role_name, 0) + 1

        chart_worksheet.cell(row=1, column=18, value="Role")
        chart_worksheet.cell(row=1, column=19, value="Jumlah")

        role_idx = 1
        for role_name, count in sorted(role_counts.items(), key=lambda x: x[1], reverse=True):
            curr_row = 1 + role_idx
            chart_worksheet.cell(row=curr_row, column=18, value=role_name)
            chart_worksheet.cell(row=curr_row, column=19, value=count)
            role_idx += 1

        chart_role = DoughnutChart()
        chart_role.title = "Distribusi Subtask per Role"
        chart_role.legend.legendPos = "r"

        chart_role.dataLabels = DataLabelList()
        chart_role.dataLabels.showPercent = True
        chart_role.dataLabels.showVal = False
        chart_role.dataLabels.showCatName = False
        chart_role.dataLabels.showSerName = False
        chart_role.dataLabels.showLegendKey = False
        chart_role.dataLabels.numFmt = "0%"

        data_ref = Reference(chart_worksheet, min_col=19, min_row=1, max_row=1 + len(role_counts))
        cats_ref = Reference(chart_worksheet, min_col=18, min_row=2, max_row=1 + len(role_counts))

        chart_role.add_data(data_ref, titles_from_data=True)
        chart_role.set_categories(cats_ref)
        chart_role.height = 13
        chart_role.width = 16

        worksheet.add_chart(chart_role, f"J{start_row}")

    def _apply_column_dimensions(self, worksheet: Worksheet) -> None:
        """Applies clean, standard column widths tailored for readability."""
        column_width_map = {
            1: 8,   # No
            2: 20,  # Key Subtask (Link) / Key Story
            3: 48,  # Judul Subtask / Judul Story
            4: 26,  # Assignee (Developer)
            5: 16,  # Role
            6: 18,  # Key Parent
            7: 54,  # Story Induk
            8: 16,  # Status / % Selesai
        }
        for col in worksheet.columns:
            col_num = col[0].column
            col_letter = openpyxl.utils.get_column_letter(col_num)
            if col_num in column_width_map:
                worksheet.column_dimensions[col_letter].width = column_width_map[col_num]
            elif col_num > 8:
                worksheet.column_dimensions[col_letter].width = 12

    def _save_workbook(
        self,
        workbook: openpyxl.Workbook,
        full_path: str,
        safe_key: str,
        output_path: str,
        filename: str,
    ) -> str:
        """Saves workbook safely with a timestamped fallback if file is locked by Excel.
        Returns the full absolute path of the saved file."""
        try:
            workbook.save(full_path)
            return full_path  # Return full path so callers can display structured folder location
        except PermissionError:
            import time
            prof_name = self._get_professional_filename(safe_key)
            today_str = datetime.datetime.now().strftime("%d-%m-%Y")
            fallback_filename = f"Laporan_Progress_{prof_name}_{today_str}_update_{int(time.time())}.xlsx"
            fallback_path = os.path.join(os.path.dirname(full_path), fallback_filename)
            workbook.save(fallback_path)
            print(f"Peringatan: File '{filename}' sedang dibuka di Microsoft Excel. Hasil baru disimpan sebagai: '{fallback_path}'")
            return fallback_path

    # =========================================================================
    # BACKWARDS COMPATIBILITY
    # =========================================================================

    def generate_report(
        self, balanced_results: Dict[str, Any], epic_key: str, output_path: str = "."
    ) -> str:
        """Legacy workload balance export (kept for backwards compatibility)."""
        member_progress = []
        detailed_subtasks = []
        total_todo = 0
        total_sp = 0.0

        for item in balanced_results.get("assignments", []):
            emp = item.get("employee", {})
            tasks = item.get("assigned_subtasks", [])
            story_points = item.get("total_story_points", 0.0)
            total_todo += len(tasks)
            total_sp += story_points

            member_progress.append({
                "name": emp.get("name", ""),
                "role": emp.get("role", ""),
                "todo": len(tasks),
                "in_progress": 0,
                "done": 0,
                "total_subtasks": len(tasks),
                "total_sp": story_points,
                "percent_done": 0.0,
            })

            for task in tasks:
                detailed_subtasks.append({
                    "key": "",
                    "summary": task.get("summary", ""),
                    "parent_key": task.get("parent_key", epic_key),
                    "parent_summary": task.get("parent_summary", ""),
                    "assignee": emp.get("name", "Unassigned"),
                    "role": task.get("role", emp.get("role", "")),
                    "status": "To Do",
                    "status_category": "To Do",
                    "story_points": task.get("story_points", 0.0),
                    "url": f"{settings.JIRA_URL.rstrip('/')}/browse/{task.get('parent_key', epic_key)}",
                })

        report_data = {
            "root_key": epic_key,
            "root_summary": f"Alokasi Subtask Baru {epic_key}",
            "total_epics_count": 1,
            "overall_status": {
                "todo": total_todo,
                "in_progress": 0,
                "done": 0,
                "total": total_todo,
                "percent_done": 0.0,
            },
            "member_progress": member_progress,
            "story_progress": [
                {
                    "key": epic_key,
                    "summary": f"Subtask AI Baru {epic_key}",
                    "todo": total_todo,
                    "in_progress": 0,
                    "done": 0,
                    "total_subtasks": total_todo,
                    "total_sp": total_sp,
                    "percent_done": 0.0,
                }
            ],
            "detailed_subtasks": detailed_subtasks,
        }

        return self.generate_progress_report(report_data, epic_key, output_path)
