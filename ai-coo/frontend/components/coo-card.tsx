'use client';

// Muted sage green to match the toned-down palette
const G = '134,239,172'; // #86EFAC

export function COOCard() {
  return (
    <div
      className="relative h-full rounded-3xl overflow-hidden backdrop-blur-2xl backdrop-saturate-[180%]"
      style={{
        background: 'var(--card-glass-bg)',
        border: `1px solid rgba(${G},0.45)`,
        boxShadow: `0 0 32px rgba(${G},0.12), inset 0 1px 0 rgba(255,255,255,0.90), var(--card-border-shadow)`,
      }}
    >
      {/* Diagonal sheen */}
      <div
        className="absolute inset-0 pointer-events-none rounded-3xl"
        style={{
          background: 'linear-gradient(135deg, rgba(255,255,255,0.14) 0%, rgba(255,255,255,0.05) 40%, transparent 70%)',
        }}
      />

      {/* Radial glow */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: `radial-gradient(ellipse 85% 55% at 50% 0%, rgba(${G},0.28) 0%, transparent 100%)`,
        }}
      />

      {/* Floor wash */}
      <div
        className="absolute bottom-0 left-0 right-0 h-2/5 pointer-events-none"
        style={{
          background: `linear-gradient(to top, rgba(${G},0.05) 0%, transparent 100%)`,
        }}
      />

      {/* Top accent line */}
      <div
        className="absolute top-0 left-0 right-0 h-px pointer-events-none"
        style={{
          background: `linear-gradient(to right, transparent, rgba(${G},0.7) 35%, rgba(${G},0.7) 65%, transparent)`,
        }}
      />

      {/* Content */}
      <div className="relative h-full flex flex-col items-center justify-center gap-3 p-6">
        <div
          className="relative w-12 h-12 rounded-xl flex items-center justify-center shrink-0"
          style={{
            background: `rgba(${G},0.14)`,
            border: `1px solid rgba(${G},0.40)`,
          }}
        >
          <svg viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-5 h-5">
            <circle cx="10" cy="10" r="9" stroke="currentColor" strokeOpacity="0.12" strokeWidth="1.2" />
            <circle cx="10"   cy="4"  r="1.5" fill={`rgba(${G},1)`} />
            <circle cx="15.2" cy="7"  r="1.5" fill={`rgba(${G},0.65)`} />
            <circle cx="15.2" cy="13" r="1.5" fill={`rgba(${G},0.45)`} />
            <circle cx="10"   cy="16" r="1.5" fill={`rgba(${G},0.65)`} />
            <circle cx="4.8"  cy="13" r="1.5" fill={`rgba(${G},0.45)`} />
            <circle cx="4.8"  cy="7"  r="1.5" fill={`rgba(${G},0.65)`} />
            <circle cx="10"   cy="10" r="2.5" fill={`rgba(${G},1)`} />
          </svg>

          <span
            className="absolute inset-0 rounded-xl animate-ping opacity-25"
            style={{ border: `1px solid rgba(${G},1)`, animationDuration: '2.5s' }}
          />
        </div>

        <p
          className="relative font-semibold text-sm text-foreground/90"
          style={{ fontFamily: 'var(--font-heading)' }}
        >
          Orchestrator
        </p>

        <div className="relative flex items-center gap-1.5">
          <span
            className="w-1.5 h-1.5 rounded-full animate-pulse"
            style={{ backgroundColor: `rgb(${G})` }}
          />
          <span className="text-xs font-medium" style={{ color: `rgba(${G},0.85)` }}>
            Active
          </span>
        </div>
      </div>
    </div>
  );
}
