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
// NORMALIZE ROLE
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
    value === 'web'
  ) {
    return 'Frontend';
  }

  if (
    value === 'backend' ||
    value === 'back-end' ||
    value === 'back end' ||
    value === 'be'
  ) {
    return 'Backend';
  }

  if (
    value === 'mobile' ||
    value === 'android' ||
    value === 'ios'
  ) {
    return 'Mobile';
  }

  if (
    value === 'qa' ||
    value === 'quality assurance' ||
    value === 'tester' ||
    value === 'testing'
  ) {
    return 'QA';
  }

  return 'Backend';
}

function extractSquadName(summary = '') {
  const text = String(summary || '').trim();
  const match = text.match(/^\[(.*?)\]/);
  if (match && match[1]) {
    return normalizeCategory(match[1].trim());
  }
  if (/^mobile/i.test(text) || /\bmobile\b/i.test(text) || /^mob\b/i.test(text)) {
    return 'Mobile';
  }
  if (/^be\b/i.test(text) || /\bbackend\b/i.test(text)) {
    return 'Backend';
  }
  if (/^web\b/i.test(text) || /^fe\b/i.test(text) || /\bfrontend\b/i.test(text)) {
    return 'Frontend';
  }
  if (/^qa\b/i.test(text) || /\btesting\b/i.test(text) || /\bpengujian\b/i.test(text)) {
    return 'QA';
  }
  const lower = text.toLowerCase();
  if (lower.includes('frontend') || lower.includes('fe') || lower.includes('web') || lower.includes('ui')) {
    return 'Frontend';
  }
  if (lower.includes('backend') || lower.includes('be') || lower.includes('api') || lower.includes('endpoint')) {
    return 'Backend';
  }
  if (lower.includes('qa') || lower.includes('testing') || lower.includes('test') || lower.includes('review')) {
    return 'QA';
  }
  return 'Backend';
}


// ============================================================
// NORMALIZE TASK & PREDICTABLE KEY CALCULATION
// ============================================================

function calculateSubtaskKey(parentKey, existingSubtasks, index) {
  const match = String(parentKey || '').match(/^([A-Za-z0-9_]+)-(\d+)$/);
  if (!match) {
    return `draf-${index + 1}`;
  }
  const prefix = match[1];
  let maxNum = parseInt(match[2], 10);

  if (Array.isArray(existingSubtasks) && existingSubtasks.length > 0) {
    for (const sub of existingSubtasks) {
      const subKey = sub.key || sub.id || '';
      const subMatch = String(subKey).match(/^([A-Za-z0-9_]+)-(\d+)$/);
      if (subMatch) {
        const subNum = parseInt(subMatch[2], 10);
        if (subNum > maxNum) {
          maxNum = subNum;
        }
      }
    }
  }

  return `${prefix}-${maxNum + index + 1}`;
}

function normalizeTask(task, index, category, parentKey = '', existingSubtasks = []) {
  const generatedId = calculateSubtaskKey(parentKey, existingSubtasks, index);

  // ----------------------------------------
  // Jika AI mengembalikan string
  // ----------------------------------------

  if (typeof task === 'string') {
    const text = task.trim();

    return {
      id: generatedId,
      text,
      summary: text,
      description: text,
      role: category.toLowerCase(),
      story_points: 1,
    };
  }


  // ----------------------------------------
  // Jika AI mengembalikan object
  // ----------------------------------------

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
      generatedId,

    text: String(summary).trim(),

    summary: String(summary).trim(),

    description: String(description).trim(),

    role:
      task?.role ||
      task?.category ||
      category.toLowerCase(),

    assigneeName:
      task?.assigneeName ||
      task?.assigned_to ||
      task?.employee?.name ||
      '',

    assigneePn:
      task?.assigneePn ||
      task?.assigned_pn ||
      task?.employee?.pn ||
      '',

    assigneeRole:
      task?.assigneeRole ||
      task?.assigned_role ||
      task?.employee?.role ||
      '',

    parent_key:
      task?.parent_key ||
      task?.parentKey ||
      parentKey ||
      '',

    parent_summary:
      task?.parent_summary ||
      task?.parentSummary ||
      '',

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
  console.log(
    '============================================================'
  );

  console.log(
    '[Forge Resolver] Mencoba membaca response FastAPI...'
  );

  console.log(
    '[Forge Resolver] Response:',
    JSON.stringify(resJson, null, 2)
  );


  // ==========================================================
  // CASE 1
  //
  // [
  //   {
  //      summary: "...",
  //      role: "backend"
  //   }
  // ]
  // ==========================================================

  if (Array.isArray(resJson)) {
    console.log(
      '[Forge Resolver] Format response: ARRAY'
    );

    return resJson;
  }


  // ==========================================================
  // CASE 2
  //
  // {
  //   subtasks: [...]
  // }
  // ==========================================================

  if (Array.isArray(resJson?.subtasks)) {
    console.log(
      '[Forge Resolver] Format response: subtasks[]'
    );

    return resJson.subtasks;
  }


  // ==========================================================
  // CASE 3
  //
  // {
  //   results: [...]
  // }
  // ==========================================================

  if (Array.isArray(resJson?.results)) {
    console.log(
      '[Forge Resolver] Format response: results[]'
    );

    return resJson.results;
  }


  // ==========================================================
  // CASE 4
  //
  // {
  //   data: [...]
  // }
  // ==========================================================

  if (Array.isArray(resJson?.data)) {
    console.log(
      '[Forge Resolver] Format response: data[]'
    );

    return resJson.data;
  }


  // ==========================================================
  // CASE 5
  //
  // {
  //   result: [...]
  // }
  // ==========================================================

  if (Array.isArray(resJson?.result)) {
    console.log(
      '[Forge Resolver] Format response: result[]'
    );

    return resJson.result;
  }


  // ==========================================================
  // CASE 6
  //
  // {
  //   recommendations: [...]
  // }
  // ==========================================================

  if (Array.isArray(resJson?.recommendations)) {
    console.log(
      '[Forge Resolver] Format response: recommendations[]'
    );

    return resJson.recommendations;
  }


  // ==========================================================
  // CASE 7
  //
  // {
  //   generated_subtasks: [...]
  // }
  // ==========================================================

  if (Array.isArray(resJson?.generated_subtasks)) {
    console.log(
      '[Forge Resolver] Format response: generated_subtasks[]'
    );

    return resJson.generated_subtasks;
  }


  // ==========================================================
  // CASE 8
  //
  // {
  //   generatedSubtasks: [...]
  // }
  // ==========================================================

  if (Array.isArray(resJson?.generatedSubtasks)) {
    console.log(
      '[Forge Resolver] Format response: generatedSubtasks[]'
    );

    return resJson.generatedSubtasks;
  }


  // ==========================================================
  // CASE 9
  //
  // {
  //   results: {
  //      subtasks: [...]
  //   }
  // }
  // ==========================================================

  if (Array.isArray(resJson?.results?.subtasks)) {
    console.log(
      '[Forge Resolver] Format response: results.subtasks[]'
    );

    return resJson.results.subtasks;
  }


  // ==========================================================
  // CASE 10
  //
  // {
  //   data: {
  //      subtasks: [...]
  //   }
  // }
  // ==========================================================

  if (Array.isArray(resJson?.data?.subtasks)) {
    console.log(
      '[Forge Resolver] Format response: data.subtasks[]'
    );

    return resJson.data.subtasks;
  }


  // ==========================================================
  // CASE 11
  //
  // {
  //   result: {
  //      subtasks: [...]
  //   }
  // }
  // ==========================================================

  if (Array.isArray(resJson?.result?.subtasks)) {
    console.log(
      '[Forge Resolver] Format response: result.subtasks[]'
    );

    return resJson.result.subtasks;
  }


  // ==========================================================
  // CASE 12
  //
  // {
  //   data: {
  //      results: [...]
  //   }
  // }
  // ==========================================================

  if (Array.isArray(resJson?.data?.results)) {
    console.log(
      '[Forge Resolver] Format response: data.results[]'
    );

    return resJson.data.results;
  }


  // ==========================================================
  // CASE 13
  //
  // {
  //   results: {
  //      results: [...]
  //   }
  // }
  // ==========================================================

  if (Array.isArray(resJson?.results?.results)) {
    console.log(
      '[Forge Resolver] Format response: results.results[]'
    );

    return resJson.results.results;
  }


  // ==========================================================
  // CASE 14 — FORMAT FASTAPI SAAT INI
  //
  // {
  //   status: "success",
  //   results: {
  //     assignments: [
  //       {
  //         employee: {...},
  //         assigned_subtasks: [...]
  //       }
  //     ],
  //     unassigned_subtasks: [...]
  //   }
  // }
  // ==========================================================

  if (
    Array.isArray(resJson?.results?.assignments)
  ) {
    console.log(
      '[Forge Resolver] Format response: results.assignments[].assigned_subtasks[]'
    );

    const assignedSubtasks =
      resJson.results.assignments.flatMap(
        (assignment) =>
          Array.isArray(
            assignment?.assigned_subtasks
          )
            ? assignment.assigned_subtasks.map((st) => ({
                ...st,
                assigneeName: assignment.employee?.name || st.assigned_to,
                assigneePn: assignment.employee?.pn || st.assigned_pn,
                assigneeRole: assignment.employee?.role || st.assigned_role,
              }))
            : []
      );

    const unassignedSubtasks =
      Array.isArray(
        resJson?.results?.unassigned_subtasks
      )
        ? resJson.results.unassigned_subtasks
        : [];

    console.log(
      '[Forge Resolver] Assigned subtasks:',
      assignedSubtasks.length
    );

    console.log(
      '[Forge Resolver] Unassigned subtasks:',
      unassignedSubtasks.length
    );

    return [
      ...assignedSubtasks,
      ...unassignedSubtasks,
    ];
  }


  // ==========================================================
  // CASE 15
  //
  // Fallback jika assignments langsung berisi subtasks
  // ==========================================================

  if (
    Array.isArray(resJson?.assignments)
  ) {
    console.log(
      '[Forge Resolver] Format response: assignments[]'
    );

    const assignedSubtasks =
      resJson.assignments.flatMap(
        (assignment) =>
          Array.isArray(
            assignment?.assigned_subtasks
          )
            ? assignment.assigned_subtasks
            : []
      );

    return assignedSubtasks;
  }


  console.warn(
    '[Forge Resolver] TIDAK menemukan array subtasks di response FastAPI.'
  );

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

    const category =
      normalizeCategory(role);

    const task =
      normalizeTask(
        rawTask,
        index,
        category
      );

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


  const groups =
    Object.values(groupMap);


  groups.forEach((group) => {
    group.badgeCount =
      `${group.tasks.length} task`;
  });


  return groups;
}


// ============================================================
// 1. SQUAD PROGRESS REPORT
// ============================================================

resolver.define(
  'getSquadProgress',
  async (req) => {
    try {
      const {
        projectKey = 'SCRUM',
      } = req.payload || {};

      const jql =
        `project = "${projectKey}" AND issuetype in subTaskIssueTypes()`;

      console.log(
        '[Squad Report] JQL:',
        jql
      );


      const response =
        await api
          .asUser()
          .requestJira(
            route`/rest/api/3/search/jql`,
            {
              method: 'POST',

              headers: {
                Accept:
                  'application/json',

                'Content-Type':
                  'application/json',
              },

              body:
                JSON.stringify({
                  jql,

                  fields: [
                    'summary',
                    'status',
                    'assignee',
                    'parent',
                  ],
                }),
            }
          );


      if (!response.ok) {
        console.error(
          '[Squad Report] Jira error:',
          await response.text()
        );

        return {
          parentIssues: [],
          squadsList: [],
          memberDataBySquad: {},
        };
      }


      const data =
        await response.json();

      const issues =
        Array.isArray(data.issues)
          ? data.issues
          : [];


      const parentMap = {};
      const squadSet = new Set();
      const memberMapBySquad = {};


      const initStats = () => ({
        todo: 0,
        inProgress: 0,
        done: 0,
        total: 0,
      });


      issues.forEach((issue) => {
        const parentKey =
          issue.fields?.parent?.key ||
          'Lainnya';

        const parentSummary =
          issue.fields?.parent?.fields?.summary ||
          parentKey;

        const summary =
          issue.fields?.summary ||
          '';

        const statusCategory =
          issue.fields?.status?.statusCategory?.key;

        const assigneeName =
          issue.fields?.assignee?.displayName ||
          'Unassigned';


        const match =
          summary.match(/^\[(.*?)\]/);

        const squadName =
          match
            ? match[1].trim()
            : 'Lainnya';


        squadSet.add(
          squadName
        );


        if (!parentMap[parentKey]) {
          parentMap[parentKey] = {
            key: parentKey,

            title:
              `${parentSummary} (${parentKey})`,

            squadMap: {},
          };
        }


        if (
          !parentMap[parentKey]
            .squadMap[squadName]
        ) {
          parentMap[parentKey]
            .squadMap[squadName] =
            initStats();
        }


        if (
          !memberMapBySquad[squadName]
        ) {
          memberMapBySquad[squadName] = {};
        }


        if (
          !memberMapBySquad[squadName]
          [assigneeName]
        ) {
          memberMapBySquad[squadName]
          [assigneeName] =
            initStats();
        }


        const parentStats =
          parentMap[parentKey]
            .squadMap[squadName];

        const memberStats =
          memberMapBySquad[squadName]
          [assigneeName];


        if (statusCategory === 'new') {
          parentStats.todo++;
          memberStats.todo++;
        } else if (
          statusCategory === 'indeterminate'
        ) {
          parentStats.inProgress++;
          memberStats.inProgress++;
        } else if (
          statusCategory === 'done'
        ) {
          parentStats.done++;
          memberStats.done++;
        }


        parentStats.total++;
        memberStats.total++;
      });


      const parentIssues =
        Object.values(parentMap)
          .map((item) => ({
            key: item.key,
            title: item.title,

            chartData:
              Object.keys(item.squadMap)
                .map((sq) => ({
                  name: sq,
                  ...item.squadMap[sq],
                })),
          }));


      const memberDataBySquad = {};


      Object.keys(
        memberMapBySquad
      ).forEach((squad) => {
        memberDataBySquad[squad] =
          Object.keys(
            memberMapBySquad[squad]
          ).map((member) => ({
            name: member,
            ...memberMapBySquad[squad][member],
          }));
      });


      return {
        parentIssues,
        squadsList:
          Array.from(squadSet),
        memberDataBySquad,
      };

    } catch (error) {
      console.error(
        '[Squad Report] Error:',
        error
      );

      return {
        parentIssues: [],
        squadsList: [],
        memberDataBySquad: {},
      };
    }
  }
);


// ============================================================
// 1B. GET PROJECT EPICS (FOR AGILE REPORTS)
// ============================================================

resolver.define('getProjectEpics', async (req) => {
  const { projectKey } = req.payload || {};
  const cleanProjectKey = String(projectKey || 'JT').trim();

  try {
    const jql = `project = "${cleanProjectKey}" AND (issuetype = "Epic" OR hierarchyLevel = 1) ORDER BY created DESC`;
    console.log('[getProjectEpics] Executing JQL:', jql);

    let response = await api.asUser().requestJira(route`/rest/api/3/search/jql`, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        jql,
        maxResults: 100,
        fields: ['summary', 'status', 'issuetype'],
      }),
    });

    if (!response.ok) {
      console.warn(`[getProjectEpics] asUser failed (${response.status}), retrying with asApp...`);
      response = await api.asApp().requestJira(route`/rest/api/3/search/jql`, {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          jql,
          maxResults: 100,
          fields: ['summary', 'status', 'issuetype'],
        }),
      });
    }

    if (!response.ok) {
      const errText = await response.text();
      console.error(`[getProjectEpics] JQL failed: ${response.status} ${errText}`);
      return { epics: [] };
    }

    const data = await response.json();
    const epics = (data.issues || []).map((issue) => ({
      key: issue.key,
      summary: issue.fields?.summary || issue.key,
      status: issue.fields?.status?.name || 'Unknown',
    }));

    return { epics };
  } catch (err) {
    console.error('[getProjectEpics] Error:', err);
    return { epics: [] };
  }
});


// ============================================================
// 1C. GET EPIC STORY DETAILS & SUBTASKS (FOR SQUAD REPORT)
// ============================================================

resolver.define('getEpicStoryDetails', async (req) => {
  const { epicKey, projectKey } = req.payload || {};
  if (!epicKey) {
    return { stories: [] };
  }

  // Extract clean key, e.g. from "[JT-22] Brispot..." -> "JT-22"
  const cleanEpicKey = String(epicKey).trim().replace(/^\[|\]$/g, '').split(' ')[0].split('-')[0] + '-' + (String(epicKey).match(/\d+/) ? String(epicKey).match(/\d+/)[0] : '');
  const targetKey = cleanEpicKey.includes('-') ? cleanEpicKey : String(epicKey).trim();

  try {
    console.log(`[getEpicStoryDetails] Fetching child stories for Epic: ${targetKey}`);

    let epicDetails = {
      key: targetKey,
      summary: '',
      startDate: '',
      endDate: '',
      sprintName: '',
      duedate: '',
      created: ''
    };

    try {
      let epicRes = await api.asUser().requestJira(route`/rest/api/3/issue/${targetKey}?fields=summary,status,duedate,created,customfield_10020,fixVersions`);
      if (!epicRes.ok) {
        epicRes = await api.asApp().requestJira(route`/rest/api/3/issue/${targetKey}?fields=summary,status,duedate,created,customfield_10020,fixVersions`);
      }
      if (epicRes.ok) {
        const epData = await epicRes.json();
        const f = epData.fields || {};
        const sprints = Array.isArray(f.customfield_10020) ? f.customfield_10020 : [];
        const activeSprint = sprints.find((s) => s.state === 'active') || sprints[sprints.length - 1];

        epicDetails.summary = f.summary || '';
        epicDetails.duedate = f.duedate || '';
        epicDetails.created = f.created || '';

        if (activeSprint) {
          epicDetails.sprintName = activeSprint.name || '';
          epicDetails.startDate = activeSprint.startDate || f.created;
          epicDetails.endDate = activeSprint.endDate || f.duedate;
        } else {
          epicDetails.startDate = f.created || '';
          epicDetails.endDate = f.duedate || '';
        }
      }
    } catch (eErr) {
      console.warn('[getEpicStoryDetails] Gagal fetch epic metadata:', eErr);
    }

    const storyJql = `(parent = "${targetKey}" OR "Epic Link" = "${targetKey}") ORDER BY key ASC`;

    let storyRes = await api.asUser().requestJira(route`/rest/api/3/search/jql`, {
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
    });

    if (!storyRes.ok) {
      console.warn(`[getEpicStoryDetails] asUser search failed (${storyRes.status}), retrying asApp...`);
      storyRes = await api.asApp().requestJira(route`/rest/api/3/search/jql`, {
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
      });
    }

    if (!storyRes.ok) {
      console.error('[getEpicStoryDetails] Story query failed:', await storyRes.text());
      return { stories: [] };
    }

    const storyData = await storyRes.json();
    const rawStories = storyData.issues || [];

    // Filter out subtasks from direct children (only Stories / Tasks)
    const stories = rawStories.filter((s) => {
      const typeName = (s.fields?.issuetype?.name || '').toLowerCase();
      return !typeName.includes('sub-task') && !typeName.includes('subtask') && !s.fields?.issuetype?.subtask;
    });

    if (stories.length === 0) {
      return { stories: [] };
    }

    const storyKeys = stories.map((s) => s.key);
    const subtaskJql = `parent in (${storyKeys.map((k) => `"${k}"`).join(',')}) ORDER BY key ASC`;

    let subtaskRes = await api.asUser().requestJira(route`/rest/api/3/search/jql`, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        jql: subtaskJql,
        maxResults: 500,
        fields: ['summary', 'status', 'parent', 'assignee', 'issuetype'],
      }),
    });

    if (!subtaskRes.ok) {
      subtaskRes = await api.asApp().requestJira(route`/rest/api/3/search/jql`, {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          jql: subtaskJql,
          maxResults: 500,
          fields: ['summary', 'status', 'parent', 'assignee', 'issuetype'],
        }),
      });
    }

    let subtasks = [];
    if (subtaskRes.ok) {
      const subtaskData = await subtaskRes.json();
      subtasks = subtaskData.issues || [];
    }

    const subtasksByStoryKey = {};
    subtasks.forEach((st) => {
      const parentKey = st.fields?.parent?.key;
      if (!parentKey) return;

      if (!subtasksByStoryKey[parentKey]) {
        subtasksByStoryKey[parentKey] = [];
      }

      const summary = st.fields?.summary || '';
      const assigneeName = st.fields?.assignee?.displayName;
      const role = extractSquadName(summary);

      subtasksByStoryKey[parentKey].push({
        key: st.key,
        summary: st.fields?.summary || '',
        status: st.fields?.status?.name || 'To Do',
        role: role,
        assignee: assigneeName || 'Unassigned',
        iconUrl: st.fields?.issuetype?.iconUrl || '',
        typeName: st.fields?.issuetype?.name || 'Sub-task'
      });
    });

    const processedStories = stories.map((story) => {
      const storySubtasks = subtasksByStoryKey[story.key] || [];
      const roleMap = {};

      storySubtasks.forEach((st) => {
        if (!roleMap[st.role]) {
          roleMap[st.role] = { name: st.role, total: 0 };
        }
        roleMap[st.role][st.status] = (roleMap[st.role][st.status] || 0) + 1;
        roleMap[st.role].total += 1;
      });

      const roleChartData = Object.values(roleMap);
      const availableRoles = Object.keys(roleMap);

      return {
        key: story.key,
        summary: story.fields?.summary || story.key,
        status: story.fields?.status?.name || 'Unknown',
        iconUrl: story.fields?.issuetype?.iconUrl || '',
        typeName: story.fields?.issuetype?.name || 'Story',
        subtasks: storySubtasks,
        roleChartData,
        availableRoles,
      };
    });

    return { stories: processedStories, epicDetails };
  } catch (err) {
    console.error('[getEpicStoryDetails] Error:', err);
    return { stories: [], epicDetails: null };
  }
});


// ============================================================
// 1D. EXPORT EXCEL VIA PYTHON BACKEND (WITH NATIVE CHARTS)
// ============================================================

resolver.define('exportExcelReport', async (req) => {
  const payload = req.payload || {};
  const FASTAPI_REPORT_URL =
    'https://seattle-velvet-exploration-compete.trycloudflare.com/api/v1/reporting/export-excel';

  try {
    console.log('[Export Excel] Calling Python Excel Reporter:', FASTAPI_REPORT_URL);
    const pyRes = await fetch(FASTAPI_REPORT_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'bypass-tunnel-reminder': 'true',
      },
      body: JSON.stringify({
        ...payload,
        return_base64: true,
      }),
    });

    if (!pyRes.ok) {
      const errText = await pyRes.text();
      console.error('[Export Excel] Python backend error:', pyRes.status, errText);
      return {
        success: false,
        error: `Python report error: ${errText}`,
      };
    }

    const data = await pyRes.json();
    return {
      success: true,
      filename: data.filename || `Laporan_Progress_${payload.root_key || 'Sprint'}.xlsx`,
      base64: data.base64,
    };
  } catch (err) {
    console.error('[Export Excel] Error:', err);
    return {
      success: false,
      error: err?.message || String(err),
    };
  }
});


// ============================================================
// 2. GET AI RECOMMENDATIONS
// ============================================================

resolver.define(
  'getRecommendations',
  async (req) => {

    const {
      issueKey,
    } = req.payload || {};


    console.log(
      '============================================================'
    );

    console.log(
      '[AI Recommendation] START'
    );

    console.log(
      '[AI Recommendation] issueKey:',
      issueKey
    );


    if (!issueKey) {
      console.error(
        '[AI Recommendation] issueKey kosong'
      );

      return [];
    }


    try {

      // ========================================================
      // STEP 1 — GET JIRA ISSUE
      // ========================================================

      const jiraResponse =
        await api
          .asUser()
          .requestJira(
            route`/rest/api/3/issue/${issueKey}?fields=summary,description,subtasks,issuetype,customfield_10016`
          );

      if (!jiraResponse.ok) {
        const errorText =
          await jiraResponse.text();
        console.error(
          '[AI Recommendation] Jira error:',
          jiraResponse.status,
          errorText
        );
        return [];
      }

      const jiraData =
        await jiraResponse.json();

      const summary =
        jiraData.fields?.summary ||
        '';

      const descriptionText =
        extractTextFromADF(
          jiraData.fields?.description
        );

      const existingSubtasks =
        jiraData.fields?.subtasks ||
        [];

      const issueTypeName = (jiraData.fields?.issuetype?.name || '').toLowerCase();
      const isEpic = (
        issueTypeName === 'epic' ||
        jiraData.fields?.issuetype?.hierarchyLevel === 1
      );

      let childStories = [];
      if (isEpic) {
        console.log(`[AI Recommendation] Issue ${issueKey} terdeteksi sebagai EPIC. Mengambil seluruh child work items...`);
        try {
          const jqlQuery = `parent = "${issueKey}" OR "Epic Link" = "${issueKey}" ORDER BY created ASC`;
          const searchRes = await api.asUser().requestJira(route`/rest/api/3/search/jql`, {
            method: 'POST',
            headers: {
              Accept: 'application/json',
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              jql: jqlQuery,
              fields: ['summary', 'description', 'subtasks', 'issuetype', 'status', 'customfield_10016'],
              maxResults: 100
            })
          });
          if (searchRes.ok) {
            const searchData = await searchRes.json();
            const rawChildren = Array.isArray(searchData.issues) ? searchData.issues : [];
            childStories = rawChildren
              .filter(ch => {
                const typeName = (ch.fields?.issuetype?.name || '').toLowerCase();
                const isSub = ch.fields?.issuetype?.subtask || typeName.includes('sub-task') || typeName.includes('subtask');
                return !isSub;
              })
              .map(ch => {
                const chSummary = ch.fields?.summary || ch.key;
                const chDesc = extractTextFromADF(ch.fields?.description) || chSummary;
                const chExisting = (ch.fields?.subtasks || []).map(st => st.fields?.summary || '').filter(Boolean);
                const chSp = ch.fields?.customfield_10016 || 3.0;
                return {
                  key: ch.key,
                  title: chSummary,
                  summary: chSummary,
                  ac_text: chDesc,
                  description: chDesc,
                  parent_sp: chSp,
                  existing_subtask_summaries: chExisting,
                  parent_type: ch.fields?.issuetype?.name || 'Story'
                };
              });
            console.log(`[AI Recommendation] Berhasil menemukan ${childStories.length} child stories di bawah Epic ${issueKey}:`, childStories.map(c => c.key));
          }
        } catch (epicErr) {
          console.warn(`[AI Recommendation] Gagal mencari child stories untuk Epic ${issueKey}:`, epicErr);
        }
      }

      console.log(
        '[AI Recommendation] Summary:',
        summary
      );

      console.log(
        '[AI Recommendation] Description:',
        descriptionText
      );

      console.log(
        '[AI Recommendation] Existing subtasks:',
        existingSubtasks.length
      );

      // ========================================================
      // STEP 2 — FASTAPI
      // ========================================================

      const FASTAPI_URL =
        "https://seattle-velvet-exploration-compete.trycloudflare.com/api/v1/predict";

      console.log('========================================');
      console.log('[DEBUG JIRA → FASTAPI]');
      console.log('[DEBUG] issueKey:', issueKey);
      console.log('[DEBUG] Summary:', summary);
      console.log('[DEBUG] isEpic:', isEpic);
      console.log('[DEBUG] childStories count:', childStories.length);
      console.log('========================================');

      const requestBody = {
        issue_key:
          issueKey,

        title:
          summary,

        ac_text:
          descriptionText ||
          summary,

        parent_sp:
          3.0,

        is_epic:
          isEpic && childStories.length > 0,

        stories:
          childStories.length > 0 ? childStories : [],

        existing_subtask_summaries:
          existingSubtasks.map(
            (st) => st.fields?.summary || ''
          ).filter(Boolean),

        members: [
          {
            pn: '001',
            name: 'Developer Backend',
            role: 'backend',
          },

          {
            pn: '002',
            name: 'Developer Frontend',
            role: 'frontend',
          },

          {
            pn: '003',
            name: 'QA Engineer',
            role: 'qa',
          },
        ],

        selected_role:
          'all',

        parent_type:
          isEpic ? 'Epic' : 'Story',
      };

      console.log(
        '[DEBUG] Request Body:',
        JSON.stringify(requestBody, null, 2)
      );

      console.log(
        '[AI Recommendation] Calling FastAPI:',
        FASTAPI_URL
      );

      console.log(
        '[AI Recommendation] Request body:',
        JSON.stringify(
          requestBody,
          null,
          2
        )
      );


      // ========================================================
      // STEP 3 — REQUEST
      // ========================================================

      const pyResponse =
        await fetch(
          FASTAPI_URL,
          {
            method: 'POST',

            headers: {
              'Content-Type':
                'application/json',

              'bypass-tunnel-reminder':
                'true',
            },

            body:
              JSON.stringify(
                requestBody
              ),
          }
        );


      // ========================================================
      // STEP 4 — BACA RAW RESPONSE
      // ========================================================

      const responseText =
        await pyResponse.text();


      console.log(
        '[AI Recommendation] FastAPI HTTP status:',
        pyResponse.status
      );


      console.log(
        '[AI Recommendation] FastAPI raw response:',
        responseText
      );


      if (!pyResponse.ok) {
        console.error(
          '============================================================'
        );
        console.error(
          '[DIAGNOSTIK KONEKSI] FE <-> RESOLVER <-> FASTAPI BACKEND TERHUBUNG 100%!'
        );
        console.error(
          `[DIAGNOSTIK KONEKSI] Namun FastAPI melempar error status HTTP ${pyResponse.status}:`,
          responseText
        );
        console.error(
          '============================================================'
        );

        let diagMsg = `[KONEKSI OK] Backend melempar error HTTP ${pyResponse.status}`;
        if (responseText.includes('429') || responseText.includes('Quota exceeded') || responseText.includes('RESOURCE_EXHAUSTED')) {
          diagMsg = `[KONEKSI OK 100%] Gagal di Gemini AI: Quota Limit 429 Habis. Ganti API Key di .env untuk mengatasi.`;
        } else if (responseText.includes('403') || responseText.includes('PERMISSION_DENIED')) {
          diagMsg = `[KONEKSI OK 100%] Gagal di Gemini AI: API Key (HTTP 403) Tidak Valid. Perbarui API Key di .env.`;
        }

        return {
          success: false,
          errorType: 'AI_MODEL_LIMIT',
          status: pyResponse.status,
          message: diagMsg,
          rawError: responseText.substring(0, 200),
          subtasks: []
        };
      }


      // ========================================================
      // STEP 5 — PARSE JSON
      // ========================================================

      let resJson;


      try {

        resJson =
          JSON.parse(
            responseText
          );

      } catch (error) {

        console.error(
          '[AI Recommendation] FastAPI response bukan JSON:',
          error
        );

        return [];
      }


      console.log(
        '[AI Recommendation] Parsed response:',
        JSON.stringify(
          resJson,
          null,
          2
        )
      );


      // ========================================================
      // STEP 6 — EXTRACT SUBTASKS
      // ========================================================

      const rawSubtasks =
        extractSubtasksFromAIResponse(
          resJson
        );


      console.log(
        '[AI Recommendation] Raw subtasks count:',
        rawSubtasks.length
      );


      if (
        rawSubtasks.length === 0
      ) {

        console.warn(
          '[AI Recommendation] FastAPI 200 tetapi tidak ada subtasks.'
        );

        return [];
      }


      // ========================================================
      // STEP 7 — EXISTING SUBTASKS
      // ========================================================

      const existingCounts = {};


      for (
        const st of existingSubtasks
      ) {

        const existingSummary =
          cleanText(
            st.fields?.summary ||
            ''
          );


        if (!existingSummary) {
          continue;
        }


        existingCounts[
          existingSummary
        ] =
          (
            existingCounts[
            existingSummary
            ] || 0
          ) + 1;
      }


      // ========================================================
      // STEP 8 — NORMALIZE
      // ========================================================

      const normalizedTasks =
        rawSubtasks
          .map((task, index) => {

            let role =
              'backend';


            if (
              typeof task === 'object'
            ) {

              role =
                task?.role ||
                task?.category ||
                task?.team ||
                'backend';
            }


            const category =
              normalizeCategory(
                role
              );


            return normalizeTask(
              task,
              index,
              category,
              issueKey,
              existingSubtasks
            );
          })
          .filter(
            (task) =>
              task.text &&
              task.text.trim()
          );


      console.log(
        '[AI Recommendation] Normalized tasks:',
        JSON.stringify(
          normalizedTasks,
          null,
          2
        )
      );


      // ========================================================
      // STEP 9 — FILTER DUPLICATE
      // ========================================================

      const remainingTasks = [];

      const counts = {
        ...existingCounts,
      };


      for (
        const task of normalizedTasks
      ) {

        const taskClean =
          cleanText(
            task.text
          );


        if (
          counts[taskClean] &&
          counts[taskClean] > 0
        ) {

          counts[taskClean]--;

          console.log(
            '[AI Recommendation] Existing task skipped:',
            task.text
          );

        } else {

          remainingTasks.push(
            task
          );
        }
      }


      // ========================================================
      // STEP 10 — CONVERT TO GROUPS
      // ========================================================

      const groups =
        convertSubtasksToGroups(
          remainingTasks
        );


      console.log(
        '[AI Recommendation] Remaining task count:',
        remainingTasks.length
      );


      console.log(
        '[AI Recommendation] FINAL GROUPS:',
        JSON.stringify(
          groups,
          null,
          2
        )
      );


      console.log(
        '[AI Recommendation] END'
      );


      return groups;

    } catch (error) {

      console.error(
        '[AI Recommendation] ERROR:',
        error
      );

      console.error(
        '[AI Recommendation] STACK:',
        error?.stack
      );

      return [];
    }
  }
);


// ============================================================
// 3. CREATE SUBTASKS
// ============================================================

resolver.define(
  'createSubtasks',
  async (req) => {

    const {
      issueKey,
      subtasks,
    } = req.payload || {};


    console.log(
      '[Create Subtasks] issueKey:',
      issueKey
    );

    console.log(
      '[Create Subtasks] subtasks:',
      JSON.stringify(
        subtasks,
        null,
        2
      )
    );


    if (
      !issueKey ||
      !Array.isArray(subtasks) ||
      subtasks.length === 0
    ) {

      return {
        success: false,
        error:
          'Data tidak lengkap',
      };
    }


    try {

      // ========================================================
      // GET ISSUE
      // ========================================================

      const issueResponse =
        await api
          .asApp()
          .requestJira(
            route`/rest/api/3/issue/${issueKey}?fields=project`
          );


      if (!issueResponse.ok) {

        const errorText =
          await issueResponse.text();

        return {
          success: false,

          error:
            `Gagal mengambil issue: ${errorText}`,
        };
      }


      const issueData =
        await issueResponse.json();


      const projectId =
        issueData.fields?.project?.id;


      if (!projectId) {

        return {
          success: false,
          error:
            'Project ID tidak ditemukan',
        };
      }


      // ========================================================
      // GET PROJECT ISSUE TYPES
      // ========================================================

      const projectResponse =
        await api
          .asApp()
          .requestJira(
            route`/rest/api/3/project/${projectId}`
          );


      if (!projectResponse.ok) {

        const errorText =
          await projectResponse.text();

        return {
          success: false,

          error:
            `Gagal mengambil project: ${errorText}`,
        };
      }


      const projectData =
        await projectResponse.json();


      const subtaskType =
        (
          projectData.issueTypes ||
          []
        ).find(
          (type) =>
            type.subtask === true
        );


      if (!subtaskType) {

        return {
          success: false,

          error:
            'Subtask issue type tidak ditemukan',
        };
      }


      // ========================================================
      // CREATE SUBTASKS
      // ========================================================

      const results = [];


      for (
        const rawTask of subtasks
      ) {

        let taskText;


        if (
          typeof rawTask === 'string'
        ) {

          taskText =
            rawTask.trim();

        } else {

          taskText =
            String(
              rawTask?.text ||
              rawTask?.summary ||
              ''
            ).trim();
        }


        if (!taskText) {
          continue;
        }


        const assigneeName =
          rawTask?.assigneeName ||
          rawTask?.assigned_to ||
          '';

        let assigneeField = undefined;

        if (assigneeName) {
          try {
            const userSearchRes = await api
              .asApp()
              .requestJira(
                route`/rest/api/3/user/search?query=${encodeURIComponent(assigneeName)}`
              );
            if (userSearchRes.ok) {
              const users = await userSearchRes.json();
              if (Array.isArray(users) && users.length > 0) {
                const matchedUser =
                  users.find(
                    (u) =>
                      u.displayName?.toLowerCase().trim() ===
                      assigneeName.toLowerCase().trim()
                  ) || users[0];
                if (matchedUser?.accountId) {
                  assigneeField = {
                    accountId: matchedUser.accountId,
                    id: matchedUser.accountId,
                  };
                  console.log(
                    `[Create Subtasks] Auto-assigning to ${matchedUser.displayName} (${matchedUser.accountId})`
                  );
                }
              }
            }
          } catch (userErr) {
            console.warn(
              `[Create Subtasks] Could not resolve assignee accountId for ${assigneeName}:`,
              userErr
            );
          }
        }

        const bodyData = {
          fields: {

            summary:
              taskText,

            project: {
              id: projectId,
            },

            parent: {
              key: rawTask?.parent_key || rawTask?.parentKey || issueKey,
            },

            issuetype: {
              id: subtaskType.id,
            },

            ...(assigneeField ? { assignee: assigneeField } : {}),

          },
        };


        console.log(
          '[Create Subtasks] Creating:',
          taskText
        );


        const createResponse =
          await api
            .asApp()
            .requestJira(
              route`/rest/api/3/issue`,
              {
                method: 'POST',

                headers: {
                  Accept:
                    'application/json',

                  'Content-Type':
                    'application/json',
                },

                body:
                  JSON.stringify(
                    bodyData
                  ),
              }
            );


        if (
          createResponse.status === 201
        ) {

          const created =
            await createResponse.json();


          results.push({
            success: true,
            key: created.key,
            summary: taskText,
          });


          console.log(
            '[Create Subtasks] SUCCESS:',
            created.key
          );

        } else {

          const errorText =
            await createResponse.text();


          console.error(
            '[Create Subtasks] FAILED:',
            errorText
          );


          results.push({
            success: false,
            error: errorText,
            summary: taskText,
          });
        }
      }


      const createdKeys =
        results
          .filter(
            (item) =>
              item.success
          )
          .map(
            (item) =>
              item.key
          );


      return {
        success:
          createdKeys.length > 0,

        createdKeys,

        results,
      };

    } catch (error) {

      console.error(
        '[Create Subtasks] ERROR:',
        error
      );


      return {
        success: false,

        error:
          error?.message ||
          String(error),
      };
    }
  }
);


// ============================================================
// EXPORT
// ============================================================

export const handler =
  resolver.getDefinitions();