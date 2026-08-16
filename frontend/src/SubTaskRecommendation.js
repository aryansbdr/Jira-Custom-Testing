import React, { useState, useEffect } from 'react';
<<<<<<< HEAD
import { invoke, view, router } from '@forge/bridge'; 
=======
import { invoke, router } from '@forge/bridge'; 
>>>>>>> 2239c07801b0fec768ead33c87ffa76895523331

export default function SubTaskRecommendation({ issueKey }) {
  const [recommendations, setRecommendations] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    async function fetchRecs() {
      setLoading(true);
      const res = await invoke('getIssueRecommendations', { issueKey });
      setRecommendations(res || []);
      setLoading(false);
    }
    fetchRecs();
  }, [issueKey]);

  const toggleSelect = (id) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]
    );
  };

  const handleValidate = async () => {
    setSubmitting(true);
    const tasksToCreate = recommendations.filter((r) => selectedIds.includes(r.id));
    
    const res = await invoke('createSubtasks', {
      parentKey: issueKey,
      subtasks: tasksToCreate,
    });

    if (res.success) {
      alert(`Berhasil menambahkan ${res.createdKeys.length} Sub-Task ke ${issueKey}!`);
<<<<<<< HEAD

      setRecommendations((prev) =>
        prev.filter((r) => !selectedIds.includes(r.id))
      );

      setSelectedIds([]);

  // Tunggu Jira selesai commit issue
      await new Promise((resolve) => setTimeout(resolve, 1000));

  // Reload halaman Jira
      await router.reload();
    }
    
=======
      
      setRecommendations((prev) => prev.filter((r) => !selectedIds.includes(r.id)));
      setSelectedIds([]);

      await router.reload();
    } else {
      alert('Gagal membuat sub-task');
    }
>>>>>>> 2239c07801b0fec768ead33c87ffa76895523331
    setSubmitting(false);
  };

  if (loading) return <div>Memuat rekomendasi sub-task...</div>;

  return (
    <div style={{ padding: 8 }}>
      <p style={{ fontWeight: 'bold', fontSize: 13, marginBottom: 8 }}>
        Rekomendasi Sub-Task untuk {issueKey}:
      </p>

      {recommendations.length === 0 ? (
        <p style={{ color: '#6B778C', fontSize: 12 }}>Tidak ada rekomendasi tersisa.</p>
      ) : (
        <>
          {recommendations.map((item) => (
            <div key={item.id} style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
              <input
                type="checkbox"
                id={item.id}
                checked={selectedIds.includes(item.id)}
                onChange={() => toggleSelect(item.id)}
              />
              <label htmlFor={item.id} style={{ fontSize: 12, cursor: 'pointer' }}>
                {item.summary}
              </label>
            </div>
          ))}

          <button
            onClick={handleValidate}
            disabled={submitting || selectedIds.length === 0}
            style={{
              marginTop: 8,
              width: '100%',
              padding: '6px 12px',
              backgroundColor: '#0052CC',
              color: '#fff',
              border: 'none',
              borderRadius: 3,
              cursor: 'pointer',
            }}
          >
            {submitting ? 'Membuat...' : `Validasi & Buat (${selectedIds.length}) Sub-Task`}
          </button>
        </>
      )}
    </div>
  );
}