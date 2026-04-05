import { API_BASE } from '@/lib/api/config'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init)
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const data = await res.json()
      detail = typeof data?.detail === 'string' ? data.detail : detail
    } catch {}
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export const legalApi = {
  chat: (message: string, history: { role: string; content: string }[]) =>
    request<{ reply: string }>('/api/legal/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, history }),
    }),

  uploadFile: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return fetch(`${API_BASE}/api/legal/upload`, { method: 'POST', body: form })
      .then(r => r.ok ? r.json() : r.json().then(d => Promise.reject(new Error(d.detail))))
  },
}
