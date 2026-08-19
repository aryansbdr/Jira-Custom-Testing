import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { invoke, view } from '@forge/bridge';

import { THEME } from './theme';
import DaysRemainingGadget from './DaysRemainingGadget';
import SprintHealthGadget from './SprintHealthGadget';
import WorkloadChart from './WorkloadChart';
import FilterTable from './FilterTable';

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

  // Data pie chart per developer (di-memo supaya tidak dihitung ulang setiap render)
  const memberPieCharts = useMemo(() => {
    return metrics.memberList.map((member) => ({
      name: member.name,
      data: [
        { name: 'To Do', value: member.todo, color: THEME.chart.todo },
        { name: 'In Progress', value: member.inProgress, color: THEME.chart.inProgress },
        { name: 'Done', value: member.done, color: THEME.chart.done }
      ]
    }));
  }, [metrics.memberList]);

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
    let statusColor = THEME.status.success;
    if (daysRemaining <= 0) {
      status = 'Overdue';
      statusColor = THEME.status.danger;
    } else if (timeElapsedPercent > metrics.percentDone + 25) {
      status = 'At Risk';
      statusColor = THEME.status.warning;
    } else if (metrics.percentDone >= timeElapsedPercent) {
      status = 'Ahead';
      statusColor = THEME.status.success;
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
        backgroundColor: `var(--ds-surface, ${THEME.surface.base})`,
        color: `var(--ds-text, ${THEME.text.primary})`,
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
          backgroundColor: `var(--ds-surface-overlay, ${THEME.surface.overlay})`,
          padding: '16px 20px',
          borderRadius: '8px',
          border: `1px solid var(--ds-border, ${THEME.border.default})`,
          boxShadow: '0 1px 3px rgba(0, 0, 0, 0.25)',
          marginBottom: '20px'
        }}
      >
        <div style={{ flex: '1 1 280px', minWidth: 0 }}>
          <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 'bold', color: `var(--ds-text, ${THEME.text.primary})` }}>
            {currentEpicObj ? `[${currentEpicObj.key}] ${currentEpicObj.summary}` : 'Sprint & Squad Health Overview'}
          </h2>
          <p style={{ margin: '4px 0 0 0', fontSize: '12px', color: `var(--ds-text-subtle, ${THEME.text.subtle})` }}>
            Executive Dashboard • Project: <strong>{currentProjectKey}</strong> • Sisa Waktu Sprint & Status Beban Tim
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap', flex: '0 0 auto' }}>
          {/* Epic Selector */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <label htmlFor="epic-top-select" style={{ fontSize: '12px', fontWeight: 600, color: `var(--ds-text-subtle, ${THEME.text.subtle})` }}>
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
                border: `1px solid var(--ds-border, ${THEME.border.input})`,
                backgroundColor: `var(--ds-surface-raised, ${THEME.surface.raised})`,
                color: `var(--ds-text, ${THEME.text.primary})`,
                fontSize: '13px',
                fontWeight: 500,
                maxWidth: '240px',
                outline: 'none'
              }}
            >
              {epics.map((e) => (
                <option key={e.key} value={e.key} style={{ backgroundColor: THEME.surface.overlay, color: THEME.text.primary }}>
                  [{e.key}] {e.summary}
                </option>
              ))}
            </select>
          </div>

          {/* Story Selector */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <label htmlFor="story-top-select" style={{ fontSize: '12px', fontWeight: 600, color: `var(--ds-text-subtle, ${THEME.text.subtle})` }}>
              Story:
            </label>
            <select
              id="story-top-select"
              value={selectedStoryKey}
              onChange={(e) => {
                setSelectedStoryKey(e.target.value);
                setCurrentPage(1);
              }}
              disabled={loadingStories || stories.length === 0}
              style={{
                padding: '6px 12px',
                borderRadius: '4px',
                border: `1px solid var(--ds-border, ${THEME.border.input})`,
                backgroundColor: `var(--ds-surface-raised, ${THEME.surface.raised})`,
                color: `var(--ds-text, ${THEME.text.primary})`,
                fontSize: '13px',
                fontWeight: 500,
                maxWidth: '220px',
                outline: 'none'
              }}
            >
              <option value="ALL" style={{ backgroundColor: THEME.surface.overlay, color: THEME.text.primary }}>Semua Story ({stories.length})</option>
              {stories.map((s) => (
                <option key={s.key} value={s.key} style={{ backgroundColor: THEME.surface.overlay, color: THEME.text.primary }}>
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
              color: THEME.text.onBold,
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
        <div
          role="alert"
          style={{ padding: '10px 14px', backgroundColor: 'rgba(222, 53, 11, 0.2)', color: '#FF8F73', border: `1px solid ${THEME.status.dangerStrong}`, borderRadius: '4px', marginBottom: '16px', fontSize: '13px' }}
        >
          ⚠️ {error}
        </div>
      )}
      {successNotice && (
        <div
          role="status"
          style={{ padding: '10px 14px', backgroundColor: 'rgba(0, 135, 90, 0.2)', color: THEME.status.successText, border: `1px solid ${THEME.status.successStrong}`, borderRadius: '4px', marginBottom: '16px', fontSize: '13px' }}
        >
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
        <DaysRemainingGadget
          currentProjectKey={currentProjectKey}
          currentSelectionInfo={currentSelectionInfo}
          sprintInfo={sprintInfo}
        />

        <SprintHealthGadget
          currentSelectionInfo={currentSelectionInfo}
          currentProjectKey={currentProjectKey}
          metrics={metrics}
          sprintInfo={sprintInfo}
        />

        <WorkloadChart memberPieCharts={memberPieCharts} />

        <FilterTable
          paginatedItems={paginatedItems}
          totalItems={metrics.allTableItems.length}
          currentPage={currentPage}
          setCurrentPage={setCurrentPage}
          totalPages={totalPages}
          pageSize={pageSize}
        />
      </div>
    </div>
  );
}

export default SquadReport;