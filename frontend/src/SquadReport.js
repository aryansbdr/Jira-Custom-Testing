import React, { useState } from 'react';
import * as XLSX from 'xlsx';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell
} from 'recharts';

// ==========================================================
// MOCK DATA (Data Report dengan Ringkasan Total Status)
// ==========================================================
const MOCK_PARENT_ISSUES = [
  {
    key: 'SCRUM-1',
    title: 'Task 1 (SCRUM-1)',
    // Ringkasan Total Sub-Task Akumulasi (Tampilan 'Squad / Semua Role')
    squadSummaryData: [
      { status: 'To Do', count: 3, color: '#4C6B1F' },
      { status: 'In Progress', count: 1, color: '#0052CC' },
      { status: 'Done', count: 2, color: '#36B37E' }
    ],
    // Data per Member (Tampilan saat filter Frontend / Backend / QA)
    memberChartData: {
      Backend: [
        { name: 'Budi (Backend)', todo: 1, inProgress: 1, done: 0 }
      ],
      Frontend: [
        { name: 'Siti (Frontend)', todo: 1, inProgress: 0, done: 1 },
        { name: 'Rian (Frontend)', todo: 1, inProgress: 0, done: 1 }
      ],
      QA: []
    }
  },
  {
    key: 'SCRUM-2',
    title: 'Task 2 (SCRUM-2)',
    squadSummaryData: [
      { status: 'To Do', count: 13, color: '#4C6B1F' },
      { status: 'In Progress', count: 3, color: '#0052CC' },
      { status: 'Done', count: 3, color: '#36B37E' }
    ],
    memberChartData: {
      Backend: [
        { name: 'Budi (Backend)', todo: 3, inProgress: 1, done: 1 },
        { name: 'Andi (Backend)', todo: 2, inProgress: 1, done: 0 }
      ],
      Frontend: [
        { name: 'Siti (Frontend)', todo: 4, inProgress: 1, done: 1 },
        { name: 'Rian (Frontend)', todo: 2, inProgress: 0, done: 1 }
      ],
      QA: [
        { name: 'Dewi (QA)', todo: 2, inProgress: 0, done: 0 }
      ]
    }
  },
  {
    key: 'SCRUM-26',
    title: 'Team 3 (SCRUM-26)',
    squadSummaryData: [
      { status: 'To Do', count: 1, color: '#4C6B1F' },
      { status: 'In Progress', count: 1, color: '#0052CC' },
      { status: 'Done', count: 0, color: '#36B37E' }
    ],
    memberChartData: {
      Backend: [
        { name: 'Andi (Backend)', todo: 1, inProgress: 1, done: 0 }
      ],
      Frontend: [],
      QA: []
    }
  }
];

export function SquadReport() {
  const [filters, setFilters] = useState({});

  const handleFilterChange = (issueKey, value) => {
    setFilters((prev) => ({
      ...prev,
      [issueKey]: value
    }));
  };

  // FUNGSI EXPORT DATA KE EXCEL
  const exportToExcel = () => {
    const formattedRows = [];

    MOCK_PARENT_ISSUES.forEach((issue) => {
      const currentFilter = filters[issue.key] || 'Squad';

      if (currentFilter === 'Squad') {
        const todoCount = issue.squadSummaryData.find((s) => s.status === 'To Do')?.count || 0;
        const inProgressCount = issue.squadSummaryData.find((s) => s.status === 'In Progress')?.count || 0;
        const doneCount = issue.squadSummaryData.find((s) => s.status === 'Done')?.count || 0;

        formattedRows.push({
          'Parent Issue': issue.title,
          'Tipe View': 'Squad (Semua Role)',
          'Nama / Kategori': 'Total Akumulasi Task',
          'To Do': todoCount,
          'In Progress': inProgressCount,
          'Done': doneCount,
          'Total Sub-Task': todoCount + inProgressCount + doneCount
        });
      } else {
        const members = issue.memberChartData[currentFilter] || [];
        members.forEach((mem) => {
          formattedRows.push({
            'Parent Issue': issue.title,
            'Tipe View': `Member (${currentFilter})`,
            'Nama / Kategori': mem.name,
            'To Do': mem.todo,
            'In Progress': mem.inProgress,
            'Done': mem.done,
            'Total Sub-Task': mem.todo + mem.inProgress + mem.done
          });
        });
      }
    });

    const worksheet = XLSX.utils.json_to_sheet(formattedRows);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, 'Squad Progress');

    const dateStr = new Date().toISOString().split('T')[0];
    XLSX.writeFile(workbook, `Squad_Progress_Report_${dateStr}.xlsx`);
  };

  return (
    <div style={{ padding: '24px', fontFamily: 'sans-serif', backgroundColor: '#FFFFFF' }}>
      {/* HEADER SECTION DENGAN TOMBOL EXPORT */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '24px'
        }}
      >
        <div>
          <h2 style={{ margin: 0 }}>📊 Reporting Progress Sub-Tasks Project</h2>
          <p style={{ color: '#6B778C', margin: '4px 0 0 0' }}>
            Data grafik berasal dari seluruh Sub-Task hasil validasi pada setiap Story/Task.
          </p>
        </div>

        <button
          onClick={exportToExcel}
          style={{
            backgroundColor: '#217346',
            color: '#FFFFFF',
            border: 'none',
            borderRadius: '4px',
            padding: '10px 16px',
            fontWeight: 'bold',
            fontSize: '14px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
          }}
        >
          📥 Export to Excel (.xlsx)
        </button>
      </div>

      {/* DAFTAR CARD DIAGRAM PER ISSUE */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        {MOCK_PARENT_ISSUES.map((issue) => {
          const currentFilter = filters[issue.key] || 'Squad';
          const isSquadView = currentFilter === 'Squad';
          const memberData = issue.memberChartData[currentFilter] || [];

          return (
            <div
              key={issue.key}
              style={{
                border: '1px solid #C1C7D0',
                borderRadius: '8px',
                padding: '20px',
                backgroundColor: '#FAFBFC',
                boxShadow: '0 1px 3px rgba(0,0,0,0.05)'
              }}
            >
              {/* HEADER CARD & FILTER */}
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: '16px',
                  borderBottom: '1px solid #DFE1E6',
                  paddingBottom: '12px'
                }}
              >
                <h4 style={{ margin: 0, color: '#091E42', fontSize: '16px' }}>
                  📌 {issue.title}
                </h4>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <label
                    htmlFor={`filter-${issue.key}`}
                    style={{ fontSize: '13px', fontWeight: 'bold', color: '#42526E' }}
                  >
                    Filter View:
                  </label>
                  <select
                    id={`filter-${issue.key}`}
                    value={currentFilter}
                    onChange={(e) => handleFilterChange(issue.key, e.target.value)}
                    style={{
                      padding: '6px 12px',
                      borderRadius: '4px',
                      border: '1px solid #A5ADBA',
                      fontSize: '13px',
                      cursor: 'pointer',
                      backgroundColor: '#FFFFFF',
                      fontWeight: '500'
                    }}
                  >
                    <option value="Squad">Squad (Semua Role)</option>
                    <option value="Frontend">Frontend</option>
                    <option value="Backend">Backend</option>
                    <option value="QA">QA</option>
                  </select>
                </div>
              </div>

              {/* RENDER DIAGRAM */}
              {!isSquadView && memberData.length === 0 ? (
                <div
                  style={{
                    padding: '24px',
                    textAlign: 'center',
                    color: '#6B778C',
                    backgroundColor: '#F4F5F7',
                    borderRadius: '4px'
                  }}
                >
                  Tidak ada sub-task / anggota pada filter <strong>{currentFilter}</strong> untuk task ini.
                </div>
              ) : (
                <div style={{ width: '100%', height: 250 }}>
                  <ResponsiveContainer>
                    {isSquadView ? (
                      /* TAMPILAN SQUAD (SEMUA ROLE): TOTAL TO DO, IN PROGRESS, DONE */
                      <BarChart data={issue.squadSummaryData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="status" />
                        <YAxis allowDecimals={false} />
                        <Tooltip />
                        <Bar dataKey="count" name="Jumlah Sub-Task" radius={[4, 4, 0, 0]}>
                          {issue.squadSummaryData.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                          ))}
                        </Bar>
                      </BarChart>
                    ) : (
                      /* TAMPILAN FILTER PER ROLE (FRONTEND/BACKEND/QA) PER MEMBER */
                      <BarChart data={memberData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="name" />
                        <YAxis allowDecimals={false} />
                        <Tooltip />
                        <Legend />
                        <Bar dataKey="todo" name="To Do" fill="#4C6B1F" />
                        <Bar dataKey="inProgress" name="In Progress" fill="#0052CC" />
                        <Bar dataKey="done" name="Done" fill="#36B37E" />
                      </BarChart>
                    )}
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}