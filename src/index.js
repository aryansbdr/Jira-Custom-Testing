import Resolver from '@forge/resolver';
import api, { route } from '@forge/api';

const resolver = new Resolver();

// ============================================================
// HELPER
// ============================================================

function cleanText(str) {
  if (!str) return '';

  return String(str)
    .replace(/^\[.*?\]\s*/, '')
    .trim()
    .toLowerCase();
}


// ============================================================
// EXTRACT TEXT FROM JIRA ADF
// ============================================================

function extractTextFromADF(adf) {
  if (!adf) return '';

  if (typeof adf === 'string') {
    return adf;
  }

  let text = '';

  if (adf.content && Array.isArray(adf.content)) {
    for (const node of adf.content) {
      if (node.text) {
        text += node.text + ' ';
      }

      if (node.content) {
        text += extractTextFromADF(node) + ' ';
      }
    }
  }

  return text.trim();
}


// ============================================================
// NORMALIZE ROLE & SQUAD EXTRACTION
// ============================================================

function normalizeCategory(role) {
  const value = String(role || '')
    .trim()
    .toLowerCase();

  if (
    value === 'frontend' ||
    value === 'front-end' ||
    value === 'front end' ||
    value === 'fe' ||
    value === 'web' ||
    value === 'ui'
  ) {
    return 'WEB';
  }

  if (
    value === 'backend' ||
    value === 'back-end' ||
    value === 'back end' ||
    value === 'be' ||
    value === 'api'
  ) {
    return 'Backend';
  }

  if (
    value === 'mobile' ||
    value === 'android' ||
    value === 'ios' ||
    value === 'flutter' ||
    value === 'mob'
  ) {
    return 'Mobile';
  }

  if (
    value === 'qa' ||
    value === 'quality assurance' ||
    value === 'tester' ||
    value === 'testing' ||
    value === 'pengujian'
  ) {
    return 'QA';
  }

  return 'Backend';
}

function extractSquadName(summary = '') {
  const text = String(summary || '').trim();

  // 1. Prioritas Utama: Cek prefix kurung siku [WEB], [BE], [Mobile], [QA]
  const match = text.match(/^\[(.*?)\]/);
  if (match && match[1]) {
    return normalizeCategory(match[1].trim());
  }

  // 2. Deteksi Mobile: Diawali atau mengandung kata "Mobile" / "MOB"
  if (/^mobile/i.test(text) || /\bmobile\b/i.test(text) || /^mob\b/i.test(text)) {
    return 'Mobile';
  }

  // 3. Deteksi Backend: Diawali "BE" atau mengandung kata "Backend"
  if (/^be\b/i.test(text) || /\bbackend\b/i.test(text)) {
    return 'Backend';
  }

  // 4. Deteksi WEB: Diawali "WEB", "FE", atau mengandung "Frontend"
  if (/^web\b/i.test(text) || /^fe\b/i.test(text) || /\bfrontend\b/i.test(text)) {
    return 'WEB';
  }

  // 5. Deteksi QA
  if (/^qa\b/i.test(text) || /\btesting\b/i.test(text) || /\bpengujian\b/i.test(text)) {
    return 'QA';
  }

  // 6. Fallback: Analisis kata kunci di dalam string
  const lower = text.toLowerCase();

  if (
    lower.includes('web') ||
    lower.includes('frontend') ||
    lower.includes('front-end') ||
    lower.includes('fe') ||
    lower.includes('ui') ||
    lower.includes('tampilan')
  ) {
    return 'WEB';
  }

  if (
    lower.includes('backend') ||
    lower.includes('back-end') ||
    lower.includes('be') ||
    lower.includes('api') ||
    lower.includes('otp') ||
    lower.includes('log') ||
    lower.includes('database') ||
    lower.includes('integrasi')
  ) {
    return 'Backend';
  }

  if (
    lower.includes('qa') ||
    lower.includes('testing') ||
    lower.includes('test') ||
    lower.includes('pengujian') ||
    lower.includes('review')
  ) {
    return 'QA';
  }

  if (
    lower.includes('mobile') ||
    lower.includes('android') ||
    lower.includes('ios') ||
    lower.includes('flutter')
  ) {
    return 'Mobile';
  }

  return 'Lainnya';
}


// ============================================================
// NORMALIZE TASK
// ============================================================

function normalizeTask(task, index, category) {
  if (typeof task === 'string') {
    const text = task.trim();

    return {
      id: `${category}-${index}-${Date.now()}`,
      text,
      summary: text,
      description: text,
      role: category.toLowerCase(),
      story_points: 1,
    };
  }

  const summary =
    task?.summary ||
    task?.text ||
    task?.title ||
    task?.name ||
    task?.task ||
    '';

  const description =
    task?.description ||
    summary;

  return {
    id:
      task?.id ??
      task?.key ??
      `${category}-${index}-${Date.now()}`,

    text: String(summary).trim(),

    summary: String(summary).trim(),

    description: String(description).trim(),

    role:
      task?.role ||
      task?.category ||
      category.toLowerCase(),

    story_points:
      Number(
        task?.story_points ??
        task?.storyPoints ??
        task?.sp ??
        1
      ),
  };
}


// ============================================================
// EXTRACT SUBTASKS DARI RESPONSE FASTAPI
// ============================================================

function extractSubtasksFromAIResponse(resJson) {
  if (Array.isArray(resJson)) {
    return resJson;
  }

  if (Array.isArray(resJson?.subtasks)) {
    return resJson.subtasks;
  }

  if (Array.isArray(resJson?.results)) {
    return resJson.results;
  }

  if (Array.isArray(resJson?.data)) {
    return resJson.data;
  }

  if (Array.isArray(resJson?.result)) {
    return resJson.result;
  }

  if (Array.isArray(resJson?.recommendations)) {
    return resJson.recommendations;
  }

  if (Array.isArray(resJson?.generated_subtasks)) {
    return resJson.generated_subtasks;
  }

  if (Array.isArray(resJson?.generatedSubtasks)) {
    return resJson.generatedSubtasks;
  }

  if (Array.isArray(resJson?.results?.subtasks)) {
    return resJson.results.subtasks;
  }

  if (Array.isArray(resJson?.data?.subtasks)) {
    return resJson.data.subtasks;
  }

  if (Array.isArray(resJson?.result?.subtasks)) {
    return resJson.result.subtasks;
  }

  if (Array.isArray(resJson?.data?.results)) {
    return resJson.data.results;
  }

  if (Array.isArray(resJson?.results?.results)) {
    return resJson.results.results;
  }

  if (Array.isArray(resJson?.results?.assignments)) {
    const assignedSubtasks =
      resJson.results.assignments.flatMap(
        (assignment) =>
          Array.isArray(assignment?.assigned_subtasks)
            ? assignment.assigned_subtasks
            : []
      );

    const unassignedSubtasks =
      Array.isArray(resJson?.results?.unassigned_subtasks)
        ? resJson.results.unassigned_subtasks
        : [];

    return [
      ...assignedSubtasks,
      ...unassignedSubtasks,
    ];
  }

  if (Array.isArray(resJson?.assignments)) {
    return resJson.assignments.flatMap(
      (assignment) =>
        Array.isArray(assignment?.assigned_subtasks)
          ? assignment.assigned_subtasks
          : []
    );
  }

  return [];
}


// ============================================================
// CONVERT SUBTASKS → GROUPS UNTUK REACT
// ============================================================

function convertSubtasksToGroups(subtasks) {
  const groupMap = {};

  subtasks.forEach((rawTask, index) => {
    if (!rawTask) {
      return;
    }

    let role = 'backend';

    if (typeof rawTask === 'object') {
      role =
        rawTask.role ||
        rawTask.category ||
        rawTask.team ||
        'backend';
    }

    const category = normalizeCategory(role);

    const task = normalizeTask(rawTask, index, category);

    if (!task.text) {
      return;
    }

    if (!groupMap[category]) {
      groupMap[category] = {
        category,
        badgeCount: '0 task',
        tasks: [],
      };
    }

    groupMap[category].tasks.push(task);
  });

  const groups = Object.values(groupMap);

  groups.forEach((group) => {
    group.badgeCount = `${group.tasks.length} task`;
  });

  return groups;
}


// ============================================================
// 1. SQUAD PROGRESS REPORT
// ============================================================

resolver.define('getSquadProgress', async (req) => {
  try {
    const { projectKey = 'SCRUM' } = req.payload || {};
    const jql = `project = "${projectKey}" AND issuetype in subTaskIssueTypes() ORDER BY parent`;

    let allSubtasks = [];
    let startAt = 0;
    let isLastPage = false;
    const maxResultsPerPage = 100;

    while (!isLastPage && allSubtasks.length < 1000) {
      let response = await api.asUser().requestJira(route`/rest/api/3/search/jql`, {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          jql,
          startAt,
          maxResults: maxResultsPerPage,
          fields: ['summary', 'status', 'assignee', 'parent'],
        }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        console.error('[Squad Report] Jira API Error:', response.status, errorText);
        break;
      }

      const data = await response.json();
      const fetchedIssues = Array.isArray(data.issues) ? data.issues : [];
      allSubtasks.push(...fetchedIssues);

      if (fetchedIssues.length < maxResultsPerPage || allSubtasks.length >= (data.total || 0)) {
        isLastPage = true;
      } else {
        startAt += fetchedIssues.length;
      }
    }

    const parentMap = {};
    const allStatuses = new Set();

    allSubtasks.forEach((issue) => {
      const fields = issue.fields || {};
      const parentKey = fields.parent?.key;

      if (!parentKey) return;

      const parentSummary = fields.parent?.fields?.summary || parentKey;
      const summary = fields.summary || '';
      const statusName = fields.status?.name || 'To Do';
      const assigneeName = fields.assignee?.displayName || 'Unassigned';

      allStatuses.add(statusName);
      const squadName = extractSquadName(summary);

      if (!parentMap[parentKey]) {
        parentMap[parentKey] = {
          key: parentKey,
          title: `${parentSummary} (${parentKey})`,
          parentSummary: parentSummary,
          squadStats: {},
          memberStats: {},
          totalSubtasks: 0,
          completedSubtasks: 0,
        };
      }

      const parent = parentMap[parentKey];
      parent.totalSubtasks += 1;

      const statusLower = statusName.toLowerCase();
      if (['done', 'closed', 'resolved', 'selesai', 'complete', 'completed'].includes(statusLower)) {
        parent.completedSubtasks += 1;
      }

      if (!parent.squadStats[squadName]) {
        parent.squadStats[squadName] = { total: 0 };
      }
      const squadStats = parent.squadStats[squadName];
      squadStats[statusName] = (squadStats[statusName] || 0) + 1;
      squadStats.total = (squadStats.total || 0) + 1;

      if (!parent.memberStats[squadName]) {
        parent.memberStats[squadName] = {};
      }
      if (!parent.memberStats[squadName][assigneeName]) {
        parent.memberStats[squadName][assigneeName] = { total: 0 };
      }
      const memberStats = parent.memberStats[squadName][assigneeName];
      memberStats[statusName] = (memberStats[statusName] || 0) + 1;
      memberStats.total = (memberStats.total || 0) + 1;
    });

    const DEFAULT_ROLES = ['Backend', 'WEB', 'Mobile', 'QA', 'Lainnya'];
    const statusList = Array.from(allStatuses);

    const parentIssues = Object.values(parentMap).map((parent) => {
      DEFAULT_ROLES.forEach((role) => {
        if (!parent.squadStats[role]) {
          parent.squadStats[role] = { total: 0 };
        }
      });

      const chartData = Object.keys(parent.squadStats).map((squad) => {
        const item = { name: squad, total: parent.squadStats[squad].total || 0 };
        statusList.forEach((st) => {
          item[st] = parent.squadStats[squad][st] || 0;
        });
        return item;
      });

      const memberDataByCategory = {};
      Object.keys(parent.memberStats).forEach((squad) => {
        memberDataByCategory[squad] = Object.keys(parent.memberStats[squad]).map((member) => {
          const item = { name: member, total: parent.memberStats[squad][member].total || 0 };
          statusList.forEach((st) => {
            item[st] = parent.memberStats[squad][member][st] || 0;
          });
          return item;
        });
      });

      const progressPercentage = parent.totalSubtasks > 0
        ? Math.round((parent.completedSubtasks / parent.totalSubtasks) * 100)
        : 0;

      return {
        key: parent.key,
        title: parent.title,
        parentSummary: parent.parentSummary,
        totalSubtasks: parent.totalSubtasks,
        completedSubtasks: parent.completedSubtasks,
        progressPercentage,
        chartData,
        memberDataByCategory,
      };
    });

    return {
      parentIssues,
      availableStatuses: statusList,
    };

  } catch (error) {
    console.error('[Squad Report] Error:', error);
    return {
      parentIssues: [],
      availableStatuses: [],
    };
  }
});


// ============================================================
// 2. GET PROJECT EPICS (FIXED API)
// ============================================================

resolver.define('getProjectEpics', async (req) => {
  const { projectKey } = req.payload || {};
  if (!projectKey) {
    throw new Error('Project Key tidak ditemukan.');
  }

  const jql = `project = "${projectKey}" AND issuetype = "Epic" ORDER BY created DESC`;
  
  const response = await api.asUser().requestJira(
    route`/rest/api/3/search/jql`,
    {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        jql,
        maxResults: 100,
        fields: ['summary', 'status'],
      }),
    }
  );

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`Gagal mengambil Epics: ${response.status} ${errText}`);
  }

  const data = await response.json();
  const epics = (data.issues || []).map((issue) => ({
    key: issue.key,
    summary: issue.fields.summary,
    status: issue.fields.status?.name || 'Unknown'
  }));

  return { epics };
});


// ============================================================
// 3. GET EPIC STORY DETAILS & ROLE BREAKDOWN (FIXED API)
// ============================================================

resolver.define('getEpicStoryDetails', async (req) => {
  const { epicKey, projectKey } = req.payload || {};
  if (!epicKey) {
    return { stories: [] };
  }

  const storyJql = `project = "${projectKey}" AND (parent = "${epicKey}" OR "Epic Link" = "${epicKey}") ORDER BY key ASC`;
  
  const storyRes = await api.asUser().requestJira(
    route`/rest/api/3/search/jql`,
    {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        jql: storyJql,
        maxResults: 100,
        fields: ['summary', 'status', 'issuetype'],
      }),
    }
  );

  if (!storyRes.ok) {
    const errText = await storyRes.text();
    throw new Error(`Gagal mengambil Story untuk Epic ${epicKey}: ${errText}`);
  }

  const storyData = await storyRes.json();
  const stories = storyData.issues || [];

  if (stories.length === 0) {
    return { stories: [] };
  }

  const storyKeys = stories.map((s) => s.key);
  const subtaskJql = `parent in (${storyKeys.map((k) => `"${k}"`).join(',')}) ORDER BY key ASC`;

  const subtaskRes = await api.asUser().requestJira(
    route`/rest/api/3/search/jql`,
    {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        jql: subtaskJql,
        maxResults: 500,
        fields: ['summary', 'status', 'parent', 'assignee'],
      }),
    }
  );

  let subtasks = [];
  if (subtaskRes.ok) {
    const subtaskData = await subtaskRes.json();
    subtasks = subtaskData.issues || [];
  }

  const subtasksByStoryKey = {};
  subtasks.forEach((st) => {
    const parentKey = st.fields.parent?.key;
    if (!parentKey) return;

    if (!subtasksByStoryKey[parentKey]) {
      subtasksByStoryKey[parentKey] = [];
    }

    const summary = st.fields.summary || '';
    const assigneeName = st.fields.assignee?.displayName;
    const role = extractSquadName(summary);

    subtasksByStoryKey[parentKey].push({
      key: st.key,
      summary: st.fields.summary,
      status: st.fields.status?.name || 'To Do',
      role: role,
      assignee: assigneeName || 'Unassigned'
    });
  });

  const processedStories = stories.map((story) => {
    const storySubtasks = subtasksByStoryKey[story.key] || [];

    // Map dinamis: Hanya membuat entry untuk role yang benar-benar ada subtasknya
    const roleMap = {};

    storySubtasks.forEach((st) => {
      if (!roleMap[st.role]) {
        roleMap[st.role] = { name: st.role, total: 0 };
      }
      roleMap[st.role][st.status] = (roleMap[st.role][st.status] || 0) + 1;
      roleMap[st.role].total += 1;
    });

    const roleChartData = Object.values(roleMap);
    const availableRoles = Object.keys(roleMap); // Mengirim daftar role aktif saja

    return {
      key: story.key,
      summary: story.fields.summary,
      status: story.fields.status?.name || 'Unknown',
      subtasks: storySubtasks,
      roleChartData,
      availableRoles
    };
  });

  return { stories: processedStories };
});


// ============================================================
// 4. GET AI RECOMMENDATIONS
// ============================================================

resolver.define('getRecommendations', async (req) => {
  const { issueKey } = req.payload || {};

  if (!issueKey) {
    return [];
  }

  try {
    const jiraResponse = await api
      .asApp()
      .requestJira(
        route`/rest/api/3/issue/${issueKey}?fields=summary,description,subtasks`
      );

    if (!jiraResponse.ok) {
      return [];
    }

    const jiraData = await jiraResponse.json();

    const summary = jiraData.fields?.summary || '';
    const descriptionText = extractTextFromADF(jiraData.fields?.description);
    const existingSubtasks = jiraData.fields?.subtasks || [];

    const FASTAPI_URL = 'https://every-showers-clean.loca.lt/api/v1/predict';

    const requestBody = {
      title: summary,
      ac_text: descriptionText || summary,
      parent_sp: 3.0,
      members: [
        { pn: '001', name: 'Developer Backend', role: 'backend' },
        { pn: '002', name: 'Developer Frontend', role: 'frontend' },
        { pn: '003', name: 'QA Engineer', role: 'qa' },
      ],
      selected_role: 'all',
      parent_type: 'Story',
    };

    const pyResponse = await fetch(FASTAPI_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'bypass-tunnel-reminder': 'true',
      },
      body: JSON.stringify(requestBody),
    });

    const responseText = await pyResponse.text();

    if (!pyResponse.ok) {
      return [];
    }

    let resJson;
    try {
      resJson = JSON.parse(responseText);
    } catch (error) {
      return [];
    }

    const rawSubtasks = extractSubtasksFromAIResponse(resJson);

    if (rawSubtasks.length === 0) {
      return [];
    }

    const existingCounts = {};
    for (const st of existingSubtasks) {
      const existingSummary = cleanText(st.fields?.summary || '');
      if (!existingSummary) continue;
      existingCounts[existingSummary] = (existingCounts[existingSummary] || 0) + 1;
    }

    const normalizedTasks = rawSubtasks
      .map((task, index) => {
        let role = 'backend';
        if (typeof task === 'object') {
          role = task?.role || task?.category || task?.team || 'backend';
        }
        const category = normalizeCategory(role);
        return normalizeTask(task, index, category);
      })
      .filter((task) => task.text && task.text.trim());

    const remainingTasks = [];
    const counts = { ...existingCounts };

    for (const task of normalizedTasks) {
      const taskClean = cleanText(task.text);
      if (counts[taskClean] && counts[taskClean] > 0) {
        counts[taskClean]--;
      } else {
        remainingTasks.push(task);
      }
    }

    return convertSubtasksToGroups(remainingTasks);

  } catch (error) {
    return [];
  }
});


// ============================================================
// 5. CREATE SUBTASKS
// ============================================================

resolver.define('createSubtasks', async (req) => {
  const { issueKey, subtasks } = req.payload || {};

  if (!issueKey || !Array.isArray(subtasks) || subtasks.length === 0) {
    return {
      success: false,
      error: 'Data tidak lengkap',
    };
  }

  try {
    const issueResponse = await api
      .asApp()
      .requestJira(route`/rest/api/3/issue/${issueKey}?fields=project`);

    if (!issueResponse.ok) {
      const errorText = await issueResponse.text();
      return {
        success: false,
        error: `Gagal mengambil issue: ${errorText}`,
      };
    }

    const issueData = await issueResponse.json();
    const projectId = issueData.fields?.project?.id;

    if (!projectId) {
      return {
        success: false,
        error: 'Project ID tidak ditemukan',
      };
    }

    const projectResponse = await api
      .asApp()
      .requestJira(route`/rest/api/3/project/${projectId}`);

    if (!projectResponse.ok) {
      const errorText = await projectResponse.text();
      return {
        success: false,
        error: `Gagal mengambil project: ${errorText}`,
      };
    }

    const projectData = await projectResponse.json();
    const subtaskType = (projectData.issueTypes || []).find(
      (type) => type.subtask === true
    );

    if (!subtaskType) {
      return {
        success: false,
        error: 'Subtask issue type tidak ditemukan',
      };
    }

    const results = [];

    for (const rawTask of subtasks) {
      let taskText;
      if (typeof rawTask === 'string') {
        taskText = rawTask.trim();
      } else {
        taskText = String(rawTask?.text || rawTask?.summary || '').trim();
      }

      if (!taskText) continue;

      const bodyData = {
        fields: {
          summary: taskText,
          project: {
            id: projectId,
          },
          parent: {
            key: issueKey,
          },
          issuetype: {
            id: subtaskType.id,
          },
        },
      };

      const createResponse = await api
        .asApp()
        .requestJira(route`/rest/api/3/issue`, {
          method: 'POST',
          headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(bodyData),
        });

      if (createResponse.status === 201) {
        const created = await createResponse.json();
        results.push({
          success: true,
          key: created.key,
          summary: taskText,
        });
      } else {
        const errorText = await createResponse.text();
        results.push({
          success: false,
          error: errorText,
          summary: taskText,
        });
      }
    }

    const createdKeys = results
      .filter((item) => item.success)
      .map((item) => item.key);

    return {
      success: createdKeys.length > 0,
      createdKeys,
      results,
    };

  } catch (error) {
    return {
      success: false,
      error: error?.message || String(error),
    };
  }
});


// ============================================================
// EXPORT
// ============================================================

export const handler = resolver.getDefinitions();