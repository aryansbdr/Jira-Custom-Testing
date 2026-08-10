import React, { useState, useEffect, useMemo } from 'react';
import { invoke, view } from '@forge/bridge';
import { SquadReport } from './SquadReport';

const SpinAnimation = () => (
  <style>
    {`
      @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
      }
    `}
  </style>
);

function App() {
  // ==========================================================
  // 1. STATE HOOKS
  // ==========================================================
  const [isReportPage, setIsReportPage] = useState(false);
  const [groups, setGroups] = useState([]);
  const [issueKey, setIssueKey] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadingText, setLoadingText] = useState('Memuat info Epic...');
  const [statusMsg, setStatusMsg] = useState('');
  const [statusType, setStatusType] = useState('success');
  const [hasGenerated, setHasGenerated] = useState(false);
  const [selectedRole, setSelectedRole] = useState('ALL');

  // ==========================================================
  // 2. EFFECT HOOKS
  // ==========================================================
  useEffect(() => {
    async function loadContext() {
      try {
        if (view && view.theme) {
          view.theme.enable();
        }

        const context = await view.getContext();
        console.log("Forge Context", context);

        if (!context) {
          setLoading(false);
          return;
        }

        const isProjectView =
          context.moduleKey === 'custom-reports-with-filter' ||
          context.moduleKey === 'squad-report-page' ||
          context.extension?.type === 'jira:projectPage' ||
          !context.extension?.issue;

        if (isProjectView) {
          setIsReportPage(true);
          setLoading(false);
          return;
        }

        if (context.extension?.issue) {
          setIssueKey(context.extension.issue.key);
          setLoading(false);
          return;
        }

        setLoading(false);
      } catch (error) {
        console.error('[App] Context error:', error);
        setStatusType('error');
        setStatusMsg('Tidak dapat membaca Jira issue context.');
        setLoading(false);
      }
    }

    loadContext();
  }, []);

  // ==========================================================
  // 3. MEMO HOOKS
  // ==========================================================
  const totalTasks = useMemo(() => {
    return groups.reduce(
      (acc, group) => acc + (Array.isArray(group.tasks) ? group.tasks.length : 0),
      0
    );
  }, [groups]);

  const availableRoles = useMemo(() => {
    const rolesFromGroups = groups.map((g) => g.category).filter(Boolean);
    return ['ALL', ...Array.from(new Set(rolesFromGroups))];
  }, [groups]);

  const filteredGroups = useMemo(() => {
    if (selectedRole === 'ALL') return groups;
    return groups.filter(
      (g) => g.category?.toLowerCase() === selectedRole.toLowerCase()
    );
  }, [groups, selectedRole]);

  // ==========================================================
  // 4. HANDLER FUNCTIONS
  // ==========================================================
  const handleGenerateSubtasks = async () => {
    if (!issueKey) {
      setStatusType('error');
      setStatusMsg('Issue Jira tidak ditemukan.');
      return;
    }

    setLoadingText('AI sedang menganalisis deskripsi Epic & membuat rekomendasi...');
    setLoading(true);
    setStatusMsg('');
    setStatusType('success');

    try {
      const data = await invoke('getRecommendations', { issueKey });
      console.log('[App] getRecommendations response:', data);

      if (!Array.isArray(data)) {
        setGroups([]);
        setStatusType('error');
        setStatusMsg('Format rekomendasi dari backend tidak valid.');
        setHasGenerated(true);
        return;
      }

      setGroups(data);
      setHasGenerated(true);

      const total = data.reduce(
        (acc, group) => acc + (Array.isArray(group.tasks) ? group.tasks.length : 0),
        0
      );

      if (total === 0) {
        setStatusType('warning');
        setStatusMsg('AI berhasil dipanggil, tetapi tidak menghasilkan rekomendasi baru.');
      } else {
        setStatusType('success');
        setStatusMsg(`${total} rekomendasi sub-task berhasil dibuat oleh AI.`);
      }
    } catch (error) {
      console.error('[App] Generate error:', error);
      setGroups([]);
      setHasGenerated(true);
      setStatusType('error');
      setStatusMsg('Gagal mengambil rekomendasi sub-task dari server.');
    } finally {
      setLoading(false);
    }
  };

  const handleRemoveTask = (groupIndex, taskId) => {
    setGroups((prev) =>
      prev.map((group, gIdx) => {
        if (gIdx !== groupIndex) return group;
        return {
          ...group,
          tasks: (group.tasks || []).filter((task) => task.id !== taskId),
        };
      })
    );
  };

  const handleAddSingle = async (groupIndex, task) => {
    if (!issueKey) return;

    const taskText = task.text || task.summary || '';
    if (!taskText.trim()) {
      setStatusType('error');
      setStatusMsg('Summary sub-task kosong.');
      return;
    }

    setLoadingText(`Membuat sub-task "${taskText}"...`);
    setLoading(true);
    setStatusMsg('');

    try {
      const res = await invoke('createSubtasks', {
        issueKey,
        subtasks: [taskText],
      });

      if (res?.success) {
        handleRemoveTask(groupIndex, task.id);
        setStatusType('success');
        setStatusMsg(`Sub-task "${taskText}" berhasil ditambahkan ke ${issueKey}.`);
      } else {
        setStatusType('error');
        setStatusMsg(res?.error || 'Gagal membuat sub-task.');
      }
    } catch (error) {
      console.error('[App] Create single error:', error);
      setStatusType('error');
      setStatusMsg('Terjadi kesalahan saat membuat sub-task.');
    } finally {
      setLoading(false);
    }
  };

  const handleAddAllCategory = async (groupIndex) => {
    if (!issueKey) return;

    const group = groups[groupIndex];
    if (!group || !Array.isArray(group.tasks) || group.tasks.length === 0) return;

    const tasks = group.tasks;
    setLoadingText(`Membuat ${tasks.length} sub-task ${group.category}...`);
    setLoading(true);
    setStatusMsg('');

    const subtaskTexts = tasks
      .map((task) => task.text || task.summary || '')
      .filter((text) => text.trim());

    try {
      const res = await invoke('createSubtasks', {
        issueKey,
        subtasks: subtaskTexts,
      });

      if (res?.success) {
        setGroups((prev) =>
          prev.map((g, idx) =>
            idx === groupIndex
              ? { ...g, tasks: [] }
              : g
          )
        );

        const count = Array.isArray(res.createdKeys) ? res.createdKeys.length : 0;
        setStatusType('success');
        setStatusMsg(`${count} sub-task ${group.category} berhasil dibuat di ${issueKey}.`);
      } else {
        setStatusType('error');
        setStatusMsg(res?.error || 'Gagal membuat sub-task.');
      }
    } catch (error) {
      console.error('[App] Create category error:', error);
      setStatusType('error');
      setStatusMsg('Terjadi kesalahan saat membuat sub-task.');
    } finally {
      setLoading(false);
    }
  };

  // ==========================================================
  // 5. CONDITIONAL RENDER (EARLY RETURN)
  // ==========================================================
  if (isReportPage) {
    return <SquadReport />;
  }

  // Dynamic Style untuk Status Message
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
  // 6. MAIN RENDER
  // ==========================================================
  return (
    <div
      style={{
        position: 'relative',
        fontFamily:
          '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        padding: '12px',
        color: 'var(--ds-text, #172B4D)',
        backgroundColor: 'var(--ds-surface, transparent)',
        minHeight: '180px',
      }}
    >
      <SpinAnimation />

      {/* LOADING OVERLAY */}
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
              border: '4px solid var(--ds-border, #DFE1E6)',
              borderTop: '4px solid var(--ds-background-brand-bold, #0052CC)',
              borderRadius: '50%',
              animation: 'spin 0.8s linear infinite',
            }}
          />
          <p
            style={{
              marginTop: '12px',
              fontSize: '13px',
              fontWeight: 600,
              color: 'var(--ds-text-brand, #0052CC)',
              textAlign: 'center',
            }}
          >
            {loadingText}
          </p>
        </div>
      )}

      {/* INITIAL STATE */}
      {!hasGenerated ? (
        <div style={{ textAlign: 'center', padding: '20px 10px' }}>
          <p
            style={{
              fontSize: '13px',
              color: 'var(--ds-text-subtle, #5E6C84)',
              marginBottom: '16px',
            }}
          >
            Klik tombol di bawah untuk membuat rekomendasi sub-task secara
            otomatis menggunakan AI berdasarkan deskripsi issue ini.
          </p>
          <button
            onClick={handleGenerateSubtasks}
            disabled={loading || !issueKey}
            style={{
              backgroundColor: 'var(--ds-background-brand-bold, #0052CC)',
              color: 'var(--ds-text-on-bold, #FFFFFF)',
              border: 'none',
              padding: '8px 16px',
              borderRadius: '3px',
              fontWeight: 600,
              fontSize: '13px',
              cursor: loading || !issueKey ? 'not-allowed' : 'pointer',
              transition: 'background-color 0.2s ease',
            }}
          >
            ✨ Generate Sub-Task Recommendations
          </button>
        </div>
      ) : (
        <>
          {/* HEADER */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '10px',
            }}
          >
            <div
              style={{
                fontWeight: 700,
                fontSize: '12px',
                color: 'var(--ds-text-subtle, #5E6C84)',
                letterSpacing: '0.5px',
              }}
            >
              RECOMMENDED SUB TASKS ({totalTasks})
            </div>

            <button
              onClick={handleGenerateSubtasks}
              disabled={loading}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--ds-text-brand, #0052CC)',
                fontSize: '11px',
                fontWeight: 600,
                cursor: loading ? 'not-allowed' : 'pointer',
                textDecoration: 'none',
              }}
            >
              🔄 Regenerate
            </button>
          </div>

          {/* ROLE TAB FILTERING */}
          {availableRoles.length > 1 && (
            <div
              style={{
                display: 'flex',
                gap: '6px',
                overflowX: 'auto',
                paddingBottom: '8px',
                marginBottom: '12px',
                borderBottom: '1px solid var(--ds-border, #EBECF0)',
              }}
            >
              {availableRoles.map((role) => {
                const isActive = selectedRole === role;
                return (
                  <button
                    key={role}
                    onClick={() => setSelectedRole(role)}
                    style={{
                      border: 'none',
                      backgroundColor: isActive
                        ? 'var(--ds-background-selected, #DEEBFF)'
                        : 'var(--ds-background-neutral-subtle, #F4F5F7)',
                      color: isActive
                        ? 'var(--ds-text-selected, #0747A6)'
                        : 'var(--ds-text-subtle, #5E6C84)',
                      padding: '4px 10px',
                      borderRadius: '12px',
                      fontSize: '11px',
                      fontWeight: isActive ? 700 : 500,
                      cursor: 'pointer',
                      whiteSpace: 'nowrap',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    {role === 'ALL' ? 'Semua Role' : role}
                  </button>
                );
              })}
            </div>
          )}

          {/* STATUS MESSAGE */}
          {statusMsg && (
            <div
              style={{
                padding: '8px 12px',
                backgroundColor: statusBackground,
                color: statusColor,
                borderRadius: '4px',
                fontSize: '12px',
                fontWeight: 500,
                marginBottom: '12px',
              }}
            >
              {statusMsg}
            </div>
          )}

          {/* GROUPS & TASKS LIST */}
          {filteredGroups.length === 0 ? (
            <div
              style={{
                padding: '16px',
                textAlign: 'center',
                color: 'var(--ds-text-subtle, #5E6C84)',
                fontSize: '12px',
              }}
            >
              Tidak ada rekomendasi sub-task untuk role ini.
            </div>
          ) : (
            filteredGroups.map((group, groupIdx) => {
              const originalGroupIdx = groups.findIndex(
                (g) => g.category === group.category
              );
              const activeIndex =
                originalGroupIdx !== -1 ? originalGroupIdx : groupIdx;

              return (
                <div
                  key={`${group.category || 'cat'}-${groupIdx}`}
                  style={{
                    marginBottom: '14px',
                    border: '1px solid var(--ds-border, #EBECF0)',
                    borderRadius: '6px',
                    padding: '8px',
                    backgroundColor: 'var(--ds-surface, #FFFFFF)',
                  }}
                >
                  {/* GROUP HEADER */}
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      backgroundColor: 'var(--ds-background-neutral, #F4F5F7)',
                      padding: '6px 10px',
                      borderRadius: '4px',
                      marginBottom: '8px',
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                      }}
                    >
                      <span
                        style={{
                          fontWeight: 700,
                          fontSize: '12px',
                          color: 'var(--ds-text, #172B4D)',
                        }}
                      >
                        {group.category}
                      </span>

                      <span
                        style={{
                          fontSize: '10px',
                          fontWeight: 600,
                          color: 'var(--ds-text-subtle, #5E6C84)',
                          backgroundColor:
                            'var(--ds-background-neutral-subtle, #EBECF0)',
                          padding: '1px 6px',
                          borderRadius: '10px',
                        }}
                      >
                        {group.tasks?.length || 0} task
                      </span>
                    </div>

                    <button
                      disabled={
                        loading ||
                        !group.tasks ||
                        group.tasks.length === 0
                      }
                      onClick={() => handleAddAllCategory(activeIndex)}
                      style={{
                        border: 'none',
                        backgroundColor:
                          loading ||
                          !group.tasks ||
                          group.tasks.length === 0
                            ? 'var(--ds-background-disabled, #C1C7D0)'
                            : 'var(--ds-background-brand-bold, #0052CC)',
                        color: 'var(--ds-text-on-bold, #FFFFFF)',
                        fontSize: '11px',
                        fontWeight: 600,
                        padding: '4px 8px',
                        borderRadius: '3px',
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
                      flexDirection: 'column',
                      gap: '6px',
                      paddingLeft: '4px',
                      paddingRight: '4px',
                    }}
                  >
                    {!group.tasks || group.tasks.length === 0 ? (
                      <span
                        style={{
                          fontSize: '11px',
                          color: 'var(--ds-text-success, #00875A)',
                          fontStyle: 'italic',
                          padding: '4px 8px',
                        }}
                      >
                        Semua rekomendasi {group.category} sudah ditambahkan.
                      </span>
                    ) : (
                      group.tasks.map((task) => (
                        <div
                          key={task.id}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            gap: '8px',
                            fontSize: '12px',
                            padding: '4px 6px',
                            borderRadius: '3px',
                            backgroundColor:
                              'var(--ds-surface-subtle, transparent)',
                          }}
                        >
                          <div
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: '8px',
                              minWidth: 0,
                            }}
                          >
                            <span
                              onClick={() =>
                                handleRemoveTask(activeIndex, task.id)
                              }
                              style={{
                                color: 'var(--ds-text-danger, #DE350B)',
                                cursor: 'pointer',
                                fontWeight: 'bold',
                                fontSize: '13px',
                                width: '14px',
                                flexShrink: 0,
                                textAlign: 'center',
                              }}
                              title="Abaikan rekomendasi"
                            >
                              ✕
                            </span>

                            <span
                              style={{
                                color: 'var(--ds-text, #172B4D)',
                                wordBreak: 'break-word',
                                lineHeight: '1.4',
                              }}
                            >
                              {task.text || task.summary}
                            </span>
                          </div>

                          <button
                            disabled={loading}
                            onClick={() =>
                              handleAddSingle(activeIndex, task)
                            }
                            style={{
                              border: 'none',
                              backgroundColor:
                                'var(--ds-background-neutral, #DFE1E6)',
                              color: 'var(--ds-text, #42526E)',
                              fontSize: '10px',
                              fontWeight: 600,
                              padding: '3px 8px',
                              borderRadius: '3px',
                              cursor: loading ? 'not-allowed' : 'pointer',
                              flexShrink: 0,
                            }}
                          >
                            + Add
                          </button>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              );
            })
          )}
        </>
      )}
    </div>
  );
}

export default App;