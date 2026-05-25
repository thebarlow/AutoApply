import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import Navbar from "./Navbar";

export default function Docs() {
  const [docs, setDocs] = useState([]);
  const [active, setActive] = useState(null);
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch("/api/docs")
      .then((r) => r.json())
      .then((list) => {
        setDocs(list);
        if (list.length) setActive(list[0]);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!active) return;
    setLoading(true);
    fetch(`/api/docs/${encodeURIComponent(active.filename)}`)
      .then((r) => r.text())
      .then((md) => { setContent(md); setLoading(false); })
      .catch(() => { setContent("Failed to load document."); setLoading(false); });
  }, [active]);

  return (
    <div className="min-h-screen bg-[#0f0f1a] text-space-text">
      <Navbar />
      <div className="max-w-4xl mx-auto p-6">
        <div className="flex gap-6">
          <nav className="w-48 shrink-0">
            <ul className="space-y-1 text-sm">
              {docs.map((d) => (
                <li key={d.filename}>
                  <button
                    onClick={() => setActive(d)}
                    className={`w-full text-left px-0 py-0.5 transition-colors ${
                      d.filename === active?.filename
                        ? "font-semibold text-space-text"
                        : "text-space-dim hover:text-space-text"
                    }`}
                  >
                    {d.title}
                  </button>
                </li>
              ))}
            </ul>
          </nav>
          <article className="prose prose-invert flex-1 min-w-0">
            {loading ? (
              <p className="text-space-dim text-sm">Loading…</p>
            ) : (
              <ReactMarkdown>{content}</ReactMarkdown>
            )}
          </article>
        </div>
      </div>
    </div>
  );
}
