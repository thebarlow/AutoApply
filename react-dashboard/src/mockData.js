export const inboxJobs = [
  { id: 1, title: 'Frontend Engineer', company: 'Stripe', dateAdded: '2026-05-18' },
  { id: 2, title: 'React Developer', company: 'Vercel', dateAdded: '2026-05-17' },
  { id: 3, title: 'UI Engineer', company: 'Linear', dateAdded: '2026-05-17' },
  { id: 4, title: 'Software Engineer', company: 'Notion', dateAdded: '2026-05-16' },
  { id: 5, title: 'Product Engineer', company: 'Loom', dateAdded: '2026-05-15' },
]

export const processingJobs = [
  { id: 6, title: 'Full Stack Developer', company: 'Retool', stage: 'Scoring' },
  { id: 7, title: 'TypeScript Engineer', company: 'Prisma', stage: 'Generating' },
  { id: 8, title: 'Staff Engineer', company: 'PlanetScale', stage: 'Scoring' },
]

export const outboxJobs = [
  { id: 9, title: 'Backend Engineer', company: 'Supabase', outcome: 'Applied' },
  { id: 10, title: 'DevOps Engineer', company: 'Railway', outcome: 'Skipped' },
  { id: 11, title: 'Python Developer', company: 'Prefect', outcome: 'Applied' },
]

export const stats = {
  totalJobs: 47,
  applied: 11,
  successRate: '23%',
  creditsUsed: '$2.84',
}

export const settings = {
  resumePath: '~/auto_apply/resumes/matthew_barlow.pdf',
  targetRoles: 'Frontend Engineer, React Developer, UI Engineer',
  locationPreference: 'Remote',
  modelInUse: 'claude-sonnet-4-6',
}
