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

export const marketingApi = {
  chat: (message: string, history: { role: string; content: string }[]) =>
    request<{ reply: string; posts_drafted: MarketingPost[] }>('/api/marketing/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, history }),
    }),

  getContent: (status = 'pending_approval', limit = 20) =>
    request<{ content: MarketingPost[]; count: number }>(
      `/api/marketing/content?status=${status}&limit=${limit}`
    ),

  getTrends: (limit = 15) =>
    request<{ trends: MarketingTrend[]; count: number }>(
      `/api/marketing/trends?limit=${limit}`
    ),

  getStatus: () =>
    request<{ agent: string; status: string; pending_posts: number; published_posts: number; trends_tracked: number }>(
      '/api/marketing/status'
    ),
}

export interface MarketingPost {
  id: string
  platform: string
  body: string
  content_type: string | null
  status: 'draft' | 'pending_approval' | 'published' | 'rejected'
  published_url: string | null
  published_at: string | null
  created_at: string | null
}

export interface MarketingTrend {
  id: string
  platform: string
  url: string | null
  topic: string
  relevance_score: number
  original_content: string
  suggested_action: string | null
  found_at: string | null
  created_at: string | null
}
