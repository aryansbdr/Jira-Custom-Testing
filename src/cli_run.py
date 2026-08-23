import os
from shared.config import settings
from shared.database import init_db

# Infrastructure & Repository Imports
from modules.generate_subtask.infrastructure.sqlite_story_repository import (
    SqliteStoryRepository,
)
from modules.generate_subtask.infrastructure.llm_client import LlmClient
from modules.generate_subtask.infrastructure.jira_rest_client import JiraRestClient
from modules.reporting.infrastructure.pandas_excel_parser import PandasExcelParser

# Domain Service Imports
from modules.reporting.domain.balancer_service import WorkloadBalancerService
from modules.notification.infrastructure.telegram_client import TelegramBotClient
from modules.notification.application.send_sprint_reminder_use_case import SendSprintReminderUseCase
# Application Use Cases Imports
from modules.generate_subtask.application.generate_subtasks_use_case import (
    GenerateSubtasksUseCase,
)
from modules.reporting.application.balance_workload_use_case import (
    BalanceWorkloadUseCase,
)


def main():
    # 1. Initialize SQLite Database
    init_db()

    # Instantiate classes
    story_repo = SqliteStoryRepository()
    llm_client = LlmClient()
    jira_client = JiraRestClient()
    excel_parser = PandasExcelParser()

    generate_subtasks_uc = GenerateSubtasksUseCase(story_repo, llm_client)
    balance_workload_uc = BalanceWorkloadUseCase(WorkloadBalancerService())

    # 2. Check and auto-import RAG reference data if database is empty
    existing = story_repo.get_all()
    historical_file = "historical_references.xlsx"


    if not existing:
        if os.path.exists(historical_file):
            print(f"Database RAG kosong. Mengimpor data dari '{historical_file}'...")
            try:
                with open(historical_file, "rb") as f:
                    stories = excel_parser.parse_historical_import(f.read())

                success_count = 0
                for story in stories:
                    text_to_embed = f"{story.summary}\n{story.description}"
                    embedding = llm_client.get_text_embedding(text_to_embed)
                    story_repo.save(story, embedding)
                    success_count += 1
                print(
                    f"-> Berhasil mengimpor {success_count} story referensi ke database RAG."
                )
            except Exception as e:
                print(f"Warning: Gagal mengimpor data RAG: {e}")
        else:
            print("Peringatan: Database referensi RAG masih kosong.")
            print(
                f"Anda bisa menaruh file '{historical_file}' di folder ini untuk menyelaraskan output AI."
            )

    # 3. Read active members
    members_file = "Members.xlsx"
    if not os.path.exists(members_file):
        print(f"Error: File '{members_file}' tidak ditemukan.")
        print(
            "Harap buat file 'members.xlsx' terlebih dahulu dengan kolom: PN, Nama Pegawai, Role."
        )
        return

    print(f"Reading active members from '{members_file}'...")
    try:
        with open(members_file, "rb") as f:
            employees = excel_parser.parse_employees(f.read())
        print(f"-> Berhasil memuat {len(employees)} anggota aktif dari Excel.")
    except Exception as e:
        print(f"Error parsing members Excel: {e}")
        return

    # =============================================================
    # MAIN MENU SELECTION
    # =============================================================
    print("\n" + "=" * 65)
    print("        GENERATE SUBTASK AI & WORKLOAD BALANCER (CLI)        ")
    print("=" * 65)
    print("Pilih Menu:")
    print("  [1] Generate Subtask AI & Workload Balancer (Alur Lengkap)")
    print("  [2] Ekspor Laporan Progress Jira ke Excel (.xlsx dengan Grafik)")
    print("  [3] Tes & Kirim Notifikasi Sprint Reminder ke Telegram (Auto-Tag Member)")
    print("  [4] Keluar")
    main_menu = input("Pilih menu [1/2/3/4, default=1]: ").strip()

    if main_menu == "4":
        return

   
    if main_menu == "3":
        default_project = "JT"
        input_key = input(f"\nMasukkan Project Key / Query JQL / URL Dashboard Jira / Epic Key\n(default: '{default_project}', contoh: JT, 26953, BL-38812, atau project = BL AND resolution = Unresolved...): ").strip()
        if not input_key:
            input_key = default_project

        print(f"\nMengambil info Sprint aktif & sisa hari secara dinamis dari Jira untuk '{input_key}'...")
        detected_sprint = None
        if hasattr(jira_client, "get_active_sprint_info"):
            try:
                detected_sprint = jira_client.get_active_sprint_info(input_key)
            except Exception:
                pass

        detected_name = detected_sprint.get("name") if detected_sprint else "Active Sprint"
        detected_days = detected_sprint.get("days_remaining") if detected_sprint and detected_sprint.get("days_remaining") is not None else 2

        print(f"-> Info Dinamis Jira: Sprint '{detected_name}' (Sisa: {detected_days} Hari Kerja)")
        sprint_name_in = input(f"Masukkan Nama Sprint [Tekan Enter untuk '{detected_name}']: ").strip()
        sprint_name = sprint_name_in if sprint_name_in else detected_name

        days_in = input(f"Masukkan Sisa Hari Sprint [Tekan Enter untuk {detected_days}]: ").strip()
        days_rem = int(days_in) if days_in.isdigit() else detected_days

        print(f"\nMengirim notifikasi Sprint Reminder untuk '{input_key}' ke Telegram...")
        try:
            tg_client = TelegramBotClient()
            reminder_uc = SendSprintReminderUseCase(jira_client, tg_client)
            result = reminder_uc.execute(
                epic_key=input_key,
                sprint_name=sprint_name,
                days_remaining=days_rem,
                employees=employees,
            )

            if result.get("status") == "success":
                print("\n" + "=" * 60)
                print("SUKSES! Notifikasi Sprint Reminder berhasil terkirim ke Telegram!")
                print("=" * 60)
                print(f" Target         : {result.get('epic_key')} ({result.get('sprint_name')})")
                print(f" Sisa Hari      : {days_rem} Hari Kerja")
                print(f" Total Subtask  : {result.get('total_tasks')}")
                print(f" Selesai (Done) : {result.get('done_tasks')}")
                print(f" Sisa Pending   : {result.get('pending_tasks')}")
                print("=" * 60)
                print("Silakan cek grup Telegram Anda, pesan auto-tag sudah masuk! 📲")
            else:
                print(f"Gagal mengirim pesan: {result}")
            return
        except Exception as e:
            print(f"Error mengirim notifikasi Telegram: {e}")
            return


    if main_menu == "2":
        default_project = "JT"
        print("\n" + "-" * 70)
        print("PILIHAN TARGET LAPORAN EXCEL:")
        print("  • Project Key       : contoh 'JT' atau 'BL'")
        print("  • Raw JQL Query     : contoh 'project = BL AND resolution = Unresolved ORDER BY priority DESC, updated DESC'")
        print("  • URL/ID Dashboard  : contoh '26953' atau 'https://jira.bri.co.id/...selectPageId=26953'")
        print("  • Epic Key / Issue  : contoh 'BL-38812' atau 'JT-161'")
        print("  • Filter ID         : contoh '48596'")
        print("-" * 70)
        input_key = input(f"Masukkan Project Key / Query JQL / Dashboard ID [default: '{default_project}']: ").strip()
        if not input_key:
            input_key = default_project

        print(f"\nMengambil data status & progress riil untuk '{input_key}' dari Jira...")
        try:
            from modules.reporting.infrastructure.excel_reporter import ExcelReporter
            progress_data = jira_client.get_progress_report_data(input_key, employees)

            if not progress_data.get("detailed_subtasks"):
                print(f"Peringatan: Tidak ditemukan subtask di bawah '{input_key}' di Jira.")
                return

            overall = progress_data.get("overall_status", {})
            epics_count = progress_data.get("total_epics_count", 0)
            print("\n" + "=" * 60)
            print(f"   RINGKASAN PROGRESS SPRINT / SQUAD: {progress_data.get('root_key')}")
            print("=" * 60)
            print(f" Total Epic / Story : {epics_count} tiket induk")
            print(f" Total Subtask      : {overall.get('total', 0)} subtask")
            print(f" To Do              : {overall.get('todo', 0)}")
            print(f" In Progress        : {overall.get('in_progress', 0)}")
            print(f" Done               : {overall.get('done', 0)} ({overall.get('percent_done', 0.0)}% Selesai)")
            print("=" * 60)

            reporter = ExcelReporter()
            safe_key = "".join([c for c in input_key if c.isalnum() or c in ("-", "_")]).strip() or "Sprint_Report"
            filename = reporter.generate_progress_report(progress_data, safe_key)

            print(f"\n{'=' * 65}")
            print(f"  ✅  LAPORAN EXCEL BERHASIL DIBUAT!")
            print(f"{'=' * 65}")
            print(f"  📂 Lokasi File  : {filename}")
            print(f"  📁 Folder       : {os.path.dirname(filename)}")
            print(f"  📄 Nama File    : {os.path.basename(filename)}")
            print(f"{'=' * 65}")
            return
        except Exception as e:
            print(f"Gagal mengambil data progress atau membuat file Excel: {e}")
            return

    # -------------------------------------------------------------
    # MENU 1: FULL SUBTASK GENERATION & LOAD BALANCER
    # -------------------------------------------------------------
    # 4. Fetch issues from Jira — support BOTH Epic Key and single Story/Task Key
    input_key = input("\nMasukkan Epic Key atau Story/Task Key Jira (contoh: BL-38812 atau BL-38813): ").strip()
    if not input_key:
        print("Key tidak boleh kosong.")
        return

    print("\nPilih Mode Generate Subtask:")
    print("  [1] Mode Bebas   — Generate semua subtask berdasarkan isi AC (default)")
    print("  [2] Mode Ketat   — Tentukan jumlah subtask berdasarkan SP (1-2SP=1, 3SP=2, 5-8SP=3, 13SP=4 subtask)")
    mode_input = input("Pilih mode [1/2, default=1]: ").strip()
    generation_mode = "strict" if mode_input == "2" else "free"
    mode_label = "KETAT (SP-based)" if generation_mode == "strict" else "BEBAS (AC-based)"
    print(f"\n Mode dipilih: {mode_label}")

    jira_stories = []
    try:
        print(f"\nMengambil issue '{input_key}' dari Jira...")
        single = jira_client.get_single_issue(input_key)

        if single and single.issue_type.lower() == "epic":
            children = jira_client.get_epic_issues(single.key)
            if children:
                jira_stories = children
                type_counts = {}
                for s in jira_stories:
                    t = s.issue_type.title()
                    type_counts[t] = type_counts.get(t, 0) + 1
                breakdown_parts = [f"{v} {k}" for k, v in type_counts.items()]
                print(f"Ditemukan {len(jira_stories)} Story/Task di bawah Epic {single.key} ({', '.join(breakdown_parts)}).")
            else:
                print(f"Epic '{single.key}' tidak memiliki child issue Story/Task.")
                return
        elif single:
            jira_stories = [single]
            print(f"Berhasil memuat Story/Task tunggal: [{single.key}] {single.summary} ({single.story_points} SP)")
        else:
            children = jira_client.get_epic_issues(input_key)
            if children:
                jira_stories = children
                print(f"Ditemukan {len(jira_stories)} child issue di bawah Epic {input_key}.")
            else:
                print(f"\nTiket '{input_key}' tidak ditemukan di Jira ({settings.JIRA_URL}).")
                print("Pastikan Key tiket valid dan koneksi/kredensial ke server Jira di file .env sudah sesuai.")
                return

    except Exception as e:
        print(f"Gagal mengambil issue dari Jira: {e}")
        print("Pastikan konfigurasi JIRA_URL, JIRA_EMAIL, dan JIRA_API_TOKEN di file .env sudah benar.")
        return

    # 6. Process RAG + Gemini Subtask Generation with Controlled Parallel Concurrency (2 Workers)
    import time
    start_time = time.time()
    print("\nMulai melakukan dekomposisi subtask")
    all_subtasks = []

    def process_story(item_tuple):
        idx, story = item_tuple
        desc = story.description or story.summary
        time.sleep(1.0)  # Pacing delay to prevent hitting Gemini Free Tier 15 RPM limit
        try:
            existing_titles = list(jira_client.get_existing_subtask_summaries(story.key))
            generated_subs = generate_subtasks_uc.execute(
                summary=story.summary,
                description=desc,
                parent_sp=story.story_points,
                mode=generation_mode,
                existing_subtasks=existing_titles,
                issue_key=story.key
            )
            for sub in generated_subs:
                sub.parent_key = story.key
                sub.parent_summary = story.summary
                sub.parent_type = story.issue_type
            return idx, story, generated_subs, None
        except Exception as err:
            return idx, story, [], err

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = executor.map(process_story, list(enumerate(jira_stories)))
        
        for idx, story, generated_subs, err in futures:
            print(
                "\n-----------------------------------------------------------------"
            )
            print(
                f" [{idx + 1}/{len(jira_stories)}] TIKET INDUK: [{story.key}] {story.summary} ({story.story_points} SP)"
            )
            print(
                "-----------------------------------------------------------------"
            )
            if err:
                print(f" Gagal meng-generate subtask untuk {story.key}: {err}")
                continue
            
            if generated_subs:
                print(f"   Subtask yang Dihasilkan ({len(generated_subs)} subtask):")
                for sub_idx, sub in enumerate(generated_subs, 1):
                    all_subtasks.append(sub)
                    print(
                        f"    {sub_idx}. {sub.summary}"
                    )
            else:
                existing_count = len(jira_client.get_existing_subtask_summaries(story.key))
                if existing_count > 0:
                    print(f" [LENGKAP] Semua kebutuhan AC ({existing_count} subtask) sudah terpenuhi di Jira. Tidak ada subtask tambahan.")
                else:
                    print(" [SKIP] Tiket Kategori Test / Deployment (Dieksepsikan dari pembuatan subtask)")

    




    if not all_subtasks:
        print("\nTidak ada subtask yang berhasil dibuat oleh AI.")
        return

    # 7. Balance workload
    print("\nMenyeimbangkan beban kerja (Load Balancing)...")
    balanced = balance_workload_uc.execute(employees, all_subtasks)

    # 8. Print preview
    print("\n" + "=" * 65)
    print("          PREVIEW PEMBAGIAN TUGAS (WORKLOAD BALANCER)         ")
    print("=" * 65)

    active_assignments = []
    for item in balanced["assignments"]:
        emp = item["employee"]
        tasks = item["assigned_subtasks"]
        total_sp = item["total_story_points"]

        print(f"\n DEVELOPER : {emp['name'].upper()} ({emp['role']})")
        print(f"   TOTAL LOAD: {total_sp} Story Points")
        print("   --------------------------------------------------------------")

        if not tasks:
            print("      (Tidak ada tugas yang didelegasikan untuk developer ini)")
            continue

        active_assignments.append(item)
        for idx, t in enumerate(tasks, 1):
            parent_info = f"{t['parent_key']} - {t.get('parent_summary', '')}".strip(" -")
            print(f"   {idx}. [{parent_info}]")
            print(f"       {t['summary']}")
            if idx < len(tasks):
                print("      . . . . . . . . . . . . . . . . . . . . . . . . . . .")

    if balanced["unassigned_subtasks"]:
        print("\n" + "🚨" + "!" * 63)
        print("  TUGAS TIDAK DAPAT DI-ASSIGN (TIDAK ADA ROLE COCOK):")
        print("─" * 65)
        for t in balanced["unassigned_subtasks"]:
            parent_info = f"{t['parent_key']} - {t.get('parent_summary', '')}".strip(" -")
            print(
                f"  ⚠️  [{parent_info}] {t['summary']} (Target: {t['role']})"
            )
        print("!" * 65)

    # 9. Export workload & progress report to Excel (Optional)
    export_choice = (
        input(
            "\nApakah Anda ingin mengekspor laporan progress & beban kerja ini ke Excel dengan grafik? (y/n, default y): "
        )
        .strip()
        .lower()
    )
    if export_choice != "n":
        from modules.reporting.infrastructure.excel_reporter import ExcelReporter

        reporter = ExcelReporter()
        safe_key = "".join([c for c in input_key if c.isalnum() or c in ("-", "_")]).strip() or "report"
        print("\nMengumpulkan data progress status riil dari Jira...")
        try:
            progress_data = jira_client.get_progress_report_data(input_key, employees)
            if progress_data.get("detailed_subtasks"):
                filename = reporter.generate_progress_report(progress_data, safe_key)
            else:
                # Fallback to balanced subtask preview structure
                filename = reporter.generate_report(balanced, safe_key)
            print(f"✅ Sukses! Laporan Excel (.xlsx) dengan grafik berhasil dibuat: '{filename}'")
        except Exception as e:
            print(f"Warning: Gagal mengekspor laporan Excel: {e}")

    # 10. Interactive & Intuitive Subtask Selection Before Committing to Jira
    # Group tasks hierarchically by Parent Story
    story_map = {}
    for item in active_assignments:
        emp = item["employee"]
        for t in item["assigned_subtasks"]:
            parent_k = t.get("parent_key", "GENERAL")
            if parent_k not in story_map:
                story_map[parent_k] = {
                    "parent_key": parent_k,
                    "parent_summary": t.get("parent_summary", ""),
                    "subtasks": []
                }
            story_map[parent_k]["subtasks"].append({
                "subtask": t,
                "employee": emp
            })

    total_stories = len(story_map)
    flat_tasks = []
    
    for s_idx, (parent_k, st_info) in enumerate(story_map.items(), 1):
        for sub_idx, item_task in enumerate(st_info["subtasks"], 1):
            code_str = f"{s_idx}.{sub_idx}" if total_stories > 1 else f"{sub_idx}"
            flat_tasks.append({
                "story_idx": s_idx,
                "sub_idx": sub_idx,
                "code": code_str,
                "subtask": item_task["subtask"],
                "employee": item_task["employee"],
            })

    if not flat_tasks:
        print("\nTidak ada subtask yang dialokasikan untuk di-push.")
        return

    print("\n" + "=" * 72)
    print("        PILIH SUBTASK YANG INGIN DIBUAT (PUSH) KE JIRA        ")
    print("=" * 72)

    current_story_idx = None
    for item_task in flat_tasks:
        s_idx = item_task["story_idx"]
        t = item_task["subtask"]
        emp = item_task["employee"]
        role_badge = "[FE]" if "front" in str(t.get("role", "")).lower() or "web" in str(t.get("role", "")).lower() or "mobile" in str(t.get("role", "")).lower() else "[BE]"
        parent_k = t.get("parent_key", "")
        parent_title = t.get("parent_summary", "")

        if s_idx != current_story_idx:
            current_story_idx = s_idx
            story_prefix = f"📁 STORY {s_idx}: [{parent_k}] {parent_title}".strip() if total_stories > 1 else f"📁 [{parent_k}] {parent_title}".strip()
            print(f"\n  {story_prefix}")
            print("  " + "─" * 68)

        print(f"    [{item_task['sub_idx']:>2}] {role_badge} {t['summary']}  (Assignee: {emp['name']})")

    print("\n" + "=" * 72)
    print("Opsi Input (Format: <Index Story>: <Nomor Subtask>):")
    if total_stories > 1:
        print("  • Tekan [Enter] atau ketik 'all'          : Push SEMUA subtask")
        print("  • Buang subtask di Story tertentu         : contoh: '1: 2, 5' (Story 1 buang #2 dan #5)")
        print("  • Buang rentang di Story tertentu         : contoh: '1: 2-4' (Story 1 buang #2 s/d #4)")
        print("  • Buang 1 Story penuh                     : contoh: 'skip 2' atau '!2' (Buang Story 2)")
        print("  • Bisa sebut Key langsung                 : contoh: 'JT-284: 2, 5'")
        print("  • Filter Role                             : contoh: 'fe' atau 'be'")
    else:
        print("  • Tekan [Enter] atau ketik 'all'          : Push SEMUA subtask")
        print("  • Ketik nomor (contoh: 1-4, 6)            : Hanya push nomor tersebut")
        print("  • Ketik 'skip 2, 5' atau '!2, 5'          : Push semua KECUALI nomor 2 dan 5")
    print("  • Ketik 'n' atau 'batal'                  : Batalkan (tidak ada tiket dibuat)")
    print("-" * 72)

    import re
    def _parse_cli_selection(input_str: str, tasks_list: list, num_stories: int) -> set:
        s = input_str.strip().lower()
        total_count = len(tasks_list)
        if not s or s in ("all", "y", "ya", "yes", "*"):
            return set(range(total_count))
        if s in ("n", "no", "tidak", "cancel", "0", "none", "batal"):
            return set()

        is_exclude = False
        if s.startswith(("skip", "except", "kecuali", "buang", "hapus")):
            is_exclude = True
            s = re.sub(r'^(skip|except|kecuali|buang|hapus)\s*', '', s).strip()
        elif s.startswith(("!", "-")) or s.startswith("x "):
            is_exclude = True
            s = s[1:].strip() if not s.startswith("x ") else s[2:].strip()

        matched_indices = set()

        # Check for syntax like '1: 2, 5' or 'JT-284: 2, 5' or '1: 2-4'
        colon_patterns = re.findall(r'([a-zA-Z0-9_\-]+)\s*[:]\s*([0-9\s,\-]+)', s)
        if colon_patterns:
            for key_part, nums_part in colon_patterns:
                target_story_indices = []
                for i, itm in enumerate(tasks_list):
                    if key_part.isdigit() and itm["story_idx"] == int(key_part):
                        target_story_indices.append(i)
                    elif not key_part.isdigit() and (key_part == str(itm["subtask"].get("parent_key", "")).lower() or (len(key_part) >= 3 and key_part in str(itm["subtask"].get("parent_key", "")).lower())):
                        target_story_indices.append(i)

                num_tokens = [n.strip() for n in re.split(r'[\s,]+', nums_part) if n.strip()]
                for n_tok in num_tokens:
                    if "-" in n_tok and not n_tok.startswith("-"):
                        p = n_tok.split("-")
                        if len(p) == 2 and p[0].isdigit() and p[1].isdigit():
                            for v in range(min(int(p[0]), int(p[1])), max(int(p[0]), int(p[1])) + 1):
                                for i in target_story_indices:
                                    if tasks_list[i]["sub_idx"] == v:
                                        matched_indices.add(i)
                            continue
                    if n_tok.isdigit():
                        v = int(n_tok)
                        for i in target_story_indices:
                            if tasks_list[i]["sub_idx"] == v:
                                matched_indices.add(i)

            all_indices = set(range(total_count))
            return all_indices - matched_indices

        # Tokenize remaining inputs
        tokens = [t.strip(' ,') for t in re.split(r'[\s,]+', s) if t.strip(' ,')]
        for tok in tokens:
            if not tok:
                continue
            # Role filter
            if tok in ("fe", "frontend", "web", "mobile"):
                for i, itm in enumerate(tasks_list):
                    sub_r = str(itm["subtask"].get("role", "")).lower()
                    if "front" in sub_r or "web" in sub_r or "mobile" in sub_r or sub_r == "fe":
                        matched_indices.add(i)
                continue
            if tok in ("be", "backend"):
                for i, itm in enumerate(tasks_list):
                    sub_r = str(itm["subtask"].get("role", "")).lower()
                    if "back" in sub_r or "be" in sub_r:
                        matched_indices.add(i)
                continue
            # Single story index (when num_stories > 1, e.g. '2' selects whole Story 2)
            if tok.isdigit() and num_stories > 1:
                val = int(tok)
                for i, itm in enumerate(tasks_list):
                    if itm["story_idx"] == val:
                        matched_indices.add(i)
                continue
            # Single subtask index (when num_stories == 1, e.g. '2' selects subtask 2)
            if tok.isdigit() and num_stories == 1:
                val = int(tok)
                for i, itm in enumerate(tasks_list):
                    if itm["sub_idx"] == val:
                        matched_indices.add(i)
                continue
            # Numeric range when num_stories == 1 (e.g. 1-4)
            if "-" in tok and not tok.startswith("-") and num_stories == 1:
                parts = tok.split("-")
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    for i, itm in enumerate(tasks_list):
                        if min(int(parts[0]), int(parts[1])) <= itm["sub_idx"] <= max(int(parts[0]), int(parts[1])):
                            matched_indices.add(i)
                    continue
            # Ticket Key filter (e.g. JT-284 or 284)
            ticket_matched = False
            for i, itm in enumerate(tasks_list):
                pk = str(itm["subtask"].get("parent_key", "")).lower()
                if tok == pk or (len(tok) >= 3 and tok in pk):
                    matched_indices.add(i)
                    ticket_matched = True
            if ticket_matched:
                continue
            # Assignee filter (e.g. aryan, habibi)
            for i, itm in enumerate(tasks_list):
                emp_n = str(itm["employee"].get("name", "")).lower()
                if len(tok) >= 3 and tok in emp_n:
                    matched_indices.add(i)

        all_indices = set(range(total_count))
        return (all_indices - matched_indices) if is_exclude else matched_indices

    user_sel_input = input("Pilihan Anda [Tekan Enter untuk semua]: ").strip()
    selected_indices = _parse_cli_selection(user_sel_input, flat_tasks, total_stories)

    if not selected_indices:
        print("\n❌ Proses dibatalkan. Tidak ada subtask yang dibuat ke Jira.")
        return

    tasks_to_create = [flat_tasks[i] for i in sorted(selected_indices)]

    print(f"\n-> Anda memilih {len(tasks_to_create)} dari {len(flat_tasks)} subtask:")
    for idx, item_task in enumerate(tasks_to_create, 1):
        t = item_task["subtask"]
        emp = item_task["employee"]
        print(f"   {idx}. {t['summary']} (-> {emp['name']})")

    final_confirm = input("\nLanjutkan push tiket ke Jira? [Y/n, default Y]: ").strip().lower()
    if final_confirm in ("n", "no", "tidak", "cancel", "batal"):
        print("❌ Pembuatan tiket ke Jira dibatalkan.")
        return

    # 11. Write chosen subtasks to Jira (With Deduplication Check)
    print("\n🚀 Mulai menulis subtask ke Jira...")
    created_count = 0
    skipped_count = 0
    parent_existing_subtasks = {}

    # Cache user Jira IDs by PN / name
    jira_user_ids = {}

    for item_task in tasks_to_create:
        t = item_task["subtask"]
        emp = item_task["employee"]
        emp_key = emp.get("pn") or emp.get("name")

        if emp_key not in jira_user_ids:
            print(f"\nMencari akun Jira untuk {emp['name']}...")
            jira_id = jira_client.find_user_by_name(emp["name"], pn=emp.get("pn"))
            if not jira_id:
                print(f"Warning: Akun Jira '{emp['name']}' tidak ditemukan. Subtask akan dibuat tanpa assignee.")
            jira_user_ids[emp_key] = jira_id

        jira_id = jira_user_ids[emp_key]
        parent_key = t["parent_key"]
        sub_summary = t["summary"].strip()
        sub_summary_lower = sub_summary.lower()

        if parent_key not in parent_existing_subtasks:
            parent_existing_subtasks[parent_key] = jira_client.get_existing_subtask_summaries(parent_key)

        existing_titles = parent_existing_subtasks[parent_key]

        if sub_summary_lower in existing_titles:
            print(f" ⚠️  [SKIP DUPLIKAT] Subtask '{sub_summary}' sudah ada di tiket {parent_key}.")
            skipped_count += 1
            continue

        print(f"Membuat subtask: '{sub_summary}' di bawah parent {parent_key}...")
        try:
            result = jira_client.create_subtask_issue(
                parent_key=parent_key,
                summary=sub_summary,
                description=t.get("description", ""),
                story_points=0,
                assignee_id=jira_id,
                parent_type=t.get("parent_type", "task"),
            )
            print(f" ✅ Sukses! Subtask Key: {result.get('key')}")
            created_count += 1
            existing_titles.add(sub_summary_lower)
        except Exception as e:
            print(f" ❌ Gagal membuat subtask: {e}")

    summary_msg = f"\n🎉 Selesai! Berhasil membuat {created_count} subtask baru di Jira."
    if skipped_count > 0:
        summary_msg += f" ({skipped_count} subtask duplikat dilewati)."
    print(summary_msg)


if __name__ == "__main__":
    main()
