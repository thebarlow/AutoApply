import { COFFEE_URL } from './links'

// Small public footer for the landing page and legal pages.
export default function SiteFooter() {
  const link = 'hover:text-purple-400 transition-colors'
  return (
    <footer className="border-t border-space-border px-4 sm:px-6 py-8">
      <div className="mx-auto max-w-5xl flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm text-space-dim">
        <span>© 2026 Matthew Barlow</span>
        <a href="/privacy" className={link}>Privacy Policy</a>
        <a href="/terms" className={link}>Terms of Service</a>
        {/* Plain link, no BMC widget script: the CSP is script-src 'self'. */}
        <a href={COFFEE_URL} target="_blank" rel="noopener noreferrer" className={link}>
          Buy me a coffee
        </a>
      </div>
    </footer>
  )
}
