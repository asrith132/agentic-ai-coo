'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Bell, ChevronRight } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { agents, type AgentStatus } from '@/lib/mock-data'

const API = 'http://localhost:8001'

type NotificationItem = {
  id: string
  agent: string
  title: string
  body: string
  priority: string   // low | medium | high | urgent
  read: boolean
  created_at: string | null
}

// Map backend priority → display tone
function priorityToTone(priority: string): 'default' | 'warning' | 'success' {
  if (priority === 'urgent' || priority === 'high') return 'warning'
  if (priority === 'low') return 'success'
  return 'default'
}

function timeAgo(iso: string | null): string {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const s = Math.floor(diff / 1000)
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

const statusAccent: Record<AgentStatus, string> = {
  thinking: 'bg-primary',
  done: 'bg-emerald-400',
  blocked: 'bg-destructive',
  idle: 'bg-muted-foreground/50',
}

function Dot({ className }: { className?: string }) {
  return (
    <svg
      width="6"
      height="6"
      fill="currentColor"
      viewBox="0 0 6 6"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      <circle cx="3" cy="3" r="3" />
    </svg>
  )
}

interface NotificationsPopoverProps {
  onViewAll: () => void
}

export function NotificationsPopover({ onViewAll }: NotificationsPopoverProps) {
  const [notifications, setNotifications] = useState<NotificationItem[]>([])
  const [loading, setLoading] = useState(false)

  const fetchNotifications = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API}/api/notifications?limit=20`)
      if (!res.ok) return
      const data: NotificationItem[] = await res.json()
      setNotifications(data)
    } catch {
      // Backend not running — stay empty
    } finally {
      setLoading(false)
    }
  }, [])

  // Fetch on mount
  useEffect(() => {
    fetchNotifications()
  }, [fetchNotifications])

  const unreadCount = notifications.filter((n) => n.read === false).length

  const blockedAgents = useMemo(
    () => agents.filter((agent) => agent.status === 'blocked'),
    [],
  )

  const handleMarkAllAsRead = async () => {
    const unread = notifications.filter((n) => !n.read)
    // Optimistic update
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })))
    // Persist each in parallel
    await Promise.allSettled(
      unread.map((n) =>
        fetch(`${API}/api/notifications/${n.id}/read`, { method: 'POST' }),
      ),
    )
  }

  const handleNotificationClick = async (id: string) => {
    // Optimistic update
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read: true } : n)),
    )
    try {
      await fetch(`${API}/api/notifications/${id}/read`, { method: 'POST' })
    } catch {
      // Silently degrade
    }
  }

  return (
    <Popover onOpenChange={(open) => { if (open) fetchNotifications() }}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label="Open notifications"
          className="relative w-9 h-9 rounded-lg bg-white/8 hover:bg-white/15 flex items-center justify-center transition-colors duration-150 cursor-pointer"
        >
          <Bell className="w-4 h-4 text-white" />
          {unreadCount > 0 && (
            <Badge className="absolute -top-1.5 left-full min-w-5 -translate-x-1/2 px-1 py-0 text-[10px]">
              {unreadCount > 99 ? '99+' : unreadCount}
            </Badge>
          )}
        </button>
      </PopoverTrigger>

      <PopoverContent
        align="end"
        sideOffset={10}
        className="w-[22rem] p-1 border-border/60 bg-card/95 backdrop-blur-xl"
      >
        <div className="flex items-start justify-between gap-4 px-3 py-2">
          <div>
            <div className="text-sm font-semibold text-foreground">Notifications</div>
            <div className="text-xs text-muted-foreground">
              {blockedAgents.length} blocked agent{blockedAgents.length === 1 ? '' : 's'} need attention
            </div>
          </div>
          {unreadCount > 0 && (
            <button
              type="button"
              className="text-xs font-medium text-primary hover:underline cursor-pointer"
              onClick={handleMarkAllAsRead}
            >
              Mark all as read
            </button>
          )}
        </div>

        <div
          role="separator"
          aria-orientation="horizontal"
          className="-mx-1 my-1 h-px bg-border/70"
        />

        <div className="px-2 pb-2 space-y-2">
          <button
            type="button"
            onClick={onViewAll}
            className="mb-2 flex w-full items-center justify-between rounded-md border border-border/60 bg-secondary/30 px-3 py-2 text-left text-sm text-foreground transition-colors hover:bg-secondary/60 cursor-pointer"
          >
            <span className="font-medium">View all notifications</span>
            <ChevronRight className="size-4 text-muted-foreground" />
          </button>

          {blockedAgents.length > 0 && (
            <div className="mb-2 rounded-md border border-destructive/20 bg-destructive/5 px-3 py-2">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-destructive/90">
                Immediate attention
              </div>
              <div className="mt-1 space-y-1.5">
                {blockedAgents.map((agent) => (
                  <div key={agent.id} className="flex items-start gap-2 text-xs text-muted-foreground">
                    <span className={`mt-1.5 h-1.5 w-1.5 rounded-full ${statusAccent[agent.status]}`} />
                    <span>
                      <span className="font-medium text-foreground">{agent.name}</span>{' '}
                      {agent.risks[0]}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {loading && notifications.length === 0 && (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="animate-pulse rounded-lg border border-border/50 bg-secondary/20 px-3 py-3 space-y-2">
                  <div className="h-2.5 bg-secondary/70 rounded-full w-3/4" />
                  <div className="h-2 bg-secondary/50 rounded-full w-full" />
                </div>
              ))}
            </div>
          )}

          {!loading && notifications.length === 0 && (
            <div className="py-6 text-center text-xs text-muted-foreground/50">
              No notifications yet
            </div>
          )}

          {notifications.map((notification) => {
            const tone = priorityToTone(notification.priority)
            return (
              <div
                key={notification.id}
                className="rounded-lg border border-border/90 bg-secondary/20 px-3 py-3 text-sm transition-colors hover:bg-accent/40 hover:border-foreground/20"
              >
                <div className="relative flex items-start pe-3">
                  <div className="flex-1 space-y-1">
                    <button
                      type="button"
                      className="text-left text-foreground/80 after:absolute after:inset-0 cursor-pointer"
                      onClick={() => handleNotificationClick(notification.id)}
                    >
                      <span className="font-medium text-foreground">{notification.title}</span>
                      <span className="block text-foreground/70">{notification.body}</span>
                    </button>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      {notification.created_at && (
                        <span>{timeAgo(notification.created_at)}</span>
                      )}
                      <span className="inline-flex items-center rounded-full bg-background/70 px-2 py-0.5">
                        <span
                          className={
                            tone === 'warning'
                              ? 'text-destructive'
                              : tone === 'success'
                                ? 'text-emerald-400'
                                : 'text-primary'
                          }
                        >
                          {tone === 'warning' ? 'Risk' : tone === 'success' ? 'Complete' : 'Update'}
                        </span>
                      </span>
                    </div>
                  </div>
                  {!notification.read && (
                    <div className="absolute end-0 top-1 text-primary">
                      <span className="sr-only">Unread</span>
                      <Dot />
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </PopoverContent>
    </Popover>
  )
}
