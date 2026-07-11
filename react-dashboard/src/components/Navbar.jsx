import { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { logout, verifyPurchase } from "../api";

export default function Navbar({ me }) {
  const [serverDown, setServerDown] = useState(false);
  const missesRef = useRef(0);

  // Poll session-cost purely as a server-liveness heartbeat (drives the
  // "Server offline" overlay). Two consecutive misses → assume the server died.
  useEffect(() => {
    const poll = () =>
      fetch("/api/session-cost")
        .then((r) => r.json())
        .then(() => {
          missesRef.current = 0;
        })
        .catch(() => {
          missesRef.current += 1;
          if (missesRef.current >= 2) setServerDown(true);
        });
    poll();
    const id = setInterval(poll, 5000);
    return () => clearInterval(id);
  }, []);

  // On return from Stripe Checkout, confirm payment + grant credits via the
  // verify fallback (covers the webhook not reaching localhost / being delayed).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const purchase = params.get("purchase");
    const sessionId = params.get("session_id");
    if (purchase === "success") {
      const done = () => {
        window.dispatchEvent(new Event("auto-apply:credits-stale"));
        window.dispatchEvent(new Event("auto-apply:purchase-success"));
      };
      if (sessionId) verifyPurchase(sessionId).then(done).catch(done);
      else done();
    }
    if (purchase) {
      params.delete("purchase");
      params.delete("session_id");
      const qs = params.toString();
      window.history.replaceState({}, "", window.location.pathname + (qs ? `?${qs}` : ""));
    }
  }, []);

  return (
    <nav className="sticky top-0 z-50 w-full backdrop-blur-md bg-space-bg/80 border-b border-space-border px-6 py-3 flex items-center justify-between">
      <Link
        to="/"
        className="flex items-center gap-2 text-lg font-bold tracking-tight text-white hover:text-purple-300 transition-colors"
      >
        <img src="/static/images/favicon-32x32.png" alt="" className="w-6 h-6" />
        <span>Auto Apply</span>
      </Link>

      <div className="flex items-center gap-4">
        {me?.is_admin && (
          <Link
            to="/admin"
            className="text-sm font-semibold text-black bg-amber-400 hover:bg-amber-300 rounded-md px-2.5 py-1 transition-colors"
          >
            Admin
          </Link>
        )}

        {/* About / marketing page */}
        <Link
          to="/about"
          className="text-sm text-space-dim hover:text-purple-400 transition-colors"
        >
          About
        </Link>

        {/* Find remote jobs */}
        <Link
          to="/find-jobs"
          className="text-sm text-space-dim hover:text-purple-400 transition-colors"
        >
          Find Jobs
        </Link>

        {/* Replay the onboarding tour */}
        <button
          onClick={() => window.dispatchEvent(new CustomEvent('auto-apply:tour-replay'))}
          className="text-sm text-space-dim hover:text-purple-400 transition-colors bg-transparent border-0 p-0 cursor-pointer"
        >
          Take a tour
        </button>

        {/* Help link */}
        <a
          href="/docs"
          className="text-sm text-space-dim hover:text-purple-400 transition-colors"
          aria-label="Help"
        >
          Help
        </a>

        {/* Logout */}
        <button
          onClick={logout}
          className="text-sm text-space-dim hover:text-purple-400 transition-colors bg-transparent border-0 p-0 cursor-pointer"
          aria-label="Logout"
        >
          Logout
        </button>
      </div>

      {serverDown && (
        <div className="fixed inset-0 z-[200] flex flex-col items-center justify-center bg-black/90">
          <svg
            className="w-12 h-12 text-red-500 mb-4"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
          >
            <path d="M12 2v8" />
            <path d="M6.3 5.3a9 9 0 1 0 11.4 0" />
          </svg>
          <p className="text-white text-xl font-semibold mb-1">Server offline</p>
          <p className="text-space-dim text-sm">Close this window or restart via start.bat</p>
        </div>
      )}
    </nav>
  );
}
