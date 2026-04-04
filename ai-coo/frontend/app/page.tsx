'use client';

import { useState } from 'react';
import { LandingPage } from '@/components/landing-page';
import { IntakeForm } from '@/components/intake-form';
import { LoadingScreen } from '@/components/loading-screen';
import { Dashboard } from '@/components/dashboard';
import { NotificationsPage } from '@/components/notifications-page';
import { ProjectDetails } from '@/lib/mock-data';

type AppState = 'landing' | 'intake' | 'loading' | 'dashboard' | 'notifications';

export default function Home() {
  const [appState, setAppState] = useState<AppState>('landing');
  const [, setProjectDetails] = useState<ProjectDetails | null>(null);

  const handleIntakeSubmit = (details: ProjectDetails) => {
    setProjectDetails(details);
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
