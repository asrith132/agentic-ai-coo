'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { techStackItems } from '@/lib/mock-data';
import { cn } from '@/lib/utils';

export function TechStackPanel() {
  return (
    <Card className="bg-card/50 border-border/50 backdrop-blur-sm">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          <span>⚡</span>
          Tech Stack
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-2">
          {techStackItems.map((tech, i) => (
            <Badge
              key={i}
              variant="outline"
              className={cn(
                'text-xs py-1.5 px-3',
                tech.detected
                  ? 'bg-primary/10 text-primary border-primary/30'
                  : 'bg-secondary/50 text-muted-foreground border-border/50'
              )}
            >
              {tech.detected && <span className="w-1.5 h-1.5 rounded-full bg-primary mr-2" />}
              {tech.name}
              <span className="ml-1.5 text-[10px] opacity-60">({tech.category})</span>
            </Badge>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
