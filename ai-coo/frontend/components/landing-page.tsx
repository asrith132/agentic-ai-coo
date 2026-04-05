'use client';

import { useEffect, useState } from 'react';
import { Space_Grotesk, Inter } from 'next/font/google';
import { ArrowRight, Brain, Eye, Zap, BarChart3 } from 'lucide-react';

const spaceGrotesk = Space_Grotesk({
  subsets: ['latin'],
  variable: '--font-sg',
  weight: ['400', '500', '600', '700'],
});

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  weight: ['400', '500', '600'],
});
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { AnimatedThemeToggler } from '@/components/ui/animated-theme-toggler';
import { StarsBackground } from '@/components/ui/stars';

interface LandingPageProps {
  onGetStarted: () => void;
}

const tickerItems = [
  'Product Manager',
  'Engineer',
  'Research',
  'Marketing',
  'Legal',
  'Finance',
  'Outreach Agent',
  'Meeting Agent',
  '8 Agents in Parallel',
  'Context-Aware Planning',
  'Real-Time Visibility',
  'Launch Ready',
];

const stages = [
  { label: 'Idea', icon: '💡' },
  { label: 'MVP', icon: '🔧' },
  { label: 'Launch', icon: '🚀' },
  { label: 'Scale', icon: '📈' },
];

const agents = [
  { short: 'PM', name: 'Product', color: '#22c55e' },
  { short: 'ENG', name: 'Engineering', color: '#38bdf8' },
  { short: 'RES', name: 'Research', color: '#a78bfa' },
  { short: 'MKT', name: 'Marketing', color: '#fb923c' },
  { short: 'FIN', name: 'Finance', color: '#facc15' },
  { short: 'LEG', name: 'Legal', color: '#2dd4bf' },
  { short: 'OUT', name: 'Outreach', color: '#f472b6' },
  { short: 'MTG', name: 'Meetings', color: '#818cf8' },
];

const features = [
  {
    icon: Brain,
    title: 'Context-aware planning',
    desc: 'Each agent understands your startup stage, constraints, and goals — no generic advice.',
  },
  {
    icon: Eye,
    title: 'Real-time visibility',
    desc: 'Watch all 8 agents work in parallel. See exactly what each one is doing and why.',
  },
  {
    icon: Zap,
    title: 'Instant execution',
    desc: 'From idea to structured roadmap in minutes. Agents produce actionable outputs, not essays.',
  },
  {
    icon: BarChart3,
    title: 'Cross-functional sync',
    desc: 'Finance informs hiring, engineering informs timelines. All agents share context.',
  },
];

const faqs = [
  {
    q: 'What happens after I submit the intake form?',
    a: 'All 8 specialist agents activate in parallel. Within 90 seconds, each one produces a structured output specific to your startup — from a technical architecture proposal to a hiring plan.',
  },
  {
    q: 'Is this real AI or mock data?',
    a: 'The current version is a frontend demo with realistic mock data. The production version connects each agent to a language model with domain-specific instructions and tooling.',
  },
  {
    q: 'What stage does this work best for?',
    a: 'Orchestrate works at every stage — from raw idea validation to post-launch scaling. The agents adapt their outputs based on the stage you select in the intake form.',
  },
  {
    q: 'Can I use this for an existing company?',
    a: 'Yes. Enter your current state in the intake form (stage, tech stack, constraints) and the agents will tailor their analysis to where you are now, not where you\'re starting.',
  },
  {
    q: 'How is this different from ChatGPT?',
    a: 'Instead of one general-purpose model, Orchestrate uses 8 specialist agents that work simultaneously and share context with each other. The output is structured, cross-functional, and startup-specific.',
  },
];

export function LandingPage({ onGetStarted }: LandingPageProps) {
  const [isDark, setIsDark] = useState(true);

  useEffect(() => {
    const el = document.documentElement;
    const update = () => setIsDark(el.classList.contains('dark'));
    update();
    const observer = new MutationObserver(update);
    observer.observe(el, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);

  return (
    <div className={`${spaceGrotesk.variable} ${inter.variable} min-h-screen text-foreground overflow-x-hidden`}
      style={{ fontFamily: 'var(--font-inter)' }}
    >

      {/* Fixed star background — stays pinned while content scrolls */}
      <div className="fixed inset-0 -z-10 pointer-events-none overflow-hidden">
        <StarsBackground
          variant={isDark ? 'dark' : 'light'}
          speed={isDark ? 55 : 85}
          className="w-full h-full"
        />
      </div>

      {/* ── Nav ── */}
      <nav className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-4 border-b border-border/20 bg-background/5 backdrop-blur-xl">
        <div className="flex items-center gap-2">
          {/* Logo mark */}
          <svg viewBox="0 0 24 24" fill="none" className="w-6 h-6" aria-hidden="true">
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.2" strokeWidth="1.5" />
            <circle cx="12" cy="4.5" r="1.8" className="fill-primary" />
            <circle cx="18.2" cy="8.2" r="1.8" className="fill-primary/60" />
            <circle cx="18.2" cy="15.8" r="1.8" className="fill-primary/40" />
            <circle cx="12" cy="19.5" r="1.8" className="fill-primary/60" />
            <circle cx="5.8" cy="15.8" r="1.8" className="fill-primary/40" />
            <circle cx="5.8" cy="8.2" r="1.8" className="fill-primary/60" />
            <circle cx="12" cy="12" r="3" className="fill-primary" />
          </svg>
          <span className="font-semibold text-sm tracking-tight" style={{ fontFamily: 'var(--font-sg)' }}>
            orchestrate
          </span>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={onGetStarted}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
          >
            Sign in
          </button>
          <AnimatedThemeToggler className="w-8 h-8 flex items-center justify-center rounded-lg border border-border/60 bg-secondary/50 text-muted-foreground hover:text-foreground hover:border-border hover:bg-secondary transition-all duration-150 cursor-pointer" />
          <button
            onClick={onGetStarted}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:bg-primary/90 transition-colors cursor-pointer"
          >
            Get started
            <ArrowRight className="w-3 h-3" />
          </button>
        </div>
      </nav>

      {/* ── Hero ── */}
      <section className="relative pt-32 pb-44 px-6 overflow-hidden">
        {/* Grid background — dark mode only */}
        {isDark && (
          <div
            className="absolute inset-0 opacity-[0.25] pointer-events-none"
            style={{
              backgroundImage: `linear-gradient(to right, oklch(0.20 0.014 262) 1px, transparent 1px), linear-gradient(to bottom, oklch(0.20 0.014 262) 1px, transparent 1px)`,
              backgroundSize: '4rem 4rem',
            }}
          />
        )}
        {/* Grid fade */}
        <div className="absolute inset-0 bg-gradient-to-b from-background/0 via-background/60 to-background pointer-events-none" />

        <div className="relative max-w-4xl mx-auto text-center">
          {/* Badge */}
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-primary/30 bg-primary/8 mb-6">
            <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
            <span className="text-xs font-medium text-primary tracking-wide">8 AI agents · working in parallel</span>
          </div>

          {/* Headline */}
          <h1
            className="text-5xl sm:text-6xl lg:text-7xl font-bold leading-[1.05] tracking-tight mb-6"
            style={{ fontFamily: 'var(--font-sg)' }}
          >
            Your startup's
            <br />
            <span className="text-primary">operating system</span>
          </h1>

          <p className="text-lg text-muted-foreground max-w-xl mx-auto mb-10 leading-relaxed">
            Describe your idea. Eight specialist AI agents — product, engineering, finance, marketing, legal, and more — build your entire operating plan in under two minutes.
          </p>

          {/* CTAs */}
          <div className="flex items-center justify-center gap-3 flex-wrap">
            <button
              onClick={onGetStarted}
              className="flex items-center gap-2 px-6 py-3 rounded-xl bg-primary text-primary-foreground font-semibold text-sm hover:bg-primary/90 transition-all duration-200 hover:shadow-lg hover:shadow-primary/25 hover:-translate-y-0.5 cursor-pointer"
            >
              Start building
              <ArrowRight className="w-4 h-4" />
            </button>
            <button
              onClick={onGetStarted}
              className="flex items-center gap-2 px-6 py-3 rounded-xl border border-border bg-card/50 text-foreground/80 font-medium text-sm hover:border-primary/40 hover:text-foreground hover:bg-card transition-all duration-200 cursor-pointer"
            >
              See a demo
            </button>
          </div>

          {/* Stage pills */}
          <div className="flex items-center justify-center gap-2 mt-10 flex-wrap">
            <span className="text-xs text-muted-foreground/60 mr-1">Works at every stage:</span>
            {stages.map((s) => (
              <span
                key={s.label}
                className="px-2.5 py-1 rounded-full border border-border/60 bg-secondary/50 text-xs text-muted-foreground"
              >
                {s.label}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* ── Ticker ── */}
      <div
        className="relative w-full overflow-hidden py-4"
        style={isDark ? {
          background: 'rgba(255,255,255,0.06)',
          backdropFilter: 'blur(16px) saturate(160%)',
          WebkitBackdropFilter: 'blur(16px) saturate(160%)',
          borderTop: '1px solid rgba(255,255,255,0.10)',
          borderBottom: '1px solid rgba(255,255,255,0.05)',
        } : {
          background: 'rgba(0,0,0,0.07)',
          backdropFilter: 'blur(16px) saturate(160%)',
          WebkitBackdropFilter: 'blur(16px) saturate(160%)',
          borderTop: '1px solid rgba(0,0,0,0.10)',
          borderBottom: '1px solid rgba(0,0,0,0.06)',
        }}
      >
        {/* Inner top highlight */}
        <div
          className="absolute inset-x-0 top-0 h-1/2 pointer-events-none"
          style={{ background: isDark
            ? 'linear-gradient(to bottom, rgba(255,255,255,0.05), transparent)'
            : 'linear-gradient(to bottom, rgba(255,255,255,0.30), transparent)'
          }}
        />
        <div
          className="relative"
          style={{
            maskImage: 'linear-gradient(to right, transparent 0%, black 8%, black 92%, transparent 100%)',
            WebkitMaskImage: 'linear-gradient(to right, transparent 0%, black 8%, black 92%, transparent 100%)',
          }}
        >
          <div
            className="flex items-center animate-marquee-forward"
            style={{ '--marquee-duration': '32s', width: 'max-content' } as React.CSSProperties}
          >
            {[...tickerItems, ...tickerItems, ...tickerItems].map((item, i) => (
              <span key={i} className="flex items-center gap-5 px-5 shrink-0">
                <span className="text-sm font-medium whitespace-nowrap tracking-wide" style={{ color: isDark ? 'rgba(255,255,255,0.70)' : 'rgba(0,0,0,0.60)', fontFamily: 'var(--font-sg)' }}>
                  {item}
                </span>
                <span className="text-[10px]" style={{ color: isDark ? 'rgba(255,255,255,0.18)' : 'rgba(0,0,0,0.20)' }}>◆</span>
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* ── How it works ── */}
      <section className="px-6 pt-20 pb-24 max-w-5xl mx-auto">
        <div className="text-center mb-12">
          <p className="text-xs font-semibold text-primary tracking-widest uppercase mb-3">How it works</p>
          <h2 className="text-3xl font-bold" style={{ fontFamily: 'var(--font-sg)' }}>
            From idea to operating plan in 3 steps
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {/* Step 01 */}
          <div className="rounded-2xl border border-border/60 bg-card/60 overflow-hidden">
            <div className="p-5 pb-0">
              <span className="text-4xl font-bold text-border/50" style={{ fontFamily: 'var(--font-sg)' }}>01</span>
              <h3 className="text-base font-semibold mt-2 mb-1" style={{ fontFamily: 'var(--font-sg)' }}>Describe your startup</h3>
              <p className="text-xs text-muted-foreground leading-relaxed">Fill out a quick intake — your idea, stage, timeline, and constraints.</p>
            </div>
            {/* Mini form mockup */}
            <div className="mx-4 mt-4 mb-5 rounded-xl border border-border/50 bg-background/60 p-3 space-y-2">
              {['Startup idea', 'Current stage', 'Tech stack'].map((label) => (
                <div key={label}>
                  <div className="text-[9px] text-muted-foreground/60 uppercase tracking-wider mb-0.5">{label}</div>
                  <div className="h-5 rounded-md bg-secondary/60 border border-border/40" />
                </div>
              ))}
              <div className="pt-1">
                <div className="h-6 rounded-lg bg-primary/20 border border-primary/30 flex items-center justify-center">
                  <div className="w-12 h-1.5 rounded-full bg-primary/40" />
                </div>
              </div>
            </div>
          </div>

          {/* Step 02 */}
          <div className="rounded-2xl border border-border/60 bg-card/60 overflow-hidden">
            <div className="p-5 pb-0">
              <span className="text-4xl font-bold text-border/50" style={{ fontFamily: 'var(--font-sg)' }}>02</span>
              <h3 className="text-base font-semibold mt-2 mb-1" style={{ fontFamily: 'var(--font-sg)' }}>Agents activate in parallel</h3>
              <p className="text-xs text-muted-foreground leading-relaxed">Eight specialists spin up simultaneously — each focused on their domain.</p>
            </div>
            {/* Mini agent grid mockup */}
            <div className="mx-4 mt-4 mb-5 rounded-xl border border-border/50 bg-background/60 p-3">
              <div className="grid grid-cols-3 gap-1.5">
                {agents.slice(0, 9).map((a, i) => (
                  <div
                    key={i}
                    className="h-7 rounded-md border flex items-center justify-center text-[8px] font-bold font-mono"
                    style={{
                      borderColor: i === 4 ? a.color + '60' : 'oklch(0.20 0.014 262)',
                      background: i === 4 ? a.color + '15' : 'oklch(0.09 0.012 262)',
                      color: i === 4 ? a.color : 'oklch(0.56 0.018 260)',
                    }}
                  >
                    {i === 4 ? '●' : agents[i % agents.length].short}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Step 03 */}
          <div className="rounded-2xl border border-border/60 bg-card/60 overflow-hidden">
            <div className="p-5 pb-0">
              <span className="text-4xl font-bold text-border/50" style={{ fontFamily: 'var(--font-sg)' }}>03</span>
              <h3 className="text-base font-semibold mt-2 mb-1" style={{ fontFamily: 'var(--font-sg)' }}>Review your operating plan</h3>
              <p className="text-xs text-muted-foreground leading-relaxed">Explore each agent's output — tasks, risks, and decisions, all structured.</p>
            </div>
            {/* Mini output cards mockup */}
            <div className="mx-4 mt-4 mb-5 space-y-1.5">
              {[
                { label: 'PM', color: '#22c55e', text: 'MVP scope · 12 features' },
                { label: 'ENG', color: '#38bdf8', text: 'Architecture · Next.js' },
                { label: 'FIN', color: '#facc15', text: 'Runway · 8 months' },
              ].map((item) => (
                <div
                  key={item.label}
                  className="flex items-center gap-2 rounded-lg border border-border/40 bg-background/60 px-2.5 py-1.5"
                >
                  <span
                    className="text-[8px] font-bold font-mono px-1 py-0.5 rounded"
                    style={{ background: item.color + '20', color: item.color }}
                  >
                    {item.label}
                  </span>
                  <span className="text-[9px] text-muted-foreground truncate">{item.text}</span>
                  <span className="ml-auto w-1.5 h-1.5 rounded-full bg-success shrink-0" />
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── Features ── */}
      <section className="px-6 pb-24 max-w-5xl mx-auto">
        <div className="text-center mb-12">
          <p className="text-xs font-semibold text-primary tracking-widest uppercase mb-3">Features</p>
          <h2 className="text-3xl font-bold" style={{ fontFamily: 'var(--font-sg)' }}>
            Built for founders who move fast
          </h2>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {features.map((f) => (
            <div
              key={f.title}
              className="flex gap-4 p-5 rounded-2xl border border-border/60 bg-card/40 hover:border-primary/30 hover:bg-card/70 transition-all duration-200"
            >
              <div className="w-9 h-9 rounded-lg bg-primary/10 border border-primary/25 flex items-center justify-center shrink-0">
                <f.icon className="w-4.5 h-4.5 text-primary" />
              </div>
              <div>
                <h3 className="text-sm font-semibold mb-1" style={{ fontFamily: 'var(--font-sg)' }}>{f.title}</h3>
                <p className="text-xs text-muted-foreground leading-relaxed">{f.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Agent roster ── */}
      <section className="px-6 pb-24 max-w-5xl mx-auto">
        <div className="text-center mb-10">
          <p className="text-xs font-semibold text-primary tracking-widest uppercase mb-3">The team</p>
          <h2 className="text-3xl font-bold" style={{ fontFamily: 'var(--font-sg)' }}>
            8 specialists. One shared mission.
          </h2>
          <p className="text-sm text-muted-foreground mt-3 max-w-md mx-auto">
            Every agent is purpose-built for its domain, trained on startup-specific knowledge, and shares context with all others.
          </p>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {agents.map((a) => (
            <div
              key={a.short}
              className="flex items-center gap-3 p-3.5 rounded-xl border border-border/50 bg-card/50 hover:border-border hover:bg-card transition-all duration-150"
            >
              <div
                className="w-8 h-8 rounded-lg flex items-center justify-center text-[10px] font-bold font-mono shrink-0"
                style={{ background: a.color + '18', border: `1px solid ${a.color}40`, color: a.color }}
              >
                {a.short}
              </div>
              <div>
                <p className="text-xs font-semibold" style={{ fontFamily: 'var(--font-sg)' }}>{a.name}</p>
                <p className="text-[10px] text-muted-foreground">Agent</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── FAQ ── */}
      <section className="px-6 pb-24 max-w-3xl mx-auto">
        <div className="text-center mb-10">
          <p className="text-xs font-semibold text-primary tracking-widest uppercase mb-3">FAQ</p>
          <h2 className="text-3xl font-bold" style={{ fontFamily: 'var(--font-sg)' }}>
            Common questions
          </h2>
        </div>

        <Accordion type="single" collapsible className="space-y-2">
          {faqs.map((faq, i) => (
            <AccordionItem
              key={i}
              value={`faq-${i}`}
              className="border border-border/50 rounded-xl px-5 bg-card/40 hover:bg-card/60 transition-colors"
            >
              <AccordionTrigger className="text-sm font-medium py-4 hover:no-underline text-left">
                {faq.q}
              </AccordionTrigger>
              <AccordionContent className="text-xs text-muted-foreground leading-relaxed pb-4">
                {faq.a}
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </section>

      {/* ── CTA ── */}
      <section className="px-6 pb-24">
        <div className="max-w-2xl mx-auto text-center rounded-2xl border border-primary/20 bg-gradient-to-b from-primary/8 to-primary/3 p-12">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-primary/30 bg-primary/10 mb-6">
            <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
            <span className="text-xs font-medium text-primary">Free to try · No signup required</span>
          </div>
          <h2
            className="text-3xl font-bold mb-4"
            style={{ fontFamily: 'var(--font-sg)' }}
          >
            Ready to build smarter?
          </h2>
          <p className="text-sm text-muted-foreground mb-8 leading-relaxed">
            Describe your idea and watch 8 AI agents produce your complete operating plan.
          </p>
          <button
            onClick={onGetStarted}
            className="inline-flex items-center gap-2 px-8 py-3.5 rounded-xl bg-primary text-primary-foreground font-semibold text-sm hover:bg-primary/90 transition-all duration-200 hover:shadow-xl hover:shadow-primary/30 hover:-translate-y-0.5 cursor-pointer"
          >
            Start building now
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-border/40 px-6 py-10">
        <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-start justify-between gap-8">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5" aria-hidden="true">
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.2" strokeWidth="1.5" />
                <circle cx="12" cy="4.5" r="1.8" className="fill-primary" />
                <circle cx="18.2" cy="8.2" r="1.8" className="fill-primary/60" />
                <circle cx="12" cy="12" r="3" className="fill-primary" />
                <circle cx="5.8" cy="8.2" r="1.8" className="fill-primary/60" />
              </svg>
              <span className="font-semibold text-sm" style={{ fontFamily: 'var(--font-sg)' }}>orchestrate</span>
            </div>
            <p className="text-xs text-muted-foreground max-w-[200px] leading-relaxed">
              The AI-powered operating system for startups.
            </p>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-8 text-xs">
            <div className="space-y-2">
              <p className="font-semibold text-foreground/80 mb-3" style={{ fontFamily: 'var(--font-sg)' }}>Product</p>
              {['How it works', 'Agents', 'Pricing', 'Changelog'].map((l) => (
                <p key={l} className="text-muted-foreground hover:text-foreground transition-colors cursor-pointer">{l}</p>
              ))}
            </div>
            <div className="space-y-2">
              <p className="font-semibold text-foreground/80 mb-3" style={{ fontFamily: 'var(--font-sg)' }}>Company</p>
              {['About', 'Blog', 'Careers', 'Contact'].map((l) => (
                <p key={l} className="text-muted-foreground hover:text-foreground transition-colors cursor-pointer">{l}</p>
              ))}
            </div>
            <div className="space-y-2">
              <p className="font-semibold text-foreground/80 mb-3" style={{ fontFamily: 'var(--font-sg)' }}>Legal</p>
              {['Privacy', 'Terms', 'Security'].map((l) => (
                <p key={l} className="text-muted-foreground hover:text-foreground transition-colors cursor-pointer">{l}</p>
              ))}
            </div>
          </div>
        </div>
        <div className="max-w-5xl mx-auto mt-8 pt-6 border-t border-border/30 flex items-center justify-between">
          <p className="text-xs text-muted-foreground/50">© 2024 Orchestrate. All rights reserved.</p>
          <p className="text-xs text-muted-foreground/50">Built with AI</p>
        </div>
      </footer>

    </div>
  );
}
