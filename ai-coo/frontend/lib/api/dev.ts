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

export const devApi = {
  listCommits: (limit = 20, branch?: string) =>
    request<{ commits: Commit[]; total: number }>(
      `/api/dev/commits?limit=${limit}${branch ? `&branch=${encodeURIComponent(branch)}` : ''}`,
    ),

  listFeatures: (status?: string) =>
    request<{ features: Feature[]; total: number }>(
      `/api/dev/features${status ? `?status=${encodeURIComponent(status)}` : ''}`,
    ),

  getStatus: () =>
    request<DevStatus>('/api/dev/status'),

  chat: (message: string, history: { role: string; content: string }[]) =>
    request<{ reply: string }>('/api/dev/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, history }),
    }),
}

export interface Commit {
  id?: string
  sha: string
  message: string
  author: string
  branch: string
  timestamp: string | null
  parsed_summary: string | null
  commit_type: string | null
  features_referenced: string[] | null
  created_at: string | null
}

export interface Feature {
  id?: string
  feature_name: string
  description: string | null
  status: string
  shipped_at: string | null
  related_commits: string[] | null
}

export interface DevStatus {
  agent: string
  status: string
  total_commits: number
  features: Record<string, number>
  total_features: number
  last_commit: { sha: string | null; branch: string | null; summary: string | null } | null
}
