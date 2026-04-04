'use client';

import { Agent, AgentStatus } from '@/lib/mock-data';
import { cn } from '@/lib/utils';

interface AgentCardProps {
  agent: Agent;
  onClick: () => void;
  className?: string;
}

const agentColors: Record<string, string> = {
  'product-manager': '#86EFAC',
  'engineer':        '#93C5FD',
  'research':        '#C4B5FD',
  'marketing':       '#FDBA74',
  'legal':           '#5EEAD4',
  'finance':         '#FCD34D',
  'outreach-agent':  '#F9A8D4',
  'meeting-agent':   '#A5B4FC',
};

function hexToRgb(hex: string) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `${r},${g},${b}`;
}

function getBadgeStyles(status: AgentStatus, color: string) {
  if (status === 'blocked') {
    return {
      bg:     'rgba(239,68,68,0.10)',
      border: 'rgba(239,68,68,0.28)',
      color:  '#FCA5A5',
    };
  }
  const rgb = hexToRgb(color);
  const opacity = { thinking: 0.14, done: 0.09, idle: 0.06 }[status] ?? 0.08;
  const bdr     = { thinking: 0.38, done: 0.20, idle: 0.12 }[status] ?? 0.15;
  return {
    bg:     `rgba(${rgb},${opacity})`,
    border: `rgba(${rgb},${bdr})`,
    color:  color,
  };
}

const statusLabel: Record<AgentStatus, string> = {
  thinking: 'Thinking',
  done:     'Done',
  blocked:  'Blocked',
  idle:     'Idle',
};

function statusDotColor(status: AgentStatus, color: string) {
  if (status === 'blocked') return '#EF4444';
  if (status === 'idle')    return 'rgba(148,163,184,0.4)';
  return color;
}

function statusTextColor(status: AgentStatus, color: string) {
  if (status === 'blocked') return '#FCA5A5';
  if (status === 'idle')    return 'rgba(148,163,184,0.55)';
  return color;
}

export function AgentCard({ agent, onClick, className }: AgentCardProps) {
  const color = agentColors[agent.id] ?? '#94A3B8';
  const rgb   = hexToRgb(color);
  const badge = getBadgeStyles(agent.status, color);

  return (
    <button
      className={cn(
        'group w-full h-full text-left cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 rounded-full',
        className,
      )}
      onClick={onClick}
      aria-label={`${agent.name} — ${statusLabel[agent.status]}`}
    >
      <div
        className={cn(
          'relative h-full rounded-full overflow-hidden',
          'transition-all duration-300 ease-out',
          'hover:-translate-y-1 hover:scale-[1.01]',
          'backdrop-blur-2xl backdrop-saturate-[180%]',
        )}
        style={{
          background: 'var(--card-glass-bg)',
          border: '1px solid rgba(255,255,255,0.07)',
          boxShadow: '0 4px 24px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.08), var(--card-border-shadow)',
        }}
      >
        {/* Diagonal sheen */}
        <div
          className="absolute inset-0 pointer-events-none rounded-full"
          style={{
            background: 'linear-gradient(135deg, rgba(255,255,255,0.10) 0%, rgba(255,255,255,0.03) 40%, transparent 70%)',
          }}
        />

        {/* ── Default state ── */}
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 transition-all duration-200 group-hover:opacity-0 group-hover:scale-90">

          {/* Badge — color lives here only */}
          <div
            className="relative w-12 h-12 rounded-xl flex items-center justify-center text-xs font-bold tracking-wider shrink-0 font-mono"
            style={{
              background: badge.bg,
              border:     `1px solid ${badge.border}`,
              color:      badge.color,
            }}
          >
            {agent.shortName}
            {agent.status === 'thinking' && (
              <span
                className="absolute inset-0 rounded-xl animate-ping opacity-30"
                style={{ border: `1px solid ${color}` }}
              />
            )}
          </div>

          <p
            className="relative font-semibold text-sm text-foreground/90 text-center leading-tight"
            style={{ fontFamily: 'var(--font-heading)' }}
          >
            {agent.name}
          </p>

          <div className="relative flex items-center gap-1.5">
            <span
              className={cn('w-1.5 h-1.5 rounded-full shrink-0', agent.status === 'thinking' && 'animate-pulse')}
              style={{ backgroundColor: statusDotColor(agent.status, color) }}
            />
            <span
              className="text-xs"
              style={{ color: statusTextColor(agent.status, color) }}
            >
              {statusLabel[agent.status]}
            </span>
          </div>
        </div>

        {/* ── Hover state ── */}
        <div className="absolute inset-0 flex flex-col p-4 opacity-0 translate-y-1 scale-95 transition-all duration-200 group-hover:opacity-100 group-hover:translate-y-0 group-hover:scale-100">
          {/* Header */}
          <div className="flex items-center gap-2 mb-2.5">
            <div
              className="w-7 h-7 rounded-lg flex items-center justify-center text-[10px] font-bold font-mono shrink-0"
              style={{
                background: badge.bg,
                border:     `1px solid ${badge.border}`,
                color:      badge.color,
              }}
            >
              {agent.shortName}
            </div>
            <div className="min-w-0">
              <p className="font-semibold text-[11px] text-foreground/90 leading-tight truncate" style={{ fontFamily: 'var(--font-heading)' }}>
                {agent.name}
              </p>
              <div className="flex items-center gap-1 mt-0.5">
                <span
                  className={cn('w-1.5 h-1.5 rounded-full shrink-0', agent.status === 'thinking' && 'animate-pulse')}
                  style={{ backgroundColor: statusDotColor(agent.status, color) }}
                />
                <span className="text-[9px]" style={{ color: statusTextColor(agent.status, color) }}>
                  {statusLabel[agent.status]}
                </span>
              </div>
            </div>
          </div>

          {/* Summary */}
          <p className="text-[10px] text-foreground/50 leading-relaxed mb-2.5 line-clamp-2">
            {agent.summary}
          </p>

          {/* Tasks */}
          <div className="flex-1 min-h-0 space-y-1.5">
            {agent.tasks.slice(0, 2).map((task, i) => (
              <div key={i} className="flex items-start gap-1.5">
                <span className="w-1 h-1 rounded-full mt-1.5 shrink-0" style={{ backgroundColor: `rgba(${rgb},0.5)` }} />
                <span className="text-[10px] text-foreground/70 line-clamp-1">{task}</span>
              </div>
            ))}
          </div>

          {/* Output */}
          <div className="pt-2 mt-auto border-t border-white/[0.06]">
            <p className="text-[10px] line-clamp-1 leading-snug text-foreground/45">
              {agent.outputs[0]}
            </p>
          </div>
        </div>
      </div>
    </button>
  );
}
