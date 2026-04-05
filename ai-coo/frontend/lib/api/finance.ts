import { API_BASE } from '@/lib/api/config'
import type {
  FinanceStatus,
  FinanceSnapshot,
  FinanceTransaction,
  SpendingAnomaly,
  UploadResult,
} from '@/lib/types/finance'

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

export const financeApi = {
  getStatus: () =>
    request<FinanceStatus>('/api/finance/status'),

  getRunway: () =>
    request<{
      snapshot: FinanceSnapshot | null
      runway_months: number | null
      monthly_burn: number | null
      monthly_revenue: number | null
      net: number | null
      current_balance: number | null
      month: string | null
      message?: string
    }>('/api/finance/runway'),

  getSummary: () =>
    request<{
      summary: string
      snapshot: FinanceSnapshot | null
      anomalies: SpendingAnomaly[]
    }>('/api/finance/summary'),

  listTransactions: (params?: { limit?: number; category?: string; month?: string }) => {
    const q = new URLSearchParams()
    if (params?.limit)    q.set('limit', String(params.limit))
    if (params?.category) q.set('category', params.category)
    if (params?.month)    q.set('month', params.month)
    return request<{ transactions: FinanceTransaction[]; total: number }>(
      `/api/finance/transactions?${q}`,
    )
  },

  listSnapshots: (limit = 12) =>
    request<{ snapshots: FinanceSnapshot[]; total: number }>(
      `/api/finance/snapshots?limit=${limit}`,
    ),

  uploadCSV: (file: File, currentBalance?: number, replaceExisting = false) => {
    const form = new FormData()
    form.append('file', file)
    if (currentBalance !== undefined) form.append('current_balance', String(currentBalance))
    form.append('replace_existing', String(replaceExisting))
    return request<UploadResult>('/api/finance/upload', { method: 'POST', body: form })
  },

  chat: (message: string, history: { role: string; content: string }[]) =>
    request<{ reply: string }>('/api/finance/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, history }),
    }),
}
