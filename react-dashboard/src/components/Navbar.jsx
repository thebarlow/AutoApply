import { Link } from "react-router-dom";

export default function Navbar() {
  return (
    <nav className="sticky top-0 z-50 w-full backdrop-blur-md bg-space-bg/80 border-b border-space-border px-6 py-3 flex items-center justify-between">
      <Link to="/" className="text-lg font-bold tracking-tight text-white hover:text-purple-300 transition-colors">
        Auto Apply
      </Link>
      <div className="flex items-center gap-4">
        <span className="text-sm font-medium text-purple-400">
          Credits: $0.00
        </span>
        <a
          href="/docs"
          target="_blank"
          rel="noopener noreferrer"
          className="text-space-dim hover:text-purple-400 transition-colors"
          aria-label="Help"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
        </a>
      </div>
    </nav>
  )
}
