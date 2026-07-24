import React, { useState } from 'react';
import * as XLSX from 'xlsx'; // 👈 1. Import library XLSX
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';

// ==========================================================
// MOCK DATA (Data Report)
// ==========================================================
const MOCK_PARENT_ISSUES = [
  {
    key: 'SCRUM-1',
    title: 'Task 1 (SCRUM-1)',
    squadChartData: [
      { name: 'Backend', todo: 1, inProgress: 0, done: 0 },
      { name: 'Frontend', todo: 2, inProgress: 0, done: 0 }
    ],
    memberChartData: {
      Backend: [{ name: 'Budi (Backend)', todo: 1, inProgress: 0, done: 0 }],
      Frontend: [
        { name: 'Siti (Frontend)', todo: 1, inProgress: 0, done: 0 },
        { name: 'Rian (Frontend)', todo: 1, inProgress: 0, done: 0 }
      ],
      QA: []
    }
  },
  {
    key: 'SCRUM-2',
    title: 'Task 2 (SCRUM-2)',
    squadChartData: [
      { name: 'Backend', todo: 5, inProgress: 2, done: 1 },
      { name: 'Frontend', todo: 6, inProgress: 1, done: 2 },
      { name: 'QA', todo: 2, inProgress: 0, done: 0 }
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
      QA: [{ name: 'Dewi (QA)', todo: 2, inProgress: 0, done: 0 }]
    }
  },
  {
    key: 'SCRUM-26',
    title: 'Team 3 (SCRUM-26)',
    squadChartData: [
      { name: 'Backend', todo: 1, inProgress: 1, done: 0 }
    ],
    memberChartData: {
      Backend: [{ name: 'Andi (Backend)', todo: 1, inProgress: 1, done: 0 }],
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

  // 👈 2. FUNGSI UNTUK EXPORT DATA KE EXCEL
  const exportToExcel = () => {
    const formattedRows = [];

    // Merapikan data agar menjadi baris-baris tabel Excel yang rapi
    MOCK_PARENT_ISSUES.forEach((issue) => {
      const currentFilter = filters[issue.key] || 'Squad';

      if (currentFilter === 'Squad') {
        issue.squadChartData.forEach((sq) => {
          formattedRows.push({
            'Parent Issue': issue.title,
            'Tipe View': 'Squad Summary',
            'Squad / Nama Member': sq.name,
            'To Do': sq.todo,
            'In Progress': sq.inProgress,
            'Done': sq.done,
            'Total Sub-Task': sq.todo + sq.inProgress + sq.done
          });
        });
      } else {
        const members = issue.memberChartData[currentFilter] || [];
        members.forEach((mem) => {
          formattedRows.push({
            'Parent Issue': issue.title,
            'Tipe View': `Member Filter (${currentFilter})`,
            'Squad / Nama Member': mem.name,
            'To Do': mem.todo,
            'In Progress': mem.inProgress,
            'Done': mem.done,
            'Total Sub-Task': mem.todo + mem.inProgress + mem.done
          });
        });
      }
    });

    // Buat Worksheet & Workbook
    const worksheet = XLSX.utils.json_to_sheet(formattedRows);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, 'Squad Progress');

    // Generate tanggal untuk nama file
    const dateStr = new Date().toISOString().split('T')[0];
    
    // Download File Excel
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
          <h2 style={{ margin: 0 }}> Reporting Progress Sub-Tasks Project</h2>
          <p style={{ color: '#6B778C', margin: '4px 0 0 0' }}>
            Data grafik berasal dari seluruh Sub-Task hasil validasi pada setiap Story/Task.
          </p>
        </div>

        {/* 👈 3. TOMBOL EXPORT EXCEL */}
        <button
          onClick={exportToExcel}
          style={{
            backgroundColor: '#217346', // Warna Hijau khas Excel
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
           Export to Excel (.xlsx)
        </button>
      </div>

      {/* DAFTAR CARD DIAGRAM PER ISSUE */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        {MOCK_PARENT_ISSUES.map((issue) => {
          const currentFilter = filters[issue.key] || 'Squad';
          const chartData =
            currentFilter === 'Squad'
              ? issue.squadChartData
              : issue.memberChartData[currentFilter] || [];

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
                   {issue.title}
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

              {chartData.length === 0 ? (
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
                    <BarChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="name" />
                      <YAxis allowDecimals={false} />
                      <Tooltip />
                      <Legend />
                      <Bar dataKey="todo" name="To Do" fill="#4C6B1F" />
                      <Bar dataKey="inProgress" name="In Progress" fill="#0052CC" />
                      <Bar dataKey="done" name="Done" fill="#36B37E" />
                    </BarChart>
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