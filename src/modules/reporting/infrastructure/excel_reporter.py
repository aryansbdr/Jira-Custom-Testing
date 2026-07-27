import openpyxl
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
import os
from shared.config import settings


class ExcelReporter:
    """
    Service to generate professional Excel reports from workload balancing results,
    including a native Excel Bar Chart and clickable direct Jira URL Hyperlinks.
    """

    def generate_report(
        self, balanced_results: dict, epic_key: str, output_path: str = "."
    ) -> str:
        # Create a new workbook
        wb = openpyxl.Workbook()
        base_jira_url = settings.JIRA_URL.rstrip("/")

        # -------------------------------------------------------------
        # SHEET 1: RINGKASAN BEBAN KERJA (SUMMARY & CHART)
        # -------------------------------------------------------------
        ws_summary = wb.active
        ws_summary.title = "Ringkasan Beban Kerja"
        ws_summary.views.sheetView[0].showGridLines = True

        # Styles definition
        font_title = Font(name="Segoe UI", size=16, bold=True, color="1F4E79")
        font_header = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        font_data = Font(name="Segoe UI", size=11)
        font_bold = Font(name="Segoe UI", size=11, bold=True)

        fill_header = PatternFill(
            start_color="1F4E79", end_color="1F4E79", fill_type="solid"
        )
        fill_accent = PatternFill(
            start_color="D9E1F2", end_color="D9E1F2", fill_type="solid"
        )

        thin_border = Border(
            left=Side(style="thin", color="BFBFBF"),
            right=Side(style="thin", color="BFBFBF"),
            top=Side(style="thin", color="BFBFBF"),
            bottom=Side(style="thin", color="BFBFBF"),
        )

        # Title block
        ws_summary["A1"] = f"Laporan Beban Kerja Epic: {epic_key}"
        ws_summary["A1"].font = font_title
        ws_summary.row_dimensions[1].height = 30

        # Table Headers
        headers = ["Nama Developer", "Role", "Total Story Points", "Jumlah Tugas"]
        for col_idx, header in enumerate(headers, 1):
            cell = ws_summary.cell(row=3, column=col_idx, value=header)
            cell.font = font_header
            cell.fill = fill_header
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin_border
        ws_summary.row_dimensions[3].height = 25

        # Fill Data
        assignments = balanced_results.get("assignments", [])
        row_idx = 4

        for item in assignments:
            emp = item.get("employee", {})
            tasks = item.get("assigned_subtasks", [])
            total_sp = item.get("total_story_points", 0.0)

            ws_summary.cell(
                row=row_idx, column=1, value=emp.get("name", "")
            ).font = font_data
            ws_summary.cell(
                row=row_idx, column=2, value=emp.get("role", "")
            ).font = font_data

            # Story points
            sp_cell = ws_summary.cell(row=row_idx, column=3, value=total_sp)
            sp_cell.font = font_data
            sp_cell.number_format = "0.0"
            sp_cell.alignment = Alignment(horizontal="right")

            # Tasks count
            tasks_cell = ws_summary.cell(row=row_idx, column=4, value=len(tasks))
            tasks_cell.font = font_data
            tasks_cell.alignment = Alignment(horizontal="right")

            # Apply borders
            for c in range(1, 5):
                ws_summary.cell(row=row_idx, column=c).border = thin_border

            ws_summary.row_dimensions[row_idx].height = 20
            row_idx += 1

        # Total Row
        ws_summary.cell(
            row=row_idx, column=1, value="Total Keseluruhan"
        ).font = font_bold
        ws_summary.cell(row=row_idx, column=1).fill = fill_accent
        ws_summary.cell(row=row_idx, column=1).border = thin_border

        ws_summary.cell(row=row_idx, column=2, value="").border = thin_border
        ws_summary.cell(row=row_idx, column=2).fill = fill_accent

        # SP Formula
        total_sp_cell = ws_summary.cell(
            row=row_idx, column=3, value=f"=SUM(C4:C{row_idx - 1})"
        )
        total_sp_cell.font = font_bold
        total_sp_cell.number_format = "0.0"
        total_sp_cell.fill = fill_accent
        total_sp_cell.alignment = Alignment(horizontal="right")
        total_sp_cell.border = thin_border

        # Tasks Formula
        total_tasks_cell = ws_summary.cell(
            row=row_idx, column=4, value=f"=SUM(D4:D{row_idx - 1})"
        )
        total_tasks_cell.font = font_bold
        total_tasks_cell.fill = fill_accent
        total_tasks_cell.alignment = Alignment(horizontal="right")
        total_tasks_cell.border = thin_border

        ws_summary.row_dimensions[row_idx].height = 22

        # Auto-fit columns
        for col in ws_summary.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws_summary.column_dimensions[col_letter].width = max(max_len + 3, 12)

        # -------------------------------------------------------------
        # ADD NATIVE BAR CHART
        # -------------------------------------------------------------
        chart = BarChart()
        chart.type = "col"
        chart.style = 10
        chart.title = "Distribusi Beban Kerja Tim (Story Points)"
        chart.y_axis.title = "Story Points"
        chart.x_axis.title = "Nama Developer"

        # Data Reference (Total Story Points column C4 to C_row_idx-1)
        data = Reference(ws_summary, min_col=3, min_row=3, max_row=row_idx - 1)
        # Categories Reference (Developer Names column A4 to A_row_idx-1)
        cats = Reference(ws_summary, min_col=1, min_row=4, max_row=row_idx - 1)

        chart.add_data(data, titles_from_data=True)
        chart.set_categories(cats)
        chart.legend = None

        # Chart size
        chart.height = 14
        chart.width = 18

        # Position chart next to the table
        ws_summary.add_chart(chart, "F3")

        # -------------------------------------------------------------
        # SHEET 2: DETAIL PEMBAGIAN TUGAS WITH HYPERLINKS
        # -------------------------------------------------------------
        ws_detail = wb.create_sheet(title="Detail Tugas")
        ws_detail.views.sheetView[0].showGridLines = True

        ws_detail["A1"] = f"Detail Pecahan Subtask untuk Epic: {epic_key}"
        ws_detail["A1"].font = font_title
        ws_detail.row_dimensions[1].height = 30

        detail_headers = [
            "Key Story Induk (Link)",
            "Subtask Title",
            "Deskripsi Subtask",
            "Role",
            "Assignee",
            "Subtask SP",
        ]
        for col_idx, d_header in enumerate(detail_headers, 1):
            cell = ws_detail.cell(row=3, column=col_idx, value=d_header)
            cell.font = font_header
            cell.fill = fill_header
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin_border
        ws_detail.row_dimensions[3].height = 25

        # Link style
        font_link = Font(name="Segoe UI", size=11, color="0563C1", underline="single")

        d_row = 4
        d_row = 4
        # Flat list of all assigned subtasks
        for item in assignments:
            emp = item.get("employee", {})
            for sub in item.get("assigned_subtasks", []):
                parent_key = sub.get("parent_key", "") if isinstance(sub, dict) else getattr(sub, "parent_key", "")
                jira_link = f"{base_jira_url}/browse/{parent_key}"

                key_cell = ws_detail.cell(row=d_row, column=1)
                key_cell.value = f'=HYPERLINK("{jira_link}", "{parent_key}")'
                key_cell.font = font_link

                summary_val = sub.get("summary", "") if isinstance(sub, dict) else getattr(sub, "summary", "")
                desc_val = sub.get("description", "") if isinstance(sub, dict) else getattr(sub, "description", "")
                role_val = sub.get("role", "") if isinstance(sub, dict) else getattr(sub, "role", "")
                sp_val = sub.get("story_points", 0.0) if isinstance(sub, dict) else getattr(sub, "story_points", 0.0)

                ws_detail.cell(row=d_row, column=2, value=summary_val).font = font_data
                ws_detail.cell(
                    row=d_row, column=3, value=desc_val
                ).font = font_data
                ws_detail.cell(row=d_row, column=4, value=role_val).font = font_data
                ws_detail.cell(
                    row=d_row, column=5, value=emp.get("name", "")
                ).font = font_data

                sp_c = ws_detail.cell(row=d_row, column=6, value=sp_val)
                sp_c.font = font_data
                sp_c.number_format = "0.0"
                sp_c.alignment = Alignment(horizontal="right")

                for c in range(1, 7):
                    ws_detail.cell(row=d_row, column=c).border = thin_border

                ws_detail.row_dimensions[d_row].height = 20
                d_row += 1

        # Unassigned Subtasks
        unassigned = balanced_results.get("unassigned_subtasks", [])
        if unassigned:
            # Row Gap
            d_row += 2
            ws_detail.cell(
                row=d_row,
                column=1,
                value="TUGAS YANG TIDAK DAPAT DIALLOCATE (TIDAK ADA ROLE COCOK)",
            ).font = font_bold
            ws_detail.cell(row=d_row, column=1).font = Font(
                name="Segoe UI", size=11, bold=True, color="FF0000"
            )
            d_row += 1

            for col_idx, d_header in enumerate(
                detail_headers[:4] + ["Status", "Subtask SP"], 1
            ):
                cell = ws_detail.cell(row=d_row, column=col_idx, value=d_header)
                cell.font = font_header
                cell.fill = PatternFill(
                    start_color="C00000", end_color="C00000", fill_type="solid"
                )
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.border = thin_border
            ws_detail.row_dimensions[d_row].height = 25
            d_row += 1

            for sub in unassigned:
                parent_key = sub.get("parent_key", "") if isinstance(sub, dict) else getattr(sub, "parent_key", "")
                jira_link = f"{base_jira_url}/browse/{parent_key}"

                key_cell = ws_detail.cell(row=d_row, column=1)
                key_cell.value = f'=HYPERLINK("{jira_link}", "{parent_key}")'
                key_cell.font = font_link

                summary_val = sub.get("summary", "") if isinstance(sub, dict) else getattr(sub, "summary", "")
                desc_val = sub.get("description", "") if isinstance(sub, dict) else getattr(sub, "description", "")
                role_val = sub.get("role", "") if isinstance(sub, dict) else getattr(sub, "role", "")
                sp_val = sub.get("story_points", 0.0) if isinstance(sub, dict) else getattr(sub, "story_points", 0.0)

                ws_detail.cell(row=d_row, column=2, value=summary_val).font = font_data
                ws_detail.cell(
                    row=d_row, column=3, value=desc_val
                ).font = font_data
                ws_detail.cell(row=d_row, column=4, value=role_val).font = font_data
                ws_detail.cell(
                    row=d_row, column=5, value="Unassigned (No Member Role)"
                ).font = Font(name="Segoe UI", color="FF0000")

                sp_c = ws_detail.cell(row=d_row, column=6, value=sp_val)
                sp_c.font = font_data
                sp_c.number_format = "0.0"
                sp_c.alignment = Alignment(horizontal="right")

                for c in range(1, 7):
                    ws_detail.cell(row=d_row, column=c).border = thin_border

                ws_detail.row_dimensions[d_row].height = 20
                d_row += 1

        # Auto-fit columns for sheet 2
        for col in ws_detail.columns:
            max_len = 0
            for cell in col:
                val = str(cell.value or "")
                if len(val) > 45:
                    max_len = max(max_len, 45)
                else:
                    max_len = max(max_len, len(val))
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws_detail.column_dimensions[col_letter].width = max(max_len + 3, 12)

        # Save workbook
        filename = f"workload_report_{epic_key}.xlsx"
        full_path = os.path.join(output_path, filename)
        wb.save(full_path)
        return filename
