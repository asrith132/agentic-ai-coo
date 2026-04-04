'use client';

import { Agent, AgentStatus } from '@/lib/mock-data';
import { cn } from '@/lib/utils';

interface AgentCardProps {
  agent: Agent;
  onClick: () => void;
  className?: string;
  isPlanetMode?: boolean;
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
    return { bg: 'rgba(239,68,68,0.10)', border: 'rgba(239,68,68,0.28)', color: '#FCA5A5' };
  }
  const rgb     = hexToRgb(color);
  const opacity = { thinking: 0.14, done: 0.09, idle: 0.06 }[status] ?? 0.08;
  const bdr     = { thinking: 0.38, done: 0.20, idle: 0.12 }[status] ?? 0.15;
  return { bg: `rgba(${rgb},${opacity})`, border: `rgba(${rgb},${bdr})`, color };
}

const statusLabel: Record<AgentStatus, string> = {
  thinking: 'Thinking', done: 'Done', blocked: 'Blocked', idle: 'Idle',
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

// ── Planet definitions ────────────────────────────────────────────────────────

interface PlanetDef {
  surface: string;
  glow: string;
  atmosphere: string;
  bands?: string;
  textColor: string;
  textColorMuted: string;
  ring?: { gradient: string; tilt: string };
}

const planets: Record<string, PlanetDef> = {

  // Jupiter — PM (center). Warm banded gas giant.
  'product-manager': {
    surface: [
      'radial-gradient(ellipse at 36% 28%, rgba(255,235,180,0.9) 0%, transparent 45%)',
      'radial-gradient(ellipse at 68% 70%, rgba(160,80,20,0.6)   0%, transparent 40%)',
      'linear-gradient(168deg, #8b4513 0%, #c8732a 18%, #e8a560 32%, #d4855a 46%, #b05a2a 58%, #c8852a 70%, #8a4010 100%)',
    ].join(','),
    glow: '0 0 45px 10px rgba(220,140,50,0.4), 0 0 90px 25px rgba(180,100,20,0.15)',
    atmosphere: 'radial-gradient(ellipse at 33% 26%, rgba(255,245,200,0.4) 0%, transparent 55%)',
    bands: 'repeating-linear-gradient(178deg, transparent 0%, transparent 8%, rgba(0,0,0,0.08) 9%, rgba(0,0,0,0.08) 11%, transparent 12%)',
    textColor: '#fff5e0',
    textColorMuted: 'rgba(255,235,190,0.7)',
  },

  // Mars — Engineer. Red rocky desert planet.
  'engineer': {
    surface: [
      'radial-gradient(ellipse at 35% 30%, rgba(220,140,100,0.85) 0%, transparent 50%)',
      'radial-gradient(ellipse at 65% 65%, rgba(100,35,15,0.7)    0%, transparent 45%)',
      'linear-gradient(155deg, #6b1a0a 0%, #a03020 20%, #c04830 38%, #a83828 55%, #7a2010 72%, #5a1508 100%)',
    ].join(','),
    glow: '0 0 40px 8px rgba(180,60,30,0.38), 0 0 80px 22px rgba(140,40,15,0.15)',
    atmosphere: 'radial-gradient(ellipse at 32% 28%, rgba(240,160,120,0.35) 0%, transparent 52%)',
    textColor: '#ffe0d0',
    textColorMuted: 'rgba(255,210,185,0.65)',
  },

  // Neptune — Legal. Deep electric blue ice giant.
  'legal': {
    surface: [
      'radial-gradient(ellipse at 38% 30%, rgba(120,210,255,0.7) 0%, transparent 48%)',
      'radial-gradient(ellipse at 65% 68%, rgba(5,25,80,0.8)     0%, transparent 45%)',
      'linear-gradient(160deg, #041a4a 0%, #082e7a 22%, #0d50b0 42%, #0a3d8a 62%, #051a50 82%, #020d30 100%)',
    ].join(','),
    glow: '0 0 42px 10px rgba(20,100,220,0.45), 0 0 85px 24px rgba(10,60,160,0.18)',
    atmosphere: 'radial-gradient(ellipse at 34% 27%, rgba(140,220,255,0.4) 0%, transparent 55%)',
    bands: 'repeating-linear-gradient(172deg, transparent 0%, transparent 18%, rgba(255,255,255,0.04) 19%, rgba(255,255,255,0.04) 21%, transparent 22%)',
    textColor: '#d0f0ff',
    textColorMuted: 'rgba(180,230,255,0.65)',
  },

  // Ocean World — Research. Teal deep-sea planet.
  'research': {
    surface: [
      'radial-gradient(ellipse at 38% 33%, rgba(80,220,210,0.65) 0%, transparent 45%)',
      'radial-gradient(ellipse at 62% 62%, rgba(5,60,70,0.75)    0%, transparent 42%)',
      'radial-gradient(ellipse at 55% 25%, rgba(30,120,160,0.5)  0%, transparent 35%)',
      'linear-gradient(155deg, #03303a 0%, #045a70 22%, #077a90 40%, #056070 58%, #033848 78%, #021e28 100%)',
    ].join(','),
    glow: '0 0 40px 9px rgba(10,160,180,0.4), 0 0 85px 22px rgba(5,100,120,0.16)',
    atmosphere: 'radial-gradient(ellipse at 35% 28%, rgba(80,220,220,0.35) 0%, transparent 52%)',
    textColor: '#c0f4f8',
    textColorMuted: 'rgba(160,235,240,0.65)',
  },

  // Hot Jupiter — Marketing. Vivid swirling magenta/violet.
  'marketing': {
    surface: [
      'radial-gradient(ellipse at 36% 30%, rgba(255,160,220,0.8) 0%, transparent 45%)',
      'radial-gradient(ellipse at 66% 65%, rgba(80,10,100,0.7)   0%, transparent 42%)',
      'linear-gradient(158deg, #4a0060 0%, #8a10a0 20%, #c030c8 38%, #a020b0 55%, #6a0888 72%, #380050 100%)',
    ].join(','),
    glow: '0 0 44px 10px rgba(200,40,220,0.42), 0 0 90px 24px rgba(150,20,170,0.18)',
    atmosphere: 'radial-gradient(ellipse at 33% 27%, rgba(255,180,240,0.38) 0%, transparent 52%)',
    bands: 'repeating-linear-gradient(175deg, transparent 0%, transparent 12%, rgba(255,255,255,0.05) 13%, rgba(255,255,255,0.05) 15%, transparent 16%)',
    textColor: '#ffe0ff',
    textColorMuted: 'rgba(255,210,255,0.65)',
  },

  // Saturn — Finance. Gold ringed gas giant. ✓
  'finance': {
    surface: [
      'radial-gradient(ellipse at 38% 32%, rgba(255,245,180,0.95) 0%, transparent 55%)',
      'radial-gradient(ellipse at 70% 65%, rgba(180,120,20,0.7)   0%, transparent 50%)',
      'linear-gradient(160deg, #c8860a 0%, #e8a820 22%, #f5c842 40%, #c07010 62%, #7a4800 100%)',
    ].join(','),
    glow: '0 0 40px 8px rgba(252,180,30,0.38), 0 0 82px 22px rgba(200,130,10,0.15)',
    atmosphere: 'radial-gradient(ellipse at 35% 28%, rgba(255,255,220,0.42) 0%, transparent 58%)',
    bands: 'repeating-linear-gradient(173deg, transparent 0%, transparent 10%, rgba(0,0,0,0.07) 11%, rgba(0,0,0,0.07) 13%, transparent 14%)',
    textColor: '#fff0c0',
    textColorMuted: 'rgba(255,230,150,0.65)',
    ring: {
      gradient: 'linear-gradient(90deg, transparent 0%, rgba(200,150,20,0.12) 12%, rgba(240,190,60,0.5) 28%, rgba(252,210,80,0.72) 44%, rgba(255,222,90,0.78) 50%, rgba(252,210,80,0.72) 56%, rgba(240,190,60,0.5) 72%, rgba(200,150,20,0.12) 88%, transparent 100%)',
      tilt: 'rotateX(74deg) rotateZ(-14deg)',
    },
  },

  // Venus — Outreach. Thick amber/coral haze, no visible surface.
  'outreach-agent': {
    surface: [
      'radial-gradient(ellipse at 36% 30%, rgba(255,220,150,0.9) 0%, transparent 50%)',
      'radial-gradient(ellipse at 65% 65%, rgba(180,80,20,0.65)  0%, transparent 45%)',
      'linear-gradient(158deg, #7a3800 0%, #b85a10 18%, #e08830 35%, #c87020 52%, #904010 68%, #5a2208 100%)',
    ].join(','),
    glow: '0 0 45px 10px rgba(240,150,40,0.4), 0 0 90px 25px rgba(190,100,10,0.16)',
    atmosphere: 'radial-gradient(ellipse at 32% 26%, rgba(255,230,170,0.45) 0%, transparent 55%)',
    textColor: '#fff0d0',
    textColorMuted: 'rgba(255,225,170,0.65)',
  },

  // Uranus / Ice Giant — Meeting Agent. Soft cyan-mint.
  'meeting-agent': {
    surface: [
      'radial-gradient(ellipse at 38% 32%, rgba(180,240,240,0.7) 0%, transparent 50%)',
      'radial-gradient(ellipse at 64% 64%, rgba(20,80,100,0.65)  0%, transparent 42%)',
      'linear-gradient(158deg, #0a3040 0%, #124a60 20%, #1a7088 38%, #126070 56%, #0a4050 74%, #052030 100%)',
    ].join(','),
    glow: '0 0 42px 10px rgba(60,180,200,0.38), 0 0 86px 22px rgba(30,120,150,0.15)',
    atmosphere: 'radial-gradient(ellipse at 34% 28%, rgba(180,240,245,0.38) 0%, transparent 54%)',
    textColor: '#d0f5f8',
    textColorMuted: 'rgba(180,235,242,0.65)',
  },
};

// ── Component ─────────────────────────────────────────────────────────────────

export function AgentCard({ agent, onClick, className, isPlanetMode = false }: AgentCardProps) {
  const color  = agentColors[agent.id] ?? '#94A3B8';
  const rgb    = hexToRgb(color);
  const badge  = getBadgeStyles(agent.status, color);
  const planet = planets[agent.id];

  // ── Planet rendering ───────────────────────────────────────────────────────
  if (isPlanetMode && planet) {
    return (
      <button
        className={cn('group relative cursor-pointer focus-visible:outline-none', className)}
        onClick={onClick}
        aria-label={`${agent.name} — ${statusLabel[agent.status]}`}
        style={{ display: 'block' }}
      >
        {/* Ring — behind the sphere */}
        {planet.ring && (
          <div
            className="absolute pointer-events-none z-0"
            style={{
              inset: '0 -32% 0 -32%',
              top: '34%',
              height: '32%',
              background: planet.ring.gradient,
              borderRadius: '50%',
              transform: planet.ring.tilt,
              filter: 'blur(1.5px)',
              opacity: 0.9,
            }}
          />
        )}

        {/* Sphere */}
        <div
          className="relative z-10 w-full h-full rounded-full overflow-hidden transition-all duration-300 ease-out hover:-translate-y-1 hover:scale-[1.04]"
          style={{
            background: planet.surface,
            boxShadow: `${planet.glow}, inset -8px -8px 24px rgba(0,0,0,0.55), inset 3px 3px 10px rgba(255,255,255,0.12)`,
            aspectRatio: '1',
          }}
        >
          {/* Atmosphere highlight */}
          <div className="absolute inset-0 pointer-events-none rounded-full" style={{ background: planet.atmosphere }} />

          {/* Surface bands */}
          {planet.bands && (
            <div className="absolute inset-0 pointer-events-none rounded-full" style={{ background: planet.bands }} />
          )}

          {/* Limb darkening — edge darkness for sphere illusion */}
          <div
            className="absolute inset-0 pointer-events-none rounded-full"
            style={{ background: 'radial-gradient(ellipse at 50% 50%, transparent 55%, rgba(0,0,0,0.45) 100%)' }}
          />

          {/* Default label */}
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-1.5 transition-all duration-200 group-hover:opacity-0">
            <p
              className="font-bold text-[11px] text-center leading-tight px-3 drop-shadow"
              style={{ fontFamily: 'var(--font-heading)', color: planet.textColor }}
            >
              {agent.name}
            </p>
            <div className="flex items-center gap-1">
              <span
                className={cn('w-1.5 h-1.5 rounded-full shrink-0', agent.status === 'thinking' && 'animate-pulse')}
                style={{ backgroundColor: statusDotColor(agent.status, color) }}
              />
              <span className="text-[9px] drop-shadow" style={{ color: planet.textColorMuted }}>
                {statusLabel[agent.status]}
              </span>
            </div>
          </div>

          {/* Hover state */}
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 py-10 px-5 opacity-0 scale-95 transition-all duration-200 group-hover:opacity-100 group-hover:scale-100">
            <p
              className="font-semibold text-[11px] text-center leading-tight drop-shadow"
              style={{ fontFamily: 'var(--font-heading)', color: planet.textColor }}
            >
              {agent.name}
            </p>
            <div className="flex items-center gap-1">
              <span
                className={cn('w-1.5 h-1.5 rounded-full shrink-0', agent.status === 'thinking' && 'animate-pulse')}
                style={{ backgroundColor: statusDotColor(agent.status, color) }}
              />
              <span className="text-[9px]" style={{ color: planet.textColorMuted }}>
                {statusLabel[agent.status]}
              </span>
            </div>
            <p
              className="text-[10px] leading-snug line-clamp-2 text-center drop-shadow"
              style={{ color: planet.textColorMuted }}
            >
              {agent.summary}
            </p>
            {agent.tasks[0] && (
              <div className="flex items-start gap-1.5 justify-center">
                <span className="w-1 h-1 rounded-full mt-1.5 shrink-0" style={{ backgroundColor: planet.textColorMuted }} />
                <span className="text-[10px] line-clamp-1 drop-shadow" style={{ color: planet.textColorMuted }}>
                  {agent.tasks[0]}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Ring front half — drawn on top of sphere */}
        {planet.ring && (
          <div
            className="absolute pointer-events-none z-20"
            style={{
              inset: '0 -32% 0 -32%',
              top: '34%',
              height: '32%',
              background: planet.ring.gradient,
              borderRadius: '50%',
              transform: planet.ring.tilt,
              filter: 'blur(1.5px)',
              opacity: 0.85,
              clipPath: 'ellipse(50% 50% at 50% 0%)',
            }}
          />
        )}
      </button>
    );
  }

  // ── Default glass card ─────────────────────────────────────────────────────
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
          style={{ background: 'linear-gradient(135deg, rgba(255,255,255,0.10) 0%, rgba(255,255,255,0.03) 40%, transparent 70%)' }}
        />

        {/* Default state */}
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 p-4 transition-all duration-200 group-hover:opacity-0 group-hover:scale-90">
          <div
            className="relative w-9 h-9 rounded-lg flex items-center justify-center text-[10px] font-bold tracking-wider shrink-0 font-mono"
            style={{ background: badge.bg, border: `1px solid ${badge.border}`, color: badge.color }}
          >
            {agent.shortName}
            {agent.status === 'thinking' && (
              <span className="absolute inset-0 rounded-lg animate-ping opacity-30" style={{ border: `1px solid ${color}` }} />
            )}
          </div>
          <p className="relative font-semibold text-xs text-foreground/90 text-center leading-tight px-2" style={{ fontFamily: 'var(--font-heading)' }}>
            {agent.name}
          </p>
          <div className="relative flex items-center gap-1">
            <span className={cn('w-1.5 h-1.5 rounded-full shrink-0', agent.status === 'thinking' && 'animate-pulse')} style={{ backgroundColor: statusDotColor(agent.status, color) }} />
            <span className="text-[10px]" style={{ color: statusTextColor(agent.status, color) }}>
              {statusLabel[agent.status]}
            </span>
          </div>
        </div>

        {/* Hover state */}
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 py-10 px-6 opacity-0 translate-y-1 scale-95 transition-all duration-200 group-hover:opacity-100 group-hover:translate-y-0 group-hover:scale-100">
          <div className="flex items-center gap-1.5 w-full justify-center">
            <div
              className="w-6 h-6 rounded-md flex items-center justify-center text-[9px] font-bold font-mono shrink-0"
              style={{ background: badge.bg, border: `1px solid ${badge.border}`, color: badge.color }}
            >
              {agent.shortName}
            </div>
            <p className="font-semibold text-[11px] text-foreground/90 leading-tight truncate" style={{ fontFamily: 'var(--font-heading)' }}>
              {agent.name}
            </p>
          </div>
          <div className="flex items-center gap-1">
            <span className={cn('w-1.5 h-1.5 rounded-full shrink-0', agent.status === 'thinking' && 'animate-pulse')} style={{ backgroundColor: statusDotColor(agent.status, color) }} />
            <span className="text-[9px]" style={{ color: statusTextColor(agent.status, color) }}>{statusLabel[agent.status]}</span>
          </div>
          <p className="text-[10px] text-foreground/50 leading-snug line-clamp-2 text-center">{agent.summary}</p>
          {agent.tasks[0] && (
            <div className="flex items-start gap-1.5 w-full justify-center">
              <span className="w-1 h-1 rounded-full mt-1.5 shrink-0" style={{ backgroundColor: `rgba(${rgb},0.5)` }} />
              <span className="text-[10px] text-foreground/70 line-clamp-1">{agent.tasks[0]}</span>
            </div>
          )}
        </div>
      </div>
    </button>
  );
}
