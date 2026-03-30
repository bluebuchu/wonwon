const BASE = `${import.meta.env.VITE_API_URL || ''}/api`;

export async function fetchLatestIssues() {
  const res = await fetch(`${BASE}/issues/latest`);
  if (!res.ok) throw new Error('이슈 데이터를 불러오지 못했습니다.');
  return res.json(); // { issues, total, week_date }
}

export async function generateIssues() {
  const res = await fetch(`${BASE}/generate`, { method: 'POST' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || '생성에 실패했습니다.');
  }
  return res.json(); // { status, count, week_date }
}
