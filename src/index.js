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


// ============================================================
// NORMALIZE TASK
// ============================================================

function normalizeTask(task, index, category) {
  // ----------------------------------------
  // Jika AI mengembalikan string
  // ----------------------------------------

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
            ? assignment.assigned_subtasks
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
          .asApp()
          .requestJira(
            route`/rest/api/3/issue/${issueKey}?fields=summary,description,subtasks`
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
        'https://shaggy-books-check.loca.lt/api/v1/predict';

      
      console.log('========================================');
      console.log('[DEBUG JIRA → FASTAPI]');
      console.log('[DEBUG] issueKey:', issueKey);
      console.log('[DEBUG] Summary:', summary);
      console.log('[DEBUG] Description/AC:', descriptionText);
      console.log('[DEBUG] Description length:', descriptionText.length);
      console.log('========================================');


      const requestBody = {
        title:
          summary,

        ac_text:
          descriptionText ||
          summary,

        parent_sp:
          3.0,

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
          'Story',
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
          '[AI Recommendation] FastAPI gagal:',
          pyResponse.status,
          responseText
        );

        return [];
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
              category
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


        const bodyData = {
          fields: {

            summary:
              taskText,

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