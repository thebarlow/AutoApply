import SiteFooter from './SiteFooter'
import { CONTACT_EMAIL } from './links'

export const EFFECTIVE_DATE = '16 November 2026'

// Shared shell for the public legal pages. Plain <a> links (not react-router
// <Link>) so the pages render the same with or without a router and work for
// logged-out visitors.
export default function LegalPage({ title, children }) {
  return (
    <div className="min-h-screen bg-space-bg text-space-text">
      <div className="mx-auto max-w-2xl px-4 sm:px-6 pt-12 pb-16">
        <a href="/about" className="text-sm text-space-dim hover:text-purple-400 transition-colors">
          ← AutoApply
        </a>
        <h1 className="mt-6 text-3xl sm:text-4xl font-bold tracking-tight text-white">{title}</h1>
        <p className="mt-2 text-sm text-space-dim">Effective {EFFECTIVE_DATE}</p>
        <div className="mt-10 flex flex-col gap-8 text-[15px] leading-relaxed">{children}</div>
      </div>
      <SiteFooter />
    </div>
  )
}

export function Section({ title, children }) {
  return (
    <section>
      <h2 className="text-xl font-semibold text-white mb-3">{title}</h2>
      <div className="flex flex-col gap-3 text-space-text/90">{children}</div>
    </section>
  )
}

export function List({ children }) {
  return <ul className="list-disc pl-5 flex flex-col gap-1.5 marker:text-space-dim">{children}</ul>
}

export function Email() {
  return <span className="select-all font-medium text-purple-300">{CONTACT_EMAIL}</span>
}
