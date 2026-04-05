'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronUp,
  GitCommit,
  Bell,
  MessageSquareText,
  RefreshCw,
  Scale,
  X,
  Zap,
} from 'lucide-react';
import { API_BASE } from '@/lib/api/config';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';

// ── Types ─────────────────────────────────────────────────────────────────────

interface Approval {
  id: string;
  agent: string;
  action_type: string;
  content: Record<string, unknown>;
  status: string;
  created_at: string | null;
}

interface Notification {
  id: string;
  agent: string;
  title: string;
  body: string;
  priority: string;
  read: boolean;
  created_at: string | null;
}

interface Commit {
  sha: string;
  message: string;
  author: string;
  branch: string;
  timestamp: string;
  parsed_summary: string | null;
  commit_type: string | null;
  created_at: string | null;
}

interface LegalEvent {
  id: string;
  source_agent: string;
  event_type: string;
  payload: Record<string, unknown>;
  summary: string | null;
  priority: string;
  created_at: string | null;
}

interface OutreachEvent {
  id: string;
  source_agent: string;
  event_type: string;
  payload: Record<string, unknown>;
  summary: string | null;
  priority: string;
  timestamp: string | null;
}

type ActivityEntry =
  | { kind: 'notification'; data: Notification; sortKey: string }
  | { kind: 'commit'; data: Commit; sortKey: string }
  | { kind: 'legal_event'; data: LegalEvent; sortKey: string }
  | { kind: 'outreach_event'; data: OutreachEvent; sortKey: string };

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

function agentLabel(name: string) {
  return name
    .replace(/_/g, ' ')
    .replace(/-/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function actionLabel(type: string) {
  return type
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

const priorityDot: Record<string, string> = {
  urgent: 'bg-destructive',
  high: 'bg-warning',
  medium: 'bg-primary',
  low: 'bg-muted-foreground/50',
};

const commitTypeBadge: Record<string, { label: string; className: string }> = {
  feature: { label: 'Feature', className: 'text-emerald-400 border-emerald-400/30 bg-emerald-400/8' },
  bug_fix: { label: 'Fix', className: 'text-destructive border-destructive/30 bg-destructive/8' },
  release: { label: 'Release', className: 'text-primary border-primary/30 bg-primary/8' },
  chore: { label: 'Chore', className: 'text-muted-foreground border-border/60 bg-secondary/30' },
  refactor: { label: 'Refactor', className: 'text-amber-400 border-amber-400/30 bg-amber-400/8' },
};

const legalEventStyle: Record<string, { label: string; iconClass: string; badgeClass: string }> = {
  'legal.deadline_approaching': {
    label: 'Deadline',
    iconClass: 'text-warning',
    badgeClass: 'text-warning border-warning/30 bg-warning/8',
  },
  'legal.document_drafted': {
    label: 'Document',
    iconClass: 'text-primary/70',
    badgeClass: 'text-primary border-primary/30 bg-primary/8',
  },
  'legal.compliance_gap_found': {
    label: 'Compliance',
    iconClass: 'text-destructive',
    badgeClass: 'text-destructive border-destructive/30 bg-destructive/8',
  },
};

const outreachEventStyle: Record<string, { label: string; iconClass: string; badgeClass: string }> = {
  reply_received: {
    label: 'Reply',
    iconClass: 'text-primary',
    badgeClass: 'text-primary border-primary/30 bg-primary/8',
  },
  lead_converted: {
    label: 'Converted',
    iconClass: 'text-emerald-400',
    badgeClass: 'text-emerald-400 border-emerald-400/30 bg-emerald-400/8',
  },
  objection_heard: {
    label: 'Objection',
    iconClass: 'text-warning',
    badgeClass: 'text-warning border-warning/30 bg-warning/8',
  },
  outreach_sent: {
    label: 'Sent',
    iconClass: 'text-sky-400',
    badgeClass: 'text-sky-400 border-sky-400/30 bg-sky-400/8',
  },
};

// ── Sub-components ────────────────────────────────────────────────────────────

function SectionHeader({
  title,
  count,
  onRefresh,
  refreshing,
}: {
  title: string;
  count?: number;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  return (
    <div className="flex items-center justify-between px-4 py-3 border-b border-border/40 shrink-0">
      <div className="flex items-center gap-2">
        <span
          className="text-xs font-semibold text-foreground/80 uppercase tracking-widest"
          style={{ fontFamily: 'var(--font-heading)' }}
        >
          {title}
        </span>
        {count !== undefined && count > 0 && (
          <Badge className="px-1.5 py-0 text-[10px] min-w-[18px] h-4 flex items-center justify-center">
            {count}
          </Badge>
        )}
      </div>
      <button
        onClick={onRefresh}
        disabled={refreshing}
        className="w-7 h-7 rounded-md bg-secondary/40 hover:bg-secondary flex items-center justify-center transition-colors cursor-pointer disabled:opacity-40"
        aria-label="Refresh"
      >
        <RefreshCw className={cn('w-3 h-3', refreshing && 'animate-spin')} />
      </button>
    </div>
  );
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 gap-2 text-muted-foreground/40">
      <Zap className="w-6 h-6" />
      <span className="text-xs">{label}</span>
    </div>
  );
}

function SkeletonRows({ n = 3 }: { n?: number }) {
  return (
    <div className="space-y-2 p-3">
      {Array.from({ length: n }).map((_, i) => (
        <div key={i} className="animate-pulse space-y-1.5 rounded-xl bg-secondary/30 p-3">
          <div className="h-2.5 bg-secondary/70 rounded-full w-3/4" />
          <div className="h-2 bg-secondary/50 rounded-full w-full" />
          <div className="h-2 bg-secondary/40 rounded-full w-1/2" />
        </div>
      ))}
    </div>
  );
}

// ── Approval card ─────────────────────────────────────────────────────────────

function ApprovalCard({
  approval,
  onDecide,
}: {
  approval: Approval;
  onDecide: (id: string, status: 'approved' | 'rejected') => void;
}) {
  const [loading, setLoading] = useState<'approved' | 'rejected' | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);

  const handle = async (status: 'approved' | 'rejected') => {
    setLoading(status);
    await onDecide(approval.id, status);
    setLoading(null);
  };

  const c = approval.content as Record<string, unknown>;

  // Human-readable title for the card header
  const title = (() => {
    if (c.title) return String(c.title);
    if (c.subject) return String(c.subject);
    if (c.document_type) return actionLabel(String(c.document_type));
    return actionLabel(approval.action_type);
  })();

  // 500-char document snippet the legal agent intentionally provides
  const docPreview = c.preview ? String(c.preview) : null;

  return (
    <div className="rounded-xl border border-border/50 bg-secondary/20 overflow-hidden">
      {/* Header */}
      <div className="px-3 py-2.5 flex items-start gap-2.5">
        <div className="w-6 h-6 rounded-md bg-warning/10 border border-warning/25 flex items-center justify-center shrink-0 mt-0.5">
          <AlertTriangle className="w-3 h-3 text-warning" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-xs font-semibold text-foreground/90">{agentLabel(approval.agent)}</span>
            <Badge
              variant="outline"
              className="text-[9px] py-0 h-4 bg-secondary/50 border-border/50 text-muted-foreground font-normal"
            >
              {actionLabel(approval.action_type)}
            </Badge>
          </div>
          <p className="text-[11px] text-foreground/80 mt-0.5 leading-relaxed font-medium">
            {title}
          </p>
          {approval.created_at && (
            <span className="text-[10px] text-muted-foreground/50 mt-0.5 block">
              {timeAgo(approval.created_at)}
            </span>
          )}
        </div>
      </div>

      {/* Document preview toggle */}
      {docPreview && (
        <>
          <button
            onClick={() => setPreviewOpen((v) => !v)}
            className="w-full px-3 py-1.5 flex items-center gap-1.5 text-[10px] font-medium text-muted-foreground hover:text-foreground/70 border-t border-border/30 bg-secondary/10 hover:bg-secondary/20 transition-colors cursor-pointer"
          >
            {previewOpen ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {previewOpen ? 'Hide' : 'Show'} document preview
          </button>
          {previewOpen && (
            <div className="px-3 py-2.5 border-t border-border/30 bg-secondary/10 max-h-48 overflow-y-auto">
              <p className="text-[11px] text-muted-foreground leading-relaxed whitespace-pre-wrap font-mono">
                {docPreview}
              </p>
            </div>
          )}
        </>
      )}

      {/* Action row */}
      <div className="px-3 py-2.5 flex gap-2 border-t border-border/30">
        <button
          onClick={() => handle('approved')}
          disabled={loading !== null}
          className="flex-1 h-7 rounded-lg text-[11px] font-medium flex items-center justify-center gap-1.5 transition-all cursor-pointer disabled:opacity-50
            bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/25 hover:border-emerald-500/40"
        >
          {loading === 'approved' ? (
            <RefreshCw className="w-3 h-3 animate-spin" />
          ) : (
            <Check className="w-3 h-3" />
          )}
          Accept
        </button>
        <button
          onClick={() => handle('rejected')}
          disabled={loading !== null}
          className="flex-1 h-7 rounded-lg text-[11px] font-medium flex items-center justify-center gap-1.5 transition-all cursor-pointer disabled:opacity-50
            bg-destructive/8 hover:bg-destructive/15 text-destructive border border-destructive/25 hover:border-destructive/40"
        >
          {loading === 'rejected' ? (
            <RefreshCw className="w-3 h-3 animate-spin" />
          ) : (
            <X className="w-3 h-3" />
          )}
          Decline
        </button>
      </div>
    </div>
  );
}

// ── Activity timeline entry ───────────────────────────────────────────────────

function ActivityEntryRow({ entry, isLast }: { entry: ActivityEntry; isLast: boolean }) {
  if (entry.kind === 'notification') {
    const n = entry.data;
    return (
      <div className="flex gap-3 relative">
        {/* Timeline spine */}
        {!isLast && (
          <div className="absolute left-[11px] top-6 bottom-0 w-px bg-border/30" />
        )}
        {/* Dot */}
        <div className="shrink-0 mt-0.5 w-6 h-6 rounded-full bg-secondary/50 border border-border/50 flex items-center justify-center">
          <Bell className="w-3 h-3 text-primary/70" />
        </div>
        <div className="flex-1 min-w-0 pb-3">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="text-[11px] font-semibold text-foreground/85">{n.title}</span>
                <span
                  className={cn(
                    'w-1.5 h-1.5 rounded-full shrink-0',
                    priorityDot[n.priority] ?? 'bg-muted-foreground/50',
                  )}
                />
              </div>
              <p className="text-[11px] text-muted-foreground leading-relaxed mt-0.5 line-clamp-2">
                {n.body}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-[10px] text-primary/70">{agentLabel(n.agent)}</span>
            {n.created_at && (
              <span className="text-[10px] text-muted-foreground/50">{timeAgo(n.created_at)}</span>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (entry.kind === 'outreach_event') {
    const ev = entry.data;
    const style = outreachEventStyle[ev.event_type] ?? {
      label: 'Outreach',
      iconClass: 'text-muted-foreground',
      badgeClass: 'text-muted-foreground border-border/60 bg-secondary/30',
    };
    const payload = ev.payload ?? {};
    const detail = (() => {
      if (payload.contact_name) return String(payload.contact_name);
      if (payload.objection_text) return String(payload.objection_text);
      return ev.summary ?? ev.event_type;
    })();
    return (
      <div className="flex gap-3 relative">
        {!isLast && (
          <div className="absolute left-[11px] top-6 bottom-0 w-px bg-border/30" />
        )}
        <div className="shrink-0 mt-0.5 w-6 h-6 rounded-full bg-secondary/50 border border-border/50 flex items-center justify-center">
          <MessageSquareText className={cn('w-3 h-3', style.iconClass)} />
        </div>
        <div className="flex-1 min-w-0 pb-3">
          <div className="flex items-start gap-1.5 flex-wrap">
            <span className="text-[11px] font-semibold text-foreground/85 leading-tight">{detail}</span>
            <Badge variant="outline" className={cn('text-[9px] py-0 h-4 font-normal shrink-0', style.badgeClass)}>
              {style.label}
            </Badge>
          </div>
          {ev.summary && detail !== ev.summary && (
            <p className="text-[11px] text-muted-foreground leading-relaxed mt-0.5 line-clamp-2">
              {ev.summary}
            </p>
          )}
          <div className="flex items-center gap-2 mt-1">
            <span className="text-[10px] text-muted-foreground/50">{agentLabel(ev.source_agent)}</span>
            {ev.timestamp && (
              <span className="text-[10px] text-muted-foreground/40">{timeAgo(ev.timestamp)}</span>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Legal event
  if (entry.kind === 'legal_event') {
    const ev = entry.data;
    const style = legalEventStyle[ev.event_type] ?? {
      label: 'Legal',
      iconClass: 'text-muted-foreground',
      badgeClass: 'text-muted-foreground border-border/60 bg-secondary/30',
    };
    const p = ev.payload;
    const detail = (() => {
      if (p.item_name) return String(p.item_name);
      if (p.requirement) return String(p.requirement);
      if (p.document_type) return actionLabel(String(p.document_type));
      return ev.summary ?? ev.event_type;
    })();
    return (
      <div className="flex gap-3 relative">
        {!isLast && (
          <div className="absolute left-[11px] top-6 bottom-0 w-px bg-border/30" />
        )}
        <div className={cn('shrink-0 mt-0.5 w-6 h-6 rounded-full bg-secondary/50 border border-border/50 flex items-center justify-center')}>
          <Scale className={cn('w-3 h-3', style.iconClass)} />
        </div>
        <div className="flex-1 min-w-0 pb-3">
          <div className="flex items-start gap-1.5 flex-wrap">
            <span className="text-[11px] font-semibold text-foreground/85 leading-tight">{detail}</span>
            <Badge variant="outline" className={cn('text-[9px] py-0 h-4 font-normal shrink-0', style.badgeClass)}>
              {style.label}
            </Badge>
          </div>
          {ev.summary && detail !== ev.summary && (
            <p className="text-[11px] text-muted-foreground leading-relaxed mt-0.5 line-clamp-2">
              {ev.summary}
            </p>
          )}
          <div className="flex items-center gap-2 mt-1">
            <span className="text-[10px] text-muted-foreground/50">{agentLabel(ev.source_agent)}</span>
            {ev.created_at && (
              <span className="text-[10px] text-muted-foreground/40">{timeAgo(ev.created_at)}</span>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Commit
  const c = entry.data;
  const typeInfo = commitTypeBadge[c.commit_type ?? ''];
  return (
    <div className="flex gap-3 relative">
      {!isLast && (
        <div className="absolute left-[11px] top-6 bottom-0 w-px bg-border/30" />
      )}
      <div className="shrink-0 mt-0.5 w-6 h-6 rounded-full bg-secondary/50 border border-border/50 flex items-center justify-center">
        <GitCommit className="w-3 h-3 text-emerald-400/70" />
      </div>
      <div className="flex-1 min-w-0 pb-3">
        <div className="flex items-start gap-1.5 flex-wrap">
          <span className="text-[11px] font-semibold text-foreground/85 leading-tight">
            {c.parsed_summary ?? c.message.split('\n')[0].slice(0, 72)}
          </span>
          {typeInfo && (
            <Badge
              variant="outline"
              className={cn('text-[9px] py-0 h-4 font-normal shrink-0', typeInfo.className)}
            >
              {typeInfo.label}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2 mt-1 flex-wrap">
          <span className="text-[10px] text-emerald-400/70 font-mono">{c.sha.slice(0, 7)}</span>
          <span className="text-[10px] text-muted-foreground/50">{c.branch}</span>
          <span className="text-[10px] text-muted-foreground/50">{c.author}</span>
          {c.timestamp && (
            <span className="text-[10px] text-muted-foreground/40">{timeAgo(c.timestamp)}</span>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────

interface RightActivityPanelProps {
  open: boolean;
  onClose: () => void;
}

const MIN_WIDTH = 300;
const MAX_WIDTH = 700;
const DEFAULT_WIDTH = 360;

export function RightActivityPanel({ open, onClose }: RightActivityPanelProps) {
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [activity, setActivity] = useState<ActivityEntry[]>([]);
  const [loadingApprovals, setLoadingApprovals] = useState(false);
  const [loadingActivity, setLoadingActivity] = useState(false);
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  const dragging = useRef(false);

  // ── Fetchers ──────────────────────────────────────────────────────────────

  const fetchApprovals = useCallback(async () => {
    setLoadingApprovals(true);
    try {
      const res = await fetch(`${API_BASE}/api/approvals?status=pending`);
      if (!res.ok) throw new Error('Failed to fetch approvals');
      const data: Approval[] = await res.json();
      setApprovals(data);
    } catch {
      // Silently degrade — backend may not be running
    } finally {
      setLoadingApprovals(false);
    }
  }, []);

  const fetchActivity = useCallback(async () => {
    setLoadingActivity(true);
    try {
      const [notifRes, commitsRes, legalEventsRes, outreachEventsRes] = await Promise.all([
        fetch(`${API_BASE}/api/notifications?limit=30`),
        fetch(`${API_BASE}/api/dev/commits?limit=20`),
        fetch(`${API_BASE}/api/events?agent=legal&limit=30`),
        fetch(`${API_BASE}/api/events?agent=outreach&limit=30`),
      ]);

      const entries: ActivityEntry[] = [];

      if (notifRes.ok) {
        const notifs: Notification[] = await notifRes.json();
        for (const n of notifs) {
          entries.push({ kind: 'notification', data: n, sortKey: n.created_at ?? '0' });
        }
      }

      if (commitsRes.ok) {
        const { commits }: { commits: Commit[] } = await commitsRes.json();
        for (const c of commits) {
          entries.push({ kind: 'commit', data: c, sortKey: c.created_at ?? c.timestamp ?? '0' });
        }
      }

      if (legalEventsRes.ok) {
        const legalEvents: LegalEvent[] = await legalEventsRes.json();
        for (const ev of legalEvents) {
          entries.push({ kind: 'legal_event', data: ev, sortKey: ev.created_at ?? '0' });
        }
      }
      if (outreachEventsRes.ok) {
        const outreachEvents: OutreachEvent[] = await outreachEventsRes.json();
        for (const ev of outreachEvents) {
          entries.push({ kind: 'outreach_event', data: ev, sortKey: ev.timestamp ?? '0' });
        }
      }

      // Sort newest-first
      entries.sort((a, b) => (a.sortKey < b.sortKey ? 1 : -1));
      setActivity(entries);
    } catch {
      // Silently degrade
    } finally {
      setLoadingActivity(false);
    }
  }, []);

  // ── Load on open ──────────────────────────────────────────────────────────

  useEffect(() => {
    if (open) {
      fetchApprovals();
      fetchActivity();
    }
  }, [open, fetchApprovals, fetchActivity]);

  // Escape key
  useEffect(() => {
    const handle = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    if (open) document.addEventListener('keydown', handle);
    return () => document.removeEventListener('keydown', handle);
  }, [open, onClose]);

  // ── Drag to resize ────────────────────────────────────────────────────────

  const startDrag = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = true;

    const onMove = (ev: MouseEvent) => {
      if (!dragging.current) return;
      const newWidth = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, window.innerWidth - ev.clientX));
      setWidth(newWidth);
    };

    const onUp = () => {
      dragging.current = false;
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };

    document.body.style.cursor = 'ew-resize';
    document.body.style.userSelect = 'none';
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }, []);

  // ── Approve / Decline ─────────────────────────────────────────────────────

  const handleDecide = useCallback(
    async (id: string, status: 'approved' | 'rejected') => {
      try {
        const res = await fetch(`${API_BASE}/api/approvals/${id}/respond`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status }),
        });
        if (res.ok) {
          setApprovals((prev) => prev.filter((a) => a.id !== id));
        }
      } catch {
        // Silently degrade
      }
    },
    [],
  );

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div
      className={cn(
        'fixed top-0 right-0 h-full z-50 flex flex-col',
        'border-l border-border/50 bg-card/95 backdrop-blur-xl shadow-2xl shadow-black/40',
        'transition-transform duration-300 ease-out',
        open ? 'translate-x-0' : 'translate-x-full',
      )}
      style={{ width }}
    >
      {/* ── Drag handle ───────────────────────────────────────────────────── */}
      <div
        onMouseDown={startDrag}
        className="absolute left-0 top-0 bottom-0 w-1 z-10 cursor-ew-resize group/drag"
        title="Drag to resize"
      >
        <div className="absolute inset-y-0 left-0 w-1 bg-transparent group-hover/drag:bg-primary/30 transition-colors duration-150 rounded-full" />
      </div>

      {/* ── Panel header ──────────────────────────────────────────────────── */}
      <div className="shrink-0 flex items-center justify-between px-4 h-13 border-b border-border/40">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-md bg-primary/10 border border-primary/20 flex items-center justify-center">
            <Zap className="w-3 h-3 text-primary" />
          </div>
          <span
            className="text-sm font-semibold text-foreground/90"
            style={{ fontFamily: 'var(--font-heading)' }}
          >
            Activity
          </span>
        </div>
        <button
          onClick={onClose}
          aria-label="Close panel"
          className="w-8 h-8 rounded-lg bg-secondary/50 hover:bg-secondary flex items-center justify-center transition-colors duration-150 cursor-pointer"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* ── Top half: Alerts ──────────────────────────────────────────────── */}
      <div className="flex flex-col" style={{ flex: '0 0 50%', minHeight: 0 }}>
        <SectionHeader
          title="Alerts"
          count={approvals.length}
          onRefresh={fetchApprovals}
          refreshing={loadingApprovals}
        />

        <div className="flex-1 min-h-0 overflow-y-auto">
          {loadingApprovals ? (
            <SkeletonRows n={2} />
          ) : approvals.length === 0 ? (
            <EmptyState label="No pending approvals" />
          ) : (
            <div className="p-3 space-y-2">
              {approvals.map((a) => (
                <ApprovalCard key={a.id} approval={a} onDecide={handleDecide} />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Divider */}
      <div className="shrink-0 h-px bg-border/50" />

      {/* ── Bottom half: Activity feed ─────────────────────────────────────── */}
      <div className="flex flex-col" style={{ flex: '0 0 50%', minHeight: 0 }}>
        <SectionHeader
          title="Activity"
          count={activity.length > 0 ? activity.length : undefined}
          onRefresh={fetchActivity}
          refreshing={loadingActivity}
        />

        <div className="flex-1 min-h-0 overflow-y-auto">
          {loadingActivity ? (
            <SkeletonRows n={4} />
          ) : activity.length === 0 ? (
            <EmptyState label="No recent activity" />
          ) : (
            <div className="px-3 pt-3">
              {activity.map((entry, i) => (
                <ActivityEntryRow
                  key={
                    entry.kind === 'notification' ? `n-${entry.data.id}` :
                    entry.kind === 'commit' ? `c-${entry.data.sha}` :
                    `e-${entry.data.id}`
                  }
                  entry={entry}
                  isLast={i === activity.length - 1}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
