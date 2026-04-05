'use client';

import { useState } from 'react';
import { LandingPage } from '@/components/landing-page';
import { IntakeForm } from '@/components/intake-form';
import { LoadingScreen } from '@/components/loading-screen';
import { Dashboard } from '@/components/dashboard';
import { NotificationsPage } from '@/components/notifications-page';
import { ProjectDetails } from '@/lib/mock-data';
import { API_BASE } from '@/lib/api/config';

type AppState = 'landing' | 'intake' | 'loading' | 'dashboard' | 'notifications';

export default function Home() {
  const [appState, setAppState] = useState<AppState>('landing');
  const [, setProjectDetails] = useState<ProjectDetails | null>(null);

  const handleIntakeSubmit = async (details: ProjectDetails) => {
    setProjectDetails(details);

    const techStack = details.techStack
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)

    const stageMap: Record<string, string> = {
      idea: 'pre_launch',
      mvp: 'mvp',
      launched: 'launched',
      growth: 'growing',
    }

    try {
      await Promise.all([
        fetch(`${API_BASE}/api/context/global`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            field: 'company_profile',
            value: {
              description: details.startupIdea,
              product_description: details.startupIdea,
              tech_stack: techStack,
            },
          }),
        }),
        fetch(`${API_BASE}/api/context/global`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            field: 'target_customer',
            value: {
              persona: details.targetUsers,
              language_patterns: details.constraints
                ? details.constraints.split(',').map((item: string) => item.trim()).filter(Boolean)
                : [],
            },
          }),
        }),
        fetch(`${API_BASE}/api/context/global`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            field: 'business_state',
            value: {
              phase: stageMap[details.stage] ?? details.stage ?? 'pre_launch',
              active_priorities: [
                details.timeline ? `Timeline: ${details.timeline}` : null,
                details.monetization ? `Monetization: ${details.monetization}` : null,
                details.repoUrl ? `Repo: ${details.repoUrl}` : null,
              ].filter(Boolean),
              key_metrics: {
                monetization_model: details.monetization,
                constraints: details.constraints,
                repo_url: details.repoUrl,
              },
            },
          }),
        }),
      ])
    } catch {
      // If backend is unavailable, continue with the local flow.
    }

    setAppState('loading');
  };

  return (
    <main className="min-h-screen">
      {appState === 'landing' && (
        <LandingPage onGetStarted={() => setAppState('intake')} />
      )}
      {appState === 'intake' && (
        <IntakeForm onSubmit={handleIntakeSubmit} />
      )}
      {appState === 'loading' && (
        <LoadingScreen onComplete={() => setAppState('dashboard')} />
      )}
      {appState === 'dashboard' && (
        <Dashboard onOpenNotifications={() => setAppState('notifications')} />
      )}
      {appState === 'notifications' && (
        <NotificationsPage onBack={() => setAppState('dashboard')} />
      )}
    </main>
  );
}
