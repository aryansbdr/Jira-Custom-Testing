import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { invoke, view } from '@forge/bridge';
import {
  PieChart,
  Pie,
  ResponsiveContainer,
  Cell
} from 'recharts';

const RADIAN = Math.PI / 180;

// Render label persentase di dalam slice pie chart.
// Slice dengan value 0 tidak diberi label supaya tidak menumpuk di titik yang sama.
function renderPercentLabel({ cx, cy, midAngle, innerRadius, outerRadius, percent, value }) {
  if (!value || percent === 0) return null;

  const radius = innerRadius + (outerRadius - innerRadius) * 0.5;
  const x = cx + radius * Math.cos(-midAngle * RADIAN);
  const y = cy + radius * Math.sin(-midAngle * RADIAN);

  return (
    <text
      x={x}
      y={y}
      fill="#FFFFFF"
      textAnchor="middle"
      dominantBaseline="central"
      fontSize={11}
      fontWeight={700}
      style={{ pointerEvents: 'none' }}
    >
      {`${Math.round(percent * 100)}%`}
    </text>
  );
}

function downloadBase64File(base64Data, fileName, mimeType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') {
  const byteCharacters = atob(base64Data);
  const byteNumbers = new Array(byteCharacters.length);
  for (let i = 0; i < byteCharacters.length; i++) {
    byteNumbers[i] = byteCharacters.charCodeAt(i);
  }
  const byteArray = new Uint8Array(byteNumbers);
  const blob = new Blob([byteArray], { type: mimeType });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}

// Avatar color generator based on name
function getAvatarColor(name = '') {
  const colors = ['#0052CC', '#00875A', '#6554C0', '#FF5630', '#FFAB00', '#00B8D9', '#36B37E'];
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return colors[Math.abs(hash) % colors.length];
}

function getInitials(name = '') {
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return (name[0] || 'U').toUpperCase();
}

export function SquadReport() {
  const [currentProjectKey, setCurrentProjectKey] = useState('JT');
  const [epics, setEpics] = useState([]);
  const [selectedEpicKey, setSelectedEpicKey] = useState('');
  const [stories, setStories] = useState([]);
  const [selectedStoryKey, setSelectedStoryKey] = useState('ALL');
  const [epicDetails, setEpicDetails] = useState(null);

  const [loadingEpics, setLoadingEpics] = useState(true);
  const [loadingStories, setLoadingStories] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState('');
  const [successNotice, setSuccessNotice] = useState('');

  // Pagination for bottom-right table
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 10;

  const loadEpics = useCallback(async (projKey) => {
    try {
      setLoadingEpics(true);
      setError('');
      const keyToUse = projKey || currentProjectKey;
      const res = await invoke('getProjectEpics', { projectKey: keyToUse });
      const fetchedEpics = res?.epics || [];
      setEpics(fetchedEpics);
      if (fetchedEpics.length > 0) {
        setSelectedEpicKey(fetchedEpics[0].key);
      } else {
        setSelectedEpicKey('');
        setStories([]);
        setEpicDetails(null);
      }
    } catch (err) {
      console.error('[SquadReport] Error loading Epics:', err);
      setError(err?.message || 'Gagal memuat daftar Epic.');
    } finally {
      setLoadingEpics(false);
    }
  }, [currentProjectKey]);

  const loadStoriesForEpic = useCallback(async (epicKey, projKey) => {
    if (!epicKey) {
      setStories([]);
      setEpicDetails(null);
      return;
    }
    try {
      setLoadingStories(true);
      setError('');
      const res = await invoke('getEpicStoryDetails', {
        epicKey: epicKey,
        projectKey: projKey || currentProjectKey
      });
      setStories(res?.stories || []);
      setEpicDetails(res?.epicDetails || null);
      setSelectedStoryKey('ALL');
      setCurrentPage(1);
    } catch (err) {
      console.error('[SquadReport] Error loading Stories:', err);
      setError(err?.message || 'Gagal memuat Story untuk Epic terpilih.');
    } finally {
      setLoadingStories(false);
    }
  }, [currentProjectKey]);

  useEffect(() => {
    async function init() {
      let pKey = 'JT';
      try {
        if (view) {
          if (view.theme) await view.theme.enable();
          const context = await view.getContext();
          const keyFromContext = context?.extension?.project?.key;
          if (keyFromContext) {
            pKey = keyFromContext;
            setCurrentProjectKey(pKey);
          }
        }
      } catch (err) {
        console.warn('[SquadReport] Error getting Jira context:', err);
      }
      await loadEpics(pKey);
    }
    init();
  }, [loadEpics]);

  useEffect(() => {
    if (selectedEpicKey) {
      loadStoriesForEpic(selectedEpicKey, currentProjectKey);
    }
  }, [selectedEpicKey, loadStoriesForEpic, currentProjectKey]);

  const displayedStories = useMemo(() => {
    if (selectedStoryKey === 'ALL') return stories;
    return stories.filter((s) => s.key === selectedStoryKey);
  }, [stories, selectedStoryKey]);

  // Aggregate Metrics for Sprint & Health Gadgets
  const metrics = useMemo(() => {
    let totalSubtasks = 0;
    let todoCount = 0;
    let inProgressCount = 0;
    let doneCount = 0;
    const allTableItems = [];
    const memberMap = {};

    displayedStories.forEach((story) => {
      // Add parent story to table items
      allTableItems.push({
        type: story.typeName || 'Story',
        key: story.key,
        summary: story.summary,
        status: story.status || 'To Do',
        assignee: 'Story Parent',
        role: 'Parent',
        iconUrl: story.iconUrl || ''
      });

      // Add subtasks
      (story.subtasks || []).forEach((sub) => {
        totalSubtasks++;
        const stLower = String(sub.status || '').toLowerCase().trim();
        let statusNorm = 'To Do';
        if (stLower === 'done' || stLower === 'closed' || stLower === 'resolved' || stLower === 'complete') {
          doneCount++;
          statusNorm = 'Done';
        } else if (stLower === 'to do' || stLower === 'todo' || stLower === 'backlog') {
          todoCount++;
          statusNorm = 'To Do';
        } else {
          inProgressCount++;
          statusNorm = 'In Progress';
        }

        const assigneeName = (sub.assignee || 'Unassigned').trim();
        if (assigneeName.toLowerCase() !== 'unassigned') {
          if (!memberMap[assigneeName]) {
            memberMap[assigneeName] = {
              name: assigneeName,
              role: sub.role || 'Developer',
              todo: 0,
              inProgress: 0,
              done: 0,
              total: 0
            };
          }
          if (statusNorm === 'Done') memberMap[assigneeName].done++;
          else if (statusNorm === 'In Progress') memberMap[assigneeName].inProgress++;
          else memberMap[assigneeName].todo++;
          memberMap[assigneeName].total++;
        }

        allTableItems.push({
          type: sub.typeName || 'Sub-task',
          key: sub.key || `${story.key}-sub`,
          summary: sub.summary,
          status: sub.status || 'To Do',
          assignee: assigneeName,
          role: sub.role || 'Developer',
          iconUrl: sub.iconUrl || ''
        });
      });
    });

    const percentDone = totalSubtasks > 0 ? Math.round((doneCount / totalSubtasks) * 100) : 0;
    const memberList = Object.values(memberMap);

    return {
      totalStories: displayedStories.length,
      totalSubtasks,
      todoCount,
      inProgressCount,
      doneCount,
      percentDone,
      allTableItems,
      memberList
    };
  }, [displayedStories]);

  // Chart Data for Workload Activity Chart
  const chartData = useMemo(() => {
    if (metrics.memberList.length > 0) {
      return metrics.memberList.map((m) => ({
        name: m.name.split(' ')[0],
        fullName: m.name,
        'To Do': m.todo,
        'In Progress': m.inProgress,
        Done: m.done,
        Total: m.total
      }));
    }
    return [
      { name: 'To Do', 'To Do': metrics.todoCount },
      { name: 'In Progress', 'In Progress': metrics.inProgressCount },
      { name: 'Done', Done: metrics.doneCount }
    ];
  }, [metrics]);

  const memberPieCharts = metrics.memberList.map((member) => ({
    name: member.name,
    data: [
    { name: 'To Do', value: member.todo, color: '#7A869A' },
    { name: 'In Progress', value: member.inProgress, color: '#579DFF' },
    { name: 'Done', value: member.done, color: '#36B37E' }
  ]
  }))

  // Pagination slice
  const paginatedItems = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return metrics.allTableItems.slice(start, start + pageSize);
  }, [metrics.allTableItems, currentPage]);

  const totalPages = Math.ceil(metrics.allTableItems.length / pageSize) || 1;

  const currentEpicObj = epics.find((e) => e.key === selectedEpicKey);

  // Menentukan kode & judul yang ditampilkan di gadget:
  // - Jika user memilih salah satu Story, tampilkan kode & summary Story tersebut
  // - Jika "ALL" (belum memilih story spesifik), tampilkan kode & summary Epic
  const currentSelectionInfo = useMemo(() => {
    if (selectedStoryKey !== 'ALL') {
      const selectedStory = stories.find((s) => s.key === selectedStoryKey);
      if (selectedStory) {
        return {
          key: selectedStory.key,
          title: selectedStory.summary || selectedStory.key
        };
      }
    }
    return {
      key: selectedEpicKey,
      title: currentEpicObj ? currentEpicObj.summary : selectedEpicKey
    };
  }, [selectedStoryKey, stories, selectedEpicKey, currentEpicObj]);


  // Dynamic Sprint & Date Calculations
  const sprintInfo = useMemo(() => {
    const today = new Date();
    let start = epicDetails?.startDate ? new Date(epicDetails.startDate) : null;
    let end = epicDetails?.endDate ? new Date(epicDetails.endDate) : (epicDetails?.duedate ? new Date(epicDetails.duedate) : null);

    // If no explicit dates set in Jira, fallback to a sensible 1-month sprint cycle (start of month to end of month)
    if (!start || isNaN(start.getTime())) {
      start = new Date(today.getFullYear(), today.getMonth(), 1);
    }
    if (!end || isNaN(end.getTime())) {
      end = new Date(today.getFullYear(), today.getMonth() + 1, 0);
    }

    const totalDays = Math.max(1, Math.ceil((end - start) / (1000 * 60 * 60 * 24)));
    const daysElapsed = Math.max(0, Math.ceil((today - start) / (1000 * 60 * 60 * 24)));
    const daysRemaining = Math.max(0, Math.ceil((end - today) / (1000 * 60 * 60 * 24)));
    const timeElapsedPercent = Math.min(100, Math.max(0, Math.round((daysElapsed / totalDays) * 100)));

    let status = 'On Track';
    let statusColor = '#36B37E';
    if (daysRemaining <= 0) {
      status = 'Overdue';
      statusColor = '#FF5630';
    } else if (timeElapsedPercent > metrics.percentDone + 25) {
      status = 'At Risk';
      statusColor = '#FFAB00';
    } else if (metrics.percentDone >= timeElapsedPercent) {
      status = 'Ahead';
      statusColor = '#36B37E';
    }

    const formatDate = (d) => {
      if (!d || isNaN(d.getTime())) return '-';
      const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      return `${String(d.getDate()).padStart(2, '0')} ${months[d.getMonth()]} ${d.getFullYear()}`;
    };

    return {
      sprintName: epicDetails?.sprintName || `Sprint Aktif - ${currentEpicObj?.summary || 'Siklus Pengerjaan'}`,
      startDateStr: formatDate(start),
      dueDateStr: formatDate(end),
      daysRemaining,
      daysElapsed,
      totalDays,
      timeElapsedPercent,
      status,
      statusColor
    };
  }, [epicDetails, currentEpicObj, metrics.percentDone]);

  // Export to Excel via Python Backend
  const exportToExcelWithPython = async () => {
    if (!displayedStories || displayedStories.length === 0) {
      alert('Tidak ada data Story/Task pada Epic ini untuk diexport.');
      return;
    }
    try {
      setIsExporting(true);
      setError('');
      setSuccessNotice('');

      const epicSummary = currentEpicObj ? currentEpicObj.summary : selectedEpicKey;

      // Construct story_progress per parent story
      const storyProgressData = displayedStories.map((story) => {
        let sTodo = 0, sProg = 0, sDone = 0;
        (story.subtasks || []).forEach((st) => {
          const stL = String(st.status || '').toLowerCase();
          if (['done', 'closed', 'resolved', 'complete'].some((k) => stL.includes(k))) sDone++;
          else if (['in progress', 'in development', 'in review', 'progress'].some((k) => stL.includes(k))) sProg++;
          else sTodo++;
        });
        const sTotal = (story.subtasks || []).length;
        return {
          key: story.key,
          summary: story.summary,
          owner: story.assignee || 'Story Parent',
          todo: sTodo,
          in_progress: sProg,
          done: sDone,
          total_subtasks: sTotal,
          percent_done: sTotal > 0 ? Math.round((sDone / sTotal) * 100) : 0
        };
      });

      // Construct detailed_subtasks with parent information
      const detailedSubtasksData = displayedStories.flatMap((story) =>
        (story.subtasks || []).map((sub) => ({
          key: sub.key,
          summary: sub.summary,
          parent_key: story.key,
          parent_summary: story.summary,
          assignee: sub.assignee || 'Unassigned',
          role: sub.role || 'Developer',
          status: sub.status || 'To Do'
        }))
      );

      const exportPayload = {
        root_key: selectedEpicKey || currentProjectKey,
        root_summary: epicSummary,
        total_epics_count: epics.length || displayedStories.length,
        overall_status: {
          total: metrics.totalSubtasks,
          todo: metrics.todoCount,
          in_progress: metrics.inProgressCount,
          done: metrics.doneCount,
          percent_done: metrics.percentDone
        },
        member_progress: metrics.memberList.map((m) => ({
          name: m.name,
          role: m.role,
          todo: m.todo,
          in_progress: m.inProgress,
          done: m.done,
          total_subtasks: m.total,
          percent_done: m.total > 0 ? Math.round((m.done / m.total) * 100) : 0
        })),
        story_progress: storyProgressData,
        stories: displayedStories,
        detailed_subtasks: detailedSubtasksData,
        sprint_info: {
          name: sprintInfo.sprintName || selectedEpicKey,
          days_remaining: sprintInfo.daysRemaining,
          start_date: sprintInfo.startDateStr,
          end_date: sprintInfo.dueDateStr,
          status: sprintInfo.status,
          time_elapsed_percent: sprintInfo.timeElapsedPercent
        }
      };

      const res = await invoke('exportExcelReport', exportPayload);
      if (res?.success && res?.base64) {
        downloadBase64File(res.base64, res.filename || `Laporan_Progress_${selectedEpicKey}.xlsx`);
        setSuccessNotice(`Laporan Excel berhasil diunduh: ${res.filename}`);
      } else {
        throw new Error(res?.error || 'Gagal menerima file Excel dari backend.');
      }
    } catch (err) {
      console.error('[SquadReport] Export error:', err);
      setError(`Gagal export Excel: ${err.message}`);
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div
      style={{
        padding: '20px',
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        backgroundColor: 'var(--ds-surface, #1D2125)',
        color: 'var(--ds-text, #DCDFE4)',
        minHeight: '100vh',
        boxSizing: 'border-box'
      }}
    >
      {/* -------------------------------------------------------------
          TOP BAR: TITLE, DROPDOWNS, & EXPORT BUTTON
      -------------------------------------------------------------- */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          flexWrap: 'wrap',
          gap: '16px',
          backgroundColor: 'var(--ds-surface-overlay, #22272B)',
          padding: '16px 20px',
          borderRadius: '8px',
          border: '1px solid var(--ds-border, #333C48)',
          boxShadow: '0 1px 3px rgba(0, 0, 0, 0.25)',
          marginBottom: '20px'
        }}
      >
        <div style={{ flex: '1 1 280px', minWidth: 0 }}>
          <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 'bold', color: 'var(--ds-text, #DCDFE4)' }}>
            {currentEpicObj ? `[${currentEpicObj.key}] ${currentEpicObj.summary}` : 'Sprint & Squad Health Overview'}
          </h2>
          <p style={{ margin: '4px 0 0 0', fontSize: '12px', color: 'var(--ds-text-subtle, #8C9BAB)' }}>
            Executive Dashboard • Project: <strong>{currentProjectKey}</strong> • Sisa Waktu Sprint & Status Beban Tim
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap', flex: '0 0 auto' }}>
          {/* Epic Selector */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <label htmlFor="epic-top-select" style={{ fontSize: '12px', fontWeight: 600, color: 'var(--ds-text-subtle, #8C9BAB)' }}>
              Epic:
            </label>
            <select
              id="epic-top-select"
              value={selectedEpicKey}
              onChange={(e) => setSelectedEpicKey(e.target.value)}
              disabled={loadingEpics || epics.length === 0}
              style={{
                padding: '6px 12px',
                borderRadius: '4px',
                border: '1px solid var(--ds-border, #3B444C)',
                backgroundColor: 'var(--ds-surface-raised, #282E33)',
                color: 'var(--ds-text, #DCDFE4)',
                fontSize: '13px',
                fontWeight: 500,
                maxWidth: '240px',
                outline: 'none'
              }}
            >
              {epics.map((e) => (
                <option key={e.key} value={e.key} style={{ backgroundColor: '#22272B', color: '#DCDFE4' }}>
                  [{e.key}] {e.summary}
                </option>
              ))}
            </select>
          </div>

          {/* Story Selector */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <label htmlFor="story-top-select" style={{ fontSize: '12px', fontWeight: 600, color: 'var(--ds-text-subtle, #8C9BAB)' }}>
              Story/Task:
            </label>
            <select
              id="story-top-select"
              value={selectedStoryKey}
              onChange={(e) => setSelectedStoryKey(e.target.value)}
              disabled={loadingStories || stories.length === 0}
              style={{
                padding: '6px 12px',
                borderRadius: '4px',
                border: '1px solid var(--ds-border, #3B444C)',
                backgroundColor: 'var(--ds-surface-raised, #282E33)',
                color: 'var(--ds-text, #DCDFE4)',
                fontSize: '13px',
                fontWeight: 500,
                maxWidth: '220px',
                outline: 'none'
              }}
            >
              <option value="ALL" style={{ backgroundColor: '#22272B', color: '#DCDFE4' }}>Semua Story/Task ({stories.length})</option>
              {stories.map((s) => (
                <option key={s.key} value={s.key} style={{ backgroundColor: '#22272B', color: '#DCDFE4' }}>
                  [{s.key}] {s.summary}
                </option>
              ))}
            </select>
          </div>

          {/* Export Excel Button */}
          <button
            onClick={exportToExcelWithPython}
            disabled={displayedStories.length === 0 || isExporting}
            style={{
              backgroundColor: '#217346',
              color: '#FFFFFF',
              border: 'none',
              borderRadius: '4px',
              padding: '8px 16px',
              fontWeight: 600,
              fontSize: '13px',
              cursor: (displayedStories.length === 0 || isExporting) ? 'not-allowed' : 'pointer',
              opacity: (displayedStories.length === 0 || isExporting) ? 0.6 : 1,
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              boxShadow: '0 2px 4px rgba(33, 115, 70, 0.35)'
            }}
          >
            {isExporting ? '⏳ Mengenerate...' : 'Export to Excel (.xlsx)'}
          </button>
        </div>
      </div>

      {/* Alerts */}
      {error && (
        <div style={{ padding: '10px 14px', backgroundColor: 'rgba(222, 53, 11, 0.2)', color: '#FF8F73', border: '1px solid #DE350B', borderRadius: '4px', marginBottom: '16px', fontSize: '13px' }}>
          ⚠️ {error}
        </div>
      )}
      {successNotice && (
        <div style={{ padding: '10px 14px', backgroundColor: 'rgba(0, 135, 90, 0.2)', color: '#7EE2B8', border: '1px solid #00875A', borderRadius: '4px', marginBottom: '16px', fontSize: '13px' }}>
          ✅ {successNotice}
        </div>
      )}

      {/* -------------------------------------------------------------
          2-COLUMN EXECUTIVE GADGET GRID
      -------------------------------------------------------------- */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(480px, 1fr))',
          gap: '20px'
        }}
      >
        {/* =========================================================
            GADGET 1 (TOP LEFT): DAYS REMAINING IN SPRINT
        ========================================================== */}
        <div
          style={{
            backgroundColor: 'var(--ds-surface-overlay, #22272B)',
            border: '1px solid var(--ds-border, #333C48)',
            borderRadius: '6px',
            overflow: 'hidden',
            boxShadow: '0 1px 3px rgba(0, 0, 0, 0.25)'
          }}
        >
          {/* Blue Header Banner */}
          <div style={{ backgroundColor: '#0747A6', padding: '8px 14px', color: '#FFFFFF', fontSize: '12px', fontWeight: 600, display: 'flex', justifyContent: 'space-between' }}>
            <span>Days Remaining in Sprint Gadget</span>
            <span>•••</span>
          </div>

          <div style={{ padding: '18px 20px' }}>
            <div style={{ fontSize: '14px', fontWeight: 'bold', color: 'var(--ds-text-brand, #579DFF)' }}>{currentProjectKey} - {currentSelectionInfo.key}</div>
            <div style={{ fontSize: '12px', color: 'var(--ds-text-subtle, #8C9BAB)', marginBottom: '16px' }}>{sprintInfo.sprintName}</div>

            <div
              style={{
                backgroundColor: 'var(--ds-background-neutral-subtle, #161A1D)',
                borderRadius: '8px',
                padding: '24px 20px',
                textAlign: 'center',
                maxWidth: '240px',
                margin: '0 auto'
              }}
            >
              <div style={{ fontSize: '56px', fontWeight: 'bold', color: sprintInfo.statusColor, lineHeight: 1 }}>
                {sprintInfo.daysRemaining}
              </div>
              <div style={{ fontSize: '14px', fontWeight: 600, color: sprintInfo.statusColor, marginTop: '8px' }}>
                Days Remaining
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-around', marginTop: '18px', paddingTop: '12px', borderTop: '1px solid var(--ds-border, #2C333A)', fontSize: '12px', color: 'var(--ds-text-subtle, #8C9BAB)' }}>
              <div>Start: <strong style={{ color: 'var(--ds-text, #DCDFE4)' }}>{sprintInfo.startDateStr}</strong></div>
              <div>Due: <strong style={{ color: 'var(--ds-text, #DCDFE4)' }}>{sprintInfo.dueDateStr}</strong></div>
              <div>Status: <strong style={{ color: sprintInfo.statusColor }}>{sprintInfo.status}</strong></div>
            </div>
          </div>
        </div>

        {/* =========================================================
            GADGET 2 (TOP RIGHT): SPRINT HEALTH GADGET
        ========================================================== */}
        <div
          style={{
            backgroundColor: 'var(--ds-surface-overlay, #22272B)',
            border: '1px solid var(--ds-border, #333C48)',
            borderRadius: '6px',
            overflow: 'hidden',
            boxShadow: '0 1px 3px rgba(0, 0, 0, 0.25)'
          }}
        >
          {/* Blue Header Banner */}
          <div style={{ backgroundColor: '#0747A6', padding: '8px 14px', color: '#FFFFFF', fontSize: '12px', fontWeight: 600, display: 'flex', justifyContent: 'space-between' }}>
            <span>Sprint Health Gadget</span>
            <span>•••</span>
          </div>

          <div style={{ padding: '16px 20px' }}>
            <div style={{ fontSize: '14px', fontWeight: 'bold', color: 'var(--ds-text, #DCDFE4)', marginBottom: '14px' }}>
              Sprint Health - {currentSelectionInfo.key || currentProjectKey}
            </div>

            {/* Overall Sprint Progress Bar */}
            <div style={{ marginBottom: '16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: 'var(--ds-text-subtle, #8C9BAB)', marginBottom: '6px' }}>
                <span>Overall sprint progress (Subtask Completion)</span>
                <span><strong style={{ color: 'var(--ds-text, #DCDFE4)' }}>{metrics.totalSubtasks} Subtasks</strong> ({metrics.percentDone}%)</span>
              </div>
              <div style={{ width: '100%', height: '14px', backgroundColor: 'var(--ds-background-neutral, #161A1D)', borderRadius: '7px', overflow: 'hidden', display: 'flex' }}>
                <div style={{ width: `${metrics.percentDone}%`, backgroundColor: '#0052CC', transition: 'width 0.3s' }} />
                <div style={{ width: `${metrics.totalSubtasks > 0 ? (metrics.inProgressCount / metrics.totalSubtasks) * 100 : 0}%`, backgroundColor: '#00B8D9' }} />
              </div>
              <div style={{ textAlign: 'right', fontSize: '11px', color: 'var(--ds-text-subtle, #8C9BAB)', marginTop: '4px' }}>
                {sprintInfo.daysRemaining} days left
              </div>
            </div>

            {/* 4 Metric Stats Cards */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(4, 1fr)',
                gap: '8px',
                textAlign: 'center',
                marginBottom: '16px',
                paddingBottom: '12px',
                borderBottom: '1px solid var(--ds-border, #2C333A)'
              }}
            >
              <div>
                <div style={{ fontSize: '18px', fontWeight: 'bold', color: 'var(--ds-text, #DCDFE4)' }}>{sprintInfo.timeElapsedPercent}%</div>
                <div style={{ fontSize: '11px', color: 'var(--ds-text-subtle, #8C9BAB)' }}>Time elapsed</div>
              </div>
              <div>
                <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#36B37E' }}>{metrics.percentDone}%</div>
                <div style={{ fontSize: '11px', color: 'var(--ds-text-subtle, #8C9BAB)' }}>Work complete</div>
              </div>
              <div>
                <div style={{ fontSize: '18px', fontWeight: 'bold', color: 'var(--ds-text, #DCDFE4)' }}>0%</div>
                <div style={{ fontSize: '11px', color: 'var(--ds-text-subtle, #8C9BAB)' }}>Scope change</div>
              </div>
              <div>
                <div style={{ fontSize: '18px', fontWeight: 'bold', color: 'var(--ds-text-subtle, #8C9BAB)' }}>0</div>
                <div style={{ fontSize: '11px', color: 'var(--ds-text-subtle, #8C9BAB)' }}>Flagged / Blocked</div>
              </div>
            </div>

            {/* Assignees in Sprint (Avatars) */}
            <div>
              <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--ds-text-subtle, #8C9BAB)', marginBottom: '8px' }}>
                Assignees in Sprint ({metrics.memberList.length} Developers):
              </div>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
                {metrics.memberList.length === 0 && (
                  <span style={{ fontSize: '12px', color: 'var(--ds-text-subtle, #8C9BAB)', fontStyle: 'italic' }}>Belum ada assignee terdaftar.</span>
                )}
                {metrics.memberList.map((m) => (
                  <div
                    key={m.name}
                    title={`${m.name} (${m.role}) • ${m.total} Subtasks (${m.done} Selesai)`}
                    style={{
                      width: '32px',
                      height: '32px',
                      borderRadius: '50%',
                      backgroundColor: getAvatarColor(m.name),
                      color: '#FFFFFF',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '11px',
                      fontWeight: 'bold',
                      cursor: 'pointer',
                      boxShadow: '0 1px 2px rgba(0,0,0,0.3)'
                    }}
                  >
                    {getInitials(m.name)}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* =========================================================
            GADGET 3 (BOTTOM LEFT): WORKLOAD & PROGRESS BAR CHART
        ========================================================== */}
        <div
          style={{
            backgroundColor: 'var(--ds-surface-overlay, #22272B)',
            border: '1px solid var(--ds-border, #333C48)',
            borderRadius: '6px',
            overflow: 'hidden',
            boxShadow: '0 1px 3px rgba(0, 0, 0, 0.25)'
          }}
        >
          {/* Blue Header Banner */}
          <div style={{ backgroundColor: '#0747A6', padding: '8px 14px', color: '#FFFFFF', fontSize: '12px', fontWeight: 600, display: 'flex', justifyContent: 'space-between' }}>
            <span>Workload & Progress Activity Chart</span>
            <span>•••</span>
          </div>

          <div style={{ padding: '16px 20px' }}>
            <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--ds-text, #DCDFE4)', marginBottom: '4px' }}>
              Distribusi Subtask Per Developer (To Do, In Progress, Done)
            </div>
            <div style={{ fontSize: '11px', color: 'var(--ds-text-subtle, #8C9BAB)', marginBottom: '14px' }}>
              Monitoring beban kerja dan progres riil anggota tim pada sprint aktif.
            </div>

            <div style={{ width: '100%' }}>
              {memberPieCharts.length === 0 ? (
                <div style={{ color: '#8C9BAB', fontStyle: 'italic' }}>
                  Belum ada assignee terdaftar.
                </div>
              ) : (
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: '16px',
            }}
          >
            {memberPieCharts.map((person) => (
              <div
                key={person.name}
                style={{
                  backgroundColor: 'rgba(255,255,255,0.02)',
                  border: '1px solid #333C48',
                  borderRadius: '8px',
                  padding: '10px',
                }}
              >
                <div
                  style={{
                    textAlign: 'center',
                    fontSize: '12px',
                    fontWeight: 600,
                    color: '#DCDFE4',
                    marginBottom: '8px',
                  }}
                >
                  {person.name}
                </div>

                <div style={{ width: '100%', height: 170 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={person.data}
                        dataKey="value"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        outerRadius={58}
                        paddingAngle={2}
                        label={renderPercentLabel}
                        labelLine={false}
                      >
                        {person.data.map((entry, index) => (
                          <Cell key={`${person.name}-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                </div>

                <div
                  style={{
                    marginTop: '8px',
                    display: 'grid',
                    gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
                    gap: '6px',
                  }}
                >
                  {person.data.map((entry) => (
                    <div
                      key={`${person.name}-${entry.name}-stat`}
                      style={{
                        textAlign: 'center',
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: '4px',
                          marginBottom: '2px',
                        }}
                      >
                        <span
                          style={{
                            width: '8px',
                            height: '8px',
                            borderRadius: '50%',
                            backgroundColor: entry.color,
                            display: 'inline-block',
                          }}
                        />
                        <span style={{ fontSize: '10px', color: '#8C9BAB' }}>
                          {entry.name}
                        </span>
                      </div>
                      <div style={{ fontSize: '13px', fontWeight: 700, color: '#DCDFE4' }}>
                        {entry.value}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
          </div>
        </div>

        {/* =========================================================
            GADGET 4 (BOTTOM RIGHT): FILTER RESULTS / ISSUE LIST TABLE
        ========================================================== */}
        <div
          style={{
            backgroundColor: 'var(--ds-surface-overlay, #22272B)',
            border: '1px solid var(--ds-border, #333C48)',
            borderRadius: '6px',
            overflow: 'hidden',
            boxShadow: '0 1px 3px rgba(0, 0, 0, 0.25)',
            display: 'flex',
            flexDirection: 'column'
          }}
        >
          {/* Blue Header Banner */}
          <div style={{ backgroundColor: '#0747A6', padding: '8px 14px', color: '#FFFFFF', fontSize: '12px', fontWeight: 600, display: 'flex', justifyContent: 'space-between' }}>
            <span>Filter Results: Story & Subtask Monitor</span>
            <span>•••</span>
          </div>

          <div style={{ padding: '14px 16px', flex: 1, display: 'flex', flexDirection: 'column' }}>
            <div style={{ overflowX: 'auto', flex: 1 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid var(--ds-border, #333C48)', color: 'var(--ds-text-subtle, #8C9BAB)', textAlign: 'left' }}>
                    <th style={{ padding: '8px 8px', width: '28px' }}>T</th>
                    <th style={{ padding: '8px 8px', width: '80px' }}>Key</th>
                    <th style={{ padding: '8px 8px' }}>Summary</th>
                    <th style={{ padding: '8px 8px', width: '110px' }}>Assignee</th>
                    <th style={{ padding: '8px 8px', width: '85px', textAlign: 'right' }}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedItems.length === 0 ? (
                    <tr>
                      <td colSpan={5} style={{ padding: '24px', textAlign: 'center', color: 'var(--ds-text-subtle, #8C9BAB)', fontStyle: 'italic' }}>
                        Tidak ada tiket ditemukan.
                      </td>
                    </tr>
                  ) : (
                    paginatedItems.map((item, idx) => {
                      const isDone = ['done', 'closed', 'resolved', 'complete'].includes(String(item.status).toLowerCase());
                      const isProg = ['in progress', 'in development', 'in review'].includes(String(item.status).toLowerCase());
                      const statusBg = isDone ? 'rgba(0, 135, 90, 0.25)' : isProg ? 'rgba(7, 71, 166, 0.25)' : 'rgba(255, 255, 255, 0.08)';
                      const statusColor = isDone ? '#7EE2B8' : isProg ? '#85B8FF' : '#8C9BAB';
                      const rowBg = idx % 2 === 1 ? 'var(--ds-surface-sunken, #1B1F23)' : 'transparent';

                      return (
                        <tr
                          key={`${item.key}-${idx}`}
                          style={{
                            borderBottom: '1px solid var(--ds-border, #2C333A)',
                            backgroundColor: rowBg
                          }}
                        >
                          <td style={{ padding: '8px 8px', textAlign: 'center', verticalAlign: 'middle' }}>
                            {item.iconUrl ? (
                              <img
                                src={item.iconUrl}
                                alt={item.type}
                                title={item.type}
                                style={{ width: '16px', height: '16px', verticalAlign: 'middle', borderRadius: '2px', display: 'inline-block' }}
                                onError={(e) => {
                                  e.target.style.display = 'none';
                                }}
                              />
                            ) : item.type === 'Story' || item.type === 'Task' ? (
                              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ verticalAlign: 'middle', display: 'inline-block' }}>
                                <rect width="16" height="16" rx="2" fill="#6554C0"/>
                                <path d="M4 4H12V12H4V4Z" fill="white"/>
                              </svg>
                            ) : (
                              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ verticalAlign: 'middle', display: 'inline-block' }}>
                                <rect width="16" height="16" rx="2" fill="#0052CC"/>
                                <path d="M7 3L4 9H8L7 13L12 7H8L9 3H7Z" fill="white"/>
                              </svg>
                            )}
                          </td>
                          <td style={{ padding: '8px 8px', fontWeight: 600 }}>
                            <span style={{ color: 'var(--ds-text-brand, #579DFF)' }}>{item.key}</span>
                          </td>
                          <td style={{ padding: '8px 8px', color: 'var(--ds-text, #DCDFE4)' }}>
                            {item.summary}
                          </td>
                          <td style={{ padding: '8px 8px', color: 'var(--ds-text-subtle, #8C9BAB)' }}>
                            {item.assignee}
                          </td>
                          <td style={{ padding: '8px 8px', textAlign: 'right' }}>
                            <span
                              style={{
                                display: 'inline-block',
                                padding: '2px 8px',
                                borderRadius: '3px',
                                fontSize: '10px',
                                fontWeight: 'bold',
                                backgroundColor: statusBg,
                                color: statusColor,
                                textTransform: 'uppercase'
                              }}
                            >
                              {item.status}
                            </span>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            {metrics.allTableItems.length > 0 && (
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginTop: '12px',
                  paddingTop: '8px',
                  borderTop: '1px solid var(--ds-border, #2C333A)',
                  fontSize: '11px',
                  color: 'var(--ds-text-subtle, #8C9BAB)'
                }}
              >
                <div>
                  {(currentPage - 1) * pageSize + 1} - {Math.min(currentPage * pageSize, metrics.allTableItems.length)} of {metrics.allTableItems.length}
                </div>
                <div style={{ display: 'flex', gap: '4px' }}>
                  <button
                    disabled={currentPage === 1}
                    onClick={() => setCurrentPage((p) => Math.max(p - 1, 1))}
                    style={{
                      border: '1px solid var(--ds-border, #3B444C)',
                      backgroundColor: currentPage === 1 ? 'transparent' : 'var(--ds-surface-raised, #282E33)',
                      color: currentPage === 1 ? 'var(--ds-text-subtle, #5E6C84)' : 'var(--ds-text, #DCDFE4)',
                      padding: '2px 8px',
                      borderRadius: '3px',
                      cursor: currentPage === 1 ? 'not-allowed' : 'pointer'
                    }}
                  >
                    ◀
                  </button>

                  {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => i + 1).map((pg) => (
                    <button
                      key={pg}
                      onClick={() => setCurrentPage(pg)}
                      style={{
                        border: '1px solid',
                        borderColor: currentPage === pg ? '#0052CC' : 'var(--ds-border, #3B444C)',
                        backgroundColor: currentPage === pg ? '#0052CC' : 'var(--ds-surface-raised, #282E33)',
                        color: '#FFFFFF',
                        padding: '2px 8px',
                        borderRadius: '3px',
                        fontWeight: currentPage === pg ? 'bold' : 'normal',
                        cursor: 'pointer'
                      }}
                    >
                      {pg}
                    </button>
                  ))}

                  <button
                    disabled={currentPage === totalPages}
                    onClick={() => setCurrentPage((p) => Math.min(p + 1, totalPages))}
                    style={{
                      border: '1px solid var(--ds-border, #3B444C)',
                      backgroundColor: currentPage === totalPages ? 'transparent' : 'var(--ds-surface-raised, #282E33)',
                      color: currentPage === totalPages ? 'var(--ds-text-subtle, #5E6C84)' : 'var(--ds-text, #DCDFE4)',
                      padding: '2px 8px',
                      borderRadius: '3px',
                      cursor: currentPage === totalPages ? 'not-allowed' : 'pointer'
                    }}
                  >
                    ▶
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default SquadReport;