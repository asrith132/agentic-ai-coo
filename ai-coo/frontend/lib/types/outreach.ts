export interface OutreachContact {
  id: string
  name: string
  email: string | null
  company: string
  role: string | null
  contact_type: string
  status: string
  source: string | null
  research_cache: Record<string, unknown>
  notes: string | null
  last_contacted_at: string | null
  next_followup_at: string | null
  created_at: string | null
}

export interface OutreachMessage {
  id: string
  contact_id: string
  direction: 'sent' | 'received'
  subject: string | null
  body: string
  channel: string
  status: string
  template_used: string | null
  approval_id: string | null
  sent_at: string | null
  created_at: string | null
}

export interface OutreachApproval {
  id: string
  agent: string
  action_type: string
  content: Record<string, unknown>
  status: string
  user_edits?: Record<string, unknown> | null
  created_at: string | null
  resolved_at?: string | null
}

export interface OutreachEvent {
  id: string
  source_agent: string
  event_type: string
  payload: Record<string, unknown>
  summary: string
  priority: string
  timestamp: string | null
}

export interface OutreachStatus {
  agent: string
  status: string
  contacts: number
  messages: number
}

export interface ResearchContactPayload {
  name: string
  company: string
  context?: string
  source?: string
  status?: string
  contact_type?: string
}

export interface ResearchContactResult {
  contact: OutreachContact
  research_brief: string
}

export interface DraftEmailPayload {
  contact_id: string
  email_type: 'cold' | 'follow_up' | 'investor' | 'partnership'
  custom_notes?: string
  channel?: 'email' | 'linkedin_dm' | 'reddit_dm' | 'x_dm' | 'unknown'
}

export interface DraftEmailResult {
  message: OutreachMessage
  approval: OutreachApproval
}

export interface DiscoverContactsPayload {
  focus?: string
  limit?: number
  contact_type?: string
  auto_research?: boolean
}

export interface DiscoverContactsResult {
  prospects: Array<{
    contact: OutreachContact
    why_fit?: string
    outreach_angle?: string
    priority_score?: number
    reachable_via?: string
  }>
}

export interface SendOutreachResult {
  message: OutreachMessage
  send_result: {
    mode: string
    status: string
    provider_message_id: string | null
    detail: string
  }
}
