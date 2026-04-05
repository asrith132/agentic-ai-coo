'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  BarChart3,
  CheckCircle2,
  Loader2,
  RefreshCw,
  TrendingDown,
  TrendingUp,
  Upload,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { financeApi } from '@/lib/api/finance'
import type {
  FinanceSnapshot,
  FinanceTransaction,
  SpendingAnomaly,
  FinanceStatus,
  UploadResult,
} from '@/lib/types/finance'

type Tab = 'overview' | 'transactions' | 'upload'

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(n: number | null | undefined): string {
  if (n == null) return '—'
  return '$' + Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

function fmtMonth(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso + 'T12:00:00').toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
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

const categoryColor: Record<string, string> = {
  revenue:     'text-emerald-400 border-emerald-400/30 bg-emerald-400/8',
  hosting:     'text-sky-400 border-sky-400/30 bg-sky-400/8',
  tools:       'text-primary border-primary/30 bg-primary/8',
  contractors: 'text-amber-400 border-amber-400/30 bg-amber-400/8',
  marketing:   'text-purple-400 border-purple-400/30 bg-purple-400/8',
  salary:      'text-blue-400 border-blue-400/30 bg-blue-400/8',
  tax:         'text-destructive border-destructive/30 bg-destructive/8',
  legal:       'text-orange-400 border-orange-400/30 bg-orange-400/8',
  other:       'text-muted-foreground border-border/50 bg-secondary/30',
}

// ── Sub-components ────────────────────────────────────────────────────────────

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
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="text-[10px] font-semibold text-muted-foreground/70 uppercase tracking-widest mb-3">
      {children}
    </h4>
  )
}

function StatCard({
  label, value, sub, accent,
}: {
  label: string
  value: string
  sub?: string
  accent?: 'green' | 'red' | 'yellow' | 'default'
}) {
  const valueClass = {
    green:   'text-emerald-400',
    red:     'text-destructive',
    yellow:  'text-warning',
    default: 'text-foreground/90',
  }[accent ?? 'default']

  return (
    <div className="rounded-lg border border-border/40 bg-secondary/20 px-3 py-2.5">
      <div className="text-[10px] text-muted-foreground/60 uppercase tracking-wider mb-1">{label}</div>
      <div className={cn('text-sm font-semibold tabular-nums', valueClass)}>{value}</div>
      {sub && <div className="text-[10px] text-muted-foreground/50 mt-0.5">{sub}</div>}
    </div>
  )
}

// ── Overview tab ──────────────────────────────────────────────────────────────

function OverviewTab({
  status, snapshot, summary, anomalies, loading,
}: {
  status: FinanceStatus | null
  snapshot: FinanceSnapshot | null
  summary: string | null
  anomalies: SpendingAnomaly[]
  loading: boolean
}) {
  if (loading) return <SkeletonList n={4} />

  if (!snapshot) {
    return (
      <div className="flex flex-col items-center justify-center py-12 gap-2 text-muted-foreground/40">
        <BarChart3 className="w-8 h-8" />
        <span className="text-xs text-center">No financial data yet</span>
        <span className="text-[10px] text-center leading-relaxed">Upload a CSV in the Upload tab to get started</span>
      </div>
    )
  }

  const net = snapshot.net ?? 0
  const runway = snapshot.runway_months

  return (
    <div className="space-y-4">
      {/* Summary text */}
      {summary && (
        <div className="rounded-xl border border-primary/15 bg-primary/5 px-3 py-3">
          <p className="text-[11px] text-foreground/75 leading-relaxed">{summary}</p>
          <div className="text-[10px] text-muted-foreground/40 mt-1.5">{fmtMonth(snapshot.month)}</div>
        </div>
      )}

      {/* Key metrics grid */}
      <div>
        <SectionLabel>This month</SectionLabel>
        <div className="grid grid-cols-2 gap-2">
          <StatCard
            label="Revenue"
            value={fmt(snapshot.total_income)}
            accent="green"
          />
          <StatCard
            label="Burn"
            value={fmt(snapshot.total_expenses)}
            accent="red"
          />
          <StatCard
            label="Net"
            value={(net >= 0 ? '+' : '') + fmt(net)}
            accent={net >= 0 ? 'green' : 'red'}
          />
          <StatCard
            label="Runway"
            value={runway != null ? `${runway.toFixed(1)} mo` : '—'}
            accent={runway == null ? 'default' : runway <= 3 ? 'red' : runway <= 6 ? 'yellow' : 'green'}
            sub={snapshot.current_balance != null ? `${fmt(snapshot.current_balance)} balance` : undefined}
          />
        </div>
      </div>

      {/* Spend by category */}
      {snapshot.by_category && Object.keys(snapshot.by_category).length > 0 && (
        <div>
          <SectionLabel>Spend by category</SectionLabel>
          <div className="space-y-1.5">
            {Object.entries(snapshot.by_category)
              .sort(([, a], [, b]) => b - a)
              .map(([cat, amt]) => {
                const total = snapshot.total_expenses || 1
                const pct = Math.round((amt / total) * 100)
                return (
                  <div key={cat} className="flex items-center gap-2">
                    <Badge
                      variant="outline"
                      className={cn('text-[9px] py-0 h-4 font-normal w-20 justify-center shrink-0', categoryColor[cat] ?? categoryColor.other)}
                    >
                      {cat}
                    </Badge>
                    <div className="flex-1 h-1.5 rounded-full bg-secondary/50 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-current opacity-40"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="text-[10px] text-muted-foreground/70 tabular-nums w-14 text-right">{fmt(amt)}</span>
                  </div>
                )
              })}
          </div>
        </div>
      )}

      {/* Anomalies */}
      {anomalies.length > 0 && (
        <div>
          <SectionLabel>Spending anomalies</SectionLabel>
          <div className="space-y-2">
            {anomalies.map((a, i) => (
              <div key={i} className="rounded-lg border border-warning/25 bg-warning/5 px-3 py-2.5">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="w-3.5 h-3.5 text-warning shrink-0 mt-0.5" />
                  <div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-[11px] font-semibold text-foreground/85 capitalize">{a.category}</span>
                      <span className="text-[10px] text-warning font-medium">{fmt(a.amount)}</span>
                    </div>
                    <p className="text-[10px] text-muted-foreground leading-relaxed mt-0.5">{a.description}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Transactions tab ──────────────────────────────────────────────────────────

function TransactionsTab({
  transactions, loading,
}: {
  transactions: FinanceTransaction[]
  loading: boolean
}) {
  const [filter, setFilter] = useState<string>('all')
  const categories = ['all', ...Array.from(new Set(transactions.map(t => t.category))).sort()]

  const filtered = filter === 'all' ? transactions : transactions.filter(t => t.category === filter)

  if (loading) return <SkeletonList n={5} />

  if (transactions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 gap-2 text-muted-foreground/40">
        <ArrowUp className="w-6 h-6" />
        <span className="text-xs">No transactions yet</span>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {/* Category filter */}
      <div className="flex gap-1.5 flex-wrap">
        {categories.map(cat => (
          <button
            key={cat}
            onClick={() => setFilter(cat)}
            className={cn(
              'px-2 h-5 rounded-full text-[10px] font-medium transition-colors cursor-pointer capitalize',
              filter === cat
                ? 'bg-primary text-primary-foreground'
                : 'bg-secondary/50 text-muted-foreground hover:bg-secondary',
            )}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* Transaction list */}
      <div className="space-y-1">
        {filtered.map(tx => {
          const isIncome = tx.amount > 0
          return (
            <div key={tx.id} className="flex items-start gap-2.5 py-2 border-b border-border/20 last:border-0">
              <div className={cn(
                'w-5 h-5 rounded-md flex items-center justify-center shrink-0 mt-0.5',
                isIncome ? 'bg-emerald-400/10 border border-emerald-400/20' : 'bg-destructive/8 border border-destructive/15',
              )}>
                {isIncome
                  ? <ArrowDown className="w-2.5 h-2.5 text-emerald-400" />
                  : <ArrowUp className="w-2.5 h-2.5 text-destructive" />
                }
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-[11px] text-foreground/80 leading-tight truncate">{tx.description}</span>
                  <span className={cn(
                    'text-[11px] font-semibold tabular-nums shrink-0',
                    isIncome ? 'text-emerald-400' : 'text-foreground/70',
                  )}>
                    {isIncome ? '+' : '-'}{fmt(tx.amount)}
                  </span>
                </div>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <span className="text-[10px] text-muted-foreground/50">{tx.date}</span>
                  <Badge
                    variant="outline"
                    className={cn('text-[9px] py-0 h-3.5 font-normal', categoryColor[tx.category] ?? categoryColor.other)}
                  >
                    {tx.category}
                  </Badge>
                  {tx.is_recurring && (
                    <span className="text-[9px] text-muted-foreground/40">recurring</span>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Upload tab ────────────────────────────────────────────────────────────────

function UploadTab({ onUploadSuccess }: { onUploadSuccess: (result: UploadResult) => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [balance, setBalance] = useState('')
  const [replace, setReplace] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState<UploadResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleUpload = async () => {
    if (!file) return
    setUploading(true)
    setError(null)
    setResult(null)
    try {
      const res = await financeApi.uploadCSV(
        file,
        balance ? parseFloat(balance) : undefined,
        replace,
      )
      setResult(res)
      onUploadSuccess(res)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const dropped = e.dataTransfer.files[0]
    if (dropped && dropped.name.endsWith('.csv')) setFile(dropped)
  }

  return (
    <div className="space-y-4">
      {/* Drop zone */}
      <div
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={cn(
          'rounded-xl border-2 border-dashed flex flex-col items-center justify-center py-8 gap-2 cursor-pointer transition-colors',
          dragging
            ? 'border-primary/60 bg-primary/5'
            : file
              ? 'border-emerald-400/40 bg-emerald-400/5'
              : 'border-border/40 bg-secondary/10 hover:border-border/70 hover:bg-secondary/20',
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        {file ? (
          <>
            <CheckCircle2 className="w-6 h-6 text-emerald-400" />
            <span className="text-xs font-medium text-foreground/80">{file.name}</span>
            <span className="text-[10px] text-muted-foreground/50">{(file.size / 1024).toFixed(1)} KB</span>
          </>
        ) : (
          <>
            <Upload className="w-6 h-6 text-muted-foreground/40" />
            <span className="text-xs text-muted-foreground/60">Drop CSV or click to browse</span>
            <span className="text-[10px] text-muted-foreground/40">Supports bank exports, Stripe, QuickBooks</span>
          </>
        )}
      </div>

      {/* Balance input */}
      <div className="space-y-1">
        <label className="text-[10px] text-muted-foreground/70 uppercase tracking-wider">
          Current cash balance (optional)
        </label>
        <div className="relative">
          <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-xs text-muted-foreground/50">$</span>
          <input
            type="number"
            value={balance}
            onChange={(e) => setBalance(e.target.value)}
            placeholder="e.g. 85000"
            className="w-full text-xs bg-secondary/40 border border-border/50 rounded-md pl-6 pr-3 py-2 text-foreground/85 focus:outline-none focus:border-primary/40"
          />
        </div>
        <p className="text-[10px] text-muted-foreground/40">Required for runway calculation</p>
      </div>

      {/* Replace toggle */}
      <label className="flex items-center gap-2.5 cursor-pointer">
        <div
          onClick={() => setReplace(v => !v)}
          className={cn(
            'w-8 h-4 rounded-full transition-colors relative cursor-pointer',
            replace ? 'bg-primary' : 'bg-secondary/60 border border-border/50',
          )}
        >
          <div className={cn(
            'absolute top-0.5 w-3 h-3 rounded-full bg-white transition-transform',
            replace ? 'translate-x-4' : 'translate-x-0.5',
          )} />
        </div>
        <span className="text-[11px] text-muted-foreground">Replace existing transactions in date range</span>
      </label>

      {/* Upload button */}
      <button
        onClick={handleUpload}
        disabled={!file || uploading}
        className="w-full h-9 rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-all cursor-pointer disabled:opacity-50
          bg-primary/10 hover:bg-primary/20 text-primary border border-primary/25 hover:border-primary/40"
      >
        {uploading
          ? <><Loader2 className="w-4 h-4 animate-spin" /> Processing…</>
          : <><Upload className="w-4 h-4" /> Upload & Analyze</>
        }
      </button>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-destructive/25 bg-destructive/8 px-3 py-2.5 text-xs text-destructive">
          {error}
        </div>
      )}

      {/* Result */}
      {result?.ingestion && (
        <div className="rounded-xl border border-emerald-400/25 bg-emerald-400/5 px-3 py-3 space-y-1.5">
          <div className="flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-xs font-semibold text-emerald-400">Upload complete</span>
          </div>
          <div className="text-[11px] text-muted-foreground space-y-0.5">
            <div>{result.ingestion.rows_inserted} transactions imported</div>
            <div>{result.ingestion.income_count} income · {result.ingestion.expense_count} expenses</div>
            {result.ingestion.date_range && (
              <div>{result.ingestion.date_range.start} → {result.ingestion.date_range.end}</div>
            )}
          </div>
          {result.summary && (
            <p className="text-[11px] text-foreground/70 leading-relaxed pt-1 border-t border-border/30">
              {result.summary}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

interface FinanceAgentSidebarProps {
  rgb: string
  color: string
}

export function FinanceAgentSidebar({ rgb, color }: FinanceAgentSidebarProps) {
  const [tab, setTab] = useState<Tab>('overview')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState<FinanceStatus | null>(null)
  const [snapshot, setSnapshot] = useState<FinanceSnapshot | null>(null)
  const [summary, setSummary] = useState<string | null>(null)
  const [anomalies, setAnomalies] = useState<SpendingAnomaly[]>([])
  const [transactions, setTransactions] = useState<FinanceTransaction[]>([])
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null)

  const showToast = (msg: string, ok = true) => {
    setToast({ msg, ok })
    setTimeout(() => setToast(null), 4000)
  }

  const loadAll = useCallback(async () => {
    setLoading(true)
    try {
      const [statusRes, summaryRes, txRes] = await Promise.all([
        financeApi.getStatus(),
        financeApi.getSummary(),
        financeApi.listTransactions({ limit: 100 }),
      ])
      setStatus(statusRes)
      setSnapshot(summaryRes.snapshot)
      setSummary(summaryRes.summary)
      setAnomalies(summaryRes.anomalies)
      setTransactions(txRes.transactions)
    } catch {
      // backend not running
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadAll() }, [loadAll])

  const handleUploadSuccess = (result: UploadResult) => {
    showToast(`Imported ${result.ingestion?.rows_inserted ?? 0} transactions`)
    setSnapshot(result.snapshot)
    setSummary(result.summary)
    setAnomalies(result.anomalies)
    // Reload transactions in background
    financeApi.listTransactions({ limit: 100 })
      .then(r => setTransactions(r.transactions))
      .catch(() => {})
  }

  const tabs: { key: Tab; label: string; icon: React.ReactNode }[] = [
    { key: 'overview',      label: 'Overview',      icon: <TrendingUp className="w-3 h-3" /> },
    { key: 'transactions',  label: 'Transactions',   icon: <ArrowUp className="w-3 h-3" /> },
    { key: 'upload',        label: 'Upload',         icon: <Upload className="w-3 h-3" /> },
  ]

  const runwayMonths = snapshot?.runway_months
  const runwayAccent =
    runwayMonths == null ? 'default' :
    runwayMonths <= 3 ? 'red' :
    runwayMonths <= 6 ? 'yellow' : 'green'

  return (
    <div className="flex flex-col h-full relative">

      {/* Toast */}
      {toast && (
        <div className={cn(
          'absolute top-2 left-3 right-3 z-20 px-3 py-2 rounded-lg text-xs font-medium shadow-lg',
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
          {tabs.map(t => (
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
              {t.icon}
              {t.label}
            </button>
          ))}
        </div>

        {/* Status strip + refresh */}
        <div className="flex items-center justify-between py-2">
          <div className="flex items-center gap-2">
            {status?.latest_snapshot && (
              <span className="text-[10px] text-muted-foreground/50">
                {fmtMonth(status.latest_snapshot.month)} · {status.transaction_count} txns
              </span>
            )}
            {runwayMonths != null && (
              <span className={cn(
                'text-[10px] font-semibold tabular-nums',
                runwayAccent === 'red' ? 'text-destructive' :
                runwayAccent === 'yellow' ? 'text-warning' : 'text-emerald-400',
              )}>
                {runwayMonths.toFixed(1)} mo runway
              </span>
            )}
          </div>
          <button
            onClick={loadAll}
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
        {tab === 'overview' && (
          <OverviewTab
            status={status}
            snapshot={snapshot}
            summary={summary}
            anomalies={anomalies}
            loading={loading}
          />
        )}
        {tab === 'transactions' && (
          <TransactionsTab transactions={transactions} loading={loading} />
        )}
        {tab === 'upload' && (
          <UploadTab onUploadSuccess={handleUploadSuccess} />
        )}
      </div>
    </div>
  )
}
