import React, { useState, useEffect } from 'react';
import { invoke, router } from '@forge/bridge';

export default function SubTaskRecommendation({ issueKey }) {
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadingText, setLoadingText] = useState('');
  const [statusMsg, setStatusMsg] = useState('');
  const [statusType, setStatusType] = useState('success');
  const [hasGenerated, setHasGenerated] = useState(false);

  // ==========================================================
  // RESTORE DRAFT FROM LOCALSTORAGE (jika ada rekomendasi
  // yang belum di-approve dari sesi sebelumnya)
  // ==========================================================

  useEffect(() => {
    if (!issueKey) return;

    try {
      const saved = localStorage.getItem(`subtask_recs_${issueKey}`);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) {
          const remaining = parsed.reduce(
            (acc, g) => acc + (Array.isArray(g.tasks) ? g.tasks.length : 0),
            0
          );
          if (remaining > 0) {
            setGroups(parsed);
            setHasGenerated(true);
            console.log('[SubTaskRecommendation] Restored draft recommendations for', issueKey);
          }
        }
      }
    } catch (e) {
      console.warn('[SubTaskRecommendation] Failed to load localStorage cache:', e);
    }
  }, [issueKey]);

  // ==========================================================
  // GENERATE RECOMMENDATIONS
  // ==========================================================

  const handleGenerateSubtasks = async () => {
    if (!issueKey) {
      setStatusType('error');
      setStatusMsg('Issue Jira tidak ditemukan.');
      return;
    }

    console.log('================================');
    console.log('[SubTaskRecommendation] Generate recommendations');
    console.log('[SubTaskRecommendation] Issue:', issueKey);

    setLoadingText('AI sedang menganalisis deskripsi Epic & membuat rekomendasi...');
    setLoading(true);
    setStatusMsg('');
    setStatusType('success');

    try {
      const data = await invoke('getRecommendations', { issueKey });

      console.log('[SubTaskRecommendation] getRecommendations response:', data);

      if (data && typeof data === 'object' && data.success === false) {
        console.warn('[SubTaskRecommendation] AI error:', data);
        setGroups([]);
        setStatusType('error');
        setStatusMsg(data.message || 'Gagal menghasilkan rekomendasi.');
        setHasGenerated(true);
        return;
      }

      if (!Array.isArray(data)) {
        console.error('[SubTaskRecommendation] Response bukan array:', data);
        setGroups([]);
        setStatusType('error');
        setStatusMsg('Format rekomendasi dari backend tidak valid.');
        setHasGenerated(true);
        return;
      }

      setGroups(data);
      setHasGenerated(true);

      // Auto-save draft recommendations to localStorage
      try {
        if (Array.isArray(data) && data.length > 0) {
          localStorage.setItem(`subtask_recs_${issueKey}`, JSON.stringify(data));
        }
      } catch (e) {
        console.warn('[SubTaskRecommendation] Failed to save localStorage cache:', e);
      }

      const total = data.reduce(
        (total, group) => total + (Array.isArray(group.tasks) ? group.tasks.length : 0),
        0
      );

      console.log('[SubTaskRecommendation] Total recommendations:', total);

      if (total === 0) {
        setStatusType('warning');
        setStatusMsg('AI berhasil dipanggil, tetapi tidak menghasilkan rekomendasi baru.');
      } else {
        setStatusType('success');
        setStatusMsg(`${total} rekomendasi sub-task berhasil dibuat oleh AI.`);
      }
    } catch (error) {
      console.error('[SubTaskRecommendation] Generate error:', error);
      setGroups([]);
      setHasGenerated(true);
      setStatusType('error');
      setStatusMsg('Gagal mengambil rekomendasi sub-task dari server.');
    } finally {
      setLoading(false);
      console.log('================================');
    }
  };

  // ==========================================================
  // TOTAL TASKS
  // ==========================================================

  const totalTasks = groups.reduce(
    (acc, group) => acc + (Array.isArray(group.tasks) ? group.tasks.length : 0),
    0
  );

  // ==========================================================
  // REMOVE RECOMMENDATION
  // ==========================================================

  const handleRemoveTask = (groupIndex, taskId) => {
    setGroups((prev) => {
      const nextGroups = prev.map((group, gIdx) => {
        if (gIdx !== groupIndex) return group;
        return {
          ...group,
          tasks: (group.tasks || []).filter((task) => task.id !== taskId),
        };
      });

      // Update localStorage cache
      try {
        const totalRemaining = nextGroups.reduce(
          (acc, g) => acc + (Array.isArray(g.tasks) ? g.tasks.length : 0),
          0
        );
        if (totalRemaining > 0 && issueKey) {
          localStorage.setItem(`subtask_recs_${issueKey}`, JSON.stringify(nextGroups));
        } else if (issueKey) {
          localStorage.removeItem(`subtask_recs_${issueKey}`);
        }
      } catch (e) {}

      return nextGroups;
    });
  };

  // ==========================================================
  // CREATE SINGLE SUBTASK
  // ==========================================================

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
      console.log('[SubTaskRecommendation] Creating single subtask:', taskText);

      const res = await invoke('createSubtasks', {
        issueKey,
        subtasks: [
          {
            text: taskText,
            summary: taskText,
            assigneeName: task.assigneeName || '',
            assigneePn: task.assigneePn || '',
            assigneeRole: task.assigneeRole || '',
            parent_key: task.parent_key || '',
            parent_summary: task.parent_summary || '',
          },
        ],
      });

      console.log('[SubTaskRecommendation] createSubtasks response:', res);

      if (res?.success) {
        handleRemoveTask(groupIndex, task.id);
        setStatusType('success');
        setStatusMsg(`Sub-task "${taskText}" berhasil ditambahkan ke ${issueKey}.`);

        // Tunggu Jira selesai commit issue, lalu reload halaman
        await new Promise((resolve) => setTimeout(resolve, 1000));
        await router.reload();
      } else {
        setStatusType('error');
        setStatusMsg(res?.error || 'Gagal membuat sub-task.');
      }
    } catch (error) {
      console.error('[SubTaskRecommendation] Create single error:', error);
      setStatusType('error');
      setStatusMsg('Terjadi kesalahan saat membuat sub-task.');
    } finally {
      setLoading(false);
    }
  };

  // ==========================================================
  // CREATE ALL CATEGORY
  // ==========================================================

  const handleAddAllCategory = async (groupIndex) => {
    if (!issueKey) return;

    const group = groups[groupIndex];

    if (!group || !Array.isArray(group.tasks) || group.tasks.length === 0) {
      return;
    }

    const tasks = group.tasks;

    setLoadingText(`Membuat ${tasks.length} sub-task ${group.category}...`);
    setLoading(true);
    setStatusMsg('');

    const subtaskPayloads = tasks
      .map((task) => ({
        text: task.text || task.summary || '',
        summary: task.summary || task.text || '',
        assigneeName: task.assigneeName || '',
        assigneePn: task.assigneePn || '',
        assigneeRole: task.assigneeRole || '',
        parent_key: task.parent_key || '',
        parent_summary: task.parent_summary || '',
      }))
      .filter((t) => t.text.trim());

    try {
      console.log('[SubTaskRecommendation] Creating category:', group.category);
      console.log('[SubTaskRecommendation] Tasks with assignees:', subtaskPayloads);

      const res = await invoke('createSubtasks', {
        issueKey,
        subtasks: subtaskPayloads,
      });

      console.log('[SubTaskRecommendation] createSubtasks category response:', res);

      if (res?.success) {
        setGroups((prev) => {
          const nextGroups = prev.map((g, idx) =>
            idx === groupIndex ? { ...g, tasks: [], badgeCount: '0 task' } : g
          );

          // Update localStorage cache
          try {
            const totalRemaining = nextGroups.reduce(
              (acc, g) => acc + (Array.isArray(g.tasks) ? g.tasks.length : 0),
              0
            );
            if (totalRemaining > 0 && issueKey) {
              localStorage.setItem(`subtask_recs_${issueKey}`, JSON.stringify(nextGroups));
            } else if (issueKey) {
              localStorage.removeItem(`subtask_recs_${issueKey}`);
            }
          } catch (e) {}

          return nextGroups;
        });

        const count = Array.isArray(res.createdKeys) ? res.createdKeys.length : 0;

        setStatusType('success');
        setStatusMsg(`${count} sub-task ${group.category} berhasil dibuat di ${issueKey}.`);

        // Tunggu Jira selesai commit issue, lalu reload halaman
        await new Promise((resolve) => setTimeout(resolve, 1000));
        await router.reload();
      } else {
        setStatusType('error');
        setStatusMsg(res?.error || 'Gagal membuat sub-task.');
      }
    } catch (error) {
      console.error('[SubTaskRecommendation] Create category error:', error);
      setStatusType('error');
      setStatusMsg('Terjadi kesalahan saat membuat sub-task.');
    } finally {
      setLoading(false);
    }
  };

  // ==========================================================
  // STATUS STYLE
  // ==========================================================

  const statusBackground =
    statusType === 'error' ? '#FFEBE6' : statusType === 'warning' ? '#FFFAE6' : '#E3FCEF';

  const statusColor =
    statusType === 'error' ? '#DE350B' : statusType === 'warning' ? '#974F0C' : '#006644';

  return (
    <div
      style={{
        position: 'relative',
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        padding: '12px',
        color: 'var(--ds-text, #172B4D)',
        backgroundColor: 'var(--ds-surface, transparent)',
        minHeight: '180px',
      }}
    >
      {/* =====================================================
          LOADING OVERLAY (INTERACTIVE SPINNER)
      ====================================================== */}

      {loading && (
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'var(--ds-surface-overlay, rgba(23, 43, 77, 0.85))',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 999,
            borderRadius: '6px',
            backdropFilter: 'blur(4px)',
            padding: '20px',
          }}
        >
          <div className="spinner-ring" />

          <p
            style={{
              fontSize: '13px',
              fontWeight: 600,
              color: 'var(--ds-text-brand, #579DFF)',
              textAlign: 'center',
              margin: 0,
              maxWidth: '85%',
              lineHeight: 1.4,
            }}
          >
            {loadingText}
          </p>
        </div>
      )}

      {/* =====================================================
          INITIAL STATE
      ====================================================== */}

      {!hasGenerated ? (
        <div style={{ textAlign: 'center', padding: '20px 10px' }}>
          <p
            style={{
              fontSize: '13px',
              color: 'var(--ds-text-subtle, #5E6C84)',
              marginBottom: '16px',
            }}
          >
            Klik tombol di bawah untuk membuat rekomendasi sub-task secara otomatis menggunakan AI
            berdasarkan deskripsi issue ini.
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
              justifyContent: 'space-between',
              marginBottom: '12px',
            }}
          >
            <div
              style={{
                fontWeight: 600,
                fontSize: '13px',
                color: 'var(--ds-text-subtle, #5E6C84)',
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
                cursor: loading ? 'not-allowed' : 'pointer',
                textDecoration: 'underline',
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
                padding: '8px 10px',
                backgroundColor: statusBackground,
                color: statusColor,
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
                padding: '32px 16px',
                textAlign: 'center',
              }}
            >
              <div style={{ fontSize: '28px', marginBottom: '8px' }}>
                {statusType === 'error' ? '⚠️' : '✅'}
              </div>
              <div
                style={{
                  fontSize: '13px',
                  fontWeight: 600,
                  color: 'var(--ds-text, #172B4D)',
                  marginBottom: '4px',
                }}
              >
                {statusType === 'error'
                  ? 'Rekomendasi gagal dibuat'
                  : 'Tidak ada rekomendasi baru'}
              </div>
              <div
                style={{
                  fontSize: '12px',
                  color: 'var(--ds-text-subtle, #5E6C84)',
                  maxWidth: '260px',
                  margin: '0 auto',
                  lineHeight: 1.5,
                }}
              >
                {statusType === 'error'
                  ? 'Terjadi kendala saat memanggil AI. Coba klik Regenerate untuk mencoba lagi.'
                  : 'AI tidak menemukan sub-task tambahan yang relevan untuk issue ini — kemungkinan semua sub-task yang diperlukan sudah ada.'}
              </div>
            </div>
          ) : (
            groups.map((group, groupIdx) => (
              <div key={group.category || groupIdx} style={{ marginBottom: '16px' }}>
                {/* GROUP HEADER */}

                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    backgroundColor: 'var(--ds-background-neutral, #F4F5F7)',
                    padding: '6px 12px',
                    borderRadius: '3px',
                    marginBottom: '8px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontWeight: 700, fontSize: '12px' }}>{group.category}</span>

                    <span
                      style={{
                        fontSize: '11px',
                        color: 'var(--ds-text-subtle, #5E6C84)',
                        backgroundColor: 'var(--ds-background-neutral-subtle, #EBECF0)',
                        padding: '2px 6px',
                        borderRadius: '3px',
                      }}
                    >
                      {group.tasks?.length || 0} task
                    </span>
                  </div>

                  <button
                    disabled={loading || !group.tasks || group.tasks.length === 0}
                    onClick={() => handleAddAllCategory(groupIdx)}
                    style={{
                      border: 'none',
                      backgroundColor:
                        loading || !group.tasks || group.tasks.length === 0
                          ? 'var(--ds-background-disabled, #C1C7D0)'
                          : 'var(--ds-background-brand-bold, #0052CC)',
                      color: 'var(--ds-text-on-bold, #FFFFFF)',
                      fontSize: '11px',
                      fontWeight: 600,
                      padding: '4px 8px',
                      borderRadius: '3px',
                      cursor:
                        loading || !group.tasks || group.tasks.length === 0
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
                    gap: '8px',
                    paddingLeft: '4px',
                  }}
                >
                  {!group.tasks || group.tasks.length === 0 ? (
                    <span
                      style={{
                        fontSize: '11px',
                        color: 'var(--ds-text-success, #00875A)',
                        fontStyle: 'italic',
                        paddingLeft: '8px',
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
                          fontSize: '13px',
                        }}
                      >
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '10px',
                            minWidth: 0,
                          }}
                        >
                          <button
                            onClick={() => handleRemoveTask(groupIdx, task.id)}
                            aria-label={`Abaikan rekomendasi: ${task.text || task.summary}`}
                            title="Abaikan rekomendasi"
                            style={{
                              background: 'none',
                              border: 'none',
                              padding: 0,
                              color: 'var(--ds-text-danger, #DE350B)',
                              cursor: 'pointer',
                              fontWeight: 'bold',
                              fontSize: '14px',
                              width: '16px',
                              height: '16px',
                              flexShrink: 0,
                            }}
                          >
                            ✕
                          </button>

                          <div
                            style={{
                              display: 'flex',
                              flexDirection: 'column',
                              gap: '2px',
                              minWidth: 0,
                            }}
                          >
                            <span
                              style={{
                                color: 'var(--ds-text, #172B4D)',
                                wordBreak: 'break-word',
                              }}
                            >
                              {task.text || task.summary}
                            </span>
                            <div
                              style={{
                                display: 'flex',
                                flexWrap: 'wrap',
                                gap: '8px',
                                alignItems: 'center',
                                marginTop: '2px',
                              }}
                            >
                              {(task.parent_summary ||
                                (task.parent_key && task.parent_key !== issueKey)) && (
                                <span
                                  style={{
                                    fontSize: '11px',
                                    color: 'var(--ds-text-subtle, #6B778C)',
                                    fontWeight: 400,
                                  }}
                                >
                                  Story:{' '}
                                  <strong
                                    style={{
                                      color: 'var(--ds-text, #172B4D)',
                                      fontWeight: 600,
                                    }}
                                  >
                                    {task.parent_key ? `[${task.parent_key}] ` : ''}
                                    {task.parent_summary || task.parent_key}
                                  </strong>
                                </span>
                              )}
                              {task.assigneeName && (
                                <span
                                  style={{
                                    fontSize: '11px',
                                    color: 'var(--ds-text-subtle, #6B778C)',
                                    fontWeight: 400,
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    gap: '3px',
                                  }}
                                >
                                  👤 {task.assigneeName}{' '}
                                  {task.assigneeRole ? `(${task.assigneeRole})` : ''}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>

                        <button
                          disabled={loading}
                          onClick={() => handleAddSingle(groupIdx, task)}
                          style={{
                            border: 'none',
                            backgroundColor: 'var(--ds-background-neutral, #DFE1E6)',
                            color: 'var(--ds-text, #42526E)',
                            fontSize: '10px',
                            fontWeight: 600,
                            padding: '2px 6px',
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
            ))
          )}
        </>
      )}
    </div>
  );
}