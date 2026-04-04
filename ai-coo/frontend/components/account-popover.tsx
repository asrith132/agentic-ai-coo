'use client'

import type { ReactNode } from 'react'
import {
  BadgeCheck,
  BellRing,
  Bot,
  Building2,
  CreditCard,
  LogOut,
  Mail,
  Shield,
  Slack,
  User,
} from 'lucide-react'

import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

const integrations = [
  { name: 'GitHub', status: 'Connected' },
  { name: 'Slack', status: 'Connected' },
  { name: 'Linear', status: 'Pending' },
  { name: 'Notion', status: 'Connected' },
]

const preferences = [
  'Weekly founder brief every morning',
  'Ask before high-risk actions',
  'Auto-approve low-risk ops tasks',
]

export function AccountPopover() {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label="Open account"
          className="w-9 h-9 rounded-lg bg-secondary/50 hover:bg-secondary flex items-center justify-center transition-colors duration-150 cursor-pointer"
        >
          <User className="w-4 h-4" />
        </button>
      </PopoverTrigger>

      <PopoverContent
        align="end"
        sideOffset={10}
        className="w-[24rem] p-1 border-border/60 bg-card/95 backdrop-blur-xl"
      >
        <div className="flex items-start gap-3 px-3 py-3">
          <Avatar className="size-11 ring-1 ring-border/60">
            <AvatarFallback className="bg-primary/10 text-primary font-semibold">
              SK
            </AvatarFallback>
          </Avatar>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-foreground">Sanketh</span>
              <Badge className="px-1.5 py-0 text-[10px]">Founder</Badge>
            </div>
            <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
              <Mail className="size-3.5" />
              <span className="truncate">founder@orchestrate.ai</span>
            </div>
            <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
              <Building2 className="size-3.5" />
              <span>AI COO Workspace • MVP Stage</span>
            </div>
          </div>
        </div>

        <div className="-mx-1 my-1 h-px bg-border/70" />

        <div className="grid gap-2 px-2 py-2 sm:grid-cols-2">
          <SectionCard
            icon={<Building2 className="size-3.5" />}
            title="Workspace"
            lines={['Startup defaults configured', 'Timezone: Indianapolis', 'Team size: 4 core operators']}
          />
          <SectionCard
            icon={<Bot className="size-3.5" />}
            title="Agent Preferences"
            lines={preferences}
          />
          <SectionCard
            icon={<Slack className="size-3.5" />}
            title="Integrations"
            lines={integrations.map((item) => `${item.name}: ${item.status}`)}
          />
          <SectionCard
            icon={<CreditCard className="size-3.5" />}
            title="Billing"
            lines={['Pro plan active', '1,284 agent runs this month', 'Usage refreshes daily']}
          />
        </div>

        <div className="-mx-1 my-1 h-px bg-border/70" />

        <div className="px-2 py-2 space-y-2">
          <ActionRow
            icon={<BellRing className="size-4 text-muted-foreground" />}
            title="Notification settings"
            subtitle="Control alerts, daily briefs, and risk escalations"
          />
          <ActionRow
            icon={<Shield className="size-4 text-muted-foreground" />}
            title="Security"
            subtitle="Sessions, connected accounts, and permissions"
          />
          <ActionRow
            icon={<BadgeCheck className="size-4 text-muted-foreground" />}
            title="Founder profile"
            subtitle="Role, company details, and workspace identity"
          />
        </div>

        <div className="-mx-1 my-1 h-px bg-border/70" />

        <div className="px-2 py-2">
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-destructive transition-colors hover:bg-destructive/8 cursor-pointer"
          >
            <LogOut className="size-4" />
            <span className="font-medium">Sign out</span>
          </button>
        </div>
      </PopoverContent>
    </Popover>
  )
}

function SectionCard({
  icon,
  title,
  lines,
}: {
  icon: ReactNode
  title: string
  lines: string[]
}) {
  return (
    <div className="rounded-md border border-border/60 bg-secondary/25 px-3 py-3">
      <div className="mb-2 flex items-center gap-2 text-sm font-medium text-foreground">
        <span className="text-muted-foreground">{icon}</span>
        <span>{title}</span>
      </div>
      <div className="space-y-1">
        {lines.map((line) => (
          <div key={line} className="text-xs text-muted-foreground leading-relaxed">
            {line}
          </div>
        ))}
      </div>
    </div>
  )
}

function ActionRow({
  icon,
  title,
  subtitle,
}: {
  icon: ReactNode
  title: string
  subtitle: string
}) {
  return (
    <button
      type="button"
      className="flex w-full items-start gap-3 rounded-md px-3 py-2 text-left transition-colors hover:bg-accent/60 cursor-pointer"
    >
      <span className="mt-0.5">{icon}</span>
      <span className="min-w-0">
        <span className="block text-sm font-medium text-foreground">{title}</span>
        <span className="block text-xs text-muted-foreground">{subtitle}</span>
      </span>
    </button>
  )
}
