import React from 'react';
import { THEME } from './theme';

// Avatar color generator berdasarkan nama (hash sederhana)
function getAvatarColor(name = '') {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return THEME.avatarPalette[Math.abs(hash) % THEME.avatarPalette.length];
}

function getInitials(name = '') {
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return (name[0] || 'U').toUpperCase();
}

// Gadget "Sprint Health" — progress bar keseluruhan, 4 statistik ringkas,
// dan daftar avatar semua developer yang terlibat di sprint aktif.
export default function SprintHealthGadget({ currentSelectionInfo, currentProjectKey, metrics, sprintInfo }) {
  return (
    <div
      style={{
        backgroundColor: `var(--ds-surface-overlay, ${THEME.surface.overlay})`,
        border: `1px solid var(--ds-border, ${THEME.border.default})`,
        borderRadius: '6px',
        overflow: 'hidden',
        boxShadow: '0 1px 3px rgba(0, 0, 0, 0.25)'
      }}
    >
      {/* Blue Header Banner */}
      <div style={{ backgroundColor: THEME.brand.dark, padding: '8px 14px', color: THEME.text.onBold, fontSize: '12px', fontWeight: 600, display: 'flex', justifyContent: 'space-between' }}>
        <span>Sprint Health Gadget</span>
        <span>•••</span>
      </div>

      <div style={{ padding: '16px 20px' }}>
        <div style={{ fontSize: '14px', fontWeight: 'bold', color: `var(--ds-text, ${THEME.text.primary})`, marginBottom: '14px' }}>
          Sprint Health - {currentSelectionInfo.key || currentProjectKey}
        </div>

        {/* Overall Sprint Progress Bar */}
        <div style={{ marginBottom: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: `var(--ds-text-subtle, ${THEME.text.subtle})`, marginBottom: '6px' }}>
            <span>Overall sprint progress (Subtask Completion)</span>
            <span><strong style={{ color: `var(--ds-text, ${THEME.text.primary})` }}>{metrics.totalSubtasks} Subtasks</strong> ({metrics.percentDone}%)</span>
          </div>
          <div style={{ width: '100%', height: '14px', backgroundColor: `var(--ds-background-neutral, ${THEME.surface.neutralSubtle})`, borderRadius: '7px', overflow: 'hidden', display: 'flex' }}>
            <div style={{ width: `${metrics.percentDone}%`, backgroundColor: THEME.brand.primary, transition: 'width 0.3s' }} />
            <div style={{ width: `${metrics.totalSubtasks > 0 ? (metrics.inProgressCount / metrics.totalSubtasks) * 100 : 0}%`, backgroundColor: THEME.status.info }} />
          </div>
          <div style={{ textAlign: 'right', fontSize: '11px', color: `var(--ds-text-subtle, ${THEME.text.subtle})`, marginTop: '4px' }}>
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
            borderBottom: `1px solid var(--ds-border, ${THEME.border.subtle})`
          }}
        >
          <div>
            <div style={{ fontSize: '18px', fontWeight: 'bold', color: `var(--ds-text, ${THEME.text.primary})` }}>{sprintInfo.timeElapsedPercent}%</div>
            <div style={{ fontSize: '11px', color: `var(--ds-text-subtle, ${THEME.text.subtle})` }}>Time elapsed</div>
          </div>
          <div>
            <div style={{ fontSize: '18px', fontWeight: 'bold', color: THEME.status.success }}>{metrics.percentDone}%</div>
            <div style={{ fontSize: '11px', color: `var(--ds-text-subtle, ${THEME.text.subtle})` }}>Work complete</div>
          </div>
          <div>
            <div style={{ fontSize: '18px', fontWeight: 'bold', color: `var(--ds-text, ${THEME.text.primary})` }}>0%</div>
            <div style={{ fontSize: '11px', color: `var(--ds-text-subtle, ${THEME.text.subtle})` }}>Scope change</div>
          </div>
          <div>
            <div style={{ fontSize: '18px', fontWeight: 'bold', color: `var(--ds-text-subtle, ${THEME.text.subtle})` }}>0</div>
            <div style={{ fontSize: '11px', color: `var(--ds-text-subtle, ${THEME.text.subtle})` }}>Flagged / Blocked</div>
          </div>
        </div>

        {/* Assignees in Sprint (Avatars) */}
        <div>
          <div style={{ fontSize: '12px', fontWeight: 600, color: `var(--ds-text-subtle, ${THEME.text.subtle})`, marginBottom: '8px' }}>
            Assignees in Sprint ({metrics.memberList.length} Developers):
          </div>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
            {metrics.memberList.length === 0 && (
              <span style={{ fontSize: '12px', color: `var(--ds-text-subtle, ${THEME.text.subtle})`, fontStyle: 'italic' }}>
                Belum ada assignee terdaftar.
              </span>
            )}
            {metrics.memberList.map((m) => (
              <div
                key={m.name}
                role="img"
                aria-label={`${m.name}, ${m.role}, ${m.total} subtask, ${m.done} selesai`}
                title={`${m.name} (${m.role}) • ${m.total} Subtasks (${m.done} Selesai)`}
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '50%',
                  backgroundColor: getAvatarColor(m.name),
                  color: THEME.text.onBold,
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
  );
}