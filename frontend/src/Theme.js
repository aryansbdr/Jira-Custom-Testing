// ============================================================
// THEME — Sentralisasi warna untuk SquadReport & komponen turunannya
// ============================================================
//
// Semua warna di sini dipakai sebagai fallback dari CSS variable Jira,
// contoh: `var(--ds-surface-overlay, ${THEME.surface.overlay})`.
// Kalau suatu saat mau ganti skema warna dashboard, cukup ubah di sini
// — tidak perlu cari-ganti manual di banyak file.

export const THEME = {
  surface: {
    base: '#1D2125',
    overlay: '#22272B',
    raised: '#282E33',
    sunken: '#1B1F23',
    neutralSubtle: '#161A1D',
  },

  border: {
    default: '#333C48',
    subtle: '#2C333A',
    input: '#3B444C',
  },

  text: {
    primary: '#DCDFE4',
    subtle: '#8C9BAB',
    subtleAlt: '#5E6C84',
    brand: '#579DFF',
    onBold: '#FFFFFF',
  },

  brand: {
    primary: '#0052CC',
    dark: '#0747A6',
  },

  status: {
    success: '#36B37E',
    successStrong: '#00875A',
    successText: '#7EE2B8',
    warning: '#FFAB00',
    danger: '#FF5630',
    dangerStrong: '#DE350B',
    info: '#00B8D9',
    infoText: '#85B8FF',
  },

  // Warna slice pie chart per developer (To Do / In Progress / Done)
  chart: {
    todo: '#7A869A',
    inProgress: '#579DFF',
    done: '#36B37E',
  },

  // Palet warna avatar developer (dipilih berdasarkan hash nama)
  avatarPalette: ['#0052CC', '#00875A', '#6554C0', '#FF5630', '#FFAB00', '#00B8D9', '#36B37E'],
};

export default THEME;