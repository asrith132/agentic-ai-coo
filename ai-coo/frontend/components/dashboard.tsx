"use client";

import { useEffect, useState } from "react";
import { Menu, PanelRight } from "lucide-react";
import { agents, Agent } from "@/lib/mock-data";
import { cn } from "@/lib/utils";
import { AccountPopover } from "./account-popover";
import { AgentCard } from "./agent-card";
import { AgentChatPanel } from "./agent-chat-panel";
import { ControlPanel } from "./control-panel";
import { NotificationsPopover } from "./notifications-popover";
import { RightActivityPanel } from "./right-activity-panel";
import { AnimatedThemeToggler } from "./ui/animated-theme-toggler";
import { StarsBackground } from "./ui/stars";

interface DashboardProps {
  onOpenNotifications: () => void
}

export function Dashboard({ onOpenNotifications }: DashboardProps) {
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [activityOpen, setActivityOpen] = useState(false);
  const [isDark, setIsDark] = useState(true);

  useEffect(() => {
    const el = document.documentElement;
    const update = () => setIsDark(el.classList.contains("dark"));
    update();
    const observer = new MutationObserver(update);
    observer.observe(el, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  const handleAgentClick = (agent: Agent) => {
    setSelectedAgent(agent);
    setDrawerOpen(true);
  };

  const handleCloseDrawer = () => {
    setDrawerOpen(false);
    setTimeout(() => setSelectedAgent(null), 300);
  };

  const centerAgent = agents.find((agent) => agent.id === "product-manager") ?? agents[0];
  const surroundingAgents = agents.filter(
    (agent) => agent.id !== "product-manager" && agent.id !== "engineer"
  );
  const orbitStyles = [
    { left: "50%", top: "12%" },
    { left: "74%", top: "30%" },
    { left: "74%", top: "70%" },
    { left: "50%", top: "88%" },
    { left: "26%", top: "70%" },
    { left: "26%", top: "30%" },
  ];
  const orbitMotionStyles = [
    {
      animationDelay: "0s",
      "--wiggle-duration": "4.6s",
      "--wiggle-x-1": "7px",
      "--wiggle-y-1": "-8px",
      "--wiggle-r-1": "-1.1deg",
      "--wiggle-x-2": "-4px",
      "--wiggle-y-2": "4px",
      "--wiggle-r-2": "0.8deg",
      "--wiggle-x-3": "3px",
      "--wiggle-y-3": "-5px",
      "--wiggle-r-3": "0.9deg",
    },
    {
      animationDelay: "0.8s",
      "--wiggle-duration": "5.4s",
      "--wiggle-x-1": "-6px",
      "--wiggle-y-1": "-8px",
      "--wiggle-r-1": "1deg",
      "--wiggle-x-2": "5px",
      "--wiggle-y-2": "5px",
      "--wiggle-r-2": "-0.8deg",
      "--wiggle-x-3": "-3px",
      "--wiggle-y-3": "-6px",
      "--wiggle-r-3": "-1deg",
    },
    {
      animationDelay: "1.3s",
      "--wiggle-duration": "5s",
      "--wiggle-x-1": "5px",
      "--wiggle-y-1": "-6px",
      "--wiggle-r-1": "-0.7deg",
      "--wiggle-x-2": "-3px",
      "--wiggle-y-2": "5px",
      "--wiggle-r-2": "1deg",
      "--wiggle-x-3": "5px",
      "--wiggle-y-3": "-4px",
      "--wiggle-r-3": "0.6deg",
    },
    {
      animationDelay: "0.5s",
      "--wiggle-duration": "5.8s",
      "--wiggle-x-1": "-5px",
      "--wiggle-y-1": "-9px",
      "--wiggle-r-1": "0.9deg",
      "--wiggle-x-2": "5px",
      "--wiggle-y-2": "3px",
      "--wiggle-r-2": "-1deg",
      "--wiggle-x-3": "-2px",
      "--wiggle-y-3": "-6px",
      "--wiggle-r-3": "0.7deg",
    },
    {
      animationDelay: "1.6s",
      "--wiggle-duration": "4.9s",
      "--wiggle-x-1": "6px",
      "--wiggle-y-1": "-6px",
      "--wiggle-r-1": "-0.9deg",
      "--wiggle-x-2": "-4px",
      "--wiggle-y-2": "4px",
      "--wiggle-r-2": "0.9deg",
      "--wiggle-x-3": "4px",
      "--wiggle-y-3": "-7px",
      "--wiggle-r-3": "-0.5deg",
    },
    {
      animationDelay: "1s",
      "--wiggle-duration": "5.2s",
      "--wiggle-x-1": "-7px",
      "--wiggle-y-1": "-7px",
      "--wiggle-r-1": "1.1deg",
      "--wiggle-x-2": "3px",
      "--wiggle-y-2": "5px",
      "--wiggle-r-2": "-0.7deg",
      "--wiggle-x-3": "-4px",
      "--wiggle-y-3": "-5px",
      "--wiggle-r-3": "0.8deg",
    },
  ] as React.CSSProperties[];
  const centerMotionStyle = {
    animationDelay: "0.4s",
    "--wiggle-duration": "5.1s",
    "--wiggle-x-1": "5px",
    "--wiggle-y-1": "-6px",
    "--wiggle-r-1": "-0.8deg",
    "--wiggle-x-2": "-4px",
    "--wiggle-y-2": "4px",
    "--wiggle-r-2": "0.8deg",
    "--wiggle-x-3": "3px",
    "--wiggle-y-3": "-5px",
    "--wiggle-r-3": "0.5deg",
  } as React.CSSProperties;

  const blockedCount = agents.filter((a) => a.status === "blocked").length;
  const thinkingCount = agents.filter((a) => a.status === "thinking").length;

  return (
    <StarsBackground
      className="min-h-screen relative isolate"
      variant="dark"
      speed={isDark ? 50 : 65}
    >
      <div
        className={cn(
          "relative z-[1] transition-[margin,width] duration-250 ease-out"
        )}
        style={{
          marginLeft: sidebarOpen ? '300px' : '0px',
          width: sidebarOpen ? 'calc(100% - 300px)' : '100%',
        }}
      >
        {/* Top nav — always dark regardless of theme toggle */}
        <header className="dark sticky top-0 z-30 border-b border-white/[0.06] bg-[#0a0a0a]/80 backdrop-blur-xl relative">
          <div className="relative flex items-center px-4 h-13">
            {/* Left */}
            <div className="absolute left-4 top-1/2 -translate-y-1/2">
              <button
                onClick={() => setSidebarOpen(true)}
                aria-label="Open control panel"
                className="w-9 h-9 rounded-lg bg-white/8 hover:bg-white/15 flex items-center justify-center transition-colors duration-150 cursor-pointer"
              >
                <Menu className="w-4 h-4 text-white" />
              </button>
            </div>

            {/* Center wordmark */}
            <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 flex items-center gap-2">
              <svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-4 h-4">
                <circle cx="8" cy="8" r="7.2" stroke="white" strokeOpacity="0.15" strokeWidth="1" />
                <circle cx="8" cy="2.5" r="1.5" fill="#4ade80" />
                <circle cx="13.5" cy="5.5" r="1.2" fill="#4ade80" fillOpacity="0.6" />
                <circle cx="13.5" cy="10.5" r="1.2" fill="#4ade80" fillOpacity="0.4" />
                <circle cx="8" cy="13.5" r="1.5" fill="#4ade80" fillOpacity="0.6" />
                <circle cx="2.5" cy="10.5" r="1.2" fill="#4ade80" fillOpacity="0.4" />
                <circle cx="2.5" cy="5.5" r="1.2" fill="#4ade80" fillOpacity="0.6" />
                <circle cx="8" cy="8" r="2" fill="#4ade80" />
              </svg>
              <span className="text-sm font-semibold tracking-wide text-white/90" style={{ fontFamily: 'var(--font-heading)' }}>
                orchestrate
              </span>
            </div>

            {/* Right */}
            <div className="absolute right-4 top-1/2 -translate-y-1/2 flex items-center gap-2">
              <NotificationsPopover onViewAll={onOpenNotifications} />
              <AnimatedThemeToggler className="w-9 h-9 rounded-lg bg-white/8 hover:bg-white/15 flex items-center justify-center transition-colors duration-150 cursor-pointer [&_svg]:w-4 [&_svg]:h-4 [&_svg]:text-white" />
              <AccountPopover />
              <button
                onClick={() => setActivityOpen((v) => !v)}
                aria-label="Toggle activity panel"
                className={cn(
                  "w-9 h-9 rounded-lg flex items-center justify-center transition-colors duration-150 cursor-pointer",
                  activityOpen ? "bg-white/20" : "bg-white/8 hover:bg-white/15"
                )}
              >
                <PanelRight className="w-4 h-4 text-white" />
              </button>
            </div>
          </div>

          {/* Status bar */}
          {(thinkingCount > 0 || blockedCount > 0) && (
            <div className="px-4 py-1.5 border-t border-white/[0.06] flex items-center gap-4">
              {thinkingCount > 0 && (
                <div className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
                  <span className="text-[11px] text-white/50">
                    {thinkingCount} agent{thinkingCount > 1 ? 's' : ''} thinking
                  </span>
                </div>
              )}
              {blockedCount > 0 && (
                <div className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-destructive" />
                  <span className="text-[11px] text-white/50">
                    {blockedCount} blocked
                  </span>
                </div>
              )}
            </div>
          )}
        </header>

        {/* Main — fills remaining viewport height */}
        <main
          className="px-8 py-5 relative z-[1] flex items-center justify-center"
          style={{ height: `calc(100vh - ${(thinkingCount > 0 || blockedCount > 0) ? 84 : 52}px)` }}
        >
          <div className="relative w-full max-w-5xl aspect-square max-h-[78vh] min-h-[520px]">
            {surroundingAgents.map((agent, index) => {
              const orbitStyle = orbitStyles[index];

              return (
                <div
                  key={agent.id}
                  className="absolute -translate-x-1/2 -translate-y-1/2"
                  style={orbitStyle}
                >
                  <div className="animate-orbit-wiggle" style={orbitMotionStyles[index]}>
                    <AgentCard
                      agent={agent}
                      onClick={() => handleAgentClick(agent)}
                      className="aspect-square w-[min(220px,20vw)]"
                      isPlanetMode={!isDark}
                    />
                  </div>
                </div>
              );
            })}

            <div
              className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
            >
              <div className="animate-orbit-wiggle" style={centerMotionStyle}>
                <AgentCard
                  agent={centerAgent}
                  onClick={() => handleAgentClick(centerAgent)}
                  className="aspect-square w-[min(228px,20.5vw)]"
                  isPlanetMode={!isDark}
                />
              </div>
            </div>
          </div>
        </main>
      </div>

      <ControlPanel open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <AgentChatPanel
        agent={selectedAgent}
        open={drawerOpen}
        onClose={handleCloseDrawer}
      />

      <RightActivityPanel
        open={activityOpen}
        onClose={() => setActivityOpen(false)}
      />
    </StarsBackground>
  );
}
