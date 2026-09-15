"""
Jira Hierarchical JQL Reporter CLI Tool.

Usage:
    python run_jql_report.py "project = BL AND resolution = Unresolved ORDER BY priority DESC, updated DESC"
    python run_jql_report.py --dashboard 26953
    python run_jql_report.py --filter 48596
"""

import sys
import argparse
from collections import defaultdict, Counter
import requests

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, 'src')

from modules.generate_subtask.infrastructure.jira_rest_client import JiraRestClient


def execute_hierarchical_jql(jql_query: str, squad_filter: str = None, max_results: int = 100):
    print("=" * 80)
    print(f"🔍 JQL QUERY: {jql_query}")
    if squad_filter:
        print(f"🏢 FILTER SQUAD: {squad_filter}")
    print("=" * 80)

    jira = JiraRestClient()
    base_url = jira._get_base_url()
    headers = jira._get_headers()
    auth = jira._get_auth()

    url = f"{base_url}/rest/api/2/search"
    fields = [
        "summary", "status", "assignee", "priority", "issuetype",
        "components", "parent", "customfield_10102"
    ]
    params = {"jql": jql_query, "fields": ",".join(fields), "maxResults": max_results}

    print(f"📡 Mengambil data dari Jira BRI ({base_url})...\n")
    try:
        res = requests.get(url, headers=headers, auth=auth, params=params, timeout=25)
        if res.status_code != 200:
            print(f"❌ Gagal mengeksekusi query ({res.status_code}): {res.text[:300]}")
            return
        
        data = res.json()
        total = data.get("total", 0)
        issues = data.get("issues", [])
        print(f"✅ Berhasil menarik {len(issues)} dari total {total} tiket cocok.\n")

        if not issues:
            print("ℹ️ Tidak ada tiket yang cocok dengan kriteria query ini.")
            return

        # Metrics Counters
        status_counts = Counter()
        priority_counts = Counter()
        assignee_counts = Counter()

        # Tree Structure: Squad -> Epic -> Story -> Subtasks
        tree = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

        for iss in issues:
            key = iss.get("key")
            f = iss.get("fields", {})
            summary = f.get("summary", "-")
            status = f.get("status", {}).get("name", "Unknown")
            priority = f.get("priority", {}).get("name", "-") if f.get("priority") else "-"
            assignee = f.get("assignee", {}).get("displayName", "Unassigned") if f.get("assignee") else "Unassigned"
            itype = f.get("issuetype", {}).get("name", "Task")
            
            comps = [c.get("name") for c in f.get("components", [])] if f.get("components") else ["General Squad"]
            squad = comps[0]

            status_counts[status] += 1
            priority_counts[priority] += 1
            assignee_counts[assignee] += 1

            parent_info = f.get("parent")
            epic_key = f.get("customfield_10102") or ""

            if parent_info:
                story_key = parent_info.get("key")
                story_sum = parent_info.get("fields", {}).get("summary", "")
                story_label = f"[{story_key}] {story_sum}".strip()
                parent_epic = parent_info.get("fields", {}).get("customfield_10102")
                if not epic_key and parent_epic:
                    epic_key = parent_epic
            else:
                story_label = f"[{key}] {summary}"

            epic_label = f"[{epic_key}] Epic" if epic_key else "General Epics / No Epic Link"

            tree[squad][epic_label][story_label].append({
                "key": key,
                "summary": summary,
                "status": status,
                "priority": priority,
                "assignee": assignee,
                "type": itype
            })

        # Display Ringkasan Eksekutif
        print("📊 RINGKASAN STATUS TIKET:")
        for st, cnt in status_counts.items():
            print(f"   • {st:<18}: {cnt} tiket")
        print()

        print("👥 TOP ASSIGNEE / PIC:")
        for ass, cnt in assignee_counts.most_common(6):
            print(f"   • {ass:<30}: {cnt} tiket")
        print("\n" + "=" * 80)
        print("🌳 STRUKTUR HIERARKI: SQUAD ➔ EPIC ➔ STORY ➔ SUBTASK")
        print("=" * 80)

        if squad_filter:
            squad_lower = squad_filter.strip().lower()
            filtered_tree = {sq: epics for sq, epics in tree.items() if squad_lower in sq.lower()}
            tree = filtered_tree
            if not tree:
                print(f"ℹ️ Tidak ditemukan tiket untuk squad '{squad_filter}'.")
                return

        for squad_name, epics in tree.items():
            print(f"\n🏢 SQUAD: {squad_name.upper()} ({len(epics)} Epics)")
            for epic_name, stories in epics.items():
                print(f"  🎯 EPIC: {epic_name}")
                for story_name, subtasks in stories.items():
                    print(f"     📁 STORY: {story_name} ({len(subtasks)} Subtasks)")
                    for idx, sub in enumerate(subtasks, 1):
                        role_tag = f"[{sub['type']}]" if sub['type'] != "Sub-task" else ""
                        print(f"        {idx}. [{sub['key']}] {role_tag} {sub['summary']}")
                        print(f"           ↳ Status: {sub['status']} | Priority: {sub['priority']} | Assignee: {sub['assignee']}")
            print("-" * 80)

    except Exception as e:
        print(f"❌ Error during execution: {e}")


def main():
    parser = argparse.ArgumentParser(description="Jira Hierarchical JQL Reporter")
    parser.add_argument("query", nargs="?", default="", help="Custom JQL Query String")
    parser.add_argument("--squad", type=str, help="Filter by squad name (e.g. 'Squad Korporasi' or 'Squad Mikro 1')")
    parser.add_argument("--dashboard", type=str, help="Dashboard ID (e.g. 26953)")
    parser.add_argument("--filter", type=str, help="Filter ID (e.g. 48596)")
    parser.add_argument("--max", type=int, default=50, help="Max results to fetch (default: 50)")

    args = parser.parse_args()

    jira = JiraRestClient()
    base_url = jira._get_base_url()
    headers = jira._get_headers()
    auth = jira._get_auth()

    if args.dashboard:
        print(f"🔍 Mengambil query dari Dashboard ID: {args.dashboard}...")
        url = f"{base_url}/rest/dashboards/1.0/{args.dashboard}"
        res = requests.get(url, headers=headers, auth=auth, timeout=15)
        if res.status_code == 200:
            ddata = res.json()
            print(f"Dashboard Title: {ddata.get('title')}\n")
            # Default to active sprint filter if present
            jql = 'assignee IN ("Jamalul Insan", "Refian Eka Saputra", "Gading Condro Prakoso", "Muhammad Iqbal Ainu Rafie") AND sprint IN openSprints() AND status IN ("To Do","In Progress", "Ready for Testing", "In Testing", "Ready_For UAT", Done)'
            execute_hierarchical_jql(jql, squad_filter=args.squad, max_results=args.max)
        else:
            print(f"Gagal membuka dashboard ({res.status_code})")
        return

    if args.filter:
        print(f"🔍 Mengambil query dari Filter ID: {args.filter}...")
        url = f"{base_url}/rest/api/2/filter/{args.filter}"
        res = requests.get(url, headers=headers, auth=auth, timeout=15)
        if res.status_code == 200:
            fdata = res.json()
            jql = fdata.get("jql")
            execute_hierarchical_jql(jql, squad_filter=args.squad, max_results=args.max)
        else:
            print(f"Gagal mengambil filter ({res.status_code})")
        return

    if args.query:
        execute_hierarchical_jql(args.query, squad_filter=args.squad, max_results=args.max)
    else:
        # Default query: BL Unresolved
        default_jql = "project = BL AND resolution = Unresolved ORDER BY priority DESC, updated DESC"
        print(f"ℹ️ Menjalankan default JQL query: {default_jql}\n")
        execute_hierarchical_jql(default_jql, squad_filter=args.squad, max_results=args.max)


if __name__ == "__main__":
    main()
