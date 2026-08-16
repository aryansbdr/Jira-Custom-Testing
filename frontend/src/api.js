const BASE_URL = 'https://four-algorithm-permits-lover.trycloudflare.com';

// 1. Ambil info & deskripsi Epic
export const getEpicInfo = async (epicKey) => {
  try {
    const response = await fetch(`${BASE_URL}/api/v1/epicInfo?epic_key=${epicKey}`);
    if (!response.ok) throw new Error('Gagal mengambil data Epic');
    return await response.json();
  } catch (error) {
    console.error('API Error:', error);
    return null;
  }
};

// 2. Request AI untuk Generate Sub-Task berdasarkan Deskripsi
export const generateSubTasks = async (epicDescription) => {
  try {
    const response = await fetch(`${BASE_URL}/api/v1/generate-subtasks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ description: epicDescription }),
    });
    if (!response.ok) throw new Error('Gagal merekomendasikan sub-task');
    return await response.json();
  } catch (error) {
    console.error('API Error:', error);
    return null;
  }
};