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

export const pmApi = {
  getTasks: (params?: { status?: string; limit?: number }) => {
    const qs = new URLSearchParams()
    if (params?.status) qs.set('status', params.status)
    if (params?.limit) qs.set('limit', String(params.limit))
    return request<PMTask[]>(`/api/pm/tasks?${qs}`)
  },

  deleteTask: (taskId: string) =>
    request<void>(`/api/pm/tasks/${taskId}`, { method: 'DELETE' }),

  chat: (message: string, history: { role: string; content: string }[]) =>
    request<{ reply: string; tasks_created: PMTask[]; tasks_deleted: string[] }>('/api/pm/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, history }),
    }),
}

export interface PMTask {
  id: string
  title: string
  description: string | null
  status: 'pending_approval' | 'todo' | 'in_progress' | 'done' | 'blocked'
  priority_score: number
  priority_reason: string | null
  source_agent: string | null
  assigned_agent: string | null
  created_at: string | null
  completed_at: string | null
}
