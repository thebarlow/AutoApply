export const users = [
  { id: 1, fullName: 'Matthew Barlow', email: 'barlowmatt96@gmail.com' },
]

export let activeUserId = 1

export const inboxJobs = [
  { id: 1, title: 'Frontend Engineer', company: 'Stripe', viewed: false, docs: {} },
  { id: 2, title: 'React Developer', company: 'Vercel', viewed: true, docs: {} },
  { id: 3, title: 'UI Engineer', company: 'Linear', viewed: false, docs: {} },
  { id: 4, title: 'Software Engineer', company: 'Notion', viewed: true, docs: {} },
  { id: 5, title: 'Product Engineer', company: 'Loom', viewed: false, docs: {} },
]

export const processingJobs = [
  { id: 6, title: 'Full Stack Developer', company: 'Retool', docs: { resume: true, coverLetter: false } },
  { id: 7, title: 'TypeScript Engineer', company: 'Prisma', docs: { resume: false, coverLetter: false } },
  { id: 8, title: 'Staff Engineer', company: 'PlanetScale', docs: { resume: true, coverLetter: true } },
]

export const outboxJobs = [
  { id: 9, title: 'Backend Engineer', company: 'Supabase', outcome: 'Applied', docs: { resume: true, coverLetter: true } },
  { id: 10, title: 'DevOps Engineer', company: 'Railway', outcome: 'Skipped', docs: { resume: true, coverLetter: false } },
  { id: 11, title: 'Python Developer', company: 'Prefect', outcome: 'Applied', docs: { resume: true, coverLetter: true } },
]

export const settings = {
  provider: 'anthropic',
  model: 'claude-sonnet-4-6',
  apiKey: '',
}
