'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  CheckCircle2,
  Circle,
  ClipboardList,
  Code2,
  DollarSign,
  Gavel,
  Loader2,
  Megaphone,
  Mail,
  RefreshCw,
  Trash2,
  Zap,
} from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { pmApi, type PMTask } from '@/lib/api/pm'

// ── Agent config ──────────────────────────────────────────────────────────────

const AGENT_META: Record<string, { label: string; icon: React.ReactNode; color: string }> = {
  finance:      { label: 'Finance',      icon: <DollarSign className="w-2.5 h-2.5" />, color: '#22c55e' },
  dev_activity: { label: 'Dev',          icon: <Code2 className="w-2.5 h-2.5" />,       color: '#6366f1' },
  outreach:     { label: 'Outreach',     icon: <Mail className="w-2.5 h-2.5" />,        color: '#ec4899' },
  legal:        { label: 'Legal',        icon: <Gavel className="w-2.5 h-2.5" />,       color: '#f59e0b' },
  marketing:    { label: 'Marketing',    icon: <Megaphone className="w-2.5 h-2.5" />,   color: '#8b5cf6' },
  pm:           { label: 'PM',           icon: <ClipboardList className="w-2.5 h-2.5" />, color: '#3b82f6' },
}

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
  if (score >= 80) return 'text-destructive'
  if (score >= 50) return 'text-warning'
  return 'text-emerald-400'
}

function barColor(score: number) {
  if (score >= 80) return 'bg-destructive'
  if (score >= 50) return 'bg-warning'
  return 'bg-emerald-400'
}

// ── Task card ─────────────────────────────────────────────────────────────────

function TaskCard({ task, onDelete }: { task: PMTask; onDelete: (id: string) => void }) {
  const [deleting, setDeleting] = useState(false)
  const score = Math.round(task.priority_score)
  const agentMeta = task.assigned_agent ? AGENT_META[task.assigned_agent] : null
  const isRunning = task.status === 'in_progress'

  async function handleDelete(e: React.MouseEvent) {
    e.stopPropagation()
    if (deleting) return
    setDeleting(true)
    try {
      await pmApi.deleteTask(task.id)
      onDelete(task.id)
    } catch {
      setDeleting(false)
    }
  }

  return (
    <div className={cn(
      'group rounded-xl border bg-secondary/20 overflow-hidden transition-all',
      isRunning
        ? 'border-primary/50 shadow-[0_0_0_1px_rgba(var(--primary),0.15)] animate-pulse-border'
        : 'border-border/40',
    )}>
      {/* Running agent banner */}
      {isRunning && agentMeta && (
        <div
          className="px-3 py-1 flex items-center gap-1.5 text-[10px] font-medium"
          style={{ background: `${agentMeta.color}18`, color: agentMeta.color }}
        >
          <Loader2 className="w-2.5 h-2.5 animate-spin" />
          {agentMeta.label} agent running…
        </div>
      )}

      <div className="px-3 py-2.5 flex items-start gap-2.5">
        <div className="shrink-0 mt-0.5">
          {task.status === 'done' ? (
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          ) : isRunning ? (
            <Loader2 className="w-4 h-4 text-primary animate-spin" />
          ) : task.status === 'pending_approval' ? (
            <Circle className="w-4 h-4 text-warning" />
          ) : (
            <Circle className="w-4 h-4 text-muted-foreground/40" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[12px] font-medium text-foreground/90 leading-snug">{task.title}</p>
          {task.description && (
            <p className="text-[11px] text-muted-foreground mt-0.5 leading-relaxed line-clamp-2">
              {task.description}
            </p>
          )}
          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
            {/* Assigned agent badge */}
            {agentMeta && !isRunning && (
              <span
                className="inline-flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded-full font-medium border"
                style={{ color: agentMeta.color, borderColor: `${agentMeta.color}40`, background: `${agentMeta.color}12` }}
              >
                {agentMeta.icon}
                {agentMeta.label}
              </span>
            )}
            {task.source_agent && (
              <Badge variant="outline" className="text-[9px] py-0 h-4 bg-secondary/40 border-border/50 text-muted-foreground font-normal">
                via {task.source_agent.replace(/_/g, ' ')}
              </Badge>
            )}
            {task.created_at && (
              <span className="text-[10px] text-muted-foreground/40">{timeAgo(task.created_at)}</span>
            )}
          </div>
        </div>
        <div className="shrink-0 flex flex-col items-end gap-1 ml-1">
          <div className="text-right">
            <span className={cn('text-sm font-bold tabular-nums', scoreColor(score))}>{score}</span>
            <span className="text-[9px] text-muted-foreground/50 block leading-none">pri</span>
          </div>
          <button
            onClick={handleDelete}
            disabled={deleting || isRunning}
            className="opacity-0 group-hover:opacity-100 transition-opacity w-5 h-5 rounded flex items-center justify-center text-muted-foreground/40 hover:text-destructive hover:bg-destructive/10 disabled:opacity-20 disabled:cursor-not-allowed"
            title={isRunning ? 'Cannot delete while running' : 'Delete task'}
          >
            {deleting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
          </button>
        </div>
      </div>
      <div className="px-3 pb-2.5">
        <div className="h-0.5 rounded-full bg-secondary/60 overflow-hidden">
          <div className={cn('h-full rounded-full', isRunning ? 'animate-pulse' : '', barColor(score))} style={{ width: `${score}%` }} />
        </div>
        {task.priority_reason && (
          <p className="text-[10px] text-muted-foreground/50 mt-1 leading-snug line-clamp-1">
            {task.priority_reason}
          </p>
        )}
      </div>
    </div>
  )
}

// ── Task section ──────────────────────────────────────────────────────────────

function TaskSection({ label, tasks, emptyText, accent, onDelete }: {
  label: string; tasks: PMTask[]; emptyText: string; accent: string; onDelete: (id: string) => void
}) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <span className={cn('text-[10px] font-semibold uppercase tracking-widest', accent)}>{label}</span>
        {tasks.length > 0 && (
          <Badge className="px-1.5 py-0 text-[9px] min-w-[16px] h-4 flex items-center justify-center">
            {tasks.length}
          </Badge>
        )}
      </div>
      {tasks.length === 0 ? (
        <p className="text-[11px] text-muted-foreground/40 py-2 pl-1">{emptyText}</p>
      ) : (
        <div className="space-y-2">
          {tasks.map((t) => <TaskCard key={t.id} task={t} onDelete={onDelete} />)}
        </div>
      )}
    </div>
  )
}

// ── Main sidebar ──────────────────────────────────────────────────────────────

interface PMAgentSidebarProps {
  rgb: string
  color: string
}

export function PMAgentSidebar({ rgb, color }: PMAgentSidebarProps) {
  const [tasks, setTasks] = useState<PMTask[]>([])
  const [loading, setLoading] = useState(false)
  const prevTasksRef = useRef<PMTask[]>([])

  const fetchTasks = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const data = await pmApi.getTasks({ limit: 100 })

      // Detect tasks that just flipped from in_progress → done and toast
      const prev = prevTasksRef.current
      for (const fresh of data) {
        const old = prev.find(t => t.id === fresh.id)
        if (old?.status === 'in_progress' && fresh.status === 'done') {
          const agentMeta = fresh.assigned_agent ? AGENT_META[fresh.assigned_agent] : null
          toast.success(`Task complete: ${fresh.title}`, {
            description: agentMeta ? `Completed by ${agentMeta.label} agent` : 'Task finished',
            duration: 6000,
          })
        }
      }

      prevTasksRef.current = data
      setTasks(data)
    } catch { /* silently degrade */ }
    finally { if (!silent) setLoading(false) }
  }, [])

  // Initial load
  useEffect(() => { fetchTasks() }, [fetchTasks])

  // Auto-poll every 5s while any task is in_progress
  useEffect(() => {
    const hasRunning = tasks.some(t => t.status === 'in_progress')
    if (!hasRunning) return
    const id = setInterval(() => fetchTasks(true), 5000)
    return () => clearInterval(id)
  }, [tasks, fetchTasks])

  const removeTask = useCallback((id: string) => {
    setTasks(prev => prev.filter(t => t.id !== id))
  }, [])

  const pending    = tasks.filter(t => t.status === 'pending_approval')
  const inProgress = tasks.filter(t => t.status === 'in_progress')
  const todo       = tasks.filter(t => t.status === 'todo')
  const done       = tasks.filter(t => t.status === 'done').slice(0, 5)

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Stats bar */}
      <div className="px-5 py-3 border-b border-border/30 flex items-center gap-4 shrink-0"
        style={{ background: `rgba(${rgb}, 0.04)` }}>
        <div className="flex items-center gap-1.5">
          <ClipboardList className="w-3.5 h-3.5" style={{ color }} />
          <span className="text-[11px] font-medium text-foreground/70">
            {tasks.filter(t => t.status !== 'done').length} active
          </span>
        </div>
        {inProgress.length > 0 && (
          <div className="flex items-center gap-1.5">
            <Loader2 className="w-3 h-3 text-primary animate-spin" />
            <span className="text-[11px] font-medium text-primary">
              {inProgress.length} running
            </span>
          </div>
        )}
        {inProgress.length === 0 && (
          <div className="flex items-center gap-1.5">
            <Zap className="w-3 h-3 text-warning" />
            <span className="text-[11px] font-medium text-foreground/70">
              {pending.length} awaiting approval
            </span>
          </div>
        )}
        <button onClick={() => fetchTasks()} disabled={loading}
          className="ml-auto w-6 h-6 rounded-md bg-secondary/40 hover:bg-secondary flex items-center justify-center transition-colors cursor-pointer disabled:opacity-40">
          <RefreshCw className={cn('w-3 h-3', loading && 'animate-spin')} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-5 space-y-6">
        {loading && tasks.length === 0 ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground/40" />
          </div>
        ) : (
          <>
            <TaskSection label="Awaiting Approval" tasks={pending}    emptyText="No tasks pending approval" accent="text-warning"             onDelete={removeTask} />
            <TaskSection label="In Progress"        tasks={inProgress} emptyText="No tasks running"          accent="text-primary"             onDelete={removeTask} />
            <TaskSection label="Backlog"            tasks={todo}       emptyText="Backlog is empty"           accent="text-muted-foreground/60" onDelete={removeTask} />
            <TaskSection label="Recently Done"      tasks={done}       emptyText="No completed tasks yet"    accent="text-emerald-400"         onDelete={removeTask} />
          </>
        )}
      </div>
    </div>
  )
}
