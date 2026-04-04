'use client'

import { Bell, CheckCheck, Download, Settings2 } from 'lucide-react'
import * as React from 'react'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

type Notification = {
  id: number
  type: string
  user: {
    name: string
    avatar: string
    fallback: string
  }
  action: string
  target?: string
  content?: string
  timestamp: string
  timeAgo: string
  isRead: boolean
  hasActions?: boolean
  file?: {
    name: string
    size: string
    type: string
  }
}

const notifications: Notification[] = [
  {
    id: 1,
    type: 'comment',
    user: {
      name: 'Finance Agent',
      avatar: 'https://api.dicebear.com/7.x/notionists/svg?seed=Finance',
      fallback: 'F',
    },
    action: 'flagged a blocker in',
    target: 'Runway model',
    content:
      'I need revenue assumptions confirmed before I can finalize burn and fundraising recommendations.',
    timestamp: 'Today 9:12 AM',
    timeAgo: '12 min ago',
    isRead: false,
  },
  {
    id: 2,
    type: 'follow',
    user: {
      name: 'Marketing Agent',
      avatar: 'https://api.dicebear.com/7.x/notionists/svg?seed=Marketing',
      fallback: 'G',
    },
    action: 'posted an update in',
    target: 'Launch strategy',
    timestamp: 'Today 8:54 AM',
    timeAgo: '30 min ago',
    isRead: false,
  },
  {
    id: 3,
    type: 'invitation',
    user: {
      name: 'Outreach Agent',
      avatar: 'https://api.dicebear.com/7.x/notionists/svg?seed=Outreach',
      fallback: 'R',
    },
    action: 'requested approval for',
    target: 'founder outreach sequence',
    timestamp: 'Today 8:22 AM',
    timeAgo: '1 hour ago',
    isRead: true,
    hasActions: true,
  },
  {
    id: 4,
    type: 'file_share',
    user: {
      name: 'Research Agent',
      avatar: 'https://api.dicebear.com/7.x/notionists/svg?seed=Research',
      fallback: 'R',
    },
    action: 'shared a file in',
    target: 'Competitor brief',
    file: {
      name: 'category-analysis.pdf',
      size: '2.4 MB',
      type: 'PDF',
    },
    timestamp: 'Today 7:40 AM',
    timeAgo: '2 hours ago',
    isRead: true,
  },
  {
    id: 5,
    type: 'mention',
    user: {
      name: 'Product Agent',
      avatar: 'https://api.dicebear.com/7.x/notionists/svg?seed=Product',
      fallback: 'P',
    },
    action: 'mentioned you in',
    target: 'MVP scope',
    content:
      'Can you confirm whether we should optimize for speed-to-launch or stronger onboarding in v1?',
    timestamp: 'Yesterday 5:30 PM',
    timeAgo: '1 day ago',
    isRead: true,
  },
  {
    id: 6,
    type: 'like',
    user: {
      name: 'Engineering Agent',
      avatar: 'https://api.dicebear.com/7.x/notionists/svg?seed=Engineering',
      fallback: 'E',
    },
    action: 'completed work in',
    target: 'Architecture proposal',
    timestamp: 'Yesterday 3:15 PM',
    timeAgo: '1 day ago',
    isRead: true,
  },
]

function NotificationItem({ notification }: { notification: Notification }) {
  return (
    <div className="w-full py-4 first:pt-0 last:pb-0">
      <div className="flex gap-3">
        <Avatar className="size-11">
          <AvatarImage
            src={notification.user.avatar || '/placeholder.svg'}
            alt={`${notification.user.name}'s profile picture`}
            className="object-cover ring-1 ring-border"
          />
          <AvatarFallback>{notification.user.fallback}</AvatarFallback>
        </Avatar>

        <div className="flex flex-1 flex-col space-y-2">
          <div className="w-full items-start">
            <div>
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm">
                  <span className="font-medium">{notification.user.name}</span>
                  <span className="text-muted-foreground"> {notification.action} </span>
                  {notification.target && (
                    <span className="font-medium">{notification.target}</span>
                  )}
                </div>
                {!notification.isRead && (
                  <div className="size-1.5 rounded-full bg-emerald-500" />
                )}
              </div>
              <div className="flex items-center justify-between gap-2">
                <div className="mt-0.5 text-xs text-muted-foreground">
                  {notification.timestamp}
                </div>
                <div className="text-xs text-muted-foreground">
                  {notification.timeAgo}
                </div>
              </div>
            </div>
          </div>

          {notification.content && (
            <div className="rounded-lg bg-muted p-2.5 text-sm tracking-[-0.006em]">
              {notification.content}
            </div>
          )}

          {notification.file && (
            <div className="flex items-center gap-2 rounded-lg bg-muted p-2">
              <div className="flex size-10 shrink-0 items-center justify-center rounded-lg border border-border bg-card">
                <span className="text-[11px] font-semibold text-primary">
                  {notification.file.type}
                </span>
              </div>
              <div className="flex-1">
                <div className="text-sm font-medium">
                  {notification.file.name}
                </div>
                <div className="text-xs text-muted-foreground">
                  {notification.file.type} • {notification.file.size}
                </div>
              </div>
              <Button variant="ghost" size="icon" className="size-8">
                <Download className="size-4" />
              </Button>
            </div>
          )}

          {notification.hasActions && (
            <div className="flex gap-2">
              <Button variant="outline" size="sm" className="h-7 text-xs">
                Decline
              </Button>
              <Button size="sm" className="h-7 text-xs">
                Approve
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export function NotificationsMenu() {
  const [activeTab, setActiveTab] = React.useState<string>('all')

  const verifiedCount = notifications.filter(
    (notification) =>
      notification.type === 'follow' || notification.type === 'like',
  ).length
  const mentionCount = notifications.filter(
    (notification) => notification.type === 'mention',
  ).length

  const filteredNotifications = React.useMemo(() => {
    switch (activeTab) {
      case 'verified':
        return notifications.filter(
          (notification) =>
            notification.type === 'follow' || notification.type === 'like',
        )
      case 'mentions':
        return notifications.filter(
          (notification) => notification.type === 'mention',
        )
      default:
        return notifications
    }
  }, [activeTab])

  return (
    <Card className="flex w-full max-w-[760px] flex-col gap-6 border-border/60 bg-card/80 p-4 shadow-2xl shadow-black/20 backdrop-blur-xl md:p-8">
      <CardHeader className="p-0">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold tracking-[-0.006em]">
              Your notifications
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Agent updates, approvals, blockers, and shared outputs.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button className="size-8" variant="ghost" size="icon" aria-label="Mark all read">
              <CheckCheck className="size-4.5 text-muted-foreground" />
            </Button>
            <Button className="size-8" variant="ghost" size="icon" aria-label="Notification settings">
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
                View all
                <Badge variant="secondary">{notifications.length}</Badge>
              </TabsTrigger>
              <TabsTrigger value="verified">
                Verified
                <Badge variant="secondary">{verifiedCount}</Badge>
              </TabsTrigger>
              <TabsTrigger value="mentions">
                Mentions
                <Badge variant="secondary">{mentionCount}</Badge>
              </TabsTrigger>
            </TabsList>
          </div>
        </Tabs>
      </CardHeader>

      <CardContent className="h-full p-0">
        <div className="space-y-0 divide-y divide-dashed divide-border">
          {filteredNotifications.length > 0 ? (
            filteredNotifications.map((notification) => (
              <NotificationItem
                key={notification.id}
                notification={notification}
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
