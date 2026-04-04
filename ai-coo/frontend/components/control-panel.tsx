'use client';

import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { commandCenterData, activityFeed, agents, ActivityItem } from '@/lib/mock-data';

type Tab = 'command' | 'activity' | 'risks';

interface SidebarProps {
  open: boolean;
  onClose: () => void;
}

export function ControlPanel({ open, onClose }: SidebarProps) {
  const [activeTab, setActiveTab] = useState<Tab>('command');

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (open) {
      document.addEventListener('keydown', handleEsc);
      return () => document.removeEventListener('keydown', handleEsc);
    }
  }, [open, onClose]);

  return (
    <div
      className={cn(
        'fixed top-0 left-0 h-full w-[300px] z-50 flex flex-col border-r border-border/50 bg-card/92 shadow-2xl shadow-black/30 backdrop-blur-xl',
        'transition-transform duration-250 ease-out',
        open ? 'translate-x-0' : '-translate-x-full'
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 h-13 border-b border-border/40 shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold" style={{ fontFamily: 'var(--font-heading)' }}>
            Control Panel
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

      {/* Tabs */}
      <div className="px-4 py-3 border-b border-border/40 shrink-0">
        <div className="flex bg-secondary/50 rounded-lg p-1 gap-0.5">
          {(['command', 'activity', 'risks'] as Tab[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={cn(
                'flex-1 py-1.5 text-xs font-medium rounded-md transition-all duration-150 cursor-pointer capitalize',
                activeTab === tab
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {activeTab === 'command' && <CommandContent />}
        {activeTab === 'activity' && <ActivityContent />}
        {activeTab === 'risks' && <RisksContent />}
      </div>
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="text-[10px] font-semibold text-muted-foreground/70 uppercase tracking-widest mb-3">
      {children}
    </h4>
  );
}

function CommandContent() {
  return (
    <div className="space-y-6">
      <div>
        <SectionTitle>Top Priorities</SectionTitle>
        <ul className="space-y-2.5">
          {commandCenterData.topPriorities.map((priority, i) => (
            <li key={i} className="flex items-start gap-2.5 text-sm">
              <span className="w-5 h-5 rounded bg-primary/10 border border-primary/20 flex items-center justify-center text-[10px] font-bold text-primary shrink-0 mt-0.5">
                {i + 1}
              </span>
              <span className="text-muted-foreground leading-relaxed text-xs">{priority}</span>
            </li>
          ))}
        </ul>
      </div>

      <div>
        <SectionTitle>Next Actions</SectionTitle>
        <ul className="space-y-2.5">
          {commandCenterData.nextActions.map((action, i) => (
            <li key={i} className="flex items-start gap-2.5 text-sm">
              <span className="w-5 h-5 rounded border border-border/60 flex items-center justify-center shrink-0 mt-0.5">
                <div className="w-1.5 h-1.5 rounded-sm bg-muted-foreground/30" />
              </span>
              <span className="text-muted-foreground leading-relaxed text-xs">{action}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function ActivityContent() {
  const borderColors: Record<ActivityItem['type'], string> = {
    info: 'border-l-primary/50',
    warning: 'border-l-warning',
    success: 'border-l-success',
  };

  return (
    <div className="space-y-2.5">
      {activityFeed.map((item) => (
        <div
          key={item.id}
          className={cn(
            'bg-secondary/30 rounded-lg p-3 border-l-2 transition-colors duration-150 hover:bg-secondary/50',
            borderColors[item.type]
          )}
        >
          <p className="text-xs text-foreground/85 leading-relaxed">{item.message}</p>
          <div className="flex items-center gap-2 mt-1.5">
            <span className="text-[10px] font-medium text-primary">{item.agent}</span>
            <span className="text-[10px] text-muted-foreground/60">{item.timestamp}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function RisksContent() {
  const allRisks = agents.flatMap((agent) =>
    agent.risks.map((risk) => ({ agent: agent.name, risk, status: agent.status }))
  );

  return (
    <div className="space-y-6">
      <div>
        <SectionTitle>Critical Risks</SectionTitle>
        <ul className="space-y-2.5">
          {commandCenterData.criticalRisks.map((risk, i) => (
            <li key={i} className="flex items-start gap-2.5">
              <span className="w-5 h-5 rounded bg-destructive/10 border border-destructive/25 flex items-center justify-center shrink-0 mt-0.5">
                <div className="w-1.5 h-1.5 rounded-full bg-destructive" />
              </span>
              <span className="text-xs text-muted-foreground leading-relaxed">{risk}</span>
            </li>
          ))}
        </ul>
      </div>

      <div>
        <SectionTitle>Blocked Agents</SectionTitle>
        <ul className="space-y-2">
          {agents.filter((a) => a.status === 'blocked').map((agent) => (
            <li key={agent.id} className="bg-secondary/30 rounded-lg p-3 border border-destructive/15">
              <div className="flex items-center gap-2 mb-1">
                <span className="w-2 h-2 rounded-full bg-destructive" />
                <span className="text-xs font-medium">{agent.name}</span>
              </div>
              <p className="text-[11px] text-muted-foreground">{agent.risks[0]}</p>
            </li>
          ))}
        </ul>
      </div>

      <div>
        <SectionTitle>All Agent Risks</SectionTitle>
        <ul className="space-y-2.5">
          {allRisks.slice(0, 8).map((item, i) => (
            <li key={i} className="flex items-start gap-2.5">
              <span className="w-5 h-5 rounded bg-warning/10 border border-warning/25 flex items-center justify-center shrink-0 mt-0.5">
                <div className="w-1.5 h-1.5 rounded-full bg-warning" />
              </span>
              <div>
                <span className="text-xs text-muted-foreground leading-relaxed">{item.risk}</span>
                <span className="text-[10px] text-muted-foreground/50 block mt-0.5">{item.agent}</span>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
