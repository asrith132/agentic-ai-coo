'use client';

import { useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { ProjectDetails, defaultProjectDetails } from '@/lib/mock-data';

interface IntakeFormProps {
  onSubmit: (details: ProjectDetails, action: 'plan' | 'build') => void;
}

export function IntakeForm({ onSubmit }: IntakeFormProps) {
  const [details, setDetails] = useState<ProjectDetails>(defaultProjectDetails);

  const handleSubmit = (action: 'plan' | 'build') => {
    onSubmit(details, action);
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6 relative overflow-hidden">
      {/* Background glow */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[400px] bg-primary/5 rounded-full blur-[120px]" />
      </div>

      <div className="w-full max-w-xl relative">
        {/* Logo mark + wordmark */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center mb-5">
            <div className="relative w-12 h-12">
              <svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full h-full">
                <circle cx="24" cy="24" r="23" stroke="currentColor" strokeOpacity="0.15" strokeWidth="1.5" />
                <circle cx="24" cy="9" r="3.5" className="fill-primary" />
                <circle cx="38.5" cy="17" r="3.5" className="fill-primary/60" />
                <circle cx="38.5" cy="31" r="3.5" className="fill-primary/40" />
                <circle cx="24" cy="39" r="3.5" className="fill-primary/60" />
                <circle cx="9.5" cy="31" r="3.5" className="fill-primary/40" />
                <circle cx="9.5" cy="17" r="3.5" className="fill-primary/60" />
                <circle cx="24" cy="24" r="5" className="fill-primary animate-pulse" />
                <line x1="24" y1="9" x2="24" y2="19" stroke="currentColor" strokeOpacity="0.2" strokeWidth="1" />
                <line x1="24" y1="29" x2="24" y2="39" stroke="currentColor" strokeOpacity="0.2" strokeWidth="1" />
                <line x1="38.5" y1="17" x2="29" y2="21.5" stroke="currentColor" strokeOpacity="0.2" strokeWidth="1" />
                <line x1="9.5" y1="17" x2="19" y2="21.5" stroke="currentColor" strokeOpacity="0.2" strokeWidth="1" />
                <line x1="38.5" y1="31" x2="29" y2="26.5" stroke="currentColor" strokeOpacity="0.2" strokeWidth="1" />
                <line x1="9.5" y1="31" x2="19" y2="26.5" stroke="currentColor" strokeOpacity="0.2" strokeWidth="1" />
              </svg>
            </div>
          </div>
          <h1 className="text-4xl font-bold tracking-tight text-foreground mb-2" style={{ fontFamily: 'var(--font-heading)' }}>
            orchestrate
          </h1>
          <p className="text-muted-foreground text-base">
            Your AI-powered startup operating system
          </p>
        </div>

        <Card className="border-border/60 bg-card/60 backdrop-blur-sm shadow-2xl shadow-black/40">
          <CardContent className="p-7 space-y-5">
            <div>
              <h2 className="text-lg font-semibold text-foreground mb-0.5" style={{ fontFamily: 'var(--font-heading)' }}>
                Project Details
              </h2>
              <p className="text-sm text-muted-foreground">
                Tell us about your startup and our agents will get to work.
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="startup-idea" className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Startup Idea
              </Label>
              <Textarea
                id="startup-idea"
                placeholder="Describe your startup idea in a few sentences..."
                className="min-h-[80px] bg-input/60 border-border/60 focus:border-primary/60 focus:ring-primary/20 resize-none text-sm"
                value={details.startupIdea}
                onChange={(e) => setDetails({ ...details, startupIdea: e.target.value })}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="stage" className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  Stage
                </Label>
                <Select
                  value={details.stage}
                  onValueChange={(value) => setDetails({ ...details, stage: value })}
                >
                  <SelectTrigger id="stage" className="bg-input/60 border-border/60 text-sm">
                    <SelectValue placeholder="Select stage" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="idea">Idea</SelectItem>
                    <SelectItem value="mvp">Building MVP</SelectItem>
                    <SelectItem value="launched">Launched</SelectItem>
                    <SelectItem value="growth">Growth</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="timeline" className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  Timeline
                </Label>
                <Select
                  value={details.timeline}
                  onValueChange={(value) => setDetails({ ...details, timeline: value })}
                >
                  <SelectTrigger id="timeline" className="bg-input/60 border-border/60 text-sm">
                    <SelectValue placeholder="Select urgency" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="relaxed">Relaxed (3+ months)</SelectItem>
                    <SelectItem value="moderate">Moderate (1-3 months)</SelectItem>
                    <SelectItem value="urgent">Urgent (2-4 weeks)</SelectItem>
                    <SelectItem value="asap">ASAP (1-2 weeks)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="target-users" className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Target Users
              </Label>
              <Input
                id="target-users"
                placeholder="e.g. Small business owners, developers, students..."
                className="bg-input/60 border-border/60 focus:border-primary/60 text-sm"
                value={details.targetUsers}
                onChange={(e) => setDetails({ ...details, targetUsers: e.target.value })}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="monetization" className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Monetization
              </Label>
              <Input
                id="monetization"
                placeholder="e.g. SaaS subscription, freemium, marketplace fees..."
                className="bg-input/60 border-border/60 focus:border-primary/60 text-sm"
                value={details.monetization}
                onChange={(e) => setDetails({ ...details, monetization: e.target.value })}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="repo-url" className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  Repo URL <span className="normal-case text-muted-foreground/60">(optional)</span>
                </Label>
                <Input
                  id="repo-url"
                  placeholder="https://github.com/..."
                  className="bg-input/60 border-border/60 focus:border-primary/60 text-sm"
                  value={details.repoUrl}
                  onChange={(e) => setDetails({ ...details, repoUrl: e.target.value })}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="tech-stack" className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  Tech Stack <span className="normal-case text-muted-foreground/60">(optional)</span>
                </Label>
                <Input
                  id="tech-stack"
                  placeholder="Next.js, Supabase, Tailwind..."
                  className="bg-input/60 border-border/60 focus:border-primary/60 text-sm"
                  value={details.techStack}
                  onChange={(e) => setDetails({ ...details, techStack: e.target.value })}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="constraints" className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Constraints <span className="normal-case text-muted-foreground/60">(optional)</span>
              </Label>
              <Textarea
                id="constraints"
                placeholder="Any budget, time, or resource constraints..."
                className="min-h-[60px] bg-input/60 border-border/60 focus:border-primary/60 resize-none text-sm"
                value={details.constraints}
                onChange={(e) => setDetails({ ...details, constraints: e.target.value })}
              />
            </div>

            <div className="flex gap-3 pt-2">
              <Button
                variant="outline"
                className="flex-1 h-11 text-sm font-medium border-border/60 hover:border-primary/40 hover:text-primary hover:bg-primary/5 transition-all duration-200 cursor-pointer"
                onClick={() => handleSubmit('plan')}
              >
                Plan
              </Button>
              <Button
                className="flex-1 h-11 text-sm font-semibold bg-primary hover:bg-primary/90 text-primary-foreground shadow-lg shadow-primary/20 transition-all duration-200 cursor-pointer"
                onClick={() => handleSubmit('build')}
              >
                Start Building
              </Button>
            </div>
          </CardContent>
        </Card>

        <p className="text-center text-xs text-muted-foreground/60 mt-6">
          Specialist agents will coordinate to help you build, launch, and scale.
        </p>
      </div>
    </div>
  );
}
