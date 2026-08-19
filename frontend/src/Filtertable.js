import React from 'react';
import { THEME } from './theme';

function getPageNumbers(currentPage, totalPages) {
  const delta = 1;
  const range = [];
  const rangeWithDots = [];
  let lastPage = 0;

  for (let i = 1; i <= totalPages; i++) {
    if (i === 1 || i === totalPages || (i >= currentPage - delta && i <= currentPage + delta)) {
      range.push(i);
    }
  }

  range.forEach((i) => {
    if (lastPage) {
      if (i - lastPage === 2) {
        rangeWithDots.push(lastPage + 1);
      } else if (i - lastPage > 2) {
        rangeWithDots.push('...');
      }
    }
    rangeWithDots.push(i);
    lastPage = i;
  });

  return rangeWithDots;
}

// Gadget "Filter Results" — tabel Story + Sub-task dengan status masing-masing,
// lengkap dengan pagination yang bisa loncat ke halaman jauh (bukan cuma 5 halaman pertama).
export default function FilterTable({ paginatedItems, totalItems, currentPage, setCurrentPage, totalPages, pageSize }) {
  return (
    <div
      style={{
        backgroundColor: `var(--ds-surface-overlay, ${THEME.surface.overlay})`,
        border: `1px solid var(--ds-border, ${THEME.border.default})`,
        borderRadius: '6px',
        overflow: 'hidden',
        boxShadow: '0 1px 3px rgba(0, 0, 0, 0.25)',
        display: 'flex',
        flexDirection: 'column'
      }}
    >
      {/* Blue Header Banner */}
      <div style={{ backgroundColor: THEME.brand.dark, padding: '8px 14px', color: THEME.text.onBold, fontSize: '12px', fontWeight: 600, display: 'flex', justifyContent: 'space-between' }}>
        <span>Filter Results: Story & Subtask Monitor</span>
        <span>•••</span>
      </div>

      <div style={{ padding: '14px 16px', flex: 1, display: 'flex', flexDirection: 'column' }}>
        <div style={{ overflowX: 'auto', flex: 1 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
            <thead>
              <tr style={{ borderBottom: `2px solid var(--ds-border, ${THEME.border.default})`, color: `var(--ds-text-subtle, ${THEME.text.subtle})`, textAlign: 'left' }}>
                <th style={{ padding: '8px 8px', width: '28px' }} scope="col">T</th>
                <th style={{ padding: '8px 8px', width: '80px' }} scope="col">Key</th>
                <th style={{ padding: '8px 8px' }} scope="col">Summary</th>
                <th style={{ padding: '8px 8px', width: '110px' }} scope="col">Assignee</th>
                <th style={{ padding: '8px 8px', width: '85px', textAlign: 'right' }} scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {paginatedItems.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ padding: '24px', textAlign: 'center', color: `var(--ds-text-subtle, ${THEME.text.subtle})`, fontStyle: 'italic' }}>
                    Tidak ada tiket ditemukan.
                  </td>
                </tr>
              ) : (
                paginatedItems.map((item, idx) => {
                  const isDone = ['done', 'closed', 'resolved', 'complete'].includes(String(item.status).toLowerCase());
                  const isProg = ['in progress', 'in development', 'in review'].includes(String(item.status).toLowerCase());
                  const statusBg = isDone ? 'rgba(0, 135, 90, 0.25)' : isProg ? 'rgba(7, 71, 166, 0.25)' : 'rgba(255, 255, 255, 0.08)';
                  const statusColor = isDone ? THEME.status.successText : isProg ? THEME.status.infoText : THEME.text.subtle;
                  const rowBg = idx % 2 === 1 ? `var(--ds-surface-sunken, ${THEME.surface.sunken})` : 'transparent';

                  return (
                    <tr
                      key={`${item.key}-${idx}`}
                      style={{
                        borderBottom: `1px solid var(--ds-border, ${THEME.border.subtle})`,
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
                          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" role="img" aria-label={item.type} style={{ verticalAlign: 'middle', display: 'inline-block' }}>
                            <rect width="16" height="16" rx="2" fill="#6554C0"/>
                            <path d="M4 4H12V12H4V4Z" fill="white"/>
                          </svg>
                        ) : (
                          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" role="img" aria-label={item.type} style={{ verticalAlign: 'middle', display: 'inline-block' }}>
                            <rect width="16" height="16" rx="2" fill="#0052CC"/>
                            <path d="M7 3L4 9H8L7 13L12 7H8L9 3H7Z" fill="white"/>
                          </svg>
                        )}
                      </td>
                      <td style={{ padding: '8px 8px', fontWeight: 600 }}>
                        <span style={{ color: `var(--ds-text-brand, ${THEME.text.brand})` }}>{item.key}</span>
                      </td>
                      <td style={{ padding: '8px 8px', color: `var(--ds-text, ${THEME.text.primary})` }}>
                        {item.summary}
                      </td>
                      <td style={{ padding: '8px 8px', color: `var(--ds-text-subtle, ${THEME.text.subtle})` }}>
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
        {totalItems > 0 && (
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginTop: '12px',
              paddingTop: '8px',
              borderTop: `1px solid var(--ds-border, ${THEME.border.subtle})`,
              fontSize: '11px',
              color: `var(--ds-text-subtle, ${THEME.text.subtle})`
            }}
          >
            <div>
              {(currentPage - 1) * pageSize + 1} - {Math.min(currentPage * pageSize, totalItems)} of {totalItems}
            </div>
            <div style={{ display: 'flex', gap: '4px' }}>
              <button
                disabled={currentPage === 1}
                aria-label="Halaman sebelumnya"
                onClick={() => setCurrentPage((p) => Math.max(p - 1, 1))}
                style={{
                  border: `1px solid var(--ds-border, ${THEME.border.input})`,
                  backgroundColor: currentPage === 1 ? 'transparent' : `var(--ds-surface-raised, ${THEME.surface.raised})`,
                  color: currentPage === 1 ? `var(--ds-text-subtle, ${THEME.text.subtleAlt})` : `var(--ds-text, ${THEME.text.primary})`,
                  padding: '2px 8px',
                  borderRadius: '3px',
                  cursor: currentPage === 1 ? 'not-allowed' : 'pointer'
                }}
              >
                ◀
              </button>

              {getPageNumbers(currentPage, totalPages).map((pg, idx) =>
                pg === '...' ? (
                  <span
                    key={`dots-${idx}`}
                    style={{
                      padding: '2px 6px',
                      color: `var(--ds-text-subtle, ${THEME.text.subtleAlt})`,
                      userSelect: 'none'
                    }}
                  >
                    …
                  </span>
                ) : (
                  <button
                    key={pg}
                    aria-label={`Ke halaman ${pg}`}
                    aria-current={currentPage === pg ? 'page' : undefined}
                    onClick={() => setCurrentPage(pg)}
                    style={{
                      border: '1px solid',
                      borderColor: currentPage === pg ? THEME.brand.primary : `var(--ds-border, ${THEME.border.input})`,
                      backgroundColor: currentPage === pg ? THEME.brand.primary : `var(--ds-surface-raised, ${THEME.surface.raised})`,
                      color: THEME.text.onBold,
                      padding: '2px 8px',
                      borderRadius: '3px',
                      fontWeight: currentPage === pg ? 'bold' : 'normal',
                      cursor: 'pointer'
                    }}
                  >
                    {pg}
                  </button>
                )
              )}

              <button
                disabled={currentPage === totalPages}
                aria-label="Halaman berikutnya"
                onClick={() => setCurrentPage((p) => Math.min(p + 1, totalPages))}
                style={{
                  border: `1px solid var(--ds-border, ${THEME.border.input})`,
                  backgroundColor: currentPage === totalPages ? 'transparent' : `var(--ds-surface-raised, ${THEME.surface.raised})`,
                  color: currentPage === totalPages ? `var(--ds-text-subtle, ${THEME.text.subtleAlt})` : `var(--ds-text, ${THEME.text.primary})`,
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
  );
}