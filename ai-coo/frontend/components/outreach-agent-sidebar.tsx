'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Check,
  ChevronDown,
  ChevronUp,
  Eye,
  Loader2,
  Mail,
  Radar,
  RefreshCw,
  Search,
  Send,
  Sparkles,
  Users,
  X,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { outreachApi } from '@/lib/api/outreach'
import type {
  DiscoverContactsResult,
  OutreachApproval,
  OutreachContact,
  OutreachEvent,
  OutreachMessage,
  OutreachStatus,
  ResearchContactResult,
} from '@/lib/types/outreach'
import { cn } from '@/lib/utils'

type Tab = 'contacts' | 'messages' | 'actions' | 'activity'

function timeAgo(iso: string | null) {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const s = Math.floor(diff / 1000)
  if (s < 3600) return `${Math.max(1, Math.floor(s / 60))}m ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

function formatLabel(value: string) {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())
}

function getString(value: unknown) {
  return typeof value === 'string' && value.trim() ? value : null
}

function getStringArray(value: unknown) {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0) : []
}

function statusBadge(status: string) {
  const key = status.toLowerCase()
  if (key === 'sent' || key === 'approved' || key === 'replied' || key === 'converted') {
    return 'text-emerald-400 border-emerald-400/30 bg-emerald-400/8'
  }
  if (key === 'pending_approval' || key === 'draft' || key === 'thinking') {
    return 'text-warning border-warning/30 bg-warning/8'
  }
  if (key === 'rejected' || key === 'blocked' || key === 'negative') {
    return 'text-destructive border-destructive/30 bg-destructive/8'
  }
  return 'text-muted-foreground border-border/50 bg-secondary/30'
}

function eventBadge(eventType: string) {
  if (eventType === 'reply_received') return 'text-primary border-primary/30 bg-primary/8'
  if (eventType === 'lead_converted') return 'text-emerald-400 border-emerald-400/30 bg-emerald-400/8'
  if (eventType === 'objection_heard') return 'text-warning border-warning/30 bg-warning/8'
  if (eventType === 'outreach_sent') return 'text-sky-400 border-sky-400/30 bg-sky-400/8'
  return 'text-muted-foreground border-border/50 bg-secondary/30'
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="mb-3 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/70">
      {children}
    </h4>
  )
}

function TabButton({
  active,
  onClick,
  label,
  icon,
}: {
  active: boolean
  onClick: () => void
  label: string
  icon: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[11px] font-medium transition-colors cursor-pointer',
        active
          ? 'bg-background text-foreground shadow-sm'
          : 'text-muted-foreground hover:bg-secondary/40 hover:text-foreground',
      )}
    >
      {icon}
      {label}
    </button>
  )
}

function EmptyState({ label }: { label: string }) {
  return <div className="py-8 text-center text-[11px] text-muted-foreground/50">{label}</div>
}

interface OutreachAgentSidebarProps {
  rgb: string
  color: string
}

export function OutreachAgentSidebar({ rgb, color }: OutreachAgentSidebarProps) {
  const [tab, setTab] = useState<Tab>('contacts')
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [status, setStatus] = useState<OutreachStatus | null>(null)
  const [contacts, setContacts] = useState<OutreachContact[]>([])
  const [messages, setMessages] = useState<OutreachMessage[]>([])
  const [approvals, setApprovals] = useState<OutreachApproval[]>([])
  const [events, setEvents] = useState<OutreachEvent[]>([])
  const [selectedContactId, setSelectedContactId] = useState('')
  const [feedback, setFeedback] = useState('')
  const [submitting, setSubmitting] = useState<string | null>(null)
  const [latestResearch, setLatestResearch] = useState<ResearchContactResult | null>(null)
  const [latestDiscover, setLatestDiscover] = useState<DiscoverContactsResult | null>(null)
  const [showApprovedApprovals, setShowApprovedApprovals] = useState(false)
  const [expandedMessageId, setExpandedMessageId] = useState<string | null>(null)
  const [expandedApprovalId, setExpandedApprovalId] = useState<string | null>(null)
  const [approvalDrafts, setApprovalDrafts] = useState<Record<string, { subject: string; body: string; comment: string }>>({})

  const [researchForm, setResearchForm] = useState({
    name: '',
    company: '',
    context: '',
    contact_type: 'customer',
  })
  const [draftForm, setDraftForm] = useState({
    contact_id: '',
    email_type: 'cold',
    custom_notes: '',
    channel: 'email',
  })
  const [discoverForm, setDiscoverForm] = useState({
    focus: '',
    limit: 5,
    contact_type: 'customer',
    auto_research: true,
  })

  const loadData = useCallback(async () => {
    const [nextStatus, nextContacts, nextMessages, pendingApprovals, approvedApprovals, nextEvents] =
      await Promise.all([
        outreachApi.getStatus(),
        outreachApi.listContacts(undefined, 100),
        outreachApi.listMessages(undefined, 100),
        outreachApi.listApprovals('pending'),
        outreachApi.listApprovals('approved'),
        outreachApi.listEvents(30),
      ])

    setStatus(nextStatus)
    setContacts(nextContacts)
    setMessages(nextMessages)
    setApprovals([...pendingApprovals, ...approvedApprovals])
    setEvents(nextEvents)

    setSelectedContactId((current) => {
      if (current && nextContacts.some((contact) => contact.id === current)) return current
      return nextContacts[0]?.id ?? ''
    })
    setDraftForm((current) => ({
      ...current,
      contact_id: current.contact_id && nextContacts.some((contact) => contact.id === current.contact_id)
        ? current.contact_id
        : nextContacts[0]?.id ?? '',
    }))
  }, [])

  useEffect(() => {
    let cancelled = false

    ;(async () => {
      setLoading(true)
      setFeedback('')
      try {
        await loadData()
      } catch (error) {
        if (!cancelled) {
          setFeedback(error instanceof Error ? error.message : 'Failed to load outreach data')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [loadData])

  useEffect(() => {
    const interval = window.setInterval(() => {
      loadData().catch(() => {})
    }, 15000)

    return () => window.clearInterval(interval)
  }, [loadData])

  const refreshAll = useCallback(async () => {
    setRefreshing(true)
    setFeedback('')
    try {
      await loadData()
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : 'Refresh failed')
    } finally {
      setRefreshing(false)
    }
  }, [loadData])

  const contactsById = useMemo(() => new Map(contacts.map((contact) => [contact.id, contact])), [contacts])
  const approvalsById = useMemo(() => new Map(approvals.map((approval) => [approval.id, approval])), [approvals])

  const selectedContact = selectedContactId ? contactsById.get(selectedContactId) ?? null : null

  const filteredMessages = useMemo(
    () => messages.filter((message) => !selectedContactId || message.contact_id === selectedContactId),
    [messages, selectedContactId],
  )

  const sortedMessages = useMemo(
    () =>
      [...filteredMessages].sort((a, b) => {
        const aKey = a.sent_at ?? a.created_at ?? ''
        const bKey = b.sent_at ?? b.created_at ?? ''
        return aKey < bKey ? 1 : -1
      }),
    [filteredMessages],
  )

  const pendingApprovals = useMemo(
    () => approvals.filter((approval) => approval.status === 'pending'),
    [approvals],
  )

  const approvedApprovals = useMemo(
    () => approvals.filter((approval) => approval.status === 'approved'),
    [approvals],
  )

  const selectedContactSignals = useMemo(() => {
    const cache = selectedContact?.research_cache ?? {}
    return {
      brief: getString(cache.brief),
      reachableVia: getStringArray(cache.reachable_via),
      profiles: getStringArray(cache.profiles),
      recentPosts: getStringArray(cache.recent_posts),
      talkingPoints: getStringArray(cache.talking_points),
    }
  }, [selectedContact])

  const getApprovalDraft = useCallback((approval: OutreachApproval) => {
    const current = approvalDrafts[approval.id]
    if (current) return current
    return {
      subject: getString(approval.content.subject) ?? '',
      body: getString(approval.content.body) ?? getString(approval.content.preview) ?? '',
      comment: '',
    }
  }, [approvalDrafts])

  const handleResearch = async () => {
    setSubmitting('research')
    setFeedback('')
    try {
      const result = await outreachApi.researchContact({
        name: researchForm.name,
        company: researchForm.company,
        context: researchForm.context || undefined,
        contact_type: researchForm.contact_type,
      })
      setLatestResearch(result)
      setSelectedContactId(result.contact.id)
      setDraftForm((current) => ({ ...current, contact_id: result.contact.id }))
      setResearchForm((current) => ({ ...current, name: '', company: '', context: '' }))
      setFeedback(`Researched ${result.contact.name} and saved the targeting brief.`)
      await loadData()
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : 'Research failed')
    } finally {
      setSubmitting(null)
    }
  }

  const handleDraft = async () => {
    setSubmitting('draft')
    setFeedback('')
    try {
      const result = await outreachApi.draftEmail({
        contact_id: draftForm.contact_id,
        email_type: draftForm.email_type as 'cold' | 'follow_up' | 'investor' | 'partnership',
        custom_notes: draftForm.custom_notes || undefined,
        channel: draftForm.channel as 'email' | 'linkedin_dm' | 'reddit_dm' | 'x_dm' | 'unknown',
      })
      const contact = contactsById.get(result.message.contact_id)
      setDraftForm((current) => ({ ...current, custom_notes: '' }))
      setFeedback(`Draft queued for approval${contact ? ` for ${contact.name}` : ''}.`)
      await loadData()
      setTab('messages')
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : 'Draft failed')
    } finally {
      setSubmitting(null)
    }
  }

  const handleDiscover = async () => {
    setSubmitting('discover')
    setFeedback('')
    try {
      const result = await outreachApi.discoverContacts({
        focus: discoverForm.focus || undefined,
        limit: discoverForm.limit,
        contact_type: discoverForm.contact_type,
        auto_research: discoverForm.auto_research,
      })
      setLatestDiscover(result)
      setFeedback(`Discovered ${result.prospects.length} prospect${result.prospects.length === 1 ? '' : 's'} for follow-up.`)
      await loadData()
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : 'Discovery failed')
    } finally {
      setSubmitting(null)
    }
  }

  const handleApproval = async (approval: OutreachApproval, decision: 'approved' | 'rejected') => {
    const approvalId = approval.id
    setSubmitting(`approval:${approvalId}:${decision}`)
    setFeedback('')
    try {
      const draft = getApprovalDraft(approval)
      const edits: Record<string, unknown> = {}
      if (draft.subject.trim()) edits.subject = draft.subject.trim()
      if (draft.body.trim()) edits.body = draft.body.trim()
      if (draft.comment.trim()) edits.comment = draft.comment.trim()

      await outreachApi.decideApproval(approvalId, decision, Object.keys(edits).length > 0 ? edits : undefined)
      setFeedback(`Approval ${decision}.`)
      setApprovalDrafts((current) => {
        const next = { ...current }
        delete next[approvalId]
        return next
      })
      await loadData()
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : 'Approval update failed')
    } finally {
      setSubmitting(null)
    }
  }

  const handleSend = async (messageId: string) => {
    setSubmitting(`send:${messageId}`)
    setFeedback('')
    try {
      const result = await outreachApi.sendMessage(messageId)
      setFeedback(result.send_result.detail)
      await loadData()
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : 'Send failed')
    } finally {
      setSubmitting(null)
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div
        className="shrink-0 border-b border-border/40 px-5 py-4"
        style={{ background: `linear-gradient(180deg, rgba(${rgb},0.06) 0%, transparent 100%)` }}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-foreground/90" style={{ fontFamily: 'var(--font-heading)' }}>
              Outreach Console
            </p>
            <p className="mt-1 text-[11px] text-muted-foreground">
              Research contacts, draft outbound, approve sends, and watch responses feed back into the system.
            </p>
          </div>
          <button
            onClick={refreshAll}
            disabled={refreshing}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-border/50 bg-secondary/30 transition-colors hover:bg-secondary/50 cursor-pointer disabled:opacity-50"
            aria-label="Refresh outreach data"
          >
            <RefreshCw className={cn('h-3.5 w-3.5', refreshing && 'animate-spin')} />
          </button>
        </div>

        <div className="mt-3 grid grid-cols-3 gap-2">
          <div className="rounded-lg border border-border/40 bg-secondary/15 px-3 py-2">
            <div className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Contacts</div>
            <div className="mt-1 text-sm font-semibold">{status?.contacts ?? contacts.length}</div>
          </div>
          <div className="rounded-lg border border-border/40 bg-secondary/15 px-3 py-2">
            <div className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Messages</div>
            <div className="mt-1 text-sm font-semibold">{status?.messages ?? messages.length}</div>
          </div>
          <div className="rounded-lg border border-border/40 bg-secondary/15 px-3 py-2">
            <div className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Approvals</div>
            <div className="mt-1 text-sm font-semibold">{pendingApprovals.length}</div>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-1 rounded-lg bg-secondary/25 p-1">
          <TabButton active={tab === 'contacts'} onClick={() => setTab('contacts')} label="Contacts" icon={<Users className="h-3 w-3" />} />
          <TabButton active={tab === 'messages'} onClick={() => setTab('messages')} label="Messages" icon={<Mail className="h-3 w-3" />} />
          <TabButton active={tab === 'actions'} onClick={() => setTab('actions')} label="Actions" icon={<Sparkles className="h-3 w-3" />} />
          <TabButton active={tab === 'activity'} onClick={() => setTab('activity')} label="Activity" icon={<Radar className="h-3 w-3" />} />
        </div>

        {feedback && (
          <div
            className="mt-3 rounded-lg border px-3 py-2 text-[11px]"
            style={{ borderColor: `rgba(${rgb},0.22)`, background: `rgba(${rgb},0.08)`, color }}
          >
            {feedback}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-5 pb-24">
        {loading ? (
          <div className="py-10 text-center text-sm text-muted-foreground">Loading outreach workspace…</div>
        ) : (
          <>
            {tab === 'contacts' && (
              <div className="space-y-5">
                <div>
                  <SectionLabel>Contact List</SectionLabel>
                  {contacts.length === 0 ? (
                    <EmptyState label="No outreach contacts yet." />
                  ) : (
                    <div className="space-y-2">
                      {contacts.map((contact) => {
                        const active = contact.id === selectedContactId
                        return (
                          <button
                            key={contact.id}
                            onClick={() => {
                              setSelectedContactId(contact.id)
                              setDraftForm((current) => ({ ...current, contact_id: contact.id }))
                            }}
                            className={cn(
                              'w-full rounded-xl border px-3 py-3 text-left transition-colors cursor-pointer',
                              active ? 'border-primary/30 bg-primary/6' : 'border-border/40 bg-secondary/10 hover:bg-secondary/20',
                            )}
                          >
                            <div className="flex items-start justify-between gap-2">
                              <div>
                                <p className="text-sm font-semibold text-foreground/90">{contact.name}</p>
                                <p className="text-[11px] text-muted-foreground">
                                  {contact.company}
                                  {contact.role ? ` · ${contact.role}` : ''}
                                </p>
                              </div>
                              <Badge variant="outline" className={cn('h-4 py-0 text-[9px] capitalize', statusBadge(contact.status))}>
                                {contact.status}
                              </Badge>
                            </div>
                            <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-muted-foreground/70">
                              <span>{formatLabel(contact.contact_type)}</span>
                              {contact.email && <span>{contact.email}</span>}
                              {contact.last_contacted_at && <span>Last touch {timeAgo(contact.last_contacted_at)}</span>}
                            </div>
                          </button>
                        )
                      })}
                    </div>
                  )}
                </div>

                {selectedContact && (
                  <div className="space-y-4 rounded-xl border border-border/40 bg-secondary/10 p-4">
                    <div>
                      <SectionLabel>Selected Contact</SectionLabel>
                      <div className="space-y-2 text-[11px] text-muted-foreground">
                        <p><span className="text-foreground/85">Name:</span> {selectedContact.name}</p>
                        <p><span className="text-foreground/85">Source:</span> {selectedContact.source ?? 'manual'}</p>
                        <p><span className="text-foreground/85">Next follow-up:</span> {selectedContact.next_followup_at ? timeAgo(selectedContact.next_followup_at) : 'Not scheduled'}</p>
                        <p><span className="text-foreground/85">Notes:</span> {selectedContact.notes || 'None yet'}</p>
                        <p className="leading-relaxed">
                          <span className="text-foreground/85">Brief:</span>{' '}
                          {selectedContactSignals.brief ?? 'Run research to generate a sharper targeting brief.'}
                        </p>
                      </div>
                    </div>

                    <div className="grid gap-4 md:grid-cols-2">
                      <div>
                        <SectionLabel>Reachability</SectionLabel>
                        {selectedContactSignals.reachableVia.length === 0 ? (
                          <EmptyState label="No channels extracted yet." />
                        ) : (
                          <div className="flex flex-wrap gap-2">
                            {selectedContactSignals.reachableVia.map((channel) => (
                              <Badge key={channel} variant="outline" className="h-5 py-0 text-[10px] capitalize">
                                {channel.replace(/_/g, ' ')}
                              </Badge>
                            ))}
                          </div>
                        )}
                      </div>

                      <div>
                        <SectionLabel>Profiles</SectionLabel>
                        {selectedContactSignals.profiles.length === 0 ? (
                          <EmptyState label="No profile links stored." />
                        ) : (
                          <div className="space-y-1.5 text-[11px] text-muted-foreground">
                            {selectedContactSignals.profiles.slice(0, 3).map((profile) => (
                              <div key={profile} className="truncate rounded-lg border border-border/40 bg-background/30 px-2.5 py-1.5">
                                {profile}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>

                    <div>
                      <SectionLabel>Signals</SectionLabel>
                      {selectedContactSignals.recentPosts.length === 0 && selectedContactSignals.talkingPoints.length === 0 ? (
                        <EmptyState label="No recent posts or talking points yet." />
                      ) : (
                        <div className="space-y-2">
                          {selectedContactSignals.recentPosts.slice(0, 2).map((post) => (
                            <div key={post} className="rounded-lg border border-border/40 bg-background/30 px-3 py-2 text-[11px] leading-relaxed text-muted-foreground">
                              {post}
                            </div>
                          ))}
                          {selectedContactSignals.talkingPoints.slice(0, 3).map((point) => (
                            <div key={point} className="rounded-lg border border-border/40 bg-background/20 px-3 py-2 text-[11px] text-foreground/80">
                              {point}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}

            {tab === 'messages' && (
              <div className="space-y-5">
                <div className="flex items-center justify-between gap-2">
                  <SectionLabel>Message Thread</SectionLabel>
                  <select
                    value={selectedContactId}
                    onChange={(event) => setSelectedContactId(event.target.value)}
                    className="h-8 rounded-lg border border-border/50 bg-secondary/20 px-2 text-[11px] outline-none"
                  >
                    <option value="">All contacts</option>
                    {contacts.map((contact) => (
                      <option key={contact.id} value={contact.id}>
                        {contact.name}
                      </option>
                    ))}
                  </select>
                </div>

                {sortedMessages.length === 0 ? (
                  <EmptyState label="No outreach messages yet." />
                ) : (
                  <div className="space-y-3">
                    {sortedMessages.map((message) => {
                      const contact = contactsById.get(message.contact_id)
                      const approval = message.approval_id ? approvalsById.get(message.approval_id) : null
                      const sendKey = `send:${message.id}`
                      const expanded = expandedMessageId === message.id
                      const canSend =
                        message.direction === 'sent' &&
                        message.status !== 'sent' &&
                        (!message.approval_id || approval?.status === 'approved')

                      return (
                        <div
                          key={message.id}
                          className={cn(
                            'overflow-hidden rounded-xl border',
                            message.direction === 'received'
                              ? 'border-primary/20 bg-primary/5'
                              : 'border-border/40 bg-secondary/10',
                          )}
                        >
                          <button
                            onClick={() => setExpandedMessageId((current) => current === message.id ? null : message.id)}
                            className="flex w-full items-start justify-between gap-3 px-3 py-3 text-left transition-colors hover:bg-background/15 cursor-pointer"
                          >
                            <div className="min-w-0">
                              <div className="flex items-center gap-2 flex-wrap">
                                <p className="text-sm font-semibold text-foreground/90">
                                  {contact?.name ?? 'Unknown contact'}
                                </p>
                                <Badge variant="outline" className={cn('h-4 py-0 text-[9px]', statusBadge(message.status))}>
                                  {formatLabel(message.status)}
                                </Badge>
                                <Badge variant="outline" className="h-4 py-0 text-[9px] capitalize">
                                  {message.direction}
                                </Badge>
                                {approval && (
                                  <Badge variant="outline" className={cn('h-4 py-0 text-[9px]', statusBadge(approval.status))}>
                                    Approval {approval.status}
                                  </Badge>
                                )}
                              </div>
                              <p className="mt-1 text-[11px] text-muted-foreground">
                                {message.subject || '(no subject)'} · {message.channel.replace(/_/g, ' ')}
                              </p>
                              <p className="mt-1 line-clamp-1 text-[11px] text-muted-foreground/80">
                                {message.body}
                              </p>
                            </div>

                            <div className="flex items-center gap-2 shrink-0">
                              <span className="text-[10px] text-muted-foreground/60">
                                {timeAgo(message.sent_at || message.created_at)}
                              </span>
                              {expanded ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
                            </div>
                          </button>

                          {expanded && (
                            <div className="border-t border-border/30 bg-background/10 px-3 py-3">
                              <p className="whitespace-pre-wrap text-[11px] leading-relaxed text-foreground/75">
                                {message.body}
                              </p>

                              {!canSend && message.direction === 'sent' && message.status !== 'sent' && approval?.status === 'pending' && (
                                <p className="mt-3 text-[10px] text-warning">Waiting for approval before send.</p>
                              )}

                              {canSend && (
                                <div className="mt-3 flex justify-end">
                                  <button
                                    onClick={() => handleSend(message.id)}
                                    disabled={submitting === sendKey}
                                    className="flex items-center gap-1 rounded-md border border-primary/25 bg-primary/8 px-2 py-1 text-[10px] text-primary transition-colors hover:bg-primary/12 cursor-pointer disabled:opacity-50"
                                  >
                                    {submitting === sendKey ? <Loader2 className="h-3 w-3 animate-spin" /> : <Send className="h-3 w-3" />}
                                    Send
                                  </button>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            )}

            {tab === 'actions' && (
              <div className="space-y-5">
                <div className="rounded-xl border border-border/40 bg-secondary/10 p-4 space-y-3">
                  <SectionLabel>Research Contact</SectionLabel>
                  <div className="grid grid-cols-2 gap-2">
                    <input
                      value={researchForm.name}
                      onChange={(event) => setResearchForm((current) => ({ ...current, name: event.target.value }))}
                      placeholder="Name"
                      className="h-9 rounded-lg border border-border/50 bg-background/40 px-3 text-sm outline-none"
                    />
                    <input
                      value={researchForm.company}
                      onChange={(event) => setResearchForm((current) => ({ ...current, company: event.target.value }))}
                      placeholder="Company"
                      className="h-9 rounded-lg border border-border/50 bg-background/40 px-3 text-sm outline-none"
                    />
                  </div>
                  <textarea
                    value={researchForm.context}
                    onChange={(event) => setResearchForm((current) => ({ ...current, context: event.target.value }))}
                    placeholder="Context for personalization or sourcing"
                    className="min-h-[72px] w-full resize-none rounded-lg border border-border/50 bg-background/40 px-3 py-2 text-sm outline-none"
                  />
                  <div className="flex items-center justify-between gap-2">
                    <select
                      value={researchForm.contact_type}
                      onChange={(event) => setResearchForm((current) => ({ ...current, contact_type: event.target.value }))}
                      className="h-9 rounded-lg border border-border/50 bg-background/40 px-3 text-sm outline-none"
                    >
                      <option value="customer">Customer</option>
                      <option value="investor">Investor</option>
                      <option value="partner">Partner</option>
                    </select>
                    <button
                      onClick={handleResearch}
                      disabled={!researchForm.name || !researchForm.company || submitting === 'research'}
                      className="flex h-9 items-center gap-2 rounded-lg border border-primary/25 bg-primary/10 px-3 text-sm font-medium text-primary transition-colors hover:bg-primary/15 cursor-pointer disabled:opacity-50"
                    >
                      {submitting === 'research' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />}
                      Research
                    </button>
                  </div>
                  {latestResearch && (
                    <div className="rounded-lg border border-primary/15 bg-primary/5 px-3 py-2 text-[11px] leading-relaxed text-muted-foreground">
                      {latestResearch.research_brief}
                    </div>
                  )}
                </div>

                <div className="rounded-xl border border-border/40 bg-secondary/10 p-4 space-y-3">
                  <SectionLabel>Draft Outreach</SectionLabel>
                  <div className="grid grid-cols-2 gap-2">
                    <select
                      value={draftForm.contact_id}
                      onChange={(event) => setDraftForm((current) => ({ ...current, contact_id: event.target.value }))}
                      className="h-9 rounded-lg border border-border/50 bg-background/40 px-3 text-sm outline-none"
                    >
                      <option value="">Select contact</option>
                      {contacts.map((contact) => (
                        <option key={contact.id} value={contact.id}>
                          {contact.name}
                        </option>
                      ))}
                    </select>
                    <select
                      value={draftForm.email_type}
                      onChange={(event) => setDraftForm((current) => ({ ...current, email_type: event.target.value }))}
                      className="h-9 rounded-lg border border-border/50 bg-background/40 px-3 text-sm outline-none"
                    >
                      <option value="cold">Cold intro</option>
                      <option value="follow_up">Follow-up</option>
                      <option value="investor">Investor</option>
                      <option value="partnership">Partnership</option>
                    </select>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <select
                      value={draftForm.channel}
                      onChange={(event) => setDraftForm((current) => ({ ...current, channel: event.target.value }))}
                      className="h-9 rounded-lg border border-border/50 bg-background/40 px-3 text-sm outline-none"
                    >
                      <option value="email">Email</option>
                      <option value="linkedin_dm">LinkedIn DM</option>
                      <option value="reddit_dm">Reddit DM</option>
                      <option value="x_dm">X DM</option>
                      <option value="unknown">Unknown</option>
                    </select>
                    <div className="rounded-lg border border-border/40 bg-background/25 px-3 py-2 text-[11px] text-muted-foreground">
                      Approval required before send
                    </div>
                  </div>
                  <textarea
                    value={draftForm.custom_notes}
                    onChange={(event) => setDraftForm((current) => ({ ...current, custom_notes: event.target.value }))}
                    placeholder="Optional notes for tone, pain points, or CTA"
                    className="min-h-[72px] w-full resize-none rounded-lg border border-border/50 bg-background/40 px-3 py-2 text-sm outline-none"
                  />
                  <button
                    onClick={handleDraft}
                    disabled={!draftForm.contact_id || submitting === 'draft'}
                    className="flex h-9 items-center gap-2 rounded-lg border border-primary/25 bg-primary/10 px-3 text-sm font-medium text-primary transition-colors hover:bg-primary/15 cursor-pointer disabled:opacity-50"
                  >
                    {submitting === 'draft' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                    Draft message
                  </button>
                </div>

                <div className="rounded-xl border border-border/40 bg-secondary/10 p-4 space-y-3">
                  <SectionLabel>Discover Contacts</SectionLabel>
                  <input
                    value={discoverForm.focus}
                    onChange={(event) => setDiscoverForm((current) => ({ ...current, focus: event.target.value }))}
                    placeholder="Focus area, vertical, or conversation trend"
                    className="h-9 w-full rounded-lg border border-border/50 bg-background/40 px-3 text-sm outline-none"
                  />
                  <div className="grid grid-cols-2 gap-2">
                    <select
                      value={discoverForm.contact_type}
                      onChange={(event) => setDiscoverForm((current) => ({ ...current, contact_type: event.target.value }))}
                      className="h-9 rounded-lg border border-border/50 bg-background/40 px-3 text-sm outline-none"
                    >
                      <option value="customer">Customer</option>
                      <option value="investor">Investor</option>
                      <option value="partner">Partner</option>
                    </select>
                    <input
                      type="number"
                      min={1}
                      max={10}
                      value={discoverForm.limit}
                      onChange={(event) => setDiscoverForm((current) => ({ ...current, limit: Number(event.target.value) || 1 }))}
                      className="h-9 rounded-lg border border-border/50 bg-background/40 px-3 text-sm outline-none"
                    />
                  </div>
                  <label className="flex items-center gap-2 text-[11px] text-muted-foreground">
                    <input
                      type="checkbox"
                      checked={discoverForm.auto_research}
                      onChange={(event) => setDiscoverForm((current) => ({ ...current, auto_research: event.target.checked }))}
                      className="h-3.5 w-3.5 rounded border-border/50"
                    />
                    Auto-research discovered contacts
                  </label>
                  <button
                    onClick={handleDiscover}
                    disabled={submitting === 'discover'}
                    className="flex h-9 items-center gap-2 rounded-lg border border-primary/25 bg-primary/10 px-3 text-sm font-medium text-primary transition-colors hover:bg-primary/15 cursor-pointer disabled:opacity-50"
                  >
                    {submitting === 'discover' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Users className="h-3.5 w-3.5" />}
                    Discover prospects
                  </button>

                  {latestDiscover && (
                    <div className="space-y-2">
                      {latestDiscover.prospects.slice(0, 4).map((prospect) => (
                        <div key={prospect.contact.id} className="rounded-lg border border-border/40 bg-background/25 px-3 py-2">
                          <div className="flex items-center justify-between gap-2">
                            <div>
                              <p className="text-[11px] font-medium text-foreground/85">{prospect.contact.name}</p>
                              <p className="text-[10px] text-muted-foreground">{prospect.contact.company}</p>
                            </div>
                            {typeof prospect.priority_score === 'number' && (
                              <Badge variant="outline" className="h-4 py-0 text-[9px]">
                                Score {prospect.priority_score}
                              </Badge>
                            )}
                          </div>
                          {prospect.why_fit && (
                            <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground">{prospect.why_fit}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="rounded-xl border border-border/40 bg-secondary/10 p-4">
                  <div className="mb-3 flex items-center justify-between gap-2">
                    <SectionLabel>Approval Queue</SectionLabel>
                    {approvedApprovals.length > 0 && (
                      <button
                        onClick={() => setShowApprovedApprovals((current) => !current)}
                        className="flex items-center gap-1 text-[10px] text-muted-foreground transition-colors hover:text-foreground cursor-pointer"
                      >
                        {showApprovedApprovals ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                        {showApprovedApprovals ? 'Hide approved' : `Show approved (${approvedApprovals.length})`}
                      </button>
                    )}
                  </div>

                  {pendingApprovals.length === 0 ? (
                    <EmptyState label="No pending outreach approvals." />
                  ) : (
                    <div className="space-y-2">
                      {pendingApprovals.map((approval) => {
                        const expanded = expandedApprovalId === approval.id
                        const draft = getApprovalDraft(approval)
                        const title =
                          getString(approval.content.subject) ??
                          getString(approval.content.title) ??
                          formatLabel(approval.action_type)
                        const preview =
                          getString(approval.content.body) ??
                          getString(approval.content.preview) ??
                          'Approval content ready for review.'
                        const approveKey = `approval:${approval.id}:approved`
                        const rejectKey = `approval:${approval.id}:rejected`

                        return (
                          <div key={approval.id} className="overflow-hidden rounded-lg border border-border/40 bg-background/20">
                            <button
                              onClick={() => setExpandedApprovalId((current) => current === approval.id ? null : approval.id)}
                              className="flex w-full items-start justify-between gap-2 px-3 py-3 text-left hover:bg-background/10 cursor-pointer"
                            >
                              <div className="min-w-0">
                                <div className="flex items-center gap-2 flex-wrap">
                                  <p className="text-[11px] font-semibold text-foreground/85">{title}</p>
                                  <Badge variant="outline" className={cn('h-4 py-0 text-[9px]', statusBadge(approval.status))}>
                                    {approval.status}
                                  </Badge>
                                </div>
                                <p className="mt-1 line-clamp-2 text-[10px] leading-relaxed text-muted-foreground">{preview}</p>
                              </div>
                              <div className="flex items-center gap-2 shrink-0">
                                <Eye className="h-3.5 w-3.5 text-muted-foreground/70" />
                                {expanded ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
                              </div>
                            </button>

                            {expanded && (
                              <div className="space-y-3 border-t border-border/30 bg-background/10 px-3 py-3">
                                <div className="space-y-1.5">
                                  <label className="text-[10px] uppercase tracking-widest text-muted-foreground/70">Subject</label>
                                  <input
                                    value={draft.subject}
                                    onChange={(event) =>
                                      setApprovalDrafts((current) => ({
                                        ...current,
                                        [approval.id]: { ...draft, subject: event.target.value },
                                      }))
                                    }
                                    className="h-9 w-full rounded-lg border border-border/50 bg-background/50 px-3 text-sm outline-none"
                                    placeholder="Subject"
                                  />
                                </div>

                                <div className="space-y-1.5">
                                  <label className="text-[10px] uppercase tracking-widest text-muted-foreground/70">Message Body</label>
                                  <textarea
                                    value={draft.body}
                                    onChange={(event) =>
                                      setApprovalDrafts((current) => ({
                                        ...current,
                                        [approval.id]: { ...draft, body: event.target.value },
                                      }))
                                    }
                                    className="min-h-[160px] w-full rounded-lg border border-border/50 bg-background/50 px-3 py-2 text-sm outline-none resize-y"
                                    placeholder="Draft body"
                                  />
                                </div>

                                <div className="space-y-1.5">
                                  <label className="text-[10px] uppercase tracking-widest text-muted-foreground/70">Review Comment</label>
                                  <textarea
                                    value={draft.comment}
                                    onChange={(event) =>
                                      setApprovalDrafts((current) => ({
                                        ...current,
                                        [approval.id]: { ...draft, comment: event.target.value },
                                      }))
                                    }
                                    className="min-h-[72px] w-full rounded-lg border border-border/50 bg-background/50 px-3 py-2 text-sm outline-none resize-none"
                                    placeholder="Leave context for the approval decision or requested changes"
                                  />
                                </div>

                                <div className="rounded-lg border border-border/40 bg-secondary/20 p-3">
                                  <p className="text-[10px] uppercase tracking-widest text-muted-foreground/70">Full Item Preview</p>
                                  <pre className="mt-2 whitespace-pre-wrap break-words text-[10px] leading-relaxed text-muted-foreground">
                                    {JSON.stringify(approval.content, null, 2)}
                                  </pre>
                                </div>

                                <div className="flex flex-wrap gap-2">
                                  <button
                                    onClick={() => handleApproval(approval, 'approved')}
                                    disabled={submitting === approveKey || submitting === rejectKey}
                                    className="flex h-8 items-center gap-1 rounded-md border border-emerald-400/25 bg-emerald-400/10 px-3 text-[10px] text-emerald-400 transition-colors hover:bg-emerald-400/15 cursor-pointer disabled:opacity-50"
                                  >
                                    {submitting === approveKey ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                                    Approve with edits
                                  </button>
                                  <button
                                    onClick={() => handleApproval(approval, 'rejected')}
                                    disabled={submitting === approveKey || submitting === rejectKey}
                                    className="flex h-8 items-center gap-1 rounded-md border border-destructive/25 bg-destructive/10 px-3 text-[10px] text-destructive transition-colors hover:bg-destructive/15 cursor-pointer disabled:opacity-50"
                                  >
                                    {submitting === rejectKey ? <Loader2 className="h-3 w-3 animate-spin" /> : <X className="h-3 w-3" />}
                                    Request changes
                                  </button>
                                  <button
                                    onClick={() =>
                                      setApprovalDrafts((current) => ({
                                        ...current,
                                        [approval.id]: {
                                          subject: getString(approval.content.subject) ?? '',
                                          body: getString(approval.content.body) ?? getString(approval.content.preview) ?? '',
                                          comment: '',
                                        },
                                      }))
                                    }
                                    className="flex h-8 items-center gap-1 rounded-md border border-border/50 bg-secondary/30 px-3 text-[10px] text-muted-foreground transition-colors hover:bg-secondary/50 cursor-pointer"
                                  >
                                    Reset edits
                                  </button>
                                </div>
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  )}

                  {showApprovedApprovals && approvedApprovals.length > 0 && (
                    <div className="mt-4 space-y-2">
                      {approvedApprovals.map((approval) => (
                        <div key={approval.id} className="rounded-lg border border-border/40 bg-background/15 px-3 py-2">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-[11px] font-medium text-foreground/80">
                              {getString(approval.content.subject) ?? formatLabel(approval.action_type)}
                            </span>
                            <Badge variant="outline" className={cn('h-4 py-0 text-[9px]', statusBadge(approval.status))}>
                              {approval.status}
                            </Badge>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {tab === 'activity' && (
              <div className="space-y-5">
                <div>
                  <SectionLabel>Recent Events</SectionLabel>
                  {events.length === 0 ? (
                    <EmptyState label="No outreach events yet." />
                  ) : (
                    <div className="space-y-2">
                      {events.map((event) => (
                        <div key={event.id} className="rounded-xl border border-border/40 bg-secondary/10 p-3">
                          <div className="flex items-start justify-between gap-2">
                            <div>
                              <div className="flex items-center gap-2">
                                <p className="text-[11px] font-semibold text-foreground/85">
                                  {event.summary || formatLabel(event.event_type)}
                                </p>
                                <Badge variant="outline" className={cn('h-4 py-0 text-[9px]', eventBadge(event.event_type))}>
                                  {formatLabel(event.event_type)}
                                </Badge>
                              </div>
                              <p className="mt-1 text-[10px] text-muted-foreground">
                                {event.payload.contact_name
                                  ? String(event.payload.contact_name)
                                  : event.payload.objection_text
                                    ? String(event.payload.objection_text)
                                    : 'No additional detail'}
                              </p>
                            </div>
                            <span className="text-[10px] text-muted-foreground/50">{timeAgo(event.timestamp)}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="rounded-xl border border-border/40 bg-secondary/10 p-4">
                  <SectionLabel>Event Contract</SectionLabel>
                  <div className="space-y-3 text-[11px] text-muted-foreground">
                    <div>
                      <p className="font-medium text-foreground/85">Emits</p>
                      <p className="mt-1 leading-relaxed">
                        reply_received, lead_converted, objection_heard, outreach_sent
                      </p>
                    </div>
                    <div>
                      <p className="font-medium text-foreground/85">Consumes</p>
                      <p className="mt-1 leading-relaxed">
                        feature_shipped, trend_found, research_completed
                      </p>
                    </div>
                    <div>
                      <p className="font-medium text-foreground/85">Autonomy</p>
                      <p className="mt-1 leading-relaxed">
                        Research and draft are autonomous. Send requires approval. Approved follow-ups can notify after send.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
