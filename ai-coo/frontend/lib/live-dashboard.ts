'use client'

import { useCallback, useEffect, useState } from 'react'

import { API_BASE } from '@/lib/api/config'
import {
  activityFeed as mockActivityFeed,
  agents as mockAgents,
  type ActivityItem,
  type Agent,
  type AgentStatus,
} from '@/lib/mock-data'

type AgentStatusResponse = {
  agent: string
  status: string
  last_run?: string | null
  contacts?: number
  messages?: number
  checklist?: Record<string, number>
  total_items?: number
  next_deadline?: string | null
  documents?: Record<string, number>
  total_documents?: number
  total_commits?: number
  total_features?: number
  features?: Record<string, number>
  last_commit?: {
    sha: string | null
    branch: string | null
    summary: string | null
  } | null
}

type Notification = {
  id: string
  agent: string
  title: string
  body: string
  priority: string
  created_at: string | null
}

type Event = {
  id: string
  source_agent: string
  event_type: string
  payload: Record<string, unknown>
  summary: string
  priority: string
  timestamp: string | null
}

type Approval = {
  id: string
  agent: string
  action_type: string
  status: string
  created_at: string | null
}

type Commit = {
  sha: string
  author: string
  branch: string
  parsed_summary: string | null
  created_at: string | null
  timestamp: string | null
}

type CommandSummary = {
  topPriorities: string[]
  nextActions: string[]
  criticalRisks: string[]
}

export type LiveDashboardData = {
  agents: Agent[]
  activity: ActivityItem[]
  command: CommandSummary
  live: boolean
}

const fallbackCommand: CommandSummary = {
  topPriorities: [
    'Validate core value proposition with 5 user interviews',
    'Finalize tech stack decision and implementation order',
    'Review pending approvals before launching new workflows',
  ],
  nextActions: [
    'Review the latest agent outputs together',
    'Unblock any approvals or overdue tasks',
    'Confirm the next execution sequence across agents',
  ],
  criticalRisks: [
    'Key workflows still depend on manual review steps',
    'Some agent domains are partially implemented',
    'Backend integration quality depends on clean data in Supabase',
  ],
}

function timeAgo(iso: string | null) {
  if (!iso) return 'just now'
  const diff = Date.now() - new Date(iso).getTime()
  const s = Math.floor(diff / 1000)
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

function titleCase(value: string) {
  return value.replace(/[_-]/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())
}

function mapAgentNameToFrontendId(agentName: string) {
  const mapping: Record<string, string> = {
    pm: 'product-manager',
    dev_activity: 'engineer',
    research: 'research',
    marketing: 'marketing',
    legal: 'legal',
    finance: 'finance',
    outreach: 'outreach-agent',
    meeting: 'meeting-agent',
  }
  return mapping[agentName] ?? agentName
}

function summarizeActivityType(priority: string): ActivityItem['type'] {
  if (priority === 'urgent' || priority === 'high') return 'warning'
  if (priority === 'low') return 'success'
  return 'info'
}

async function requestJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

async function getLiveDashboardData(): Promise<LiveDashboardData> {
  const [
    pmStatus,
    devStatus,
    researchStatus,
    marketingStatus,
    legalStatus,
    financeStatus,
    outreachStatus,
    approvals,
    notifications,
    legalEvents,
    outreachEvents,
    commitsPayload,
  ] = await Promise.all([
    requestJson<AgentStatusResponse>('/api/pm/status'),
    requestJson<AgentStatusResponse>('/api/dev/status'),
    requestJson<AgentStatusResponse>('/api/research/status'),
    requestJson<AgentStatusResponse>('/api/marketing/status'),
    requestJson<AgentStatusResponse>('/api/legal/status'),
    requestJson<AgentStatusResponse>('/api/finance/status'),
    requestJson<AgentStatusResponse>('/api/outreach/status'),
    requestJson<Approval[]>('/api/approvals?status=pending'),
    requestJson<Notification[]>('/api/notifications?limit=12'),
    requestJson<Event[]>('/api/events?agent=legal&limit=12'),
    requestJson<Event[]>('/api/events?agent=outreach&limit=12'),
    requestJson<{ commits: Commit[] }>('/api/dev/commits?limit=8'),
  ])

  const pendingApprovals = approvals.filter((approval) => approval.status === 'pending')
  const legalOverdue = legalStatus.checklist?.overdue ?? 0
  const legalPending = legalStatus.checklist?.pending ?? 0
  const outreachContacts = outreachStatus.contacts ?? 0
  const outreachMessages = outreachStatus.messages ?? 0
  const devFeaturesShipped = devStatus.features?.shipped ?? 0

  const liveAgents: Agent[] = mockAgents.map((agent): Agent => {
    if (agent.id === 'product-manager') {
      const status: AgentStatus = pendingApprovals.length > 0 ? 'thinking' : 'idle'
      return {
        ...agent,
        status,
        outputs: [
          `${pendingApprovals.length} pending approval${pendingApprovals.length === 1 ? '' : 's'}`,
          pmStatus.last_run ? `Last run ${timeAgo(pmStatus.last_run)}` : 'No PM run recorded yet',
        ],
        tasks: pendingApprovals.length > 0
          ? ['Review queued approvals', 'Coordinate next execution pass', 'Watch recent system events']
          : agent.tasks,
        risks: pendingApprovals.length > 0
          ? [`${pendingApprovals.length} user decision${pendingApprovals.length === 1 ? '' : 's'} still blocking downstream work`]
          : agent.risks,
        recommendations: pendingApprovals.length > 0
          ? ['Clear approvals first so dependent agents can continue', 'Review outreach and legal decisions together']
          : agent.recommendations,
        summary: pendingApprovals.length > 0
          ? `PM is waiting on ${pendingApprovals.length} approval decision${pendingApprovals.length === 1 ? '' : 's'} before the next execution cycle.`
          : 'PM has no active backend state yet, so the dashboard is showing a passive coordination posture.',
      }
    }

    if (agent.id === 'engineer') {
      const status: AgentStatus = (devStatus.total_commits ?? 0) > 0 ? 'done' : 'idle'
      return {
        ...agent,
        status,
        outputs: [
          `${devStatus.total_commits ?? 0} parsed commit${(devStatus.total_commits ?? 0) === 1 ? '' : 's'}`,
          `${devFeaturesShipped} shipped feature${devFeaturesShipped === 1 ? '' : 's'}`,
        ],
        tasks: devStatus.last_commit?.summary
          ? [`Review latest commit: ${devStatus.last_commit.summary}`, 'Inspect feature map', 'Verify downstream PM/marketing event reactions']
          : agent.tasks,
        risks: (devStatus.total_commits ?? 0) === 0 ? ['No commit activity detected in backend yet'] : agent.risks,
        recommendations: devStatus.last_commit?.branch
          ? [`Latest branch: ${devStatus.last_commit.branch}`, 'Check whether shipped features should update messaging']
          : agent.recommendations,
        summary: devStatus.last_commit?.summary
          ? `Dev activity is live. Latest parsed change: ${devStatus.last_commit.summary}`
          : 'Dev activity endpoint is connected, but no parsed commits are available yet.',
      }
    }

    if (agent.id === 'legal') {
      const blocked = legalOverdue > 0
      const status: AgentStatus = blocked ? 'blocked' : (legalStatus.total_items ?? 0) > 0 ? 'thinking' : 'idle'
      return {
        ...agent,
        status,
        outputs: [
          `${legalStatus.total_items ?? 0} checklist item${(legalStatus.total_items ?? 0) === 1 ? '' : 's'}`,
          `${legalStatus.total_documents ?? 0} document draft${(legalStatus.total_documents ?? 0) === 1 ? '' : 's'}`,
        ],
        tasks: [
          `${legalPending} pending legal item${legalPending === 1 ? '' : 's'}`,
          blocked ? `Resolve ${legalOverdue} overdue item${legalOverdue === 1 ? '' : 's'}` : 'Track upcoming deadlines',
          'Review drafted legal documents',
        ],
        risks: blocked
          ? [`${legalOverdue} legal deadline${legalOverdue === 1 ? '' : 's'} overdue`]
          : legalPending > 0
            ? [`${legalPending} legal item${legalPending === 1 ? '' : 's'} still open`]
            : ['No legal blockers detected from backend state'],
        recommendations: blocked
          ? ['Handle overdue legal items before adding new launch work', 'Review the next deadline in the legal panel']
          : ['Keep document drafts moving through approval', 'Watch the next legal deadline'],
        summary: blocked
          ? `Legal is blocked by ${legalOverdue} overdue compliance item${legalOverdue === 1 ? '' : 's'}.`
          : (legalStatus.total_items ?? 0) > 0
            ? `Legal tracking is live with ${legalStatus.total_items} checklist items and ${legalStatus.total_documents ?? 0} stored documents.`
            : 'Legal backend is connected but no checklist items exist yet.',
      }
    }

    if (agent.id === 'outreach-agent') {
      const recentReply = outreachEvents.find((event) => event.event_type === 'reply_received')
      const recentObjection = outreachEvents.find((event) => event.event_type === 'objection_heard')
      const status: AgentStatus = pendingApprovals.some((approval) => approval.agent === 'outreach')
        ? 'thinking'
        : outreachMessages > 0
          ? 'done'
          : 'idle'
      return {
        ...agent,
        status,
        outputs: [
          `${outreachContacts} contact${outreachContacts === 1 ? '' : 's'} in pipeline`,
          `${outreachMessages} message${outreachMessages === 1 ? '' : 's'} drafted or sent`,
        ],
        tasks: pendingApprovals.some((approval) => approval.agent === 'outreach')
          ? ['Review pending outreach approvals', 'Send approved drafts', 'Monitor replies']
          : ['Research new contacts', 'Draft new outbound messages', 'Track reply quality'],
        risks: recentObjection
          ? [String(recentObjection.payload.objection_text ?? 'Recent objection heard in outreach')]
          : outreachContacts === 0
            ? ['No researched outreach contacts in the pipeline yet']
            : agent.risks,
        recommendations: recentReply
          ? [`Follow up on ${String(recentReply.payload.contact_name ?? 'the latest reply')}`, 'Update pitch with response learnings']
          : ['Use research briefs to sharpen personalization', 'Push approved follow-ups quickly'],
        summary: recentReply
          ? `Outreach is live. Latest meaningful signal: ${recentReply.summary}`
          : `Outreach backend is connected with ${outreachContacts} contact${outreachContacts === 1 ? '' : 's'} and ${outreachMessages} message${outreachMessages === 1 ? '' : 's'}.`,
      }
    }

    if (agent.id === 'research') {
      const status: AgentStatus = researchStatus.status === 'idle' ? 'idle' : 'thinking'
      return {
        ...agent,
        status,
        summary: 'Research backend status is connected, but detailed findings are not yet surfaced in the dashboard.',
      }
    }

    if (agent.id === 'marketing') {
      const status: AgentStatus = marketingStatus.status === 'idle' ? 'idle' : 'thinking'
      return {
        ...agent,
        status,
        summary: 'Marketing backend status is connected, but published content summaries are not yet surfaced here.',
      }
    }

    if (agent.id === 'finance') {
      const status: AgentStatus = financeStatus.status === 'idle' ? 'idle' : 'thinking'
      return {
        ...agent,
        status,
        summary: 'Finance backend status is connected, but runway and anomaly data are not yet surfaced in this dashboard.',
      }
    }

    return agent
  })

  const activity = [
    ...notifications.map((notification) => ({
      id: `notif:${notification.id}`,
      sortKey: notification.created_at ?? '0',
      item: {
        id: `notif:${notification.id}`,
        agent: titleCase(notification.agent),
        message: notification.title,
        timestamp: timeAgo(notification.created_at),
        type: summarizeActivityType(notification.priority),
      } satisfies ActivityItem,
    })),
    ...legalEvents.map((event) => ({
      id: `legal:${event.id}`,
      sortKey: event.timestamp ?? '0',
      item: {
        id: `legal:${event.id}`,
        agent: 'Legal',
        message: event.summary,
        timestamp: timeAgo(event.timestamp),
        type: summarizeActivityType(event.priority),
      } satisfies ActivityItem,
    })),
    ...outreachEvents.map((event) => ({
      id: `outreach:${event.id}`,
      sortKey: event.timestamp ?? '0',
      item: {
        id: `outreach:${event.id}`,
        agent: 'Outreach Agent',
        message: event.summary,
        timestamp: timeAgo(event.timestamp),
        type: summarizeActivityType(event.priority),
      } satisfies ActivityItem,
    })),
    ...commitsPayload.commits.map((commit) => ({
      id: `commit:${commit.sha}`,
      sortKey: commit.created_at ?? commit.timestamp ?? '0',
      item: {
        id: `commit:${commit.sha}`,
        agent: 'Engineer',
        message: commit.parsed_summary ?? `Processed commit ${commit.sha.slice(0, 7)}`,
        timestamp: timeAgo(commit.created_at ?? commit.timestamp),
        type: 'success' as const,
      },
    })),
  ]
    .sort((a, b) => (a.sortKey < b.sortKey ? 1 : -1))
    .slice(0, 8)
    .map((entry) => entry.item)

  const blockedAgents = liveAgents.filter((agent) => agent.status === 'blocked')
  const command: CommandSummary = {
    topPriorities: [
      pendingApprovals.length > 0 ? `Review ${pendingApprovals.length} pending approval${pendingApprovals.length === 1 ? '' : 's'}` : null,
      legalOverdue > 0 ? `Resolve ${legalOverdue} overdue legal item${legalOverdue === 1 ? '' : 's'}` : null,
      outreachContacts > 0 ? `Convert ${outreachContacts} outreach contact${outreachContacts === 1 ? '' : 's'} into qualified conversations` : null,
      devStatus.last_commit?.summary ? `Assess latest shipped work: ${devStatus.last_commit.summary}` : null,
    ].filter((item): item is string => Boolean(item)).slice(0, 3),
    nextActions: [
      pendingApprovals.some((approval) => approval.agent === 'outreach') ? 'Approve or reject queued outreach drafts' : null,
      legalStatus.next_deadline ? `Review legal deadline on ${legalStatus.next_deadline}` : null,
      notifications[0] ? `Check newest notification: ${notifications[0].title}` : null,
      commitsPayload.commits[0]?.parsed_summary ? 'Verify downstream messaging after the latest commit' : null,
    ].filter((item): item is string => Boolean(item)).slice(0, 3),
    criticalRisks: [
      ...blockedAgents.map((agent) => `${agent.name}: ${agent.risks[0]}`),
      pendingApprovals.length > 0 ? `${pendingApprovals.length} pending approval${pendingApprovals.length === 1 ? '' : 's'} can stall downstream execution` : null,
      legalOverdue === 0 && blockedAgents.length === 0 ? 'No hard blockers detected from current backend state' : null,
    ].filter((item): item is string => Boolean(item)).slice(0, 3),
  }

  return {
    agents: liveAgents,
    activity: activity.length > 0 ? activity : mockActivityFeed,
    command: {
      topPriorities: command.topPriorities.length > 0 ? command.topPriorities : fallbackCommand.topPriorities,
      nextActions: command.nextActions.length > 0 ? command.nextActions : fallbackCommand.nextActions,
      criticalRisks: command.criticalRisks.length > 0 ? command.criticalRisks : fallbackCommand.criticalRisks,
    },
    live: true,
  }
}

export function useLiveDashboardData() {
  const [data, setData] = useState<LiveDashboardData>({
    agents: mockAgents,
    activity: mockActivityFeed,
    command: fallbackCommand,
    live: false,
  })
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const nextData = await getLiveDashboardData()
      setData(nextData)
    } catch {
      setData({
        agents: mockAgents,
        activity: mockActivityFeed,
        command: fallbackCommand,
        live: false,
      })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    const interval = window.setInterval(() => {
      refresh().catch(() => {})
    }, 20000)
    return () => window.clearInterval(interval)
  }, [refresh])

  return { data, loading, refresh }
}
