import React from 'react';
import { PieChart, Pie, ResponsiveContainer, Cell } from 'recharts';
import { THEME } from './theme';

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
      fill={THEME.text.onBold}
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

// Gadget "Workload & Progress Activity Chart" — pie chart per developer
// menunjukkan proporsi To Do / In Progress / Done miliknya masing-masing.
export default function WorkloadChart({ memberPieCharts }) {
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
        <span>Workload & Progress Activity Chart</span>
        <span>•••</span>
      </div>

      <div style={{ padding: '16px 20px' }}>
        <div style={{ fontSize: '13px', fontWeight: 600, color: `var(--ds-text, ${THEME.text.primary})`, marginBottom: '4px' }}>
          Distribusi Subtask Per Developer (To Do, In Progress, Done)
        </div>
        <div style={{ fontSize: '11px', color: `var(--ds-text-subtle, ${THEME.text.subtle})`, marginBottom: '14px' }}>
          Monitoring beban kerja dan progres riil anggota tim pada sprint aktif.
        </div>

        {memberPieCharts.length === 0 ? (
          <div style={{ color: THEME.text.subtle, fontStyle: 'italic' }}>
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
                  border: `1px solid ${THEME.border.default}`,
                  borderRadius: '8px',
                  padding: '10px',
                }}
              >
                <div
                  style={{
                    textAlign: 'center',
                    fontSize: '12px',
                    fontWeight: 600,
                    color: THEME.text.primary,
                    marginBottom: '8px',
                  }}
                >
                  {person.name}
                </div>

                <div style={{ width: '100%', height: 170 }} role="img" aria-label={`Pie chart distribusi subtask ${person.name}`}>
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
                      style={{ textAlign: 'center' }}
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
                          aria-hidden="true"
                          style={{
                            width: '8px',
                            height: '8px',
                            borderRadius: '50%',
                            backgroundColor: entry.color,
                            display: 'inline-block',
                          }}
                        />
                        <span style={{ fontSize: '10px', color: THEME.text.subtle }}>
                          {entry.name}
                        </span>
                      </div>
                      <div style={{ fontSize: '13px', fontWeight: 700, color: THEME.text.primary }}>
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
  );
}