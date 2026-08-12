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
        input_key = input(f"\nMasukkan Project Key / URL Dashboard Jira / Epic Key (default: '{default_project}', contoh: JT, https://jira.bri.co.id/...selectPageId=26953): ").strip()
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
        input_key = input(f"\nMasukkan Project Key, URL/ID Dashboard, atau Epic Key (default: '{default_project}', contoh: JT, https://jira.bri.co.id/...selectPageId=26953, BL-38812): ").strip()
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
            print(f"\nSUKSES! Laporan Excel lengkap (dengan daftar Epic & grafik) berhasil dibuat:\n   📂 {filename}")
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

    # 10. Request confirmation before committing to Jira

    confirm = (
        input("Apakah Anda ingin menerapkan & membuat subtask ini di Jira? (y/n): ")
        .strip()
        .lower()
    )
    if confirm != "y":
        print("Proses dibatalkan. Tidak ada perubahan yang disimpan ke Jira.")
        return

    # 10. Write subtasks to Jira (With Deduplication Check)
    print("\nMulai menulis subtask ke Jira...")
    created_count = 0
    skipped_count = 0

    # Cache existing subtask summaries per parent key to avoid duplicate Jira issues
    parent_existing_subtasks = {}

    for item in active_assignments:
        emp = item["employee"]
        print(f"\nMencari akun Jira untuk {emp['name']}...")
        jira_id = jira_client.find_user_by_name(emp["name"], pn=emp.get("pn"))

        if not jira_id:
            print(
                f"Warning: Akun Jira '{emp['name']}' tidak ditemukan. Subtask akan dibuat tanpa assignee."
            )

        for t in item["assigned_subtasks"]:
            parent_key = t["parent_key"]
            sub_summary = t["summary"].strip()
            sub_summary_lower = sub_summary.lower()

            # Lazy-load existing subtasks for this parent
            if parent_key not in parent_existing_subtasks:
                parent_existing_subtasks[parent_key] = jira_client.get_existing_subtask_summaries(parent_key)

            existing_titles = parent_existing_subtasks[parent_key]

            # DEDUPLICATION CHECK: Skip if already exists in Jira
            if sub_summary_lower in existing_titles:
                print(f" [SKIP DUPLIKAT] Subtask '{sub_summary}' sudah ada di tiket {parent_key}.")
                skipped_count += 1
                continue

            print(
                f"Membuat subtask: '{sub_summary}' di bawah parent {parent_key}..."
            )
            try:
                result = jira_client.create_subtask_issue(
                    parent_key=parent_key,
                    summary=sub_summary,
                    description=t["description"],
                    story_points=0,
                    assignee_id=jira_id,
                    parent_type=t.get("parent_type", "task"),
                )

                print(f"Sukses! Subtask Key: {result.get('key')}")
                created_count += 1
                # Add to local cache so we don't duplicate within the same run
                existing_titles.add(sub_summary_lower)
            except Exception as e:
                print(f" Gagal membuat subtask: {e}")

    summary_msg = f"\nSelesai! Berhasil membuat {created_count} subtask baru di Jira."
    if skipped_count > 0:
        summary_msg += f" ({skipped_count} subtask duplikat dilewati)."
    print(summary_msg)


if __name__ == "__main__":
    main()
