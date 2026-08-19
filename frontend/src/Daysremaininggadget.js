import React from 'react';
import { THEME } from './theme';

export default function DaysRemainingGadget({ currentProjectKey, currentSelectionInfo, sprintInfo }) {
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
        <span>Days Remaining in Sprint Gadget</span>
        <span>•••</span>
      </div>

      <div style={{ padding: '18px 20px' }}>
        <div style={{ fontSize: '14px', fontWeight: 'bold', color: `var(--ds-text-brand, ${THEME.text.brand})` }}>
          {currentProjectKey} - {currentSelectionInfo.key}
        </div>
        <div style={{ fontSize: '12px', color: `var(--ds-text-subtle, ${THEME.text.subtle})`, marginBottom: '16px' }}>
          {sprintInfo.sprintName}
        </div>

        <div
          style={{
            backgroundColor: `var(--ds-background-neutral-subtle, ${THEME.surface.neutralSubtle})`,
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

        <div
          style={{
            display: 'flex',
            justifyContent: 'space-around',
            marginTop: '18px',
            paddingTop: '12px',
            borderTop: `1px solid var(--ds-border, ${THEME.border.subtle})`,
            fontSize: '12px',
            color: `var(--ds-text-subtle, ${THEME.text.subtle})`
          }}
        >
          <div>Start: <strong style={{ color: `var(--ds-text, ${THEME.text.primary})` }}>{sprintInfo.startDateStr}</strong></div>
          <div>Due: <strong style={{ color: `var(--ds-text, ${THEME.text.primary})` }}>{sprintInfo.dueDateStr}</strong></div>
          <div>Status: <strong style={{ color: sprintInfo.statusColor }}>{sprintInfo.status}</strong></div>
        </div>
      </div>
    </div>
  );
}