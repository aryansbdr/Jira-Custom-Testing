import Resolver from '@forge/resolver';
import api, { route } from '@forge/api';

const resolver = new Resolver();

// ==========================================
// DATA REKOMENDASI AWAL & HELPER
// ==========================================
const baseRecommendations = [
  {
    category: 'Frontend',
    badgeCount: '6 task',
    statusTag: 'NONE',
    tasks: [
      { id: 1, text: 'Desain mockup halaman investment report baru' },
      { id: 2, text: 'Implementasi komponen tabel investment data' },
      { id: 3, text: 'Implementasi komponen tabel investment data' },
      { id: 4, text: 'Implementasi komponen tabel investment data' },
      { id: 5, text: 'Implementasi komponen tabel investment data' },
      { id: 6, text: 'Implementasi komponen tabel investment data' },
    ],
  },
  {
    category: 'Backend',
    badgeCount: '4 task',
    statusTag: 'NONE',
    tasks: [
      { id: 7, text: 'Integrasi API endpoint investment report v2' },
      { id: 8, text: 'Buat endpoint export PDF dan format response' },
      { id: 9, text: 'Buat endpoint export PDF dan format response' },
      { id: 10, text: 'Buat endpoint export PDF dan format response' },
    ],
  },
  {
    category: 'QA',
    badgeCount: '3 task',
    statusTag: 'NONE',
    tasks: [
      { id: 11, text: 'Unit dan integration testing seluruh fitur' },
      { id: 12, text: 'Unit dan integration testing seluruh fitur' },
      { id: 13, text: 'Unit dan integration testing seluruh fitur' },
    ],
  },
];

function cleanText(str) {
  return str.replace(/^\[.*?\]\s*/, '').trim().toLowerCase();
}


// ==========================================
// 1. RESOLVER TAB REPORTING (PROJECT PAGE)
// ==========================================
resolver.define('getSquadProgress', async (req) => {
  try {
    const { projectKey = 'SCRUM' } = req.payload || {};

    // Tambahkan field 'parent' pada query ke Jira REST API
    const jql = `project = "${projectKey}" AND issuetype in subTaskIssueTypes()`;
    console.log('[Backend] Fetching data for issues with JQL:', jql);

    const response = await api
      .asUser()
      .requestJira(route`/rest/api/3/search/jql`, {
        method: 'POST',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          jql: `project = "${projectKey}" AND issuetype in subTaskIssueTypes()`,
          fields: ['summary', 'status', 'assignee', 'parent']
        })
      });

    if (!response.ok) {
      console.error('Jira API Error:', await response.text());
      return { parentIssues: [], squadsList: [], memberDataBySquad: {} };
    }

    const data = await response.json();
    const issues = Array.isArray(data.issues) ? data.issues : [];

    const parentMap = {};
    const squadSet = new Set();
    const memberMapBySquad = {}; 

    const initStats = () => ({ todo: 0, inProgress: 0, done: 0, total: 0 });

    issues.forEach((issue) => {
      // Data Parent Issue
      const parentKey = issue.fields?.parent?.key || 'Lainnya';
      const parentSummary = issue.fields?.parent?.fields?.summary || parentKey;

      // Data Sub-Task
      const summary = issue.fields?.summary || '';
      const statusCategory = issue.fields?.status?.statusCategory?.key; // 'new', 'indeterminate', 'done'
      const assigneeName = issue.fields?.assignee?.displayName || 'Unassigned';

      // Ekstrak nama Squad dari prefix [Backend], [Frontend], dll.
      const match = summary.match(/^\[(.*?)\]/);
      const squadName = match ? match[1].trim() : 'Lainnya';
      squadSet.add(squadName);

      // --- 1. Kelompokkan per Parent Issue ---
      if (!parentMap[parentKey]) {
        parentMap[parentKey] = {
          key: parentKey,
          title: `${parentSummary} (${parentKey})`,
          squadMap: {}
        };
      }
      if (!parentMap[parentKey].squadMap[squadName]) {
        parentMap[parentKey].squadMap[squadName] = initStats();
      }

      // --- 2. Kelompokkan Member per Squad ---
      if (!memberMapBySquad[squadName]) memberMapBySquad[squadName] = {};
      if (!memberMapBySquad[squadName][assigneeName]) {
        memberMapBySquad[squadName][assigneeName] = initStats();
      }

      // Hitung Stat
      if (statusCategory === 'new') {
        parentMap[parentKey].squadMap[squadName].todo += 1;
        memberMap[squadName][assigneeName].todo += 1;
      } else if (statusCategory === 'indeterminate') {
        parentMap[parentKey].squadMap[squadName].inProgress += 1;
        memberMap[squadName][assigneeName].inProgress += 1;
      } else if (statusCategory === 'done') {
        parentMap[parentKey].squadMap[squadName].done += 1;
        memberMap[squadName][assigneeName].done += 1;
      }

      parentMap[parentKey].squadMap[squadName].total += 1;
      memberMap[squadName][assigneeName].total += 1;
    });

    // Format array parent issues agar mudah digunakan oleh Recharts
    const parentIssues = Object.values(parentMap).map((item) => ({
      key: item.key,
      title: item.title,
      chartData: Object.keys(item.squadMap).map((sq) => ({
        name: sq,
        ...item.squadMap[sq]
      }))
    }));

    // Format array member per squad
    const memberDataBySquad = {};
    Object.keys(memberMapBySquad).forEach((squad) => {
      memberDataBySquad[squad] = Object.keys(memberMapBySquad[squad]).map((mem) => ({
        name: mem,
        ...memberMapBySquad[squad][mem]
      }));
    });

    return {
      parentIssues,
      squadsList: Array.from(squadSet),
      memberDataBySquad
    };
  } catch (error) {
    console.error('Error executing getSquadProgress:', error);
    return { parentIssues: [], squadsList: [], memberDataBySquad: {} };
  }
});

// ==========================================
// 2. RESOLVER SUB-TASK RECOMMENDATION (ISSUE PANEL)
// ==========================================
resolver.define('getRecommendations', async (req) => {
  const { issueKey } = req.payload || {};

  if (!issueKey) return baseRecommendations;

  try {
    const response = await api.asApp().requestJira(
      route`/rest/api/3/issue/${issueKey}?fields=subtasks`
    );

    if (!response.ok) return baseRecommendations;

    const data = await response.json();
    const existingSubtasks = data.fields?.subtasks || [];

    const existingCounts = {};
    for (const st of existingSubtasks) {
      const summaryClean = cleanText(st.fields?.summary || '');
      existingCounts[summaryClean] = (existingCounts[summaryClean] || 0) + 1;
    }

    const filteredGroups = baseRecommendations.map((group) => {
      const remainingTasks = [];
      const counts = { ...existingCounts };

      for (const task of group.tasks) {
        const normTask = cleanText(task.text);
        if (counts[normTask] && counts[normTask] > 0) {
          counts[normTask]--;
        } else {
          remainingTasks.push(task);
        }
      }

      return {
        ...group,
        tasks: remainingTasks,
      };
    });

    return filteredGroups;
  } catch (err) {
    console.error('Error fetching existing subtasks:', err);
    return baseRecommendations;
  }
});


// ==========================================
// 3. RESOLVER MEMBUAT SUB-TASK (VALIDASI)
// ==========================================
resolver.define('createSubtasks', async (req) => {
  const { issueKey, subtasks } = req.payload || {};

  if (!issueKey || !subtasks || subtasks.length === 0) {
    return { success: false, error: 'Data tidak lengkap' };
  }

  try {
    const issueResponse = await api.asApp().requestJira(
      route`/rest/api/3/issue/${issueKey}?fields=project`
    );
    const issueData = await issueResponse.json();
    const projectId = issueData.fields.project.id;

    const projectResponse = await api.asApp().requestJira(
      route`/rest/api/3/project/${projectId}`
    );
    const projectData = await projectResponse.json();
    const subtaskType = (projectData.issueTypes || []).find((t) => t.subtask === true);

    if (!subtaskType) {
      return { success: false, error: 'Subtask type not found' };
    }

    const results = [];
    for (const taskText of subtasks) {
      const bodyData = {
        fields: {
          summary: taskText,
          project: { id: projectId },
          parent: { key: issueKey },
          issuetype: { id: subtaskType.id },
        },
      };

      const createResponse = await api.asApp().requestJira(route`/rest/api/3/issue`, {
        method: 'POST',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(bodyData),
      });

      if (createResponse.status === 201) {
        const resJson = await createResponse.json();
        results.push({ success: true, key: resJson.key });
      } else {
        const errorText = await createResponse.text();
        results.push({ success: false, error: errorText });
      }
    }

    return { success: results.some((r) => r.success), results };
  } catch (err) {
    return { success: false, error: err.message };
  }
});

export const handler = resolver.getDefinitions();