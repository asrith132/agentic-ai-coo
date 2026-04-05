export type AgentStatus = 'thinking' | 'done' | 'blocked' | 'idle';

export interface Agent {
  id: string;
  name: string;
  shortName: string;
  status: AgentStatus;
  outputs: string[];
  tasks: string[];
  risks: string[];
  dependencies: string[];
  recommendations: string[];
  summary: string;
}

export interface ActivityItem {
  id: string;
  agent: string;
  message: string;
  timestamp: string;
  type: 'info' | 'warning' | 'success';
}

export interface ProjectDetails {
  startupIdea: string;
  stage: string;
  targetUsers: string;
  monetization: string;
  timeline: string;
  repoUrl: string;
  techStack: string;
  constraints: string;
}

export const defaultProjectDetails: ProjectDetails = {
  startupIdea: '',
  stage: '',
  targetUsers: '',
  monetization: '',
  timeline: '',
  repoUrl: '',
  techStack: '',
  constraints: '',
};

export const agents: Agent[] = [
  {
    id: 'product-manager',
    name: 'Product Manager',
    shortName: 'PM',
    status: 'thinking',
    outputs: ['Prioritizing MVP features', 'User story mapping complete'],
    tasks: ['Define MVP scope', 'Create user personas', 'Prioritize backlog'],
    risks: ['Scope creep risk', 'User research incomplete'],
    dependencies: ['Research agent findings', 'Engineer estimates'],
    recommendations: ['Focus on core 3 features for launch', 'Schedule user interviews this week'],
    summary: 'Analyzing product requirements and defining the roadmap for your startup. Currently prioritizing features based on user impact and development effort.',
  },
  {
    id: 'engineer',
    name: 'Engineer',
    shortName: 'ENG',
    status: 'done',
    outputs: ['Architecture design ready', 'Estimates: 2-3 weeks for MVP'],
    tasks: ['Design system architecture', 'Set up CI/CD', 'Implement core features'],
    risks: ['Technical debt accumulation', 'Third-party API dependencies'],
    dependencies: ['PM feature priorities', 'Tech stack decisions'],
    recommendations: ['Start with Next.js + Supabase', 'Implement feature flags early'],
    summary: 'Technical architecture has been designed. Ready to begin implementation once PM finalizes feature priorities.',
  },
  {
    id: 'research',
    name: 'Research',
    shortName: 'RES',
    status: 'thinking',
    outputs: ['Competitor analysis: 5 direct competitors', 'Market size: $2.4B TAM'],
    tasks: ['Analyze competitors', 'Survey target users', 'Validate pricing model'],
    risks: ['Limited user access', 'Market data outdated'],
    dependencies: ['Target user definition'],
    recommendations: ['Interview 10 potential users', 'Focus on underserved segment'],
    summary: 'Conducting market research and competitive analysis. Initial findings suggest strong market opportunity with clear differentiation potential.',
  },
  {
    id: 'marketing',
    name: 'Marketing',
    shortName: 'MKT',
    status: 'idle',
    outputs: ['Positioning draft ready', 'Launch campaign outline prepared'],
    tasks: ['Refine messaging', 'Plan launch campaign', 'Define content calendar'],
    risks: ['Message-market fit still unproven', 'Budget constraints on paid acquisition'],
    dependencies: ['Product launch date', 'Pricing finalized'],
    recommendations: ['Start with founder-led distribution', 'Build a waitlist before launch'],
    summary: 'Preparing go-to-market messaging and launch planning. Waiting on product timing to lock campaign sequencing.',
  },
  {
    id: 'legal',
    name: 'Legal',
    shortName: 'LEG',
    status: 'done',
    outputs: ['Initial compliance checklist prepared', 'Terms and privacy draft outlined'],
    tasks: ['Review startup legal structure', 'Draft customer-facing policies', 'Identify compliance requirements'],
    risks: ['Missing privacy language', 'Contract templates not standardized'],
    dependencies: ['Business model details', 'Data handling decisions'],
    recommendations: ['Finalize privacy policy before launch', 'Standardize contractor and vendor agreements'],
    summary: 'Core legal groundwork has been outlined. Key launch documents and compliance requirements are now identified.',
  },
  {
    id: 'finance',
    name: 'Finance',
    shortName: 'FIN',
    status: 'blocked',
    outputs: ['Runway: 8 months', 'Burn rate warning: +$3k'],
    tasks: ['Create financial model', 'Plan fundraising timeline', 'Track expenses'],
    risks: ['Runway depleting faster than expected', 'Pricing not validated'],
    dependencies: ['Revenue projections', 'Hiring plan'],
    recommendations: ['Start fundraising conversations now', 'Reduce non-essential spend'],
    summary: 'Monitoring financial health. Blocked on revenue projections to complete the financial model.',
  },
  {
    id: 'outreach-agent',
    name: 'Outreach Agent',
    shortName: 'OUT',
    status: 'idle',
    outputs: ['Prospect list: 25 warm leads', 'Partnership outreach templates drafted'],
    tasks: ['Build target outreach list', 'Draft founder outreach messages', 'Sequence follow-up cadence'],
    risks: ['Low response rates', 'Unclear ICP targeting'],
    dependencies: ['Marketing positioning', 'Validated user segment'],
    recommendations: ['Start with founder network intros', 'Personalize top 10 outreach targets manually'],
    summary: 'Outbound motion is prepared. Waiting on tighter messaging and segment validation before scaling outreach.',
  },
  {
    id: 'dev-agent',
    name: 'Dev Activity',
    shortName: 'DEV',
    status: 'done',
    outputs: ['Commits parsed and summarized', 'Feature map updated'],
    tasks: ['Watch GitHub for new commits', 'Classify commits by type', 'Update feature map'],
    risks: ['Webhook not configured', 'Commit messages too vague to parse'],
    dependencies: ['GitHub webhook integration'],
    recommendations: ['Connect GitHub webhook to start tracking commits', 'Use conventional commits for better classification'],
    summary: 'Watches GitHub for code changes, interprets them in business terms, and broadcasts context updates to other agents.',
  },
];

export const cooData = {
  mission: 'Build and launch MVP in 4 weeks with validated product-market fit',
  priorities: [
    'Complete user research by end of week',
    'Finalize MVP feature set',
    'Begin engineering sprint',
  ],
  roadmap: [
    { phase: 'Week 1-2', milestone: 'Research & Planning', status: 'in-progress' },
    { phase: 'Week 3-4', milestone: 'MVP Development', status: 'upcoming' },
    { phase: 'Week 5', milestone: 'Beta Launch', status: 'upcoming' },
    { phase: 'Week 6+', milestone: 'Iterate & Scale', status: 'upcoming' },
  ],
};

export const commandCenterData = {
  topPriorities: [
    'Validate core value proposition with 5 user interviews',
    'Finalize tech stack decision (Next.js vs Remix)',
    'Set up development environment and CI/CD',
  ],
  criticalRisks: [
    'Runway is limited - 8 months at current burn',
    'No designer on team - may delay UI polish',
    'Competitor launching similar feature next month',
  ],
  nextActions: [
    'Review PM\'s feature prioritization matrix',
    'Approve engineering architecture proposal',
    'Review legal launch checklist',
  ],
};

export const activityFeed: ActivityItem[] = [
  {
    id: '1',
    agent: 'Product Manager',
    message: 'Proposed a feature simplification: merge onboarding and setup flows',
    timestamp: '2 min ago',
    type: 'info',
  },
  {
    id: '2',
    agent: 'Engineer',
    message: 'Estimates 2 weeks for core implementation, 1 week for polish',
    timestamp: '5 min ago',
    type: 'success',
  },
  {
    id: '3',
    agent: 'Finance',
    message: 'Warning: burn rate increases by $3k if we add contractor',
    timestamp: '12 min ago',
    type: 'warning',
  },
  {
    id: '4',
    agent: 'Research',
    message: 'Completed competitor pricing analysis - we can undercut by 20%',
    timestamp: '18 min ago',
    type: 'success',
  },
  {
    id: '5',
    agent: 'Marketing',
    message: 'Refined launch messaging around founder productivity and operator visibility',
    timestamp: '25 min ago',
    type: 'info',
  },
  {
    id: '6',
    agent: 'Legal',
    message: 'Drafted privacy policy requirements for the first production release',
    timestamp: '32 min ago',
    type: 'success',
  },
];

export const techStackItems = [
  { name: 'Next.js', category: 'Framework', detected: true },
  { name: 'TypeScript', category: 'Language', detected: true },
  { name: 'Tailwind CSS', category: 'Styling', detected: true },
  { name: 'Supabase', category: 'Database', detected: true },
  { name: 'Vercel', category: 'Hosting', detected: true },
  { name: 'Stripe', category: 'Payments', detected: false },
];

export const founderBrief = `Good morning! Here's your daily briefing:

**Progress:** Your team is on track for the Week 2 milestone. Product Manager has completed feature prioritization, and Engineering is ready to begin implementation.

**Attention Needed:** Finance has flagged a burn rate concern. Review spending assumptions before expanding tools or paid distribution.

**Today's Focus:** Approve the MVP feature set and kick off the first engineering sprint. Your Research and Marketing agents have fresh insights worth reviewing together.

**Wins:** Legal has outlined the first-pass compliance and policy checklist, reducing launch risk before customer onboarding begins.`;
