'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Circle,
  Clock,
  FileText,
  Loader2,
  Play,
  Plus,
  RefreshCw,
  Scale,
  Sparkles,
} from 'lucide-react';
import { API_BASE } from '@/lib/api/config';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';

// ── Types ─────────────────────────────────────────────────────────────────────

interface ChecklistItem {
  id: string;
  item: string;
  description: string;
  category: string;
  priority: string;
  status: string;     // pending | in_progress | done | overdue
  due_date: string | null;
  notes: string | null;
}

interface LegalDocument {
  id: string;
  document_type: string;
  title: string;
  status: string;     // draft | final
  checklist_item_id: string | null;
  approval_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

interface DeadlineItem extends ChecklistItem {
  days_remaining: number;
}

type Tab = 'deadlines' | 'checklist' | 'documents';

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

function formatDate(iso: string | null): string {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

const priorityStyle: Record<string, { dot: string; badge: string }> = {
  urgent: { dot: 'bg-destructive', badge: 'text-destructive border-destructive/30 bg-destructive/8' },
  high:   { dot: 'bg-warning',     badge: 'text-warning border-warning/30 bg-warning/8' },
  medium: { dot: 'bg-primary',     badge: 'text-primary border-primary/30 bg-primary/8' },
  low:    { dot: 'bg-muted-foreground/50', badge: 'text-muted-foreground border-border/50 bg-secondary/30' },
};

const statusStyle: Record<string, { label: string; className: string; icon: React.ReactNode }> = {
  overdue:     { label: 'Overdue',     className: 'text-destructive border-destructive/30 bg-destructive/8',  icon: <AlertTriangle className="w-3 h-3" /> },
  pending:     { label: 'Pending',     className: 'text-muted-foreground border-border/50 bg-secondary/30',   icon: <Circle className="w-3 h-3" /> },
  in_progress: { label: 'In progress', className: 'text-warning border-warning/30 bg-warning/8',              icon: <Clock className="w-3 h-3" /> },
  done:        { label: 'Done',        className: 'text-emerald-400 border-emerald-400/30 bg-emerald-400/8',  icon: <CheckCircle2 className="w-3 h-3" /> },
};

const docStatusStyle: Record<string, { label: string; className: string }> = {
  draft: { label: 'Draft', className: 'text-warning border-warning/30 bg-warning/8' },
  final: { label: 'Final', className: 'text-emerald-400 border-emerald-400/30 bg-emerald-400/8' },
};

function daysUrgency(days: number): string {
  if (days < 0)   return 'text-destructive';
  if (days <= 3)  return 'text-destructive';
  if (days <= 7)  return 'text-warning';
  if (days <= 14) return 'text-amber-400';
  return 'text-muted-foreground';
}

function daysLabel(days: number): string {
  if (days < 0)   return `${Math.abs(days)}d overdue`;
  if (days === 0) return 'Due today';
  return `${days}d left`;
}

// ── Shared sub-components ─────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="text-[10px] font-semibold text-muted-foreground/70 uppercase tracking-widest mb-3">
      {children}
    </h4>
  );
}

function SkeletonList({ n = 3 }: { n?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: n }).map((_, i) => (
        <div key={i} className="animate-pulse space-y-1.5 rounded-lg bg-secondary/30 p-3">
          <div className="h-2.5 bg-secondary/70 rounded-full w-3/4" />
          <div className="h-2 bg-secondary/50 rounded-full w-1/2" />
        </div>
      ))}
    </div>
  );
}

function ActionButton({
  onClick, loading, disabled, icon, children, variant = 'default',
}: {
  onClick: () => void;
  loading?: boolean;
  disabled?: boolean;
  icon: React.ReactNode;
  children: React.ReactNode;
  variant?: 'default' | 'primary';
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled || loading}
      className={cn(
        'flex items-center gap-1.5 px-3 h-7 rounded-lg text-[11px] font-medium transition-all cursor-pointer disabled:opacity-50',
        variant === 'primary'
          ? 'bg-primary/10 hover:bg-primary/20 text-primary border border-primary/25 hover:border-primary/40'
          : 'bg-secondary/50 hover:bg-secondary text-muted-foreground hover:text-foreground border border-border/50',
      )}
    >
      {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : icon}
      {children}
    </button>
  );
}

// ── Deadline row ──────────────────────────────────────────────────────────────

function DeadlineRow({ item }: { item: DeadlineItem }) {
  const p = priorityStyle[item.priority] ?? priorityStyle.low;
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-border/30 last:border-0">
      <CalendarClock className={cn('w-3.5 h-3.5 shrink-0 mt-0.5', daysUrgency(item.days_remaining))} />
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <span className="text-xs font-medium text-foreground/85 leading-snug">{item.item}</span>
          <span className={cn('text-[10px] font-semibold shrink-0 tabular-nums', daysUrgency(item.days_remaining))}>
            {daysLabel(item.days_remaining)}
          </span>
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          <span className={cn('w-1.5 h-1.5 rounded-full shrink-0', p.dot)} />
          <span className="text-[10px] text-muted-foreground capitalize">{item.priority}</span>
          {item.due_date && (
            <span className="text-[10px] text-muted-foreground/50">{formatDate(item.due_date)}</span>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Checklist row ─────────────────────────────────────────────────────────────

function ChecklistRow({
  item,
  onDraft,
  drafting,
}: {
  item: ChecklistItem;
  onDraft: (id: string) => void;
  drafting: string | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const p = priorityStyle[item.priority] ?? priorityStyle.low;
  const s = statusStyle[item.status] ?? statusStyle.pending;
  const canDraft = item.status === 'pending' || item.status === 'overdue';
  const isDrafting = drafting === item.id;

  return (
    <div className="rounded-lg border border-border/40 bg-secondary/10 overflow-hidden">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full px-3 py-2.5 flex items-start gap-2.5 text-left cursor-pointer hover:bg-secondary/20 transition-colors"
      >
        <span className={cn('w-1.5 h-1.5 rounded-full shrink-0 mt-1.5', p.dot)} />
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2 flex-wrap">
            <span className="text-xs font-medium text-foreground/85 leading-snug flex-1">{item.item}</span>
            <Badge variant="outline" className={cn('text-[9px] py-0 h-4 font-normal gap-1 shrink-0', s.className)}>
              {s.icon}{s.label}
            </Badge>
          </div>
          {item.due_date && (
            <span className="text-[10px] text-muted-foreground/50 mt-0.5 block">
              Due {formatDate(item.due_date)}
            </span>
          )}
        </div>
        {expanded ? <ChevronUp className="w-3 h-3 text-muted-foreground/50 shrink-0 mt-0.5" /> : <ChevronDown className="w-3 h-3 text-muted-foreground/50 shrink-0 mt-0.5" />}
      </button>

      {expanded && (
        <div className="px-3 pb-3 pt-1 border-t border-border/30 bg-secondary/10 space-y-2.5">
          {item.description && (
            <p className="text-[11px] text-muted-foreground leading-relaxed">{item.description}</p>
          )}
          {item.notes && (
            <p className="text-[10px] text-muted-foreground/50">{item.notes}</p>
          )}
          {canDraft && (
            <ActionButton
              onClick={() => onDraft(item.id)}
              loading={isDrafting}
              disabled={drafting !== null && !isDrafting}
              icon={<Sparkles className="w-3 h-3" />}
              variant="primary"
            >
              {isDrafting ? 'Drafting document…' : 'Draft document'}
            </ActionButton>
          )}
        </div>
      )}
    </div>
  );
}

// ── Document row ──────────────────────────────────────────────────────────────

function DocumentRow({ doc }: { doc: LegalDocument }) {
  const s = docStatusStyle[doc.status] ?? { label: doc.status, className: 'text-muted-foreground border-border/50 bg-secondary/30' };
  const typeLabel = doc.document_type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-border/30 last:border-0">
      <div className="w-7 h-7 rounded-lg bg-secondary/40 border border-border/40 flex items-center justify-center shrink-0 mt-0.5">
        <FileText className="w-3.5 h-3.5 text-muted-foreground/70" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <span className="text-xs font-medium text-foreground/85 leading-snug flex-1 min-w-0 truncate">
            {doc.title}
          </span>
          <Badge variant="outline" className={cn('text-[9px] py-0 h-4 font-normal shrink-0', s.className)}>
            {s.label}
          </Badge>
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          <span className="text-[10px] text-muted-foreground/60">{typeLabel}</span>
          {doc.created_at && (
            <span className="text-[10px] text-muted-foreground/40">{timeAgo(doc.created_at)}</span>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Generate checklist form ───────────────────────────────────────────────────

const STAGE_OPTIONS   = ['pre_launch', 'launched', 'fundraising', 'series_a'];
const PRODUCT_OPTIONS = ['SaaS', 'marketplace', 'hardware', 'fintech', 'healthtech'];

function GenerateForm({ onGenerate, generating }: { onGenerate: (v: Record<string, string>) => void; generating: boolean }) {
  const [values, setValues] = useState({
    entity_type:  'Delaware C-Corp',
    jurisdiction: 'Delaware, USA',
    stage:        'pre_launch',
    product_type: 'SaaS',
  });

  const field = (label: string, key: keyof typeof values, options?: string[]) => (
    <div className="space-y-1">
      <label className="text-[10px] text-muted-foreground/70 uppercase tracking-wider">{label}</label>
      {options ? (
        <select
          value={values[key]}
          onChange={(e) => setValues((v) => ({ ...v, [key]: e.target.value }))}
          className="w-full text-xs bg-secondary/40 border border-border/50 rounded-md px-2.5 py-1.5 text-foreground/85 focus:outline-none focus:border-primary/40 cursor-pointer"
        >
          {options.map((o) => (
            <option key={o} value={o}>{o.replace(/_/g, ' ')}</option>
          ))}
        </select>
      ) : (
        <input
          value={values[key]}
          onChange={(e) => setValues((v) => ({ ...v, [key]: e.target.value }))}
          className="w-full text-xs bg-secondary/40 border border-border/50 rounded-md px-2.5 py-1.5 text-foreground/85 focus:outline-none focus:border-primary/40"
        />
      )}
    </div>
  );

  return (
    <div className="rounded-xl border border-primary/20 bg-primary/5 p-4 space-y-3">
      <div className="flex items-center gap-2 mb-1">
        <Sparkles className="w-3.5 h-3.5 text-primary" />
        <span className="text-xs font-semibold text-foreground/80">Generate Compliance Checklist</span>
      </div>
      {field('Entity type', 'entity_type')}
      {field('Jurisdiction', 'jurisdiction')}
      {field('Stage', 'stage', STAGE_OPTIONS)}
      {field('Product type', 'product_type', PRODUCT_OPTIONS)}
      <ActionButton
        onClick={() => onGenerate(values)}
        loading={generating}
        icon={<Plus className="w-3 h-3" />}
        variant="primary"
      >
        {generating ? 'Generating… (up to 15s)' : 'Generate checklist'}
      </ActionButton>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface LegalAgentSidebarProps {
  rgb: string;
  color: string;
}

export function LegalAgentSidebar({ rgb, color }: LegalAgentSidebarProps) {
  const [tab, setTab] = useState<Tab>('checklist');
  const [deadlines, setDeadlines]   = useState<DeadlineItem[]>([]);
  const [checklist, setChecklist]   = useState<ChecklistItem[]>([]);
  const [documents, setDocuments]   = useState<LegalDocument[]>([]);
  const [loading, setLoading]       = useState(false);
  const [runningCheck, setRunningCheck] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [drafting, setDrafting]     = useState<string | null>(null);
  const [toast, setToast]           = useState<{ msg: string; ok: boolean } | null>(null);

  const showToast = (msg: string, ok = true) => {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 4000);
  };

  const fetchTab = useCallback(async (t: Tab) => {
    setLoading(true);
    try {
      if (t === 'deadlines') {
        const res = await fetch(`${API_BASE}/api/legal/deadlines?days=30`);
        if (res.ok) setDeadlines((await res.json()).items ?? []);
      } else if (t === 'checklist') {
        const res = await fetch(`${API_BASE}/api/legal/checklist`);
        if (res.ok) setChecklist((await res.json()).items ?? []);
      } else {
        const res = await fetch(`${API_BASE}/api/legal/documents`);
        if (res.ok) setDocuments((await res.json()).documents ?? []);
      }
    } catch { /* backend not running */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchTab(tab); }, [tab, fetchTab]);

  // ── Actions ───────────────────────────────────────────────────────────────

  const handleRunCheck = async () => {
    setRunningCheck(true);
    try {
      const res = await fetch(`${API_BASE}/api/legal/run`, { method: 'POST' });
      if (res.ok) {
        showToast('Deadline check queued');
        setTimeout(() => fetchTab('deadlines'), 1500);
      } else {
        showToast('Failed to run check', false);
      }
    } catch { showToast('Backend unreachable', false); }
    finally { setRunningCheck(false); }
  };

  const handleGenerate = async (values: Record<string, string>) => {
    setGenerating(true);
    try {
      const res = await fetch(`${API_BASE}/api/legal/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      });
      if (res.ok) {
        const data = await res.json();
        showToast(`Generated ${data.items_created ?? 0} checklist items`);
        await fetchTab('checklist');
        setTab('checklist');
      } else {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail ?? 'Generation failed', false);
      }
    } catch { showToast('Backend unreachable', false); }
    finally { setGenerating(false); }
  };

  const handleDraft = async (itemId: string) => {
    setDrafting(itemId);
    try {
      const res = await fetch(`${API_BASE}/api/legal/draft/${itemId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ context: '' }),
      });
      if (res.ok) {
        const data = await res.json();
        showToast(`Draft ready: ${data.title ?? 'document'}`);
        // Refresh both checklist and documents
        await Promise.all([fetchTab('checklist'), fetch(`${API_BASE}/api/legal/documents`).then(async (r) => {
          if (r.ok) setDocuments((await r.json()).documents ?? []);
        })]);
      } else {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail ?? 'Draft failed', false);
      }
    } catch { showToast('Backend unreachable', false); }
    finally { setDrafting(null); }
  };

  // ── Sorted checklist ──────────────────────────────────────────────────────

  const statusOrder = ['overdue', 'pending', 'in_progress', 'done'];
  const priorityOrder: Record<string, number> = { urgent: 0, high: 1, medium: 2, low: 3 };
  const sortedChecklist = [...checklist].sort((a, b) => {
    const sd = statusOrder.indexOf(a.status) - statusOrder.indexOf(b.status);
    if (sd !== 0) return sd;
    return (priorityOrder[a.priority] ?? 9) - (priorityOrder[b.priority] ?? 9);
  });

  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: 'checklist', label: 'Checklist', count: checklist.length || undefined },
    { key: 'deadlines', label: 'Deadlines', count: deadlines.length || undefined },
    { key: 'documents', label: 'Docs',      count: documents.length || undefined },
  ];

  return (
    <div className="flex flex-col h-full relative">

      {/* Toast */}
      {toast && (
        <div className={cn(
          'absolute top-2 left-3 right-3 z-20 px-3 py-2 rounded-lg text-xs font-medium shadow-lg transition-all',
          toast.ok
            ? 'bg-emerald-500/15 border border-emerald-500/30 text-emerald-400'
            : 'bg-destructive/15 border border-destructive/30 text-destructive',
        )}>
          {toast.msg}
        </div>
      )}

      {/* Tabs */}
      <div
        className="shrink-0 px-4 pt-3 pb-0 border-b border-border/40"
        style={{ background: `linear-gradient(180deg, rgba(${rgb},0.04) 0%, transparent 100%)` }}
      >
        <div className="flex bg-secondary/40 rounded-lg p-0.5 gap-0.5">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                'flex-1 py-1.5 text-[11px] font-medium rounded-md transition-all duration-150 cursor-pointer flex items-center justify-center gap-1',
                tab === t.key
                  ? 'bg-background/80 text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground/70',
              )}
            >
              {t.label}
              {t.count !== undefined && tab !== t.key && (
                <span className="text-[9px] bg-secondary rounded-full px-1 leading-4 tabular-nums">
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Action row */}
        <div className="flex items-center justify-between py-2">
          {tab === 'deadlines' && (
            <ActionButton onClick={handleRunCheck} loading={runningCheck} icon={<Play className="w-3 h-3" />}>
              Run check
            </ActionButton>
          )}
          {tab !== 'deadlines' && <span />}
          <button
            onClick={() => fetchTab(tab)}
            disabled={loading}
            className="flex items-center gap-1 text-[10px] text-muted-foreground/50 hover:text-muted-foreground transition-colors cursor-pointer disabled:opacity-40"
          >
            <RefreshCw className={cn('w-3 h-3', loading && 'animate-spin')} />
            Refresh
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 overflow-y-auto px-4 py-3">
        {loading ? (
          <SkeletonList n={4} />
        ) : tab === 'checklist' ? (
          sortedChecklist.length === 0 ? (
            <div className="space-y-4">
              <div className="flex flex-col items-center justify-center py-6 gap-2 text-muted-foreground/40">
                <Scale className="w-6 h-6" />
                <span className="text-xs">No checklist items yet</span>
              </div>
              <GenerateForm onGenerate={handleGenerate} generating={generating} />
            </div>
          ) : (
            <div className="space-y-2">
              <SectionLabel>{sortedChecklist.length} items</SectionLabel>
              {sortedChecklist.map((item) => (
                <ChecklistRow key={item.id} item={item} onDraft={handleDraft} drafting={drafting} />
              ))}
              {/* Regenerate option at bottom */}
              <div className="pt-2 border-t border-border/30">
                <GenerateForm onGenerate={handleGenerate} generating={generating} />
              </div>
            </div>
          )
        ) : tab === 'deadlines' ? (
          deadlines.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 gap-2 text-muted-foreground/40">
              <CalendarClock className="w-6 h-6" />
              <span className="text-xs">No upcoming deadlines</span>
            </div>
          ) : (
            <div>
              <SectionLabel>Due within 30 days</SectionLabel>
              {deadlines.map((item) => (
                <DeadlineRow key={item.id} item={item} />
              ))}
            </div>
          )
        ) : (
          documents.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 gap-2 text-muted-foreground/40">
              <FileText className="w-6 h-6" />
              <span className="text-xs">No documents drafted yet</span>
              <p className="text-[10px] text-center leading-relaxed mt-1">
                Open a checklist item and click "Draft document"
              </p>
            </div>
          ) : (
            <div>
              <SectionLabel>{documents.length} document{documents.length !== 1 ? 's' : ''}</SectionLabel>
              {documents.map((doc) => (
                <DocumentRow key={doc.id} doc={doc} />
              ))}
            </div>
          )
        )}
      </div>
    </div>
  );
}
