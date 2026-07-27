import os
from shared.database import init_db

# Infrastructure & Repository Imports
from modules.generate_subtask.infrastructure.sqlite_story_repository import (
    SqliteStoryRepository,
)
from modules.generate_subtask.infrastructure.gemini_llm_client import GeminiLlmClient
from modules.generate_subtask.infrastructure.jira_rest_client import JiraRestClient
from modules.reporting.infrastructure.pandas_excel_parser import PandasExcelParser

# Domain Service Imports
from modules.reporting.domain.balancer_service import WorkloadBalancerService

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
    llm_client = GeminiLlmClient()
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
    members_file = "members.xlsx"
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

    # 4. Fetch child issues from Jira Epic directly
    epic_key = input("\nMasukkan Epic Key Jira (contoh: QLOLA-23279): ").strip()
    if not epic_key:
        print("Epic Key tidak boleh kosong.")
        return

    print(f"\nMengambil child issues dari Epic {epic_key} di Jira...")
    jira_stories = []
    try:
        jira_stories = jira_client.get_epic_issues(epic_key)
        if not jira_stories:
            print(f"Tidak ada child issues ditemukan di bawah Epic {epic_key}.")
            return

        # Group and count issue types dynamically
        type_counts = {}
        for s in jira_stories:
            type_name = s.issue_type.title()
            type_counts[type_name] = type_counts.get(type_name, 0) + 1

        breakdown_parts = [f"{count} {t_name}" for t_name, count in type_counts.items()]
        print(
            f"Ditemukan {len(jira_stories)} issue di bawah Epic {epic_key} ({', '.join(breakdown_parts)})."
        )

    except Exception as e:
        print(f"Gagal mengambil issue dari Jira: {e}")
        print(
            "Pastikan konfigurasi JIRA_URL, JIRA_EMAIL, dan JIRA_API_TOKEN di file .env sudah benar."
        )
        return

    # 6. Process RAG + Gemini Subtask Generation
    print("\nMulai melakukan dekomposisi subtask menggunakan Gemini AI + RAG...")
    all_subtasks = []

    for i, story in enumerate(jira_stories):
        print(
            "\n-----------------------------------------------------------------"
        )
        print(
            f" [{i + 1}/{len(jira_stories)}] TIKET INDUK: [{story.key}] {story.summary} ({story.story_points} SP)"
        )
        print(
            "-----------------------------------------------------------------"
        )
        desc = story.description or story.summary
        try:
            generated_subs = generate_subtasks_uc.execute(
                summary=story.summary, description=desc, parent_sp=story.story_points
            )
            if generated_subs:
                print(f"   Subtask yang Dihasilkan ({len(generated_subs)} subtask):")
                for sub_idx, sub in enumerate(generated_subs, 1):
                    sub.parent_key = story.key
                    sub.parent_summary = story.summary
                    sub.parent_type = story.issue_type
                    all_subtasks.append(sub)
                    print(
                        f"    {sub_idx}. {sub.summary} ({sub.story_points} SP)"
                    )
            else:
                print("   ℹ️  [SKIPPED] Tiket Kategori Test / Deployment (Dieksepsikan dari pembuatan subtask)")
        except Exception as e:
            print(f"   -> Gagal generate subtask untuk {story.key}: {e}")

        # Pacing delay to remain within Free Tier RPM (Requests Per Minute) limits
        import time
        time.sleep(2)

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
            print(f"       {t['summary']} ({t['story_points']} SP)")
            if idx < len(tasks):
                print("      . . . . . . . . . . . . . . . . . . . . . . . . . . .")

    if balanced["unassigned_subtasks"]:
        print("\n" + "🚨" + "!" * 63)
        print("  TUGAS TIDAK DAPAT DI-ASSIGN (TIDAK ADA ROLE COCOK):")
        print("─" * 65)
        for t in balanced["unassigned_subtasks"]:
            parent_info = f"{t['parent_key']} - {t.get('parent_summary', '')}".strip(" -")
            print(
                f"  ⚠️  [{parent_info}] {t['summary']} (Target: {t['role']} | {t['story_points']} SP)"
            )
        print("!" * 65)

    # 9. Export workload report to Excel (Optional)
    export_choice = (
        input(
            "\nApakah Anda ingin mengekspor laporan beban kerja ini ke Excel dengan grafik? (y/n, default y): "
        )
        .strip()
        .lower()
    )
    if export_choice != "n":
        from modules.reporting.infrastructure.excel_reporter import ExcelReporter

        reporter = ExcelReporter()
        # Clean Epic Key for filename safety
        safe_key = "".join(
            [c for c in epic_key if c.isalnum() or c in ("-", "_")]
        ).strip()
        if not safe_key:
            safe_key = "report"
        try:
            filename = reporter.generate_report(balanced, safe_key)
            print(f"-> Sukses! Laporan Excel berhasil diekspor: '{filename}'")
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

    # 10. Write subtasks to Jira
    print("\nMulai menulis subtask ke Jira...")
    created_count = 0

    for item in active_assignments:
        emp = item["employee"]
        print(f"\nMencari akun Jira untuk {emp['name']}...")
        jira_id = jira_client.find_user_by_name(emp["name"], pn=emp.get("pn"))

        if not jira_id:
            print(
                f"Warning: Akun Jira '{emp['name']}' tidak ditemukan. Subtask akan dibuat tanpa assignee."
            )

        for t in item["assigned_subtasks"]:
            print(
                f"Membuat subtask: '{t['summary']}' di bawah parent {t['parent_key']}..."
            )
            try:
                result = jira_client.create_subtask_issue(
                    parent_key=t["parent_key"],
                    summary=t["summary"],
                    description=t["description"],
                    story_points=t["story_points"],
                    assignee_id=jira_id,
                    parent_type=t.get("parent_type", "task"),
                )

                print(f"Sukses! Subtask Key: {result.get('key')}")
                created_count += 1
            except Exception as e:
                print(f" Gagal membuat subtask: {e}")

    print(f"\nSelesai! Berhasil membuat {created_count} subtask di Jira.")


if __name__ == "__main__":
    main()
