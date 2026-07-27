import React, { useState, useEffect } from 'react';
import { invoke, view } from '@forge/bridge';
import { SquadReport } from './SquadReport';

function App() {
  const [isReportPage, setIsReportPage] = useState(false);
  const [groups, setGroups] = useState([]);
  const [issueKey, setIssueKey] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadingText, setLoadingText] = useState('Memuat rekomendasi...');
  const [statusMsg, setStatusMsg] = useState('');

  useEffect(() => {
    if (view && view.theme) {
      view.theme.enable();
    }

    view.getContext().then((context) => {
      if (context) {
        const isProjectView =
          context.moduleKey === 'squad-report-page' ||
          context.extension?.type === 'jira:projectPage' ||
          !context.extension?.issue;

        if (isProjectView) {
          setIsReportPage(true);
          setLoading(false);
          return;
        }

        if (context.extension?.issue) {
          const key = context.extension.issue.key;
          setIssueKey(key);

          invoke('getRecommendations', { issueKey: key })
            .then((data) => {
              setGroups(data || []);
            })
            .catch((err) => {
              console.error(err);
            })
            .finally(() => {
              setLoading(false);
            });
        } else {
          setLoading(false);
        }
      } else {
        setLoading(false);
      }
    });
  }, []);

  if (isReportPage) {
    return <SquadReport />;
  }

  const totalTasks = groups.reduce((acc, group) => acc + (group.tasks?.length || 0), 0);

  const handleRemoveTask = (groupIndex, taskId) => {
    setGroups((prev) =>
      prev.map((group, gIdx) => {
        if (gIdx !== groupIndex) return group;
        return {
          ...group,
          tasks: group.tasks.filter((t) => t.id !== taskId),
        };
      })
    );
  };

  const handleAddSingle = async (groupIndex, task) => {
    if (!issueKey) return;
    const categoryName = groups[groupIndex].category;
    const prefixedText = `[${categoryName}] ${task.text}`;

    setLoadingText(`Membuat sub-task "${prefixedText}"...`);
    setLoading(true);

    try {
      const res = await invoke('createSubtasks', {
        issueKey,
        subtasks: [prefixedText],
      });

      if (res.success) {
        handleRemoveTask(groupIndex, task.id);
        setStatusMsg(`Sub-task ${categoryName} berhasil ditambahkan! Refresh halaman tiket untuk melihatnya di tabel atas.`);
      } else {
        setStatusMsg('Gagal membuat sub-task.');
      }
    } catch (err) {
      console.error(err);
      setStatusMsg('Terjadi kesalahan koneksi.');
    } finally {
      setLoading(false);
    }
  };

  const handleAddAllCategory = async (groupIndex) => {
    if (!issueKey) return;

    const group = groups[groupIndex];
    if (!group.tasks || group.tasks.length === 0) return;

    setLoadingText(`Validasi & membuat ${group.tasks.length} sub-task ${group.category}...`);
    setLoading(true);

    const subtaskTexts = group.tasks.map((t) => `[${group.category}] ${t.text}`);

    try {
      const res = await invoke('createSubtasks', {
        issueKey,
        subtasks: subtaskTexts,
      });

      if (res.success) {
        setGroups((prev) =>
          prev.map((g, idx) => (idx === groupIndex ? { ...g, tasks: [] } : g))
        );
        setStatusMsg(`Semua sub-task ${group.category} berhasil dibuat! Refresh halaman tiket jika ingin melihat tabel atas terbarui.`);
      } else {
        setStatusMsg('Gagal membuat beberapa sub-task.');
      }
    } catch (err) {
      console.error(err);
      setStatusMsg('Terjadi kesalahan koneksi.');
    } finally {
      setLoading(false);
    }
  };

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
      {/* LOADING OVERLAY */}
      {loading && (
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'var(--ds-surface-overlay, rgba(255, 255, 255, 0.88))',
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
          <p style={{ marginTop: '12px', fontSize: '13px', fontWeight: 600, color: 'var(--ds-text-brand, #0052CC)' }}>
            {loadingText}
          </p>
          <style>{`
            @keyframes spin {
              0% { transform: rotate(0deg); }
              100% { transform: rotate(360deg); }
            }
          `}</style>
        </div>
      )}

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600, fontSize: '13px', color: 'var(--ds-text-subtle, #5E6C84)' }}>
          <span>RECOMMENDED SUB TASKS ({totalTasks})</span>
        </div>
      </div>

      {statusMsg && (
        <div
          style={{
            padding: '6px 10px',
            backgroundColor: 'var(--ds-background-success, #E3FCEF)',
            color: 'var(--ds-text-success, #006644)',
            borderRadius: '3px',
            fontSize: '12px',
            marginBottom: '12px',
          }}
        >
          {statusMsg}
        </div>
      )}

      {/* Groups */}
      {groups.map((group, groupIdx) => (
        <div key={group.category} style={{ marginBottom: '16px' }}>
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
              <span style={{ fontWeight: 700, fontSize: '12px', color: 'var(--ds-text, #172B4D)' }}>{group.category}</span>
              <span
                style={{
                  fontSize: '11px',
                  color: 'var(--ds-text-subtle, #5E6C84)',
                  backgroundColor: 'var(--ds-background-neutral-subtle, #EBECF0)',
                  padding: '2px 6px',
                  borderRadius: '3px',
                }}
              >
                {group.tasks ? group.tasks.length : 0} task
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
                cursor: loading || !group.tasks || group.tasks.length === 0 ? 'not-allowed' : 'pointer',
              }}
            >
              Add All ({group.category})
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', paddingLeft: '4px' }}>
            {!group.tasks || group.tasks.length === 0 ? (
              <span style={{ fontSize: '11px', color: 'var(--ds-text-success, #00875A)', fontStyle: 'italic', paddingLeft: '8px' }}>
                Semua rekomendasi {group.category} sudah ditambahkan!
              </span>
            ) : (
              group.tasks.map((task) => (
                <div key={task.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '13px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span
                      onClick={() => handleRemoveTask(groupIdx, task.id)}
                      style={{ color: 'var(--ds-text-danger, #DE350B)', cursor: 'pointer', fontWeight: 'bold', fontSize: '14px', width: '12px' }}
                      title="Abaikan rekomendasi ini"
                    >
                      ✕
                    </span>
                    <span style={{ color: 'var(--ds-text, #172B4D)' }}>{task.text}</span>
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
                    }}
                  >
                    + Add
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

export default App;