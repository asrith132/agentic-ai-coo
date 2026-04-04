'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { founderBrief } from '@/lib/mock-data';

export function FounderBrief() {
  // Parse the brief for styling
  const formatBrief = (text: string) => {
    const lines = text.split('\n\n');
    return lines.map((line, i) => {
      // Bold headings
      const formatted = line.replace(/\*\*(.*?)\*\*/g, '<strong class="text-foreground">$1</strong>');
      return (
        <p
          key={i}
          className="text-xs text-muted-foreground leading-relaxed mb-2 last:mb-0"
          dangerouslySetInnerHTML={{ __html: formatted }}
        />
      );
    });
  };

  return (
    <Card className="bg-card/50 border-border/50 backdrop-blur-sm">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          <span>📋</span>
          Founder Daily Brief
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="bg-secondary/30 rounded-lg p-4 border border-border/30">
          {formatBrief(founderBrief)}
        </div>
      </CardContent>
    </Card>
  );
}
