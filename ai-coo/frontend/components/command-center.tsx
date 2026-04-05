'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useLiveDashboardData } from '@/lib/live-dashboard';

export function CommandCenter() {
  const {
    data: { command },
  } = useLiveDashboardData()

  return (
    <Card className="bg-card/50 border-border/50 backdrop-blur-sm h-full">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          <div className="w-4 h-4 rounded bg-primary/20 border border-primary/30 flex items-center justify-center">
            <div className="w-1.5 h-1.5 rounded-sm bg-primary" />
          </div>
          Command Center
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Top Priorities */}
        <div>
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            Top Priorities
          </h4>
          <ul className="space-y-2">
            {command.topPriorities.map((priority, i) => (
              <li key={i} className="flex items-start gap-2 text-xs">
                <span className="w-4 h-4 rounded bg-primary/10 border border-primary/20 flex items-center justify-center text-[10px] font-bold text-primary shrink-0">
                  {i + 1}
                </span>
                <span className="text-muted-foreground leading-relaxed">{priority}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Critical Risks */}
        <div>
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            Critical Risks
          </h4>
          <ul className="space-y-2">
            {command.criticalRisks.map((risk, i) => (
              <li key={i} className="flex items-start gap-2 text-xs">
                <span className="w-4 h-4 rounded bg-warning/10 border border-warning/30 flex items-center justify-center shrink-0">
                  <div className="w-1.5 h-1.5 rounded-full bg-warning" />
                </span>
                <span className="text-muted-foreground leading-relaxed">{risk}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Next Actions */}
        <div>
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            Next Actions
          </h4>
          <ul className="space-y-2">
            {command.nextActions.map((action, i) => (
              <li key={i} className="flex items-start gap-2 text-xs">
                <span className="w-4 h-4 rounded border border-border/50 flex items-center justify-center shrink-0">
                  <div className="w-1.5 h-1.5 rounded-sm bg-muted-foreground/30" />
                </span>
                <span className="text-muted-foreground leading-relaxed">{action}</span>
              </li>
            ))}
          </ul>
        </div>
      </CardContent>
    </Card>
  );
}
