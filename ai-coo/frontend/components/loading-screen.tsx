'use client';

import { useEffect, useState } from 'react';

const loadingMessages = [
  'Initializing orchestrate...',
  'Spinning up specialist agents...',
  'Analyzing project parameters...',
  'Configuring orchestration layer...',
  'Establishing agent connections...',
  'Preparing your command center...',
];

const agentChips = ['PM', 'ENG', 'RES', 'MKT', 'LEG', 'FIN', 'OUT', 'MTG'];

interface LoadingScreenProps {
  onComplete: () => void;
}

export function LoadingScreen({ onComplete }: LoadingScreenProps) {
  const [messageIndex, setMessageIndex] = useState(0);
  const [progress, setProgress] = useState(0);
  const [activeAgent, setActiveAgent] = useState(0);

  useEffect(() => {
    const progressInterval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 100) {
          clearInterval(progressInterval);
          return 100;
        }
        return prev + 2;
      });
    }, 60);

    const messageInterval = setInterval(() => {
      setMessageIndex((prev) => (prev + 1) % loadingMessages.length);
    }, 800);

    const agentInterval = setInterval(() => {
      setActiveAgent((prev) => (prev + 1) % agentChips.length);
    }, 400);

    const completeTimeout = setTimeout(() => {
      onComplete();
    }, 3000);

    return () => {
      clearInterval(progressInterval);
      clearInterval(messageInterval);
      clearInterval(agentInterval);
      clearTimeout(completeTimeout);
    };
  }, [onComplete]);

  return (
    <div className="min-h-screen flex items-center justify-center p-6 relative overflow-hidden">
      {/* Background glow */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-primary/6 rounded-full blur-[140px]" />
      </div>

      <div className="text-center max-w-sm relative">
        {/* Logo mark */}
        <div className="flex items-center justify-center mb-8">
          <div className="relative">
            {/* Outer ring */}
            <div className="w-20 h-20 rounded-2xl border border-border/40 bg-card/60 backdrop-blur-sm flex items-center justify-center animate-pulse-glow">
              <svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-10 h-10">
                <circle cx="24" cy="24" r="23" stroke="currentColor" strokeOpacity="0.1" strokeWidth="1.5" />
                <circle cx="24" cy="9" r="3" className="fill-primary" />
                <circle cx="38.5" cy="17" r="3" className="fill-primary/50" />
                <circle cx="38.5" cy="31" r="3" className="fill-primary/30" />
                <circle cx="24" cy="39" r="3" className="fill-primary/50" />
                <circle cx="9.5" cy="31" r="3" className="fill-primary/30" />
                <circle cx="9.5" cy="17" r="3" className="fill-primary/50" />
                <circle cx="24" cy="24" r="4.5" className="fill-primary" />
              </svg>
            </div>
          </div>
        </div>

        {/* Wordmark */}
        <h1 className="text-2xl font-bold tracking-tight text-foreground mb-6" style={{ fontFamily: 'var(--font-heading)' }}>
          orchestrate
        </h1>

        {/* Loading message */}
        <div className="h-6 mb-8 overflow-hidden">
          <p className="text-sm text-muted-foreground transition-all duration-300 ease-in-out">
            {loadingMessages[messageIndex]}
          </p>
        </div>

        {/* Progress bar */}
        <div className="w-full max-w-[280px] mx-auto mb-8">
          <div className="h-[2px] bg-border/60 rounded-full overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-all duration-75 ease-out shadow-[0_0_8px_var(--color-glow)]"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="flex justify-between items-center mt-2">
            <span className="text-[10px] text-muted-foreground/50 tabular-nums">{progress}%</span>
            <span className="text-[10px] text-muted-foreground/50">Initializing agents</span>
          </div>
        </div>

        {/* Agent chips */}
        <div className="flex justify-center gap-1.5 flex-wrap">
          {agentChips.map((agent, i) => (
            <div
              key={agent}
              className="h-7 px-2.5 rounded-md border text-[10px] font-medium flex items-center gap-1.5 transition-all duration-300"
              style={{
                borderColor: i === activeAgent ? 'color-mix(in oklch, var(--color-primary) 60%, transparent)' : 'color-mix(in oklch, var(--color-border) 100%, transparent)',
                color: i === activeAgent ? 'var(--color-primary)' : 'var(--color-muted-foreground)',
                backgroundColor: i === activeAgent ? 'color-mix(in oklch, var(--color-primary) 8%, transparent)' : 'transparent',
              }}
            >
              <span
                className="w-1 h-1 rounded-full"
                style={{
                  backgroundColor: i === activeAgent ? 'var(--color-primary)' : 'var(--color-border)',
                }}
              />
              {agent}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
