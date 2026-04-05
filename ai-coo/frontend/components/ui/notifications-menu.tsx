'use client'

import * as React from 'react'
import { Bell, CheckCheck, Loader2, Settings2 } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { API_BASE } from '@/lib/api/config'

type NotificationRecord = {
  id: string
  agent: string
  title: string
  body: string
  priority: string
  read: boolean
  created_at: string | null
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

function priorityBadge(priority: string) {
  if (priority === 'urgent' || priority === 'high') return 'text-warning border-warning/30 bg-warning/8'
  if (priority === 'low') return 'text-emerald-400 border-emerald-400/30 bg-emerald-400/8'
  return 'text-primary border-primary/30 bg-primary/8'
}

function NotificationItem({
  notification,
  onRead,
}: {
  notification: NotificationRecord
  onRead: (id: string) => Promise<void>
}) {
  const [submitting, setSubmitting] = React.useState(false)

  const handleRead = async () => {
    setSubmitting(true)
    await onRead(notification.id)
    setSubmitting(false)
  }

  return (
    <div className="w-full py-4 first:pt-0 last:pb-0">
      <div className="flex gap-3">
        <div className="flex size-11 shrink-0 items-center justify-center rounded-xl border border-border bg-card text-sm font-semibold">
          {notification.agent.slice(0, 3).toUpperCase()}
        </div>

        <div className="flex flex-1 flex-col space-y-2">
          <div>
            <div className="flex items-center justify-between gap-2">
              <div className="text-sm">
                <span className="font-medium">{notification.agent}</span>
                <span className="text-muted-foreground"> updated </span>
                <span className="font-medium">{notification.title}</span>
              </div>
              {!notification.read && (
                <div className="size-1.5 rounded-full bg-emerald-500" />
              )}
            </div>
            <div className="mt-1 flex items-center justify-between gap-2">
              <div className="text-xs text-muted-foreground">
                {notification.created_at ? new Date(notification.created_at).toLocaleString() : 'just now'}
              </div>
              <div className="text-xs text-muted-foreground">
                {timeAgo(notification.created_at)}
              </div>
            </div>
          </div>

          <div className="rounded-lg bg-muted p-2.5 text-sm tracking-[-0.006em]">
            {notification.body}
          </div>

          <div className="flex items-center justify-between gap-3">
            <Badge variant="outline" className={priorityBadge(notification.priority)}>
              {notification.priority}
            </Badge>
            {!notification.read && (
              <Button variant="outline" size="sm" className="h-7 text-xs" onClick={handleRead} disabled={submitting}>
                {submitting ? <Loader2 className="size-3 animate-spin" /> : 'Mark read'}
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export function NotificationsMenu() {
  const [activeTab, setActiveTab] = React.useState<string>('all')
  const [notifications, setNotifications] = React.useState<NotificationRecord[]>([])
  const [loading, setLoading] = React.useState(true)

  const fetchNotifications = React.useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/notifications?limit=50`)
      if (!res.ok) throw new Error('failed')
      const data: NotificationRecord[] = await res.json()
      setNotifications(data)
    } catch {
      setNotifications([])
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    fetchNotifications()
  }, [fetchNotifications])

  const unreadCount = notifications.filter((notification) => !notification.read).length
  const urgentCount = notifications.filter(
    (notification) => notification.priority === 'high' || notification.priority === 'urgent',
  ).length

  const filteredNotifications = React.useMemo(() => {
    switch (activeTab) {
      case 'unread':
        return notifications.filter((notification) => !notification.read)
      case 'priority':
        return notifications.filter(
          (notification) => notification.priority === 'high' || notification.priority === 'urgent',
        )
      default:
        return notifications
    }
  }, [activeTab, notifications])

  const handleRead = React.useCallback(async (id: string) => {
    setNotifications((current) => current.map((notification) => (
      notification.id === id ? { ...notification, read: true } : notification
    )))
    try {
      await fetch(`${API_BASE}/api/notifications/${id}/read`, { method: 'POST' })
    } catch {}
  }, [])

  const handleMarkAllRead = React.useCallback(async () => {
    const unread = notifications.filter((notification) => !notification.read)
    setNotifications((current) => current.map((notification) => ({ ...notification, read: true })))
    await Promise.allSettled(
      unread.map((notification) =>
        fetch(`${API_BASE}/api/notifications/${notification.id}/read`, { method: 'POST' }),
      ),
    )
  }, [notifications])

  return (
    <Card className="flex w-full max-w-[760px] flex-col gap-6 border-border/60 bg-card/80 p-4 shadow-2xl shadow-black/20 backdrop-blur-xl md:p-8">
      <CardHeader className="p-0">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold tracking-[-0.006em]">
              Your notifications
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Agent updates, blockers, approvals, and recent system alerts.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button className="size-8" variant="ghost" size="icon" aria-label="Mark all read" onClick={handleMarkAllRead}>
              <CheckCheck className="size-4.5 text-muted-foreground" />
            </Button>
            <Button className="size-8" variant="ghost" size="icon" aria-label="Refresh notifications" onClick={fetchNotifications}>
              <Settings2 className="size-4.5 text-muted-foreground" />
            </Button>
          </div>
        </div>

        <Tabs
          value={activeTab}
          onValueChange={setActiveTab}
          className="w-full flex-col justify-start"
        >
          <div className="flex items-center justify-between">
            <TabsList className="**:data-[slot=badge]:size-5 **:data-[slot=badge]:rounded-full **:data-[slot=badge]:bg-muted-foreground/30 [&_button]:gap-1.5">
              <TabsTrigger value="all">
                All
                <Badge variant="secondary">{notifications.length}</Badge>
              </TabsTrigger>
              <TabsTrigger value="unread">
                Unread
                <Badge variant="secondary">{unreadCount}</Badge>
              </TabsTrigger>
              <TabsTrigger value="priority">
                Priority
                <Badge variant="secondary">{urgentCount}</Badge>
              </TabsTrigger>
            </TabsList>
          </div>
        </Tabs>
      </CardHeader>

      <CardContent className="h-full p-0">
        <div className="space-y-0 divide-y divide-dashed divide-border">
          {loading ? (
            <div className="flex items-center justify-center py-12 text-sm text-muted-foreground">
              <Loader2 className="mr-2 size-4 animate-spin" />
              Loading notifications…
            </div>
          ) : filteredNotifications.length > 0 ? (
            filteredNotifications.map((notification) => (
              <NotificationItem
                key={notification.id}
                notification={notification}
                onRead={handleRead}
              />
            ))
          ) : (
            <div className="flex flex-col items-center justify-center space-y-2.5 py-12 text-center">
              <div className="rounded-full bg-muted p-4">
                <Bell className="text-muted-foreground" />
              </div>
              <p className="text-sm font-medium tracking-[-0.006em] text-muted-foreground">
                No notifications yet.
              </p>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
