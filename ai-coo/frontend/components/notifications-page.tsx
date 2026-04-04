'use client'

import { ArrowLeft } from 'lucide-react'

import { NotificationsMenu } from '@/components/ui/notifications-menu'

interface NotificationsPageProps {
  onBack: () => void
}

export function NotificationsPage({ onBack }: NotificationsPageProps) {
  return (
    <main className="min-h-screen px-6 py-8">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
        <div className="flex items-center justify-between gap-4">
          <button
            type="button"
            onClick={onBack}
            className="inline-flex items-center gap-2 rounded-lg border border-border/60 bg-card/50 px-3 py-2 text-sm font-medium text-foreground transition-colors hover:bg-secondary/70 cursor-pointer"
          >
            <ArrowLeft className="size-4" />
            Back to dashboard
          </button>
        </div>

        <NotificationsMenu />
      </div>
    </main>
  )
}
