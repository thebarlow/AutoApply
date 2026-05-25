import { useEffect, useRef, useState } from "react";

export default function HelpIcon({ text, docHref, label = "Help" }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <span ref={ref} className="relative inline-block ml-1">
      <button
        type="button"
        aria-label={label}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center justify-center w-5 h-5 rounded-full text-xs font-semibold bg-space-muted/40 text-space-dim hover:bg-space-muted/60 hover:text-space-text focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition-colors"
      >
        ?
      </button>
      {open && (
        <div
          role="tooltip"
          className="absolute z-50 left-6 top-0 w-64 p-3 text-sm bg-space-card border border-space-border rounded shadow-lg text-space-text"
        >
          <div>{text}</div>
          {docHref && (
            <a
              href={docHref}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2 inline-block text-purple-400 hover:text-purple-300 transition-colors"
            >
              Learn more →
            </a>
          )}
        </div>
      )}
    </span>
  );
}
