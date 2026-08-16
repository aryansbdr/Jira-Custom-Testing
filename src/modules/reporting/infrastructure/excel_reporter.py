import openpyxl
from openpyxl.chart import BarChart, PieChart, DoughnutChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
import os
import datetime
from shared.config import settings


class ExcelReporter:
    """
    Service to generate executive-ready Excel reports (.xlsx)
    from Jira progress and workload balancing results with Historical Daily Tracking:
    - Multi-date snapshot in 1 workbook: Adds a new tab named by Date (e.g. '09-08-2026', '10-08-2026').
    - Section 1: KPI Cards & Member Summary with side-by-side Bar and Pie Charts.
    - Section 2: Progress per Parent Story / Epic.
    - Section 3: Detailed Subtask List with clickable Jira Hyperlinks.
    - Clean Bar Chart with developer names on X-axis, numbers on bars, legend on right side.
    - Clean Pie Chart with clean % on slices and clear legend on right.
    - Professional Segoe UI typography and BRI Navy executive theme.
    """

    def generate_progress_report(
        self, report_data: dict, safe_key: str, output_path: str = "."
    ) -> str:
        """
        Generate or update Sprint & Squad Progress Excel report (.xlsx),
        creating a dedicated sheet per Date (e.g. '09-08-2026') for daily tracking.
        """
        base_jira_url = settings.JIRA_URL.rstrip("/")
        root_key = report_data.get("root_key", safe_key)
        root_summary = report_data.get("root_summary", "")

        today_date_str = datetime.datetime.now().strftime("%d-%m-%Y")
        sheet_title = today_date_str
        filename = f"Laporan_Progress_{safe_key}.xlsx"
        full_path = os.path.join(output_path, filename)

        # Multi-date tracking: Load existing workbook or create new
        if os.path.exists(full_path):
            try:
                wb = openpyxl.load_workbook(full_path)
                # If today's sheet already exists, overwrite it with latest snapshot
                if sheet_title in wb.sheetnames:
                    wb.remove(wb[sheet_title])
                ws = wb.create_sheet(title=sheet_title)
            except Exception:
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = sheet_title
        else:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = sheet_title

        wb.active = ws

        # -------------------------------------------------------------
        # STYLES & COLOR PALETTE (BRI EXECUTIVE NAVY THEME)
        # -------------------------------------------------------------
        font_main_title = Font(name="Segoe UI", size=15, bold=True, color="1F4E79")
        font_section_title = Font(name="Segoe UI", size=12, bold=True, color="1F4E79")
        font_subtitle = Font(name="Segoe UI", size=10, italic=True, color="595959")
        font_header = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
        font_data = Font(name="Segoe UI", size=10)
        font_bold = Font(name="Segoe UI", size=10, bold=True)
        font_link = Font(name="Segoe UI", size=10, color="0563C1", underline="single")

        fill_header = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
        fill_sub_header = PatternFill(start_color="2E75B6", end_color="2E75B6", fill_type="solid")
        fill_total = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
        fill_zebra = PatternFill(start_color="F9FAFC", end_color="F9FAFC", fill_type="solid")

        fill_status_done = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
        fill_status_prog = PatternFill(start_color="DDEBF7", end_color="DDEBF7", fill_type="solid")
        fill_status_todo = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")

        font_status_done = Font(name="Segoe UI", size=10, bold=True, color="276A3C")
        font_status_prog = Font(name="Segoe UI", size=10, bold=True, color="1F4E79")
        font_status_todo = Font(name="Segoe UI", size=10, bold=True, color="595959")

        thin_border = Border(
            left=Side(style="thin", color="D9D9D9"),
            right=Side(style="thin", color="D9D9D9"),
            top=Side(style="thin", color="D9D9D9"),
            bottom=Side(style="thin", color="D9D9D9"),
        )
        total_top_bottom_border = Border(
            left=Side(style="thin", color="D9D9D9"),
            right=Side(style="thin", color="D9D9D9"),
            top=Side(style="thin", color="1F4E79"),
            bottom=Side(style="double", color="1F4E79"),
        )

        now_str = datetime.datetime.now().strftime("%d %B %Y, %H:%M WIB")

        # =============================================================
        # SHEET CONTENT FOR TODAY'S DATE
        # =============================================================
        ws.views.sheetView[0].showGridLines = True

        def _format_sprint_date(dt_val):
            if not dt_val:
                return "-"
            dt_str = str(dt_val).strip()
            try:
                if "/" in dt_str:
                    parts = dt_str.split()[0].split("/")
                    if len(parts) == 3:
                        day, month, yr = parts
                        if len(yr) == 2:
                            yr = "20" + yr
                        return f"{int(day):02d} {month.capitalize()} {yr}"
                elif "-" in dt_str:
                    parts = dt_str[:10].split("-")
                    if len(parts) == 3:
                        yr, month, day = parts
                        import calendar
                        m_idx = int(month)
                        m_name = calendar.month_abbr[m_idx]
                        return f"{int(day):02d} {m_name} {yr}"
            except Exception:
                pass
            return dt_str[:11]

        # Header Block
        ws["A1"] = f"LAPORAN PROGRESS SQUAD & SPRINT: {root_key} ({today_date_str})"
        ws["A1"].font = font_main_title
        
        sprint_info = report_data.get("sprint_info") or {}
        sprint_name = sprint_info.get("name") or sprint_info.get("sprintName") or "Active Sprint"
        days_rem = sprint_info.get("days_remaining") if sprint_info.get("days_remaining") is not None else sprint_info.get("daysRemaining")
        start_date_fmt = sprint_info.get("startDateStr") or _format_sprint_date(sprint_info.get("start_date"))
        end_date_fmt = sprint_info.get("dueDateStr") or _format_sprint_date(sprint_info.get("end_date"))
        
        if days_rem is not None:
            sprint_sub = f"{root_summary} | Periode: {start_date_fmt} s/d {end_date_fmt} | Sisa Waktu: {days_rem} Hari Kerja | Diekspor: {now_str}"
        else:
            sprint_sub = f"{root_summary} | Diekspor pada: {now_str}"
        ws["A2"] = sprint_sub
        ws["A2"].font = font_subtitle
        ws.row_dimensions[1].height = 24
        ws.row_dimensions[2].height = 18

        # KPI Summary Cards Block (Rows 4-5)
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
        kpi_vals = [
            sprint_name,
            start_date_fmt,
            end_date_fmt,
            f"{days_rem} Hari Kerja" if days_rem is not None else "-",
            epics_count,
            overall.get("total", 0),
            overall.get("todo", 0),
            overall.get("in_progress", 0),
            overall.get("done", 0),
            f"{overall.get('percent_done', 0.0)}%",
        ]

        for i, (lbl, val) in enumerate(zip(kpi_labels, kpi_vals), 1):
            c_lbl = ws.cell(row=4, column=i, value=lbl)
            c_lbl.font = Font(name="Segoe UI", size=9, bold=True, color="595959")
            c_lbl.alignment = Alignment(horizontal="center", vertical="center")
            c_lbl.fill = fill_zebra
            c_lbl.border = thin_border

            c_val = ws.cell(row=5, column=i, value=val)
            c_val.font = Font(name="Segoe UI", size=11, bold=True, color="1F4E79")
            c_val.alignment = Alignment(horizontal="center", vertical="center")
            c_val.fill = fill_total
            c_val.border = thin_border

        ws.row_dimensions[4].height = 18
        ws.row_dimensions[5].height = 24

        # -------------------------------------------------------------
        # SECTION 1: RINGKASAN PROGRESS MEMBER (No Subtask SP)
        # -------------------------------------------------------------
        ws["A7"] = "1. RINGKASAN PROGRESS PER DEVELOPER"
        ws["A7"].font = font_section_title
        ws.row_dimensions[7].height = 22

        member_headers = [
            "Nama Developer",
            "Role",
            "To Do",
            "In Progress",
            "Done",
            "Total Subtask",
            "% Selesai",
        ]
        for col_idx, h_text in enumerate(member_headers, 1):
            cell = ws.cell(row=8, column=col_idx, value=h_text)
            cell.font = font_header
            cell.fill = fill_header
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin_border
        ws.row_dimensions[8].height = 22

        # Sort members: active with tasks first (descending), then idle members
        raw_members = report_data.get("member_progress", [])
        active_members = [m for m in raw_members if m.get("total_subtasks", 0) > 0]
        active_members.sort(key=lambda x: x.get("total_subtasks", 0), reverse=True)
        idle_members = [m for m in raw_members if m.get("total_subtasks", 0) == 0]
        idle_members.sort(key=lambda x: x.get("name", ""))
        members = active_members + idle_members

        m_row = 9
        for idx, m in enumerate(members):
            row_fill = fill_zebra if idx % 2 == 1 else PatternFill(fill_type=None)
            
            c_name = ws.cell(row=m_row, column=1, value=m.get("name", ""))
            c_role = ws.cell(row=m_row, column=2, value=m.get("role", ""))
            c_todo = ws.cell(row=m_row, column=3, value=m.get("todo", 0))
            c_prog = ws.cell(row=m_row, column=4, value=m.get("in_progress", 0))
            c_done = ws.cell(row=m_row, column=5, value=m.get("done", 0))
            c_tot  = ws.cell(row=m_row, column=6, value=f"=SUM(C{m_row}:E{m_row})")
            c_pct  = ws.cell(row=m_row, column=7, value=f'=IF(F{m_row}=0, 0, E{m_row}/F{m_row})')

            c_name.font = font_bold if m.get("total_subtasks", 0) > 0 else font_data
            c_role.font = font_data
            c_todo.font = font_data
            c_prog.font = font_data
            c_done.font = font_data
            c_tot.font = font_bold
            c_pct.font = font_bold

            c_name.alignment = Alignment(horizontal="left", vertical="center")
            c_role.alignment = Alignment(horizontal="center", vertical="center")
            c_todo.alignment = Alignment(horizontal="right", vertical="center")
            c_prog.alignment = Alignment(horizontal="right", vertical="center")
            c_done.alignment = Alignment(horizontal="right", vertical="center")
            c_tot.alignment  = Alignment(horizontal="right", vertical="center")
            c_pct.alignment  = Alignment(horizontal="right", vertical="center")

            c_pct.number_format = "0.0%"

            for c in range(1, 8):
                cell_obj = ws.cell(row=m_row, column=c)
                cell_obj.border = thin_border
                if row_fill.fill_type:
                    cell_obj.fill = row_fill

            ws.row_dimensions[m_row].height = 20
            m_row += 1

        # Total Row for Member Table
        tot_member_row = m_row
        ws.cell(row=tot_member_row, column=1, value="Total Akumulasi Tim").font = font_bold
        ws.cell(row=tot_member_row, column=2, value="").font = font_bold
        ws.cell(row=tot_member_row, column=3, value=f"=SUM(C9:C{tot_member_row-1})").font = font_bold
        ws.cell(row=tot_member_row, column=4, value=f"=SUM(D9:D{tot_member_row-1})").font = font_bold
        ws.cell(row=tot_member_row, column=5, value=f"=SUM(E9:E{tot_member_row-1})").font = font_bold
        ws.cell(row=tot_member_row, column=6, value=f"=SUM(F9:F{tot_member_row-1})").font = font_bold

        c_pct_tot = ws.cell(row=tot_member_row, column=7, value=f'=IF(F{tot_member_row}=0, 0, E{tot_member_row}/F{tot_member_row})')
        c_pct_tot.font = font_bold
        c_pct_tot.number_format = "0.0%"

        for c in range(1, 8):
            cell_obj = ws.cell(row=tot_member_row, column=c)
            cell_obj.fill = fill_total
            cell_obj.border = total_top_bottom_border
            if c >= 3:
                cell_obj.alignment = Alignment(horizontal="right", vertical="center")
        ws.row_dimensions[tot_member_row].height = 22

        # -------------------------------------------------------------
        # CHARTS: SIDE-BY-SIDE WITH CLEAN DIRECT DATA LABELS
        # -------------------------------------------------------------
        chart_max_row = 9 + len(active_members) - 1 if len(active_members) > 0 else tot_member_row - 1

        # 1. NATIVE CLUSTERED BAR CHART (Placed at J7)
        if len(active_members) > 0:
            chart_bar = BarChart()
            chart_bar.type = "col"
            chart_bar.style = 10
            chart_bar.title = "Distribusi Status Subtask per Developer"
            chart_bar.y_axis.title = "Jumlah Subtask"

            # Legend at right side (never collides with title!)
            chart_bar.legend.legendPos = "r"

            # Sumbu X: explicitly show developer names at bottom
            chart_bar.x_axis.tickLblPos = "low"
            chart_bar.x_axis.delete = False

            # Direct Data Labels (only show value numbers cleanly!)
            chart_bar.dataLabels = DataLabelList()
            chart_bar.dataLabels.showVal = True
            chart_bar.dataLabels.showCatName = False
            chart_bar.dataLabels.showSerName = False
            chart_bar.dataLabels.showPercent = False
            chart_bar.dataLabels.showLegendKey = False

            data_ref = Reference(ws, min_col=3, max_col=5, min_row=8, max_row=chart_max_row)
            cats_ref = Reference(ws, min_col=1, min_row=9, max_row=chart_max_row)

            chart_bar.add_data(data_ref, titles_from_data=True)
            chart_bar.set_categories(cats_ref)
            chart_bar.height = 13
            chart_bar.width = 18

            ws.add_chart(chart_bar, "J7")

        # 2. NATIVE PIE CHART: Overall Project Status Ratio (Placed at U7)
        pie_data_row = 250
        ws.cell(row=pie_data_row, column=1, value="Status")
        ws.cell(row=pie_data_row, column=2, value="Jumlah")
        ws.cell(row=pie_data_row+1, column=1, value="To Do")
        ws.cell(row=pie_data_row+1, column=2, value=f"=C{tot_member_row}")
        ws.cell(row=pie_data_row+2, column=1, value="In Progress")
        ws.cell(row=pie_data_row+2, column=2, value=f"=D{tot_member_row}")
        ws.cell(row=pie_data_row+3, column=1, value="Done")
        ws.cell(row=pie_data_row+3, column=2, value=f"=E{tot_member_row}")

        chart_pie = PieChart()
        chart_pie.title = "Proporsi Status Sprint Keseluruhan"
        
        # Clean Pie Data Labels: Percentage only on slices + Legend on right
        chart_pie.dataLabels = DataLabelList()
        chart_pie.dataLabels.showPercent = True
        chart_pie.dataLabels.showCatName = False
        chart_pie.dataLabels.showVal = False
        chart_pie.dataLabels.showSerName = False
        chart_pie.legend.legendPos = "r"

        pie_data = Reference(ws, min_col=2, min_row=pie_data_row, max_row=pie_data_row+3)
        pie_cats = Reference(ws, min_col=1, min_row=pie_data_row+1, max_row=pie_data_row+3)
        chart_pie.add_data(pie_data, titles_from_data=True)
        chart_pie.set_categories(pie_cats)
        chart_pie.height = 13
        chart_pie.width = 15

        ws.add_chart(chart_pie, "U7")

        # -------------------------------------------------------------
        # SECTION 2: PROGRESS PER PARENT STORY / EPIC (Below Section 1)
        # -------------------------------------------------------------
        sec2_start = max(tot_member_row + 3, 26)
        ws.cell(row=sec2_start, column=1, value="2. PROGRESS PER PARENT STORY / EPIC").font = font_section_title
        ws.row_dimensions[sec2_start].height = 22

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
        sec2_header_row = sec2_start + 1
        for col_idx, h_text in enumerate(story_headers, 1):
            cell = ws.cell(row=sec2_header_row, column=col_idx, value=h_text)
            cell.font = font_header
            cell.fill = fill_sub_header
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin_border
        ws.row_dimensions[sec2_header_row].height = 22

        # Extract story / parent progress data with robust fallback
        raw_stories = report_data.get("story_progress") or report_data.get("stories") or report_data.get("parent_progress") or report_data.get("epic_progress") or []
        detailed_subtasks = report_data.get("detailed_subtasks", [])

        # If stories list is not explicitly populated, auto-aggregate from detailed_subtasks
        if not raw_stories and detailed_subtasks:
            parent_map = {}
            for sub in detailed_subtasks:
                p_key = sub.get("parent_key") or "Parent Story"
                p_sum = sub.get("parent_summary") or p_key
                if p_key not in parent_map:
                    parent_map[p_key] = {
                        "key": p_key,
                        "summary": p_sum,
                        "owner": sub.get("parent_owner") or sub.get("assignee") or "-",
                        "todo": 0,
                        "in_progress": 0,
                        "done": 0,
                        "subtasks": []
                    }
                parent_map[p_key]["subtasks"].append(sub)
                s_norm = str(sub.get("status", "")).lower()
                if any(k in s_norm for k in ("done", "closed", "resolved", "complete", "selesai")):
                    parent_map[p_key]["done"] += 1
                elif any(k in s_norm for k in ("in progress", "in development", "in review", "progress")):
                    parent_map[p_key]["in_progress"] += 1
                else:
                    parent_map[p_key]["todo"] += 1
            raw_stories = list(parent_map.values())

        stories_data = []
        for st in raw_stories:
            if "todo" in st or "in_progress" in st:
                stories_data.append(st)
            else:
                st_subtasks = st.get("subtasks", [])
                st_todo = 0
                st_prog = 0
                st_done = 0
                for sub in st_subtasks:
                    s_norm = str(sub.get("status", "")).lower()
                    if any(k in s_norm for k in ("done", "closed", "resolved", "complete", "selesai")):
                        st_done += 1
                    elif any(k in s_norm for k in ("in progress", "in development", "in review", "progress")):
                        st_prog += 1
                    else:
                        st_todo += 1

                stories_data.append({
                    "key": st.get("key", ""),
                    "summary": st.get("summary", ""),
                    "owner": st.get("owner") or st.get("assignee") or "-",
                    "todo": st_todo,
                    "in_progress": st_prog,
                    "done": st_done,
                    "total_subtasks": len(st_subtasks)
                })

        fill_parent_story = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
        font_parent_bold = Font(name="Segoe UI", size=10, bold=True, color="1F4E79")
        font_subtask_indent = Font(name="Segoe UI", size=9, color="333333")
        font_subtask_link = Font(name="Segoe UI", size=9, color="0563C1", underline="single")
        font_subtask_role = Font(name="Segoe UI", size=9, italic=True, color="595959")

        detailed_subtasks = report_data.get("detailed_subtasks", [])
        parent_rows_indices = []

        s_row = sec2_header_row + 1
        for idx, st in enumerate(stories_data):
            p_key = st.get("key", "")
            p_sum = st.get("summary", "")
            jira_link = f"{base_jira_url}/browse/{p_key}"

            # 1. PARENT STORY ROW (Header Level)
            parent_rows_indices.append(s_row)
            c_key = ws.cell(row=s_row, column=1)
            c_key.value = f'=HYPERLINK("{jira_link}", "{p_key}")' if p_key else "-"
            c_key.font = font_link
            c_key.alignment = Alignment(horizontal="center", vertical="center")

            c_sum = ws.cell(row=s_row, column=2, value=p_sum)
            c_sum.font = font_parent_bold
            c_sum.alignment = Alignment(horizontal="left", vertical="center")

            c_own = ws.cell(row=s_row, column=3, value=st.get("owner", "-"))
            c_own.font = font_bold if st.get("owner") not in ("-", "Unassigned") else font_data
            c_own.alignment = Alignment(horizontal="center", vertical="center")

            c_todo = ws.cell(row=s_row, column=4, value=st.get("todo", 0))
            c_prog = ws.cell(row=s_row, column=5, value=st.get("in_progress", 0))
            c_done = ws.cell(row=s_row, column=6, value=st.get("done", 0))
            c_tot  = ws.cell(row=s_row, column=7, value=f"=SUM(D{s_row}:F{s_row})")
            c_pct  = ws.cell(row=s_row, column=8, value=f'=IF(G{s_row}=0, 0, F{s_row}/G{s_row})')

            c_todo.font = font_bold
            c_prog.font = font_bold
            c_done.font = font_bold
            c_tot.font = font_bold
            c_pct.font = font_bold

            c_todo.alignment = Alignment(horizontal="right", vertical="center")
            c_prog.alignment = Alignment(horizontal="right", vertical="center")
            c_done.alignment = Alignment(horizontal="right", vertical="center")
            c_tot.alignment  = Alignment(horizontal="right", vertical="center")
            c_pct.alignment  = Alignment(horizontal="right", vertical="center")
            c_pct.number_format = "0.0%"

            for c in range(1, 9):
                cell_obj = ws.cell(row=s_row, column=c)
                cell_obj.border = thin_border
                cell_obj.fill = fill_parent_story

            ws.row_dimensions[s_row].height = 22
            s_row += 1

            # 2. NESTED SUBTASKS (Grouped under this Parent Story)
            matching_subs = [
                sub for sub in detailed_subtasks
                if (p_key and sub.get("parent_key") == p_key) or (p_sum and sub.get("parent_summary") == p_sum)
            ]

            for s_idx, sub in enumerate(matching_subs):
                sub_key = sub.get("key", "")
                sub_url = sub.get("url") or f"{base_jira_url}/browse/{sub_key}"
                sub_summary = sub.get("summary", "")
                sub_assignee = sub.get("assignee", "Unassigned")
                sub_role = sub.get("role", "-")
                raw_status = str(sub.get("status") or sub.get("status_category") or "To Do").strip()
                st_lower = raw_status.lower()

                # Indented Subtask Key
                c_sub_key = ws.cell(row=s_row, column=1)
                c_sub_key.value = f'=HYPERLINK("{sub_url}", "  ↳ {sub_key}")' if sub_key else "  ↳ -"
                c_sub_key.font = font_subtask_link
                c_sub_key.alignment = Alignment(horizontal="left", vertical="center")

                # Indented Subtask Title
                c_sub_sum = ws.cell(row=s_row, column=2, value=f"  ↳ {sub_summary}")
                c_sub_sum.font = font_subtask_indent
                c_sub_sum.alignment = Alignment(horizontal="left", vertical="center")

                # Assignee Developer
                c_sub_ass = ws.cell(row=s_row, column=3, value=sub_assignee)
                c_sub_ass.font = font_subtask_indent
                c_sub_ass.alignment = Alignment(horizontal="center", vertical="center")

                # Empty dash for To Do / In Progress / Done counts in subtask row
                ws.cell(row=s_row, column=4, value="-").alignment = Alignment(horizontal="center", vertical="center")
                ws.cell(row=s_row, column=5, value="-").alignment = Alignment(horizontal="center", vertical="center")

                # Role column (displayed in Col 6)
                c_sub_role = ws.cell(row=s_row, column=6, value=f"Role: {sub_role}" if sub_role != "-" else "-")
                c_sub_role.font = font_subtask_role
                c_sub_role.alignment = Alignment(horizontal="center", vertical="center")

                # Subtask Story Points / Dash (Col 7)
                c_sub_sp = ws.cell(row=s_row, column=7, value=sub.get("story_points") or "-")
                c_sub_sp.font = font_subtask_indent
                c_sub_sp.alignment = Alignment(horizontal="center", vertical="center")

                # Status Badge (Col 8)
                c_sub_stat = ws.cell(row=s_row, column=8)
                c_sub_stat.alignment = Alignment(horizontal="center", vertical="center")

                if any(k in st_lower for k in ("done", "closed", "resolved", "complete", "selesai")):
                    c_sub_stat.value = "Done"
                    c_sub_stat.fill = fill_status_done
                    c_sub_stat.font = font_status_done
                elif any(k in st_lower for k in ("in progress", "in development", "in review", "progress", "sedang")):
                    c_sub_stat.value = "In Progress"
                    c_sub_stat.fill = fill_status_prog
                    c_sub_stat.font = font_status_prog
                else:
                    c_sub_stat.value = "To Do"
                    c_sub_stat.fill = fill_status_todo
                    c_sub_stat.font = font_status_todo

                for c in range(1, 9):
                    cell_obj = ws.cell(row=s_row, column=c)
                    cell_obj.border = thin_border
                    if c < 8 and s_idx % 2 == 1:
                        cell_obj.fill = fill_zebra

                # Set native Excel row grouping outline level
                ws.row_dimensions[s_row].outlineLevel = 1
                ws.row_dimensions[s_row].height = 19
                s_row += 1

        # Story Total Row
        tot_story_row = s_row
        ws.cell(row=tot_story_row, column=1, value="Total").font = font_bold
        ws.cell(row=tot_story_row, column=2, value="").font = font_bold
        ws.cell(row=tot_story_row, column=3, value="").font = font_bold

        # Sum only Parent rows to prevent double-counting
        if parent_rows_indices:
            sum_d_cells = "+".join([f"D{r}" for r in parent_rows_indices])
            sum_e_cells = "+".join([f"E{r}" for r in parent_rows_indices])
            sum_f_cells = "+".join([f"F{r}" for r in parent_rows_indices])
            sum_g_cells = "+".join([f"G{r}" for r in parent_rows_indices])
            ws.cell(row=tot_story_row, column=4, value=f"={sum_d_cells}").font = font_bold
            ws.cell(row=tot_story_row, column=5, value=f"={sum_e_cells}").font = font_bold
            ws.cell(row=tot_story_row, column=6, value=f"={sum_f_cells}").font = font_bold
            ws.cell(row=tot_story_row, column=7, value=f"={sum_g_cells}").font = font_bold
        else:
            ws.cell(row=tot_story_row, column=4, value=0).font = font_bold
            ws.cell(row=tot_story_row, column=5, value=0).font = font_bold
            ws.cell(row=tot_story_row, column=6, value=0).font = font_bold
            ws.cell(row=tot_story_row, column=7, value=0).font = font_bold

        c_pct_s_tot = ws.cell(row=tot_story_row, column=8, value=f'=IF(G{tot_story_row}=0, 0, F{tot_story_row}/G{tot_story_row})')
        c_pct_s_tot.font = font_bold
        c_pct_s_tot.number_format = "0.0%"

        for c in range(1, 9):
            cell_obj = ws.cell(row=tot_story_row, column=c)
            cell_obj.fill = fill_total
            cell_obj.border = total_top_bottom_border
            if c >= 4:
                cell_obj.alignment = Alignment(horizontal="right", vertical="center")
        ws.row_dimensions[tot_story_row].height = 22

        # -------------------------------------------------------------
        # SECTION 3: RINCIAN SELURUH SUBTASK JIRA (Below Section 2 - No SP)
        # -------------------------------------------------------------
        sec3_start = tot_story_row + 3
        ws.cell(row=sec3_start, column=1, value="3. RINCIAN LENGKAP SELURUH SUBTASK JIRA").font = font_section_title
        ws.row_dimensions[sec3_start].height = 22

        subtask_headers = [
            "No",
            "Key Subtask (Link)",
            "Judul Subtask",
            "Key Parent",
            "Story Induk",
            "Assignee",
            "Role",
            "Status",
        ]
        sec3_header_row = sec3_start + 1
        for col_idx, h_text in enumerate(subtask_headers, 1):
            cell = ws.cell(row=sec3_header_row, column=col_idx, value=h_text)
            cell.font = font_header
            cell.fill = fill_header
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin_border
        ws.row_dimensions[sec3_header_row].height = 22

        detailed_subtasks = report_data.get("detailed_subtasks", [])
        d_row = sec3_header_row + 1
        for idx, sub in enumerate(detailed_subtasks, 1):
            row_fill = fill_zebra if idx % 2 == 0 else PatternFill(fill_type=None)
            sub_key = sub.get("key", "")
            sub_url = sub.get("url") or f"{base_jira_url}/browse/{sub_key}"
            parent_key = sub.get("parent_key", "")
            parent_url = f"{base_jira_url}/browse/{parent_key}"

            c_no = ws.cell(row=d_row, column=1, value=idx)
            c_no.alignment = Alignment(horizontal="center", vertical="center")
            c_no.font = font_data

            c_skey = ws.cell(row=d_row, column=2)
            c_skey.value = f'=HYPERLINK("{sub_url}", "{sub_key}")' if sub_key else "-"
            c_skey.font = font_link
            c_skey.alignment = Alignment(horizontal="center", vertical="center")

            c_ssum = ws.cell(row=d_row, column=3, value=sub.get("summary", ""))
            c_ssum.font = font_data
            c_ssum.alignment = Alignment(horizontal="left", vertical="center")

            c_pkey = ws.cell(row=d_row, column=4)
            c_pkey.value = f'=HYPERLINK("{parent_url}", "{parent_key}")' if parent_key else "-"
            c_pkey.font = font_link
            c_pkey.alignment = Alignment(horizontal="center", vertical="center")

            c_psum = ws.cell(row=d_row, column=5, value=sub.get("parent_summary", ""))
            c_psum.font = font_data

            c_ass = ws.cell(row=d_row, column=6, value=sub.get("assignee", "Unassigned"))
            c_ass.font = font_bold if sub.get("assignee") != "Unassigned" else font_data

            c_role = ws.cell(row=d_row, column=7, value=sub.get("role", ""))
            c_role.font = font_data
            c_role.alignment = Alignment(horizontal="center", vertical="center")

            # Status badge with distinct background and font colors
            raw_status = str(sub.get("status") or sub.get("status_category") or "To Do").strip()
            st_lower = raw_status.lower()

            c_st = ws.cell(row=d_row, column=8)
            c_st.alignment = Alignment(horizontal="center", vertical="center")

            if any(k in st_lower for k in ("done", "closed", "resolved", "complete", "selesai")):
                c_st.value = "Done"
                c_st.fill = fill_status_done
                c_st.font = font_status_done
            elif any(k in st_lower for k in ("in progress", "in development", "in review", "progress", "sedang")):
                c_st.value = "In Progress"
                c_st.fill = fill_status_prog
                c_st.font = font_status_prog
            else:
                c_st.value = "To Do"
                c_st.fill = fill_status_todo
                c_st.font = font_status_todo

            for c in range(1, 9):
                cell_obj = ws.cell(row=d_row, column=c)
                cell_obj.border = thin_border
                if c != 8 and row_fill.fill_type:
                    cell_obj.fill = row_fill

            ws.row_dimensions[d_row].height = 20
            d_row += 1

        # -------------------------------------------------------------
        # CHARTS FOR SECTION 2 & SECTION 3
        # -------------------------------------------------------------
        # 1. SECTION 2 CHART: Story Completion Vertical Stacked Column Chart (Placed at J{sec2_start})
        if len(stories_data) > 0:
            s_chart_start_row = 300
            ws.cell(row=s_chart_start_row, column=1, value="Story Induk")
            ws.cell(row=s_chart_start_row, column=2, value="To Do")
            ws.cell(row=s_chart_start_row, column=3, value="In Progress")
            ws.cell(row=s_chart_start_row, column=4, value="Done")

            # Take top 15 stories for optimal visual presentation
            chart_stories = stories_data[:15]
            for s_i, s_item in enumerate(chart_stories, 1):
                s_curr_row = s_chart_start_row + s_i
                s_key = s_item.get("key", "")
                s_sum = s_item.get("summary", "")
                label_text = f"[{s_key}] {s_sum[:25]}" if s_sum else f"[{s_key}]"
                ws.cell(row=s_curr_row, column=1, value=label_text)
                ws.cell(row=s_curr_row, column=2, value=s_item.get("todo", 0))
                ws.cell(row=s_curr_row, column=3, value=s_item.get("in_progress", 0))
                ws.cell(row=s_curr_row, column=4, value=s_item.get("done", 0))

            chart_story = BarChart()
            chart_story.type = "col"
            chart_story.grouping = "stacked"
            chart_story.overlap = 100
            chart_story.title = "Progres Penyelesaian per Story Induk"
            chart_story.x_axis.title = "Story Induk (Fitur)"
            chart_story.y_axis.title = "Jumlah Subtask"
            chart_story.legend.legendPos = "r"

            chart_story.dataLabels = DataLabelList()
            chart_story.dataLabels.showVal = True
            chart_story.dataLabels.showCatName = False
            chart_story.dataLabels.showSerName = False
            chart_story.dataLabels.showPercent = False

            s_data_ref = Reference(ws, min_col=2, max_col=4, min_row=s_chart_start_row, max_row=s_chart_start_row + len(chart_stories))
            s_cats_ref = Reference(ws, min_col=1, min_row=s_chart_start_row + 1, max_row=s_chart_start_row + len(chart_stories))

            chart_story.add_data(s_data_ref, titles_from_data=True)
            chart_story.set_categories(s_cats_ref)

            # Apply semantic colors: To Do (Gray), In Progress (Blue), Done (Green)
            if len(chart_story.series) >= 3:
                chart_story.series[0].graphicalProperties.solidFill = "A6A6A6"  # To Do
                chart_story.series[1].graphicalProperties.solidFill = "2E75B6"  # In Progress
                chart_story.series[2].graphicalProperties.solidFill = "548235"  # Done

            chart_story.height = 14
            chart_story.width = 24

            ws.add_chart(chart_story, f"J{sec2_start}")

        # 2. SECTION 3 CHART: Role Breakdown Doughnut Chart (Placed at J{sec3_start})
        if len(detailed_subtasks) > 0:
            role_counts = {}
            for sub in detailed_subtasks:
                r_name = str(sub.get("role") or "General").strip().title()
                if not r_name or r_name == "-":
                    r_name = "General / Other"
                role_counts[r_name] = role_counts.get(r_name, 0) + 1

            r_chart_start_row = 330
            ws.cell(row=r_chart_start_row, column=1, value="Role")
            ws.cell(row=r_chart_start_row, column=2, value="Jumlah")

            r_idx = 1
            for r_name, r_cnt in sorted(role_counts.items(), key=lambda x: x[1], reverse=True):
                r_curr_row = r_chart_start_row + r_idx
                ws.cell(row=r_curr_row, column=1, value=r_name)
                ws.cell(row=r_curr_row, column=2, value=r_cnt)
                r_idx += 1

            chart_role = DoughnutChart()
            chart_role.title = "Distribusi Subtask per Role (BE / FE / QA)"
            chart_role.legend.legendPos = "r"

            chart_role.dataLabels = DataLabelList()
            chart_role.dataLabels.showPercent = True
            chart_role.dataLabels.showVal = False
            chart_role.dataLabels.showCatName = False
            chart_role.dataLabels.showSerName = False

            r_data_ref = Reference(ws, min_col=2, min_row=r_chart_start_row, max_row=r_chart_start_row + len(role_counts))
            r_cats_ref = Reference(ws, min_col=1, min_row=r_chart_start_row + 1, max_row=r_chart_start_row + len(role_counts))

            chart_role.add_data(r_data_ref, titles_from_data=True)
            chart_role.set_categories(r_cats_ref)
            chart_role.height = 13
            chart_role.width = 16

            ws.add_chart(chart_role, f"J{sec3_start}")

        # Auto-fit column widths
        for col in ws.columns:
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            if col[0].column in (3, 5):
                ws.column_dimensions[col_letter].width = 42
            elif col[0].column == 2:
                ws.column_dimensions[col_letter].width = 30
            elif col[0].column > 9:
                ws.column_dimensions[col_letter].width = 12
            else:
                max_len = max(len(str(cell.value or "")) for cell in col[:tot_story_row+1])
                ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

        # Save workbook safely with fallback if file is currently open in Excel
        try:
            wb.save(full_path)
            return filename
        except PermissionError:
            import time
            fallback_filename = f"Laporan_Progress_{safe_key}_update_{int(time.time())}.xlsx"
            fallback_path = os.path.join(output_path, fallback_filename)
            wb.save(fallback_path)
            print(f"Peringatan: File '{filename}' sedang dibuka di Microsoft Excel. Hasil baru disimpan sebagai: '{fallback_filename}'")
            return fallback_filename

    def generate_report(
        self, balanced_results: dict, epic_key: str, output_path: str = "."
    ) -> str:
        """
        Legacy workload balance export (kept for backwards compatibility).
        """
        member_progress = []
        detailed_subtasks = []
        tot_todo = 0
        tot_sp = 0.0

        for item in balanced_results.get("assignments", []):
            emp = item.get("employee", {})
            tasks = item.get("assigned_subtasks", [])
            sp = item.get("total_story_points", 0.0)
            tot_todo += len(tasks)
            tot_sp += sp

            member_progress.append({
                "name": emp.get("name", ""),
                "role": emp.get("role", ""),
                "todo": len(tasks),
                "in_progress": 0,
                "done": 0,
                "total_subtasks": len(tasks),
                "total_sp": sp,
                "percent_done": 0.0,
            })

            for t in tasks:
                detailed_subtasks.append({
                    "key": "",
                    "summary": t.get("summary", ""),
                    "parent_key": t.get("parent_key", epic_key),
                    "parent_summary": t.get("parent_summary", ""),
                    "assignee": emp.get("name", "Unassigned"),
                    "role": t.get("role", emp.get("role", "")),
                    "status": "To Do",
                    "status_category": "To Do",
                    "story_points": t.get("story_points", 0.0),
                    "url": f"{settings.JIRA_URL.rstrip('/')}/browse/{t.get('parent_key', epic_key)}",
                })

        report_data = {
            "root_key": epic_key,
            "root_summary": f"Alokasi Subtask Baru {epic_key}",
            "total_epics_count": 1,
            "overall_status": {
                "todo": tot_todo,
                "in_progress": 0,
                "done": 0,
                "total": tot_todo,
                "percent_done": 0.0,
            },
            "member_progress": member_progress,
            "story_progress": [
                {
                    "key": epic_key,
                    "summary": f"Subtask AI Baru {epic_key}",
                    "todo": tot_todo,
                    "in_progress": 0,
                    "done": 0,
                    "total_subtasks": tot_todo,
                    "total_sp": tot_sp,
                    "percent_done": 0.0,
                }
            ],
            "detailed_subtasks": detailed_subtasks,
        }

        return self.generate_progress_report(report_data, epic_key, output_path)
