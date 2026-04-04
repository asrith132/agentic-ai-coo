'use client'

import { useMemo, useState } from 'react'
import { Bell, ChevronRight } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { agents, type AgentStatus } from '@/lib/mock-data'

type NotificationItem = {
  id: number
  title: string
  body: string
  timestamp: string
  unread: boolean
  tone: 'default' | 'warning' | 'success'
}

const initialNotifications: NotificationItem[] = [
  {
    id: 1,
    title: 'Finance needs input',
    body: 'Runway modeling is blocked until revenue assumptions are confirmed.',
    timestamp: '2 min ago',
    unread: true,
    tone: 'warning',
  },
  {
    id: 2,
    title: 'Product updated priorities',
    body: 'The PM agent narrowed the MVP to the top three launch-critical features.',
    timestamp: '7 min ago',
    unread: true,
    tone: 'default',
  },
  {
    id: 3,
    title: 'Engineering is ready',
    body: 'Architecture is complete and implementation estimates are available.',
    timestamp: '12 min ago',
    unread: false,
    tone: 'success',
  },
  {
    id: 4,
    title: 'Research found competition risk',
    body: 'A direct competitor is entering the market with a similar offer next month.',
    timestamp: '23 min ago',
    unread: false,
    tone: 'warning',
  },
]

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
  const [notifications, setNotifications] = useState(initialNotifications)

  const unreadCount = notifications.filter((notification) => notification.unread).length
  const blockedAgents = useMemo(
    () => agents.filter((agent) => agent.status === 'blocked'),
    [],
  )

  const handleMarkAllAsRead = () => {
    setNotifications((current) =>
      current.map((notification) => ({
        ...notification,
        unread: false,
      })),
    )
  }

  const handleNotificationClick = (id: number) => {
    setNotifications((current) =>
      current.map((notification) =>
        notification.id === id
          ? { ...notification, unread: false }
          : notification,
      ),
    )
  }

  return (
    <Popover>
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

          {notifications.map((notification) => (
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
                    <span>{notification.timestamp}</span>
                    <span
                      className="inline-flex items-center rounded-full bg-background/70 px-2 py-0.5"
                    >
                      <span
                      className={
                        notification.tone === 'warning'
                          ? 'text-destructive'
                          : notification.tone === 'success'
                            ? 'text-emerald-400'
                            : 'text-primary'
                      }
                    >
                      {notification.tone === 'warning'
                        ? 'Risk'
                        : notification.tone === 'success'
                          ? 'Complete'
                          : 'Update'}
                    </span>
                    </span>
                  </div>
                </div>
                {notification.unread && (
                  <div className="absolute end-0 top-1 text-primary">
                    <span className="sr-only">Unread</span>
                    <Dot />
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  )
}
