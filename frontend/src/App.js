import React, {
  useState,
  useEffect,
} from 'react';

import {
  invoke,
  view,
} from '@forge/bridge';

import { SquadReport } from './SquadReport';

function App() {

  const [
    isReportPage,
    setIsReportPage,
  ] = useState(false);

  const [
    groups,
    setGroups,
  ] = useState([]);

  const [
    issueKey,
    setIssueKey,
  ] = useState(null);

  const [
    loading,
    setLoading,
  ] = useState(true);

  const [
    loadingText,
    setLoadingText,
  ] = useState(
    'Memuat info Epic...'
  );

  const [
    statusMsg,
    setStatusMsg,
  ] = useState('');

  const [
    statusType,
    setStatusType,
  ] = useState('success');

  const [
    hasGenerated,
    setHasGenerated,
  ] = useState(false);

  // ==========================================================
  // GET JIRA CONTEXT
  // ==========================================================

  useEffect(() => {

    async function loadContext() {

      try {

        if (view && view.theme) {
          view.theme.enable();
        }

        const context =
          await view.getContext();

        console.log(
          '[App] Forge context:',
          context
        );

        if (!context) {
          setLoading(false);
          return;
        }

        const isProjectView =
          context.moduleKey ===
            'squad-report-page' ||
          context.extension?.type ===
            'jira:projectPage' ||
          !context.extension?.issue;

        if (isProjectView) {

          console.log(
            '[App] Project page detected'
          );

          setIsReportPage(true);
          setLoading(false);

          return;
        }

        if (
          context.extension?.issue
        ) {

          const key =
            context.extension.issue.key;

          console.log(
            '[App] Issue key:',
            key
          );

          setIssueKey(key);
          setLoading(false);

          return;
        }

        setLoading(false);

      } catch (error) {

        console.error(
          '[App] Context error:',
          error
        );

        setStatusType('error');

        setStatusMsg(
          'Tidak dapat membaca Jira issue context.'
        );

        setLoading(false);
      }
    }

    loadContext();

  }, []);

  // ==========================================================
  // PROJECT PAGE
  // ==========================================================

  if (isReportPage) {
    return <SquadReport />;
  }

  // ==========================================================
  // GENERATE RECOMMENDATIONS
  // ==========================================================

  const handleGenerateSubtasks =
    async () => {

      if (!issueKey) {

        setStatusType('error');

        setStatusMsg(
          'Issue Jira tidak ditemukan.'
        );

        return;
      }

      console.log(
        '================================'
      );

      console.log(
        '[App] Generate recommendations'
      );

      console.log(
        '[App] Issue:',
        issueKey
      );

      setLoadingText(
        'AI sedang menganalisis deskripsi Epic & membuat rekomendasi...'
      );

      setLoading(true);
      setStatusMsg('');
      setStatusType('success');

      try {

        const data =
          await invoke(
            'getRecommendations',
            {
              issueKey,
            }
          );

        console.log(
          '[App] getRecommendations response:',
          data
        );

        if (!Array.isArray(data)) {

          console.error(
            '[App] Response bukan array:',
            data
          );

          setGroups([]);

          setStatusType('error');

          setStatusMsg(
            'Format rekomendasi dari backend tidak valid.'
          );

          setHasGenerated(true);

          return;
        }

        setGroups(data);
        setHasGenerated(true);

        const total =
          data.reduce(
            (total, group) =>
              total +
              (
                Array.isArray(group.tasks)
                  ? group.tasks.length
                  : 0
              ),
            0
          );

        console.log(
          '[App] Total recommendations:',
          total
        );

        if (total === 0) {

          setStatusType('warning');

          setStatusMsg(
            'AI berhasil dipanggil, tetapi tidak menghasilkan rekomendasi baru.'
          );

        } else {

          setStatusType('success');

          setStatusMsg(
            `${total} rekomendasi sub-task berhasil dibuat oleh AI.`
          );
        }

      } catch (error) {

        console.error(
          '[App] Generate error:',
          error
        );

        setGroups([]);
        setHasGenerated(true);

        setStatusType('error');

        setStatusMsg(
          'Gagal mengambil rekomendasi sub-task dari server.'
        );

      } finally {

        setLoading(false);

        console.log(
          '================================'
        );
      }
    };

  // ==========================================================
  // TOTAL TASKS
  // ==========================================================

  const totalTasks =
    groups.reduce(
      (acc, group) =>
        acc +
        (
          Array.isArray(group.tasks)
            ? group.tasks.length
            : 0
        ),
      0
    );

  // ==========================================================
  // REMOVE RECOMMENDATION
  // ==========================================================

  const handleRemoveTask =
    (
      groupIndex,
      taskId
    ) => {

      setGroups(
        (prev) =>
          prev.map(
            (group, gIdx) => {

              if (
                gIdx !== groupIndex
              ) {
                return group;
              }

              return {
                ...group,

                tasks:
                  (
                    group.tasks || []
                  ).filter(
                    (task) =>
                      task.id !== taskId
                  ),
              };
            }
          )
      );
    };

  // ==========================================================
  // CREATE SINGLE SUBTASK
  // ==========================================================

  const handleAddSingle =
    async (
      groupIndex,
      task
    ) => {

      if (!issueKey) return;

      const group =
        groups[groupIndex];

      const categoryName =
        group.category || 'Backend';

      const taskText =
        task.text ||
        task.summary ||
        '';

      if (!taskText.trim()) {

        setStatusType('error');

        setStatusMsg(
          'Summary sub-task kosong.'
        );

        return;
      }

      setLoadingText(
        `Membuat sub-task "${taskText}"...`
      );

      setLoading(true);
      setStatusMsg('');

      try {

        console.log(
          '[App] Creating single subtask:',
          taskText
        );

        const res =
          await invoke(
            'createSubtasks',
            {
              issueKey,

              subtasks: [
                taskText,
              ],
            }
          );

        console.log(
          '[App] createSubtasks response:',
          res
        );

        if (res?.success) {

          handleRemoveTask(
            groupIndex,
            task.id
          );

          setStatusType('success');

          setStatusMsg(
            `Sub-task "${taskText}" berhasil ditambahkan ke ${issueKey}.`
          );

        } else {

          setStatusType('error');

          setStatusMsg(
            res?.error ||
            'Gagal membuat sub-task.'
          );
        }

      } catch (error) {

        console.error(
          '[App] Create single error:',
          error
        );

        setStatusType('error');

        setStatusMsg(
          'Terjadi kesalahan saat membuat sub-task.'
        );

      } finally {

        setLoading(false);
      }
    };

  // ==========================================================
  // CREATE ALL CATEGORY
  // ==========================================================

  const handleAddAllCategory =
    async (
      groupIndex
    ) => {

      if (!issueKey) return;

      const group =
        groups[groupIndex];

      if (
        !group ||
        !Array.isArray(group.tasks) ||
        group.tasks.length === 0
      ) {
        return;
      }

      const tasks =
        group.tasks;

      setLoadingText(
        `Membuat ${tasks.length} sub-task ${group.category}...`
      );

      setLoading(true);
      setStatusMsg('');

      const subtaskTexts =
        tasks
          .map(
            (task) =>
              task.text ||
              task.summary ||
              ''
          )
          .filter(
            (text) =>
              text.trim()
          );

      try {

        console.log(
          '[App] Creating category:',
          group.category
        );

        console.log(
          '[App] Tasks:',
          subtaskTexts
        );

        const res =
          await invoke(
            'createSubtasks',
            {
              issueKey,

              subtasks:
                subtaskTexts,
            }
          );

        console.log(
          '[App] createSubtasks category response:',
          res
        );

        if (res?.success) {

          setGroups(
            (prev) =>
              prev.map(
                (g, idx) =>
                  idx === groupIndex
                    ? {
                        ...g,
                        tasks: [],
                        badgeCount:
                          '0 task',
                      }
                    : g
              )
          );

          const count =
            Array.isArray(
              res.createdKeys
            )
              ? res.createdKeys.length
              : 0;

          setStatusType('success');

          setStatusMsg(
            `${count} sub-task ${group.category} berhasil dibuat di ${issueKey}.`
          );

        } else {

          setStatusType('error');

          setStatusMsg(
            res?.error ||
            'Gagal membuat sub-task.'
          );
        }

      } catch (error) {

        console.error(
          '[App] Create category error:',
          error
        );

        setStatusType('error');

        setStatusMsg(
          'Terjadi kesalahan saat membuat sub-task.'
        );

      } finally {

        setLoading(false);
      }
    };

  // ==========================================================
  // STATUS STYLE
  // ==========================================================

  const statusBackground =
    statusType === 'error'
      ? '#FFEBE6'
      : statusType === 'warning'
        ? '#FFFAE6'
        : '#E3FCEF';

  const statusColor =
    statusType === 'error'
      ? '#DE350B'
      : statusType === 'warning'
        ? '#974F0C'
        : '#006644';

  // ==========================================================
  // UI
  // ==========================================================

  return (

    <div
      style={{
        position: 'relative',
        fontFamily:
          '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        padding: '12px',
        color:
          'var(--ds-text, #172B4D)',
        backgroundColor:
          'var(--ds-surface, transparent)',
        minHeight: '180px',
      }}
    >

      {/* =====================================================
          LOADING
      ====================================================== */}

      {loading && (

        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor:
              'var(--ds-surface-overlay, rgba(255,255,255,0.88))',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 999,
            borderRadius: '4px',
            backdropFilter: 'blur(2px)',
          }}
        >

          <div
            style={{
              width: '32px',
              height: '32px',
              border:
                '4px solid var(--ds-border, #DFE1E6)',
              borderTop:
                '4px solid var(--ds-background-brand-bold, #0052CC)',
              borderRadius: '50%',
              animation:
                'spin 0.8s linear infinite',
            }}
          />

          <p
            style={{
              marginTop: '12px',
              fontSize: '13px',
              fontWeight: 600,
              color:
                'var(--ds-text-brand, #0052CC)',
              textAlign: 'center',
            }}
          >
            {loadingText}
          </p>

          <style>
            {`
              @keyframes spin {
                0% {
                  transform: rotate(0deg);
                }

                100% {
                  transform: rotate(360deg);
                }
              }
            `}
          </style>

        </div>
      )}

      {/* =====================================================
          INITIAL STATE
      ====================================================== */}

      {!hasGenerated ? (

        <div
          style={{
            textAlign: 'center',
            padding: '20px 10px',
          }}
        >

          <p
            style={{
              fontSize: '13px',
              color:
                'var(--ds-text-subtle, #5E6C84)',
              marginBottom: '16px',
            }}
          >
            Klik tombol di bawah untuk membuat
            rekomendasi sub-task secara otomatis
            menggunakan AI berdasarkan deskripsi
            issue ini.
          </p>

          <button
            onClick={
              handleGenerateSubtasks
            }
            disabled={
              loading ||
              !issueKey
            }
            style={{
              backgroundColor:
                'var(--ds-background-brand-bold, #0052CC)',
              color:
                'var(--ds-text-on-bold, #FFFFFF)',
              border: 'none',
              padding: '8px 16px',
              borderRadius: '3px',
              fontWeight: 600,
              fontSize: '13px',
              cursor:
                loading || !issueKey
                  ? 'not-allowed'
                  : 'pointer',
            }}
          >
            ✨ Generate Sub-Task Recommendations
          </button>

        </div>

      ) : (

        <>
          {/* =================================================
              HEADER
          ================================================== */}

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent:
                'space-between',
              marginBottom: '12px',
            }}
          >

            <div
              style={{
                fontWeight: 600,
                fontSize: '13px',
                color:
                  'var(--ds-text-subtle, #5E6C84)',
              }}
            >
              RECOMMENDED SUB TASKS ({totalTasks})
            </div>

            <button
              onClick={
                handleGenerateSubtasks
              }
              disabled={loading}
              style={{
                background: 'none',
                border: 'none',
                color:
                  'var(--ds-text-brand, #0052CC)',
                fontSize: '11px',
                cursor:
                  loading
                    ? 'not-allowed'
                    : 'pointer',
                textDecoration:
                  'underline',
              }}
            >
              Regenerate
            </button>

          </div>

          {/* =================================================
              STATUS
          ================================================== */}

          {statusMsg && (

            <div
              style={{
                padding:
                  '8px 10px',
                backgroundColor:
                  statusBackground,
                color:
                  statusColor,
                borderRadius: '3px',
                fontSize: '12px',
                marginBottom: '12px',
              }}
            >
              {statusMsg}
            </div>

          )}

          {/* =================================================
              EMPTY
          ================================================== */}

          {groups.length === 0 ? (

            <div
              style={{
                padding: '16px',
                textAlign: 'center',
                color:
                  'var(--ds-text-subtle, #5E6C84)',
                fontSize: '12px',
              }}
            >
              Tidak ada rekomendasi sub-task.
            </div>

          ) : (

            groups.map(
              (
                group,
                groupIdx
              ) => (

                <div
                  key={
                    group.category ||
                    groupIdx
                  }
                  style={{
                    marginBottom: '16px',
                  }}
                >

                  {/* GROUP HEADER */}

                  <div
                    style={{
                      display: 'flex',
                      justifyContent:
                        'space-between',
                      alignItems:
                        'center',
                      backgroundColor:
                        'var(--ds-background-neutral, #F4F5F7)',
                      padding:
                        '6px 12px',
                      borderRadius:
                        '3px',
                      marginBottom:
                        '8px',
                    }}
                  >

                    <div
                      style={{
                        display: 'flex',
                        alignItems:
                          'center',
                        gap: '8px',
                      }}
                    >

                      <span
                        style={{
                          fontWeight: 700,
                          fontSize: '12px',
                        }}
                      >
                        {group.category}
                      </span>

                      <span
                        style={{
                          fontSize: '11px',
                          color:
                            'var(--ds-text-subtle, #5E6C84)',
                          backgroundColor:
                            'var(--ds-background-neutral-subtle, #EBECF0)',
                          padding:
                            '2px 6px',
                          borderRadius:
                            '3px',
                        }}
                      >
                        {group.tasks?.length || 0}
                        {' '}task
                      </span>

                    </div>

                    <button
                      disabled={
                        loading ||
                        !group.tasks ||
                        group.tasks.length === 0
                      }
                      onClick={() =>
                        handleAddAllCategory(
                          groupIdx
                        )
                      }
                      style={{
                        border: 'none',
                        backgroundColor:
                          loading ||
                          !group.tasks ||
                          group.tasks.length === 0
                            ? 'var(--ds-background-disabled, #C1C7D0)'
                            : 'var(--ds-background-brand-bold, #0052CC)',
                        color:
                          'var(--ds-text-on-bold, #FFFFFF)',
                        fontSize: '11px',
                        fontWeight: 600,
                        padding:
                          '4px 8px',
                        borderRadius:
                          '3px',
                        cursor:
                          loading ||
                          !group.tasks ||
                          group.tasks.length === 0
                            ? 'not-allowed'
                            : 'pointer',
                      }}
                    >
                      Add All ({group.category})
                    </button>

                  </div>

                  {/* TASKS */}

                  <div
                    style={{
                      display: 'flex',
                      flexDirection:
                        'column',
                      gap: '8px',
                      paddingLeft:
                        '4px',
                    }}
                  >

                    {!group.tasks ||
                    group.tasks.length === 0 ? (

                      <span
                        style={{
                          fontSize: '11px',
                          color:
                            'var(--ds-text-success, #00875A)',
                          fontStyle:
                            'italic',
                          paddingLeft:
                            '8px',
                        }}
                      >
                        Semua rekomendasi
                        {' '}
                        {group.category}
                        {' '}
                        sudah ditambahkan.
                      </span>

                    ) : (

                      group.tasks.map(
                        (task) => (

                          <div
                            key={
                              task.id
                            }
                            style={{
                              display: 'flex',
                              alignItems:
                                'center',
                              justifyContent:
                                'space-between',
                              gap: '8px',
                              fontSize:
                                '13px',
                            }}
                          >

                            <div
                              style={{
                                display:
                                  'flex',
                                alignItems:
                                  'center',
                                gap: '10px',
                                minWidth: 0,
                              }}
                            >

                              <span
                                onClick={() =>
                                  handleRemoveTask(
                                    groupIdx,
                                    task.id
                                  )
                                }
                                style={{
                                  color:
                                    'var(--ds-text-danger, #DE350B)',
                                  cursor:
                                    'pointer',
                                  fontWeight:
                                    'bold',
                                  fontSize:
                                    '14px',
                                  width:
                                    '12px',
                                  flexShrink: 0,
                                }}
                                title="Abaikan rekomendasi"
                              >
                                ✕
                              </span>

                              <span
                                style={{
                                  color:
                                    'var(--ds-text, #172B4D)',
                                  wordBreak:
                                    'break-word',
                                }}
                              >
                                {task.text ||
                                  task.summary}
                              </span>

                            </div>

                            <button
                              disabled={
                                loading
                              }
                              onClick={() =>
                                handleAddSingle(
                                  groupIdx,
                                  task
                                )
                              }
                              style={{
                                border:
                                  'none',
                                backgroundColor:
                                  'var(--ds-background-neutral, #DFE1E6)',
                                color:
                                  'var(--ds-text, #42526E)',
                                fontSize:
                                  '10px',
                                fontWeight:
                                  600,
                                padding:
                                  '2px 6px',
                                borderRadius:
                                  '3px',
                                cursor:
                                  loading
                                    ? 'not-allowed'
                                    : 'pointer',
                                flexShrink:
                                  0,
                              }}
                            >
                              + Add
                            </button>

                          </div>

                        )
                      )

                    )}

                  </div>

                </div>

              )
            )

          )}

        </>

      )}

    </div>
  );
}

export default App;