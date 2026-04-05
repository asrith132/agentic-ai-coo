'use client'

import { useCallback, useEffect, useState } from 'react'

import { API_BASE } from '@/lib/api/config'

type GlobalContextResponse = {
  company_profile?: {
    name?: string
    description?: string
    product_name?: string
    product_description?: string
    key_features?: string[]
    tech_stack?: string[]
    entity_type?: string
    jurisdiction?: string
  }
  target_customer?: {
    persona?: string
    industry?: string
    pain_points?: string[]
  }
  business_state?: {
    phase?: string
    active_priorities?: string[]
    runway_months?: number | null
    monthly_burn?: number | null
    team_size?: number
  }
  brand_voice?: {
    tone?: string
    personality_traits?: string[]
  }
  competitive_landscape?: {
    market_position?: string
    competitors?: Array<{ name?: string; position?: string }>
  }
}

export type TechStackItem = {
  name: string
  category: string
  detected: boolean
}

function classifyTech(name: string) {
  const normalized = name.toLowerCase()
  if (normalized.includes('next')) return 'Framework'
  if (normalized.includes('react')) return 'Frontend'
  if (normalized.includes('typescript') || normalized.includes('python')) return 'Language'
  if (normalized.includes('tailwind')) return 'Styling'
  if (normalized.includes('fastapi')) return 'Backend'
  if (normalized.includes('supabase') || normalized.includes('postgres')) return 'Database'
  if (normalized.includes('celery') || normalized.includes('redis')) return 'Infrastructure'
  if (normalized.includes('vercel')) return 'Hosting'
  return 'Tooling'
}

async function getGlobalContext(): Promise<GlobalContextResponse> {
  const res = await fetch(`${API_BASE}/api/context/global`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<GlobalContextResponse>
}

export function useLiveContext() {
  const [context, setContext] = useState<GlobalContextResponse | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const next = await getGlobalContext()
      setContext(next)
    } catch {
      setContext(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  return { context, loading, refresh }
}

export function deriveTechStack(context: GlobalContextResponse | null): TechStackItem[] {
  const stack = context?.company_profile?.tech_stack ?? []
  return stack.map((name) => ({
    name,
    category: classifyTech(name),
    detected: true,
  }))
}

export function deriveFounderBrief(context: GlobalContextResponse | null, input: {
  topPriorities: string[]
  criticalRisks: string[]
  nextActions: string[]
}) {
  const company = context?.company_profile?.name || context?.company_profile?.product_name || 'your company'
  const phase = context?.business_state?.phase ? context.business_state.phase.replace(/_/g, ' ') : 'current phase'
  const persona = context?.target_customer?.persona || 'target users'
  const runway = context?.business_state?.runway_months

  const lines = [
    `Good morning. Here's the latest brief for ${company}.`,
    '',
    `**Progress:** Operating in ${phase} for ${persona}. ${input.topPriorities[0] ?? 'No priority set yet.'}`,
    '',
    `**Attention Needed:** ${input.criticalRisks[0] ?? 'No critical blockers detected.'}${runway ? ` Runway currently modeled at ${runway} months.` : ''}`,
    '',
    `**Today's Focus:** ${input.nextActions[0] ?? 'Review the latest agent updates.'}`,
  ]

  return lines.join('\n')
}
