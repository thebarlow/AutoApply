import { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";

export default function Navbar() {
  const [sessionCost, setSessionCost] = useState(0);
  const [costOpen, setCostOpen] = useState(false);
  const [shutdownOpen, setShutdownOpen] = useState(false);
  const [inFlight, setInFlight] = useState([]);
  const [serverDown, setServerDown] = useState(false);
  const shutdownRef = useRef(null);
  const costRef = useRef(null);
  const missesRef = useRef(0);

  useEffect(() => {
    const poll = () =>
      fetch("/api/session-cost")
        .then((r) => r.json())
        .then((d) => {
          missesRef.current = 0;
          setSessionCost(d.total);
        })
        .catch(() => {
          missesRef.current += 1;
          if (missesRef.current >= 2) setServerDown(true);
        });
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
    if (!costOpen) return;
    const handler = (e) => {
      if (costRef.current && !costRef.current.contains(e.target))
        setCostOpen(false);
      if (e.key === "Escape") setCostOpen(false);
    };
    document.addEventListener("mousedown", handler);
    window.addEventListener("keydown", handler);
    return () => {
      document.removeEventListener("mousedown", handler);
      window.removeEventListener("keydown", handler);
    };
  }, [costOpen]);

  const handlePower = async () => {
    try {
      const data = await fetch("/api/llm-status").then((r) => r.json());
      if (!data.in_flight || data.in_flight.length === 0) {
        await fetch("/api/shutdown?mode=immediate", { method: "POST" });
        setServerDown(true);
      } else {
        setInFlight(data.in_flight);
        setShutdownOpen(true);
      }
    } catch (e) {
      console.error("Shutdown request failed:", e);
    }
  };

  const doShutdown = async (mode) => {
    try {
      await fetch(`/api/shutdown?mode=${mode}`, { method: "POST" });
      setShutdownOpen(false);
      setServerDown(true);
    } catch (e) {
      console.error("Shutdown request failed:", e);
    }
  };

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
        {/* Session Cost */}
        <div className="relative" ref={costRef}>
          <button
            onClick={() => setCostOpen((v) => !v)}
            className="text-sm font-medium text-purple-400 hover:text-purple-300 transition-colors bg-transparent border-0 p-0 cursor-pointer"
          >
            Session Cost: ${sessionCost.toFixed(2)}
          </button>

          {costOpen && (
            <div className="absolute right-0 top-full mt-1 bg-[#0f0f1a] border border-space-border rounded-xl p-4 shadow-2xl min-w-[200px] z-50">
              <div className="flex items-center gap-1 mb-2">
                <p className="text-sm font-semibold text-space-text">Session Cost</p>
                <div className="relative group ml-auto">
                  <span className="text-[10px] text-space-dim border border-space-border rounded-full w-4 h-4 flex items-center justify-center cursor-default select-none">
                    ?
                  </span>
                  <div className="absolute right-0 top-5 w-44 bg-[#1a1a2e] border border-space-border rounded-md px-2 py-1.5 text-[10px] text-space-dim shadow-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
                    Accumulated LLM cost this session. Resets on server restart.
                  </div>
                </div>
              </div>
              <p className="text-2xl font-mono text-purple-400">
                ${sessionCost.toFixed(8)}
              </p>
            </div>
          )}
        </div>

        {/* Help link */}
        <a
          href="/docs"
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
            <div className="absolute right-0 top-9 bg-[#0f0f1a] border border-space-border rounded-lg shadow-xl w-72 p-3 z-50">
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
