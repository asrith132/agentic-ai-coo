'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  GitCommit,
  GitMerge,
  Layers,
  RefreshCw,
  Sparkles,
  Zap,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { devApi, type Commit, type Feature } from '@/lib/api/dev';
import { API_BASE } from '@/lib/api/config';

// ── Types ─────────────────────────────────────────────────────────────────────

interface DevEvent {
  id: string;
  event_type: string;
  summary: string | null;
  priority: string;
  payload: Record<string, unknown>;
  timestamp: string | null;
}

type Tab = 'commits' | 'features' | 'events';

// ── Helpers ───────────────────────────────────────────────────────────────────

function timeAgo(iso: string | null): string {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

const commitTypeBadge: Record<string, { label: string; cls: string }> = {
  feature:     { label: 'Feature',  cls: 'text-emerald-400 border-emerald-400/30 bg-emerald-400/8' },
  bug_fix:     { label: 'Fix',      cls: 'text-destructive border-destructive/30 bg-destructive/8' },
  release:     { label: 'Release',  cls: 'text-primary border-primary/30 bg-primary/8' },
  chore:       { label: 'Chore',    cls: 'text-muted-foreground border-border/60 bg-secondary/30' },
  refactor:    { label: 'Refactor', cls: 'text-amber-400 border-amber-400/30 bg-amber-400/8' },
  maintenance: { label: 'Maint',    cls: 'text-muted-foreground border-border/60 bg-secondary/30' },
};

const eventBadge: Record<string, { label: string; cls: string }> = {
  feature_shipped:  { label: 'Shipped',  cls: 'text-emerald-400 border-emerald-400/30 bg-emerald-400/8' },
  bug_fixed:        { label: 'Fixed',    cls: 'text-destructive border-destructive/30 bg-destructive/8' },
  release_created:  { label: 'Release',  cls: 'text-primary border-primary/30 bg-primary/8' },
};

// ── Sub-components ────────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="text-[10px] font-semibold text-muted-foreground/60 uppercase tracking-widest mb-2">
      {children}
    </h4>
  );
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 gap-2 text-muted-foreground/40">
      <GitCommit className="w-5 h-5" />
      <span className="text-xs">{label}</span>
    </div>
  );
}

function CommitRow({ commit }: { commit: Commit }) {
  const typeInfo = commitTypeBadge[commit.commit_type ?? ''];
  return (
    <div className="rounded-xl border border-border/40 bg-secondary/20 px-3 py-2.5 space-y-1.5">
      <div className="flex items-start gap-1.5 flex-wrap">
        <span className="text-[11px] font-medium text-foreground/85 leading-snug flex-1 min-w-0">
          {commit.parsed_summary ?? commit.message.split('\n')[0].slice(0, 80)}
        </span>
        {typeInfo && (
          <Badge variant="outline" className={cn('text-[9px] py-0 h-4 font-normal shrink-0', typeInfo.cls)}>
            {typeInfo.label}
          </Badge>
        )}
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[10px] font-mono text-emerald-400/70">{commit.sha.slice(0, 7)}</span>
        <span className="text-[10px] text-muted-foreground/50">{commit.branch}</span>
        <span className="text-[10px] text-muted-foreground/50">{commit.author}</span>
        <span className="text-[10px] text-muted-foreground/40 ml-auto">{timeAgo(commit.timestamp)}</span>
      </div>
    </div>
  );
}

function FeatureRow({ feature }: { feature: Feature }) {
  return (
    <div className="rounded-xl border border-border/40 bg-secondary/20 px-3 py-2.5 space-y-1">
      <div className="flex items-center gap-2">
        <span className="text-[11px] font-medium text-foreground/85 flex-1 min-w-0 truncate">
          {feature.feature_name}
        </span>
        <Badge
          variant="outline"
          className={cn(
            'text-[9px] py-0 h-4 font-normal shrink-0',
            feature.status === 'shipped'
              ? 'text-emerald-400 border-emerald-400/30 bg-emerald-400/8'
              : 'text-muted-foreground border-border/60 bg-secondary/30',
          )}
        >
          {feature.status}
        </Badge>
      </div>
      {feature.description && (
        <p className="text-[10px] text-muted-foreground/70 leading-relaxed line-clamp-2">
          {feature.description}
        </p>
      )}
      {feature.shipped_at && (
        <span className="text-[10px] text-muted-foreground/40">{timeAgo(feature.shipped_at)}</span>
      )}
    </div>
  );
}

function EventRow({ event }: { event: DevEvent }) {
  const badge = eventBadge[event.event_type] ?? {
    label: event.event_type.replace(/_/g, ' '),
    cls: 'text-muted-foreground border-border/60 bg-secondary/30',
  };
  const p = event.payload ?? {};
  const title = (() => {
    if (p.feature_name) return String(p.feature_name);
    if (p.version) return `Release v${p.version}`;
    if (p.description) return String(p.description).slice(0, 60);
    return event.summary ?? event.event_type;
  })();

  return (
    <div className="rounded-xl border border-border/40 bg-secondary/20 px-3 py-2.5 space-y-1.5">
      <div className="flex items-start gap-1.5 flex-wrap">
        <span className="text-[11px] font-medium text-foreground/85 flex-1 min-w-0">{title}</span>
        <Badge variant="outline" className={cn('text-[9px] py-0 h-4 font-normal shrink-0', badge.cls)}>
          {badge.label}
        </Badge>
      </div>
      {event.summary && event.summary !== title && (
        <p className="text-[10px] text-muted-foreground/70 leading-relaxed line-clamp-2">{event.summary}</p>
      )}
      {event.timestamp && (
        <span className="text-[10px] text-muted-foreground/40">{timeAgo(event.timestamp)}</span>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface DevAgentSidebarProps {
  rgb: string;
  color: string;
}

export function DevAgentSidebar({ rgb, color }: DevAgentSidebarProps) {
  const [tab, setTab] = useState<Tab>('commits');
  const [commits, setCommits]   = useState<Commit[]>([]);
  const [features, setFeatures] = useState<Feature[]>([]);
  const [events, setEvents]     = useState<DevEvent[]>([]);
  const [loading, setLoading]   = useState(false);

  const fetchTab = useCallback(async (t: Tab) => {
    setLoading(true);
    try {
      if (t === 'commits') {
        const data = await devApi.listCommits(30);
        setCommits(data.commits ?? []);
      } else if (t === 'features') {
        const data = await devApi.listFeatures();
        setFeatures(data.features ?? []);
      } else {
        const res = await fetch(`${API_BASE}/api/events?agent=dev_activity&limit=30`);
        if (res.ok) setEvents(await res.json());
      }
    } catch {
      // Silently degrade
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchTab(tab); }, [tab, fetchTab]);

  const tabs: { key: Tab; label: string; icon: React.ReactNode; count?: number }[] = [
    { key: 'commits',  label: 'Commits',  icon: <GitCommit className="w-3 h-3" />,  count: commits.length || undefined },
    { key: 'features', label: 'Features', icon: <Layers className="w-3 h-3" />,     count: features.length || undefined },
    { key: 'events',   label: 'Events',   icon: <Zap className="w-3 h-3" />,        count: events.length || undefined },
  ];

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="shrink-0 px-5 pt-5 pb-3 border-b border-border/40">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <div
              className="w-6 h-6 rounded-lg flex items-center justify-center"
              style={{ background: `rgba(${rgb},0.12)`, border: `1px solid rgba(${rgb},0.28)` }}
            >
              <GitMerge className="w-3.5 h-3.5" style={{ color }} />
            </div>
            <span className="text-xs font-semibold text-foreground/85">Dev Activity</span>
          </div>
          <button
            onClick={() => fetchTab(tab)}
            disabled={loading}
            className="w-7 h-7 rounded-lg bg-secondary/40 hover:bg-secondary flex items-center justify-center transition-colors cursor-pointer disabled:opacity-40"
          >
            <RefreshCw className={cn('w-3 h-3', loading && 'animate-spin')} />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                'flex-1 flex items-center justify-center gap-1.5 h-7 rounded-lg text-[11px] font-medium transition-all cursor-pointer',
                tab === t.key
                  ? 'text-foreground'
                  : 'text-muted-foreground/60 hover:text-muted-foreground',
              )}
              style={
                tab === t.key
                  ? { background: `rgba(${rgb},0.12)`, border: `1px solid rgba(${rgb},0.25)`, color }
                  : { background: 'transparent', border: '1px solid transparent' }
              }
            >
              {t.icon}
              {t.label}
              {t.count !== undefined && t.count > 0 && (
                <span
                  className="text-[9px] rounded-full px-1 min-w-[14px] h-3.5 flex items-center justify-center font-mono"
                  style={{ background: `rgba(${rgb},0.18)`, color }}
                >
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        {loading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="animate-pulse rounded-xl bg-secondary/30 h-14" />
            ))}
          </div>
        ) : tab === 'commits' ? (
          commits.length === 0 ? (
            <EmptyState label="No commits yet. Connect GitHub webhook to start tracking." />
          ) : (
            <>
              <SectionLabel>{commits.length} recent commits</SectionLabel>
              {commits.map((c) => <CommitRow key={c.sha} commit={c} />)}
            </>
          )
        ) : tab === 'features' ? (
          features.length === 0 ? (
            <EmptyState label="No features detected yet. Features are extracted from commit analysis." />
          ) : (
            <>
              <SectionLabel>{features.length} shipped features</SectionLabel>
              {features.map((f) => <FeatureRow key={f.id ?? f.feature_name} feature={f} />)}
            </>
          )
        ) : (
          events.length === 0 ? (
            <EmptyState label="No dev events yet." />
          ) : (
            <>
              <SectionLabel>{events.length} events</SectionLabel>
              {events.map((ev) => <EventRow key={ev.id} event={ev} />)}
            </>
          )
        )}
      </div>
    </div>
  );
}
