export const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

export const fetchApi = async (url: string, options: RequestInit = {}) => {
  const res = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => null);
    throw new Error(errorData?.detail || `API Error: ${res.status}`);
  }
  return res.json();
};

export const postApi = (url: string, data: any) =>
  fetchApi(url, { method: 'POST', body: JSON.stringify(data) });

export const putApi = (url: string, data: any) =>
  fetchApi(url, { method: 'PUT', body: JSON.stringify(data) });
