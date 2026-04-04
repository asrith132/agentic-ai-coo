'use client';

import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Agent, AgentStatus } from '@/lib/mock-data';
import { cn } from '@/lib/utils';
import { AgentIcon } from '@/lib/agent-visuals';

interface AgentDetailDrawerProps {
  agent: Agent | null;
  open: boolean;
  onClose: () => void;
}

const statusConfig: Record<AgentStatus, { label: string; badgeClass: string; dotClass: string }> = {
  thinking: {
    label: 'Thinking',
    badgeClass: 'bg-primary/10 text-primary border-primary/25',
    dotClass: 'bg-primary animate-pulse',
  },
  done: {
    label: 'Done',
    badgeClass: 'bg-success/10 text-success border-success/25',
    dotClass: 'bg-success',
  },
  blocked: {
    label: 'Blocked',
    badgeClass: 'bg-destructive/10 text-destructive border-destructive/25',
    dotClass: 'bg-destructive',
  },
  idle: {
    label: 'Idle',
    badgeClass: 'bg-muted text-muted-foreground border-border/60',
    dotClass: 'bg-muted-foreground/50',
  },
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="text-[10px] font-semibold text-muted-foreground/70 uppercase tracking-widest mb-3">
        {title}
      </h4>
      {children}
    </div>
  );
}

export function AgentDetailDrawer({ agent, open, onClose }: AgentDetailDrawerProps) {
  if (!agent) return null;
  const status = statusConfig[agent.status];

  return (
    <Sheet open={open} onOpenChange={onClose}>
      <SheetContent className="w-full sm:max-w-md bg-card/98 backdrop-blur-md border-l border-border/50 overflow-y-auto p-0">
        {/* Header */}
        <SheetHeader className="p-5 pb-4 border-b border-border/40">
          <div className="flex items-center gap-3.5">
            <div className="w-12 h-12 rounded-xl bg-secondary/80 border border-border/60 flex items-center justify-center text-sm font-bold text-muted-foreground font-mono shrink-0">
              <AgentIcon agentId={agent.id} className="w-5 h-5" strokeWidth={2.1} />
            </div>
            <div className="min-w-0">
              <SheetTitle className="text-base font-semibold text-foreground" style={{ fontFamily: 'var(--font-heading)' }}>
                {agent.name}
              </SheetTitle>
              <SheetDescription className="sr-only">
                Details and status for {agent.name} agent
              </SheetDescription>
              <Badge
                variant="outline"
                className={cn('text-[10px] font-normal mt-1.5 gap-1.5', status.badgeClass)}
              >
                <span className={cn('w-1.5 h-1.5 rounded-full', status.dotClass)} />
                {status.label}
              </Badge>
            </div>
          </div>
        </SheetHeader>

        <div className="p-5 space-y-5">
          {/* Summary */}
          <Section title="Summary">
            <p className="text-sm text-muted-foreground leading-relaxed">{agent.summary}</p>
          </Section>

          <Separator className="bg-border/40" />

          {/* Tasks */}
          <Section title="Current Tasks">
            <ul className="space-y-2">
              {agent.tasks.map((task, i) => (
                <li key={i} className="flex items-start gap-2.5 text-sm">
                  <div className="w-5 h-5 rounded-md border border-border/50 flex items-center justify-center shrink-0 mt-0.5">
                    <div className="w-1.5 h-1.5 rounded-sm bg-primary/40" />
                  </div>
                  <span className="text-muted-foreground leading-relaxed">{task}</span>
                </li>
              ))}
            </ul>
          </Section>

          <Separator className="bg-border/40" />

          {/* Risks */}
          <Section title="Risks">
            <ul className="space-y-2">
              {agent.risks.map((risk, i) => (
                <li key={i} className="flex items-start gap-2.5 text-sm">
                  <span className="w-5 h-5 rounded-md bg-warning/10 border border-warning/25 flex items-center justify-center shrink-0 mt-0.5">
                    <div className="w-1.5 h-1.5 rounded-full bg-warning" />
                  </span>
                  <span className="text-muted-foreground leading-relaxed">{risk}</span>
                </li>
              ))}
            </ul>
          </Section>

          <Separator className="bg-border/40" />

          {/* Dependencies */}
          <Section title="Dependencies">
            <div className="flex flex-wrap gap-2">
              {agent.dependencies.map((dep, i) => (
                <Badge
                  key={i}
                  variant="secondary"
                  className="text-[11px] bg-secondary/60 border border-border/50 text-muted-foreground font-normal"
                >
                  {dep}
                </Badge>
              ))}
            </div>
          </Section>

          <Separator className="bg-border/40" />

          {/* Recommendations */}
          <Section title="Recommendations">
            <ul className="space-y-2">
              {agent.recommendations.map((rec, i) => (
                <li key={i} className="flex items-start gap-2.5 text-sm">
                  <span className="w-5 h-5 rounded-md bg-primary/8 border border-primary/20 flex items-center justify-center shrink-0 mt-0.5">
                    <div className="w-1.5 h-1.5 rounded-full bg-primary/70" />
                  </span>
                  <span className="text-muted-foreground leading-relaxed">{rec}</span>
                </li>
              ))}
            </ul>
          </Section>

          {/* Recent Outputs */}
          <div className="bg-secondary/30 rounded-xl p-4 border border-border/30">
            <h4 className="text-[10px] font-semibold text-muted-foreground/70 uppercase tracking-widest mb-3">
              Recent Outputs
            </h4>
            <ul className="space-y-1.5">
              {agent.outputs.map((output, i) => (
                <li key={i} className="flex items-start gap-2 text-sm">
                  <span className="w-1 h-1 rounded-full bg-success/70 mt-2 shrink-0" />
                  <span className="text-foreground/80 leading-relaxed">{output}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
