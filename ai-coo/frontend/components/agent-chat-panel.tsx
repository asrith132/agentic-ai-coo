'use client';

import { useState, useRef, useEffect } from 'react';
import { ArrowLeft, Send } from 'lucide-react';
import { Agent, AgentStatus } from '@/lib/mock-data';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { AgentIcon, agentColors } from '@/lib/agent-visuals';
import { LegalAgentSidebar } from '@/components/legal-agent-sidebar';
import { OutreachAgentSidebar } from '@/components/outreach-agent-sidebar';

interface AgentChatPanelProps {
  agent: Agent | null;
  open: boolean;
  onClose: () => void;
}

interface Message {
  id: string;
  role: 'user' | 'agent';
  content: string;
}

function hexToRgb(hex: string) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `${r},${g},${b}`;
}

const statusConfig: Record<AgentStatus, { label: string; badgeClass: string; dotClass: string }> = {
  thinking: { label: 'Thinking', badgeClass: 'bg-primary/10 text-primary border-primary/25', dotClass: 'bg-primary animate-pulse' },
  done:     { label: 'Done',     badgeClass: 'bg-success/10 text-success border-success/25', dotClass: 'bg-success' },
  blocked:  { label: 'Blocked',  badgeClass: 'bg-destructive/10 text-destructive border-destructive/25', dotClass: 'bg-destructive' },
  idle:     { label: 'Idle',     badgeClass: 'bg-muted text-muted-foreground border-border/60', dotClass: 'bg-muted-foreground/50' },
};

function getInitialMessages(agent: Agent): Message[] {
  const statusIntro: Record<AgentStatus, string> = {
    thinking: `I'm currently working through some things. ${agent.tasks[0] ? `Right now I'm focused on: ${agent.tasks[0].toLowerCase()}.` : ''} How can I help?`,
    done:     `I've wrapped up my current workload. ${agent.outputs[0] ? `Latest: ${agent.outputs[0].toLowerCase()}.` : ''} What do you need?`,
    blocked:  `I'm blocked and need your input to move forward. ${agent.risks[0] ? `Key concern: ${agent.risks[0].toLowerCase()}.` : ''} Can we talk through this?`,
    idle:     `I'm standing by. ${agent.recommendations[0] ? `One thing worth noting: ${agent.recommendations[0].toLowerCase()}.` : ''} What would you like to work on?`,
  };

  return [
    {
      id: '1',
      role: 'agent',
      content: `Hey! I'm your ${agent.name}. ${agent.summary}`,
    },
    {
      id: '2',
      role: 'agent',
      content: statusIntro[agent.status],
    },
  ];
}

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

export function AgentChatPanel({ agent, open, onClose }: AgentChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (agent && open) {
      setMessages(getInitialMessages(agent));
      setInput('');
    }
  }, [agent?.id, open]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || !agent) return;

    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: text };
    setMessages(prev => [...prev, userMsg]);
    setInput('');

    // Simulated agent reply
    setTimeout(() => {
      const replies = [
        `Got it. I'll factor that into my current work on ${agent.tasks[0]?.toLowerCase() ?? 'my tasks'}.`,
        `Noted. Based on what I know, ${agent.recommendations[0]?.toLowerCase() ?? 'I recommend we revisit this soon'}.`,
        `That's helpful context. My main concern right now is ${agent.risks[0]?.toLowerCase() ?? 'keeping things on track'}.`,
        `Understood. I'll update my output and flag any blockers as I go.`,
      ];
      const reply = replies[Math.floor(Math.random() * replies.length)];
      setMessages(prev => [...prev, { id: Date.now().toString(), role: 'agent', content: reply }]);
    }, 800);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (!agent) return null;

  const color = agentColors[agent.id] ?? '#94A3B8';
  const rgb = hexToRgb(color);
  const status = statusConfig[agent.status];
  const detailWidth =
    agent.id === 'outreach-agent' ? 'min(520px, 42vw)' :
    agent.id === 'legal' ? 'min(460px, 38vw)' :
    '380px';
  const chatWidth =
    agent.id === 'outreach-agent' ? 'calc(100% - min(520px, 42vw))' :
    agent.id === 'legal' ? 'calc(100% - min(460px, 38vw))' :
    'auto';

  return (
    <div
      className={cn(
        'fixed inset-0 z-50 flex transition-all duration-300',
        open ? 'opacity-100' : 'opacity-0 pointer-events-none',
      )}
      style={{ background: 'var(--background)' }}
    >
        {/* ── LEFT: Chat ── */}
        <div className="flex flex-col min-w-0 border-r border-border/40" style={{ width: chatWidth, flex: chatWidth === 'auto' ? 1 : undefined }}>

          {/* Left header — back arrow + agent info */}
          <div className="shrink-0 flex items-center gap-3 px-4 h-13 border-b border-border/40">
            <button
              onClick={onClose}
              className="w-9 h-9 rounded-lg bg-secondary/50 hover:bg-secondary flex items-center justify-center transition-colors duration-150 cursor-pointer shrink-0"
              aria-label="Back to dashboard"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div
              className="w-7 h-7 rounded-lg flex items-center justify-center text-[10px] font-bold font-mono shrink-0"
              style={{
                background: `rgba(${rgb},0.12)`,
                border: `1px solid rgba(${rgb},0.30)`,
                color: color,
              }}
            >
              <AgentIcon agentId={agent.id} className="w-3.5 h-3.5" strokeWidth={2.1} />
            </div>
            <div className="min-w-0">
              <span className="text-sm font-semibold text-foreground/90 leading-none" style={{ fontFamily: 'var(--font-heading)' }}>
                {agent.name}
              </span>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className={cn('w-1.5 h-1.5 rounded-full shrink-0', status.dotClass)} />
                <span className="text-[10px] text-muted-foreground">{status.label}</span>
              </div>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 min-h-0 overflow-y-auto px-6 py-5 space-y-4">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={cn(
                  'flex gap-2.5 max-w-[80%]',
                  msg.role === 'user' ? 'ml-auto flex-row-reverse' : '',
                )}
              >
                {/* Avatar */}
                {msg.role === 'agent' && (
                  <div
                    className="w-7 h-7 rounded-lg flex items-center justify-center text-[9px] font-bold font-mono shrink-0 mt-0.5"
                    style={{
                      background: `rgba(${rgb},0.12)`,
                      border: `1px solid rgba(${rgb},0.25)`,
                      color: color,
                    }}
                  >
                    <AgentIcon agentId={agent.id} className="w-3.5 h-3.5" strokeWidth={2.1} />
                  </div>
                )}

                {/* Bubble */}
                <div
                  className={cn(
                    'rounded-2xl px-4 py-2.5 text-sm leading-relaxed',
                    msg.role === 'agent'
                      ? 'rounded-tl-sm bg-secondary/60 text-foreground/85 border border-border/40'
                      : 'rounded-tr-sm text-foreground/95',
                  )}
                  style={
                    msg.role === 'user'
                      ? { background: `rgba(${rgb},0.15)`, border: `1px solid rgba(${rgb},0.25)` }
                      : undefined
                  }
                >
                  {msg.content}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="shrink-0 px-6 py-4 border-t border-border/40">
            <div
              className="flex items-end gap-3 rounded-2xl px-4 py-3 border"
              style={{
                background: 'var(--card-glass-bg)',
                borderColor: `rgba(${rgb},0.22)`,
              }}
            >
              <textarea
                ref={inputRef}
                rows={1}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={`Message ${agent.name}…`}
                className="flex-1 bg-transparent resize-none text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none leading-relaxed max-h-32 min-h-[1.4rem]"
                style={{ fontFamily: 'var(--font-sans)' }}
              />
              <button
                onClick={handleSend}
                disabled={!input.trim()}
                className="w-8 h-8 rounded-xl flex items-center justify-center shrink-0 transition-all duration-150 cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
                style={{
                  background: input.trim() ? `rgba(${rgb},0.20)` : 'transparent',
                  border: `1px solid rgba(${rgb},0.30)`,
                  color: color,
                }}
                aria-label="Send message"
              >
                <Send className="w-3.5 h-3.5" />
              </button>
            </div>
            <p className="text-[10px] text-muted-foreground/40 mt-2 text-center">
              Enter to send · Shift+Enter for newline
            </p>
          </div>
        </div>

      {/* ── RIGHT: Detail ── */}
      <div
        className="shrink-0 flex flex-col overflow-hidden"
        style={{ background: 'var(--card-glass-bg)', width: detailWidth }}
      >
          {/* Detail header */}
          <div
            className="shrink-0 px-5 py-4 border-b border-border/40"
            style={{
              background: `linear-gradient(180deg, rgba(${rgb},0.06) 0%, transparent 100%)`,
            }}
          >
            <div
              className="absolute top-0 left-0 right-0 h-px"
              style={{
                background: `linear-gradient(to right, transparent, rgba(${rgb},0.5) 40%, rgba(${rgb},0.5) 60%, transparent)`,
              }}
            />
            <div className="flex items-center gap-3">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center text-xs font-bold font-mono shrink-0"
                style={{
                  background: `rgba(${rgb},0.12)`,
                  border: `1px solid rgba(${rgb},0.28)`,
                  color: color,
                }}
              >
                <AgentIcon agentId={agent.id} className="w-5 h-5" strokeWidth={2.1} />
              </div>
              <div className="min-w-0">
                <p className="font-semibold text-sm text-foreground/90 leading-tight" style={{ fontFamily: 'var(--font-heading)' }}>
                  {agent.name}
                </p>
                <Badge
                  variant="outline"
                  className={cn('text-[10px] font-normal mt-1 gap-1.5', status.badgeClass)}
                >
                  <span className={cn('w-1.5 h-1.5 rounded-full', status.dotClass)} />
                  {status.label}
                </Badge>
              </div>
            </div>
          </div>

          {/* Detail sections — legal agent gets live data, others get mock */}
          {agent.id === 'legal' ? (
            <LegalAgentSidebar rgb={rgb} color={color} />
          ) : agent.id === 'outreach-agent' ? (
            <OutreachAgentSidebar rgb={rgb} color={color} />
          ) : (
            <div className="flex-1 overflow-y-auto p-5 space-y-5">
              <Section title="Summary">
                <p className="text-sm text-muted-foreground leading-relaxed">{agent.summary}</p>
              </Section>

              <Separator className="bg-border/40" />

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

              <Section title="Recommendations">
                <ul className="space-y-2">
                  {agent.recommendations.map((rec, i) => (
                    <li key={i} className="flex items-start gap-2.5 text-sm">
                      <span
                        className="w-5 h-5 rounded-md flex items-center justify-center shrink-0 mt-0.5"
                        style={{
                          background: `rgba(${rgb},0.08)`,
                          border: `1px solid rgba(${rgb},0.20)`,
                        }}
                      >
                        <div className="w-1.5 h-1.5 rounded-full" style={{ background: `rgba(${rgb},0.70)` }} />
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
          )}
        </div>
    </div>
  );
}
