import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { invoke, view } from '@forge/bridge';
import XlsxPopulate from 'xlsx-populate/browser/xlsx-populate';

import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';

const KNOWN_STATUS_COLORS = {
  'to do': '#61635e',
  'in progress': '#0052CC',
  'in review': '#6E5DC6',
  'review': '#6E5DC6',
  'testing': '#00B8D9',
  'done': '#095d17',
  'closed': '#095d17',
  'resolved': '#095d17'
};

const COLOR_PALETTE = [
  '#0052CC',
  '#095d17',
  '#6E5DC6',
  '#00B8D9',
  '#FFAB00',
  '#FF5630',
  '#61635e'
];

function getStatusColor(statusName, index) {
  const normalized = String(statusName).toLowerCase().trim();
  if (KNOWN_STATUS_COLORS[normalized]) {
    return KNOWN_STATUS_COLORS[normalized];
  }
  return COLOR_PALETTE[index % COLOR_PALETTE.length];
}

function StoryProgressCard({ story, uniqueStatuses }) {
  const [selectedRole, setSelectedRole] = useState('ALL');

  const availableRoles = useMemo(() => {
    if (story.availableRoles && story.availableRoles.length > 0) {
      return story.availableRoles;
    }
    return (story.roleChartData || []).map((r) => r.name);
  }, [story]);

  const pieChartData = useMemo(() => {
    if (!story.roleChartData) return [];

    const filteredRoles = selectedRole === 'ALL'
      ? story.roleChartData
      : story.roleChartData.filter((item) => item.name === selectedRole);

    const statusCounts = {};
    filteredRoles.forEach((roleItem) => {
      uniqueStatuses.forEach((stName) => {
        const count = roleItem[stName] || 0;
        statusCounts[stName] = (statusCounts[stName] || 0) + count;
      });
    });

    return Object.keys(statusCounts)
      .filter((stName) => statusCounts[stName] > 0)
      .map((stName) => ({
        name: stName,
        value: statusCounts[stName]
      }));
  }, [story.roleChartData, selectedRole, uniqueStatuses]);

  const totalTasks = useMemo(() => {
    return pieChartData.reduce((acc, curr) => acc + curr.value, 0);
  }, [pieChartData]);

  return (
    <div
      style={{
        border: '1px solid var(--ds-border, #C1C7D0)',
        borderRadius: '8px',
        padding: '20px',
        marginBottom: '20px',
        backgroundColor: 'var(--ds-surface-overlay, #FFFFFF)'
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          borderBottom: '1px solid var(--ds-border, #DFE1E6)',
          paddingBottom: '12px',
          marginBottom: '16px',
          flexWrap: 'wrap',
          gap: '12px'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <h4 style={{ margin: 0, fontSize: '16px' }}>
            📖 [{story.key}] {story.summary}
          </h4>
          <span
            style={{
              padding: '2px 8px',
              borderRadius: '4px',
              backgroundColor: 'var(--ds-background-neutral, #EBECF0)',
              fontSize: '12px',
              fontWeight: 'bold'
            }}
          >
            Status: {story.status}
          </span>
        </div>

        {availableRoles.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <label htmlFor={`role-select-${story.key}`} style={{ fontSize: '12px', fontWeight: 'bold' }}>
              Filter Role:
            </label>
            <select
              id={`role-select-${story.key}`}
              value={selectedRole}
              onChange={(e) => setSelectedRole(e.target.value)}
              style={{
                padding: '6px 12px',
                borderRadius: '4px',
                border: '1px solid var(--ds-border, #C1C7D0)',
                backgroundColor: 'var(--ds-surface, #FFFFFF)',
                color: 'var(--ds-text, #172B4D)',
                fontSize: '13px'
              }}
            >
              <option value="ALL">Semua Role Active ({availableRoles.join(', ')})</option>
              {availableRoles.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {pieChartData.length === 0 ? (
        <p style={{ color: 'var(--ds-text-subtle, #6B778C)', fontStyle: 'italic' }}>
          Belum ada sub-task / pembagian role pada Story ini.
        </p>
      ) : (
        <div id={`chart-container-${story.key}`} style={{ width: '100%', height: 260, position: 'relative' }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart margin={{ top: 25, right: 30, bottom: 10, left: 30 }}>
              <Pie
                data={pieChartData}
                cx="50%"
                cy="50%"
                innerRadius={50}
                outerRadius={75}
                paddingAngle={3}
                dataKey="value"
                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
              >
                {pieChartData.map((entry, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={getStatusColor(entry.name, index)}
                  />
                ))}
              </Pie>
              <Tooltip formatter={(value, name) => [`${value} Sub-task`, name]} />
              <Legend verticalAlign="bottom" height={36} />
            </PieChart>
          </ResponsiveContainer>

          <div
            style={{
              position: 'absolute',
              top: '42%',
              left: '50%',
              transform: 'translate(-50%, -50%)',
              textAlign: 'center',
              pointerEvents: 'none'
            }}
          >
            <div style={{ fontSize: '20px', fontWeight: 'bold' }}>{totalTasks}</div>
            <div style={{ fontSize: '11px', color: 'var(--ds-text-subtle, #6B778C)' }}>Sub-task</div>
          </div>
        </div>
      )}
    </div>
  );
}

export function SquadReport() {
  const [currentProjectKey, setCurrentProjectKey] = useState('SCRUM');

  const [epics, setEpics] = useState([]);
  const [selectedEpicKey, setSelectedEpicKey] = useState('');
  const [stories, setStories] = useState([]);
  const [selectedStoryKey, setSelectedStoryKey] = useState('ALL');

  const [loadingEpics, setLoadingEpics] = useState(true);
  const [loadingStories, setLoadingStories] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState('');

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
      setSelectedStoryKey('ALL');
    } catch (err) {
      console.error('[SquadReport] Error loading Stories:', err);
      setError(err?.message || 'Gagal memuat Story untuk Epic terpilih.');
    } finally {
      setLoadingStories(false);
    }
  }, [currentProjectKey]);

  useEffect(() => {
    async function init() {
      let pKey = 'SCRUM';
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

  const uniqueStatuses = useMemo(() => {
    const statusSet = new Set();
    stories.forEach((story) => {
      (story.roleChartData || []).forEach((item) => {
        Object.keys(item).forEach((k) => {
          if (k !== 'name' && k !== 'total') {
            statusSet.add(k);
          }
        });
      });
    });
    return Array.from(statusSet);
  }, [stories]);

  const displayedStories = useMemo(() => {
    if (selectedStoryKey === 'ALL') return stories;
    return stories.filter((s) => s.key === selectedStoryKey);
  }, [stories, selectedStoryKey]);

  // --------------------------------------------------------
  // EXPORT EXCEL MENULIS KE SHEET PRE-DEFINED TEMPLATE
  // --------------------------------------------------------
  const exportToExcel = async () => {
    if (!displayedStories || displayedStories.length === 0) {
      alert('Tidak ada data Story/Task pada Epic ini untuk diexport.');
      return;
    }

    try {
      setIsExporting(true);

      const response = await fetch(`./template_report.xlsx?v=${Date.now()}`, {
        cache: 'no-cache'
      });
      
      if (!response.ok) {
        throw new Error('Gagal memuat file template_report.xlsx dari folder public.');
      }
      const templateArrayBuffer = await response.arrayBuffer();
      const workbook = await XlsxPopulate.fromDataAsync(templateArrayBuffer);

      const currentEpicObj = epics.find((e) => e.key === selectedEpicKey);
      const epicSummary = currentEpicObj ? currentEpicObj.summary : selectedEpicKey;

      const availableSheets = workbook.sheets();

      if (displayedStories.length > availableSheets.length) {
        alert(
          `Jumlah Story (${displayedStories.length}) melebihi jumlah sheet template yang tersedia (${availableSheets.length}). Silakan tambahkan sheet di file template_report.xlsx.`
        );
      }

      // 1. Fill data to existing template sheets
      displayedStories.forEach((story, index) => {
        if (index >= availableSheets.length) return;

        const sheet = availableSheets[index];
        const cleanSheetName = story.key.replace(/[:\\/?*\[\]]/g, '').substring(0, 31);
        sheet.name(cleanSheetName);

        // Metadata Header
        sheet.cell('B1').value(`[${story.key}] ${story.summary}`);
        sheet.cell('B2').value(`[${selectedEpicKey}] ${epicSummary}`);
        sheet.cell('B3').value(story.status);

        // Role mapping
        const roleRowMapping = {
          'Backend': 7,
          'WEB': 8,
          'Mobile': 9
        };

        const roleDataList = story.roleChartData || [];
        let totalToDoAcc = 0;
        let totalInProgressAcc = 0;
        let totalDoneAcc = 0;

        Object.entries(roleRowMapping).forEach(([roleName, rowNum]) => {
          const roleItem = roleDataList.find(
            (r) => r.name.toLowerCase() === roleName.toLowerCase()
          );

          const getStatusValue = (targetStatus) => {
            if (!roleItem) return 0;
            const key = Object.keys(roleItem).find(
              (k) => k.toLowerCase() === targetStatus.toLowerCase()
            );
            return key ? Number(roleItem[key]) || 0 : 0;
          };

          const toDoCount = getStatusValue('To Do');
          const inProgressCount = getStatusValue('In Progress');
          const doneCount = getStatusValue('Done');
          const rowTotal = toDoCount + inProgressCount + doneCount;

          totalToDoAcc += toDoCount;
          totalInProgressAcc += inProgressCount;
          totalDoneAcc += doneCount;

          sheet.cell(`B${rowNum}`).value(toDoCount);
          sheet.cell(`C${rowNum}`).value(inProgressCount);
          sheet.cell(`D${rowNum}`).value(doneCount);
          sheet.cell(`E${rowNum}`).value(rowTotal);
        });

        // Total
        const grandTotal = totalToDoAcc + totalInProgressAcc + totalDoneAcc;
        sheet.cell('B10').value(totalToDoAcc);
        sheet.cell('C10').value(totalInProgressAcc);
        sheet.cell('D10').value(totalDoneAcc);
        sheet.cell('E10').value(grandTotal);
      });

      // 2. Hide unused sheets
      for (let i = displayedStories.length; i < availableSheets.length; i++) {
        availableSheets[i].hidden(true);
      }

      // 3. Download
      const blob = await workbook.outputAsync();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `Laporan_Progress_Epic_${selectedEpicKey}_${new Date().toISOString().split('T')[0]}.xlsx`;
      link.click();
      window.URL.revokeObjectURL(url);

    } catch (err) {
      console.error('[SquadReport] Error exporting Excel:', err);
      alert(`Gagal membuat file Excel: ${err.message}`);
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div
      style={{
        padding: '24px',
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        backgroundColor: 'var(--ds-surface, transparent)',
        color: 'var(--ds-text, #172B4D)',
        minHeight: '100vh',
        boxSizing: 'border-box'
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          width: '100%',
          marginBottom: '20px',
          gap: '16px'
        }}
      >
        <div style={{ flex: 1 }}>
          <h2 style={{ margin: 0 }}>Progress Report</h2>
          <p style={{ color: 'var(--ds-text-subtle, #6B778C)', margin: '4px 0 0 0' }}>
            Pilih Epic dan Story/Task untuk melihat persentase progress sub-task berdasarkan Peran/Role.
          </p>
        </div>

        <button
          onClick={exportToExcel}
          disabled={displayedStories.length === 0 || isExporting}
          style={{
            backgroundColor: '#217346',
            color: '#FFF',
            border: 'none',
            borderRadius: '4px',
            padding: '10px 16px',
            fontWeight: 'bold',
            cursor: (displayedStories.length === 0 || isExporting) ? 'not-allowed' : 'pointer',
            opacity: (displayedStories.length === 0 || isExporting) ? 0.6 : 1,
            whiteSpace: 'nowrap'
          }}
        >
          {isExporting ? 'Mengeksport...' : 'Export to Excel (.xlsx)'}
        </button>
      </div>

      <div
        style={{
          display: 'flex',
          gap: '16px',
          backgroundColor: 'var(--ds-background-neutral, #F4F5F7)',
          padding: '16px',
          borderRadius: '8px',
          marginBottom: '24px',
          border: '1px solid var(--ds-border, #DFE1E6)'
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', flex: 1 }}>
          <label htmlFor="epic-select" style={{ fontSize: '12px', fontWeight: 'bold' }}>1. Pilih Epic:</label>
          <select
            id="epic-select"
            value={selectedEpicKey}
            onChange={(e) => setSelectedEpicKey(e.target.value)}
            disabled={loadingEpics || epics.length === 0}
            style={{
              padding: '8px 12px',
              borderRadius: '4px',
              border: '1px solid var(--ds-border, #C1C7D0)',
              fontSize: '14px'
            }}
          >
            {epics.length === 0 && <option value="">Tidak ada Epic ditemukan</option>}
            {epics.map((epic) => (
              <option key={epic.key} value={epic.key}>
                [{epic.key}] {epic.summary} ({epic.status})
              </option>
            ))}
          </select>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', flex: 1 }}>
          <label htmlFor="story-select" style={{ fontSize: '12px', fontWeight: 'bold' }}>2. Pilih Story / Task:</label>
          <select
            id="story-select"
            value={selectedStoryKey}
            onChange={(e) => setSelectedStoryKey(e.target.value)}
            disabled={loadingStories || stories.length === 0}
            style={{
              padding: '8px 12px',
              borderRadius: '4px',
              border: '1px solid var(--ds-border, #C1C7D0)',
              fontSize: '14px'
            }}
          >
            <option value="ALL">-- Tampilkan Semua Story/Task --</option>
            {stories.map((story) => (
              <option key={story.key} value={story.key}>
                [{story.key}] {story.summary}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <div
          style={{
            padding: '12px 16px',
            backgroundColor: '#FFEBE6',
            color: '#BF2600',
            borderRadius: '4px',
            marginBottom: '20px'
          }}
        >
          {error}
        </div>
      )}

      {(loadingEpics || loadingStories) && (
        <div style={{ padding: '32px', textAlign: 'center' }}>
          <p>Sedang memuat data progress dari Jira...</p>
        </div>
      )}

      {!loadingEpics && !loadingStories && stories.length === 0 && selectedEpicKey && (
        <div
          style={{
            padding: '32px',
            textAlign: 'center',
            backgroundColor: 'var(--ds-background-neutral, #F4F5F7)',
            borderRadius: '6px'
          }}
        >
          Tidak ada Story / Task terhubung pada Epic <strong>{selectedEpicKey}</strong>.
        </div>
      )}

      {!loadingEpics &&
        !loadingStories &&
        displayedStories.map((story) => (
          <StoryProgressCard
            key={story.key}
            story={story}
            uniqueStatuses={uniqueStatuses}
          />
        ))}
    </div>
  );
}

export default SquadReport;