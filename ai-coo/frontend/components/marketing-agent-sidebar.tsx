'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  CheckCircle2,
  Clock,
  Linkedin,
  Loader2,
  Megaphone,
  RefreshCw,
  TrendingUp,
  XCircle,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { marketingApi, type MarketingPost, type MarketingTrend } from '@/lib/api/marketing'

// ── Helpers ───────────────────────────────────────────────────────────────────

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

function scoreColor(score: number) {
  if (score >= 80) return 'text-emerald-400'
  if (score >= 60) return 'text-warning'
  return 'text-muted-foreground/60'
}

function scoreBar(score: number) {
  if (score >= 80) return 'bg-emerald-400'
  if (score >= 60) return 'bg-warning'
  return 'bg-muted-foreground/30'
}

// ── Post card ─────────────────────────────────────────────────────────────────

function PostCard({ post }: { post: MarketingPost }) {
  const preview = (post.body || '').slice(0, 120).replace(/\n/g, ' ')
  const isPending = post.status === 'pending_approval'
  const isPublished = post.status === 'published'

  return (
    <div className="rounded-xl border border-border/40 bg-secondary/20 overflow-hidden">
      <div className="px-3 py-2.5 flex items-start gap-2.5">
        <div className="shrink-0 mt-0.5">
          {isPublished ? (
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          ) : isPending ? (
            <Clock className="w-4 h-4 text-warning" />
          ) : (
            <Loader2 className="w-4 h-4 text-muted-foreground/40" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 mb-1 flex-wrap">
            <Linkedin className="w-2.5 h-2.5 text-[#0077b5] shrink-0" />
            {post.content_type && (
              <Badge variant="outline" className="text-[9px] py-0 h-4 bg-secondary/40 border-border/50 text-muted-foreground font-normal capitalize">
                {post.content_type.replace(/_/g, ' ')}
              </Badge>
            )}
            {post.topic && (
              <span className="text-[10px] text-muted-foreground/60 truncate max-w-[140px]">{post.topic}</span>
            )}
          </div>
          <p className="text-[11px] text-foreground/80 leading-relaxed line-clamp-3">
            {preview}{preview.length >= 120 ? '…' : ''}
          </p>
          <div className="flex items-center gap-2 mt-1.5">
            {post.created_at && (
              <span className="text-[10px] text-muted-foreground/40">{timeAgo(post.created_at)}</span>
            )}
            {isPublished && post.published_url && (
              <a
                href={post.published_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[10px] text-[#0077b5] hover:underline"
              >
                View on LinkedIn →
              </a>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Trend card ────────────────────────────────────────────────────────────────

function TrendCard({ trend }: { trend: MarketingTrend }) {
  return (
    <div className="rounded-xl border border-border/40 bg-secondary/20 px-3 py-2.5">
      <div className="flex items-start gap-2">
        <TrendingUp className="w-3.5 h-3.5 text-muted-foreground/50 shrink-0 mt-0.5" />
        <div className="min-w-0 flex-1">
          <p className="text-[12px] font-medium text-foreground/90 leading-snug">{trend.topic}</p>
          {trend.suggested_action && (
            <p className="text-[10px] text-muted-foreground/60 mt-0.5 capitalize">
              → {trend.suggested_action.replace(/_/g, ' ')}
            </p>
          )}
          <div className="flex items-center gap-2 mt-1.5">
            <span className={cn('text-[11px] font-semibold tabular-nums', scoreColor(trend.relevance_score))}>
              {trend.relevance_score}
            </span>
            <div className="flex-1 h-0.5 rounded-full bg-secondary/60 overflow-hidden">
              <div
                className={cn('h-full rounded-full', scoreBar(trend.relevance_score))}
                style={{ width: `${trend.relevance_score}%` }}
              />
            </div>
            {(trend.found_at || trend.created_at) && (
              <span className="text-[10px] text-muted-foreground/40 shrink-0">{timeAgo(trend.found_at || trend.created_at)}</span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Section ───────────────────────────────────────────────────────────────────

function Section({ label, count, accent, emptyText, children }: {
  label: string; count: number; accent: string; emptyText: string; children: React.ReactNode
}) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <span className={cn('text-[10px] font-semibold uppercase tracking-widest', accent)}>{label}</span>
        {count > 0 && (
          <Badge className="px-1.5 py-0 text-[9px] min-w-[16px] h-4 flex items-center justify-center">
            {count}
          </Badge>
        )}
      </div>
      {count === 0 ? (
        <p className="text-[11px] text-muted-foreground/40 py-2 pl-1">{emptyText}</p>
      ) : (
        <div className="space-y-2">{children}</div>
      )}
    </div>
  )
}

// ── Main sidebar ──────────────────────────────────────────────────────────────

interface MarketingAgentSidebarProps {
  rgb: string
  color: string
}

export function MarketingAgentSidebar({ rgb, color }: MarketingAgentSidebarProps) {
  const [pendingPosts, setPendingPosts]     = useState<MarketingPost[]>([])
  const [publishedPosts, setPublishedPosts] = useState<MarketingPost[]>([])
  const [trends, setTrends]                = useState<MarketingTrend[]>([])
  const [loading, setLoading]              = useState(false)

  const fetchAll = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const [pendingRes, publishedRes, trendsRes] = await Promise.all([
        marketingApi.getContent('pending_approval', 20),
        marketingApi.getContent('published', 5),
        marketingApi.getTrends(10),
      ])
      setPendingPosts(pendingRes.content)
      setPublishedPosts(publishedRes.content)
      setTrends(trendsRes.trends)
    } catch { /* silently degrade */ }
    finally { if (!silent) setLoading(false) }
  }, [])

  useEffect(() => { fetchAll() }, [fetchAll])

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Stats bar */}
      <div
        className="px-5 py-3 border-b border-border/30 flex items-center gap-4 shrink-0"
        style={{ background: `rgba(${rgb}, 0.04)` }}
      >
        <div className="flex items-center gap-1.5">
          <Megaphone className="w-3.5 h-3.5" style={{ color }} />
          <span className="text-[11px] font-medium text-foreground/70">
            {pendingPosts.length} pending
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <Linkedin className="w-3 h-3 text-[#0077b5]" />
          <span className="text-[11px] font-medium text-foreground/70">
            {publishedPosts.length} published
          </span>
        </div>
        <button
          onClick={() => fetchAll()}
          disabled={loading}
          className="ml-auto w-6 h-6 rounded-md bg-secondary/40 hover:bg-secondary flex items-center justify-center transition-colors cursor-pointer disabled:opacity-40"
        >
          <RefreshCw className={cn('w-3 h-3', loading && 'animate-spin')} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-5 space-y-6">
        {loading && pendingPosts.length === 0 ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground/40" />
          </div>
        ) : (
          <>
            <Section label="Awaiting Approval" count={pendingPosts.length} accent="text-warning" emptyText="No posts awaiting approval">
              {pendingPosts.map(p => <PostCard key={p.id} post={p} />)}
            </Section>

            <Section label="LinkedIn Trends" count={trends.length} accent="text-emerald-400" emptyText="No trends tracked yet">
              {trends.map(t => <TrendCard key={t.id} trend={t} />)}
            </Section>

            <Section label="Recently Published" count={publishedPosts.length} accent="text-muted-foreground/60" emptyText="Nothing published yet">
              {publishedPosts.map(p => <PostCard key={p.id} post={p} />)}
            </Section>
          </>
        )}
      </div>
    </div>
  )
}
