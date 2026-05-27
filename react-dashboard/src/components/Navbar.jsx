import { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";

export default function Navbar() {
  const [sessionCost, setSessionCost] = useState(0);
  const [costModalOpen, setCostModalOpen] = useState(false);
  const [shutdownOpen, setShutdownOpen] = useState(false);
  const [inFlight, setInFlight] = useState([]);
  const shutdownRef = useRef(null);

  useEffect(() => {
    const poll = () =>
      fetch("/api/session-cost")
        .then((r) => r.json())
        .then((d) => setSessionCost(d.total))
        .catch(() => {});
    poll();
    const id = setInterval(poll, 5000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!shutdownOpen) return;
    const handler = (e) => {
      if (shutdownRef.current && !shutdownRef.current.contains(e.target))
        setShutdownOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [shutdownOpen]);

  useEffect(() => {
    if (!costModalOpen) return;
    const handler = (e) => {
      if (e.key === "Escape") setCostModalOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [costModalOpen]);

  const handlePower = async () => {
    const data = await fetch("/api/llm-status").then((r) => r.json());
    if (!data.in_flight || data.in_flight.length === 0) {
      await fetch("/api/shutdown?mode=immediate", { method: "POST" });
    } else {
      setInFlight(data.in_flight);
      setShutdownOpen(true);
    }
  };

  const doShutdown = async (mode) => {
    await fetch(`/api/shutdown?mode=${mode}`, { method: "POST" });
    setShutdownOpen(false);
  };

  return (
    <nav className="sticky top-0 z-50 w-full backdrop-blur-md bg-space-bg/80 border-b border-space-border px-6 py-3 flex items-center justify-between">
      <Link
        to="/"
        className="text-lg font-bold tracking-tight text-white hover:text-purple-300 transition-colors"
      >
        Auto Apply
      </Link>

      <div className="flex items-center gap-4">
        {/* Session Cost */}
        <button
          onClick={() => setCostModalOpen(true)}
          className="text-sm font-medium text-purple-400 hover:text-purple-300 transition-colors bg-transparent border-0 p-0 cursor-pointer"
        >
          Session Cost: ${sessionCost.toFixed(2)}
        </button>

        {/* Help link */}
        <a
          href="/docs"
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-space-dim hover:text-purple-400 transition-colors"
          aria-label="Help"
        >
          Help
        </a>

        {/* Power button */}
        <div className="relative" ref={shutdownRef}>
          <button
            onClick={handlePower}
            className="w-7 h-7 rounded-full border-2 border-red-500 flex items-center justify-center text-red-500 hover:bg-red-500/10 transition-colors"
            aria-label="Shutdown"
          >
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
            >
              <path d="M12 2v8" />
              <path d="M6.3 5.3a9 9 0 1 0 11.4 0" />
            </svg>
          </button>

          {shutdownOpen && (
            <div className="absolute right-0 top-9 bg-[#0f0f1a] border border-space-border rounded-lg shadow-xl w-68 p-3 z-50">
              <p className="text-xs text-space-dim mb-2">LLM calls in progress:</p>
              <ul className="flex flex-col gap-1 mb-3">
                {inFlight.map((item, i) => (
                  <li key={i} className="text-xs text-space-text">
                    {item.title} | {item.company}
                    {item.actions.length > 0 && (
                      <span className="text-space-dim ml-1">
                        ({item.actions.join(", ")})
                      </span>
                    )}
                  </li>
                ))}
              </ul>
              <div className="flex gap-2">
                <button
                  onClick={() => doShutdown("immediate")}
                  className="flex-1 py-1.5 text-xs rounded bg-red-600 hover:bg-red-500 text-white font-semibold transition-colors"
                >
                  Exit Now
                </button>
                <button
                  onClick={() => doShutdown("wait")}
                  className="flex-1 py-1.5 text-xs rounded border border-space-border text-space-dim hover:text-space-text transition-colors"
                >
                  Exit After LLM
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Session Cost modal */}
      {costModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
          onClick={() => setCostModalOpen(false)}
        >
          <div
            className="bg-[#0f0f1a] border border-space-border rounded-xl p-6 shadow-2xl min-w-[240px]"
            onClick={(e) => e.stopPropagation()}
          >
            <p className="text-sm font-semibold text-space-text mb-2">Session Cost</p>
            <p className="text-2xl font-mono text-purple-400">
              ${sessionCost.toFixed(8)}
            </p>
            <p className="text-xs text-space-dim mt-2">Resets on server restart</p>
            <button
              className="mt-4 w-full py-1.5 text-xs text-space-dim border border-space-border rounded hover:text-space-text transition-colors"
              onClick={() => setCostModalOpen(false)}
            >
              Close
            </button>
          </div>
        </div>
      )}
    </nav>
  );
}
