'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { activityFeed, ActivityItem } from '@/lib/mock-data';
import { cn } from '@/lib/utils';

const typeStyles = {
  info: 'border-l-primary/50',
  warning: 'border-l-warning',
  success: 'border-l-success',
};

export function ActivityFeed() {
  return (
    <Card className="bg-card/50 border-border/50 backdrop-blur-sm h-full">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          <div className="w-4 h-4 rounded bg-primary/20 border border-primary/30 flex items-center justify-center">
            <div className="w-1.5 h-1.5 rounded-sm bg-primary" />
          </div>
          Activity Feed
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {activityFeed.map((item) => (
          <ActivityItemCard key={item.id} item={item} />
        ))}
      </CardContent>
    </Card>
  );
}

function ActivityItemCard({ item }: { item: ActivityItem }) {
  return (
    <div
      className={cn(
        'bg-secondary/30 rounded-lg p-3 border-l-2 transition-all hover:bg-secondary/50',
        typeStyles[item.type]
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs text-foreground/90 leading-relaxed">{item.message}</p>
      </div>
      <div className="flex items-center gap-2 mt-2">
        <span className="text-[10px] font-medium text-primary">{item.agent}</span>
        <span className="text-[10px] text-muted-foreground">• {item.timestamp}</span>
      </div>
    </div>
  );
}
