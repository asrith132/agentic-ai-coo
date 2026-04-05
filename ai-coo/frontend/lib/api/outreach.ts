import type {
  DiscoverContactsPayload,
  DiscoverContactsResult,
  DraftEmailPayload,
  DraftEmailResult,
  OutreachApproval,
  OutreachContact,
  OutreachEvent,
  OutreachMessage,
  OutreachStatus,
  ResearchContactPayload,
  ResearchContactResult,
  SendOutreachResult,
} from '@/lib/types/outreach'
import { API_BASE } from '@/lib/api/config'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })

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

export const outreachApi = {
  getStatus: () => request<OutreachStatus>('/api/outreach/status'),
  listContacts: (status?: string, limit = 50) =>
    request<OutreachContact[]>(
      `/api/outreach/contacts?limit=${limit}${status ? `&status=${encodeURIComponent(status)}` : ''}`,
    ),
  listMessages: (contactId?: string, limit = 50) =>
    request<OutreachMessage[]>(
      `/api/outreach/messages?limit=${limit}${contactId ? `&contact_id=${encodeURIComponent(contactId)}` : ''}`,
    ),
  researchContact: (payload: ResearchContactPayload) =>
    request<ResearchContactResult>('/api/outreach/research', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  draftEmail: (payload: DraftEmailPayload) =>
    request<DraftEmailResult>('/api/outreach/draft', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  discoverContacts: (payload: DiscoverContactsPayload) =>
    request<DiscoverContactsResult>('/api/outreach/discover', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  sendMessage: (messageId: string) =>
    request<SendOutreachResult>(`/api/outreach/send/${messageId}`, {
      method: 'POST',
    }),
  listApprovals: (status = 'pending') =>
    request<OutreachApproval[]>(`/api/approvals?status=${encodeURIComponent(status)}&agent=outreach`),
  decideApproval: (
    approvalId: string,
    status: 'approved' | 'rejected',
    edits?: Record<string, unknown>,
  ) =>
    request<OutreachApproval>(`/api/approvals/${approvalId}/respond`, {
      method: 'POST',
      body: JSON.stringify({ status, edits }),
    }),
  listEvents: (limit = 20) =>
    request<OutreachEvent[]>(`/api/events?agent=outreach&limit=${limit}`),
}
