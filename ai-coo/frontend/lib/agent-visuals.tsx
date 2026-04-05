import type { LucideProps } from 'lucide-react'
import {
  BriefcaseBusiness,
  Gavel,
  GitCommit,
  LineChart,
  Megaphone,
  Search,
  Send,
  Wrench,
} from 'lucide-react'

const agentIcons = {
  'product-manager': BriefcaseBusiness,
  engineer: Wrench,
  research: Search,
  marketing: Megaphone,
  legal: Gavel,
  finance: LineChart,
  'outreach-agent': Send,
  'dev-agent': GitCommit,
} as const

export const agentColors: Record<string, string> = {
  'product-manager': '#86EFAC',
  engineer: '#93C5FD',
  research: '#C4B5FD',
  marketing: '#FDBA74',
  legal: '#5EEAD4',
  finance: '#F87171',
  'outreach-agent': '#F9A8D4',
  'dev-agent': '#A5B4FC',
}

export function AgentIcon({
  agentId,
  className,
  ...props
}: LucideProps & { agentId: string }) {
  const Icon = agentIcons[agentId as keyof typeof agentIcons] ?? BriefcaseBusiness
  return <Icon className={className} {...props} />
}
