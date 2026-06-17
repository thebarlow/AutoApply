import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import Navbar from "./Navbar";
import { getMe } from "../api";

function slugify(text) {
  return text.toLowerCase().replace(/[^\w\s-]/g, "").trim().replace(/\s+/g, "-");
}

function extractH1s(markdown) {
  const lines = markdown.split("\n");
  const headings = [];
  for (const line of lines) {
    const m = line.match(/^# (.+)/);
    if (m) headings.push({ text: m[1], id: slugify(m[1]) });
  }
  return headings;
}

export default function Docs() {
  const [me, setMe] = useState(null);
  const [docs, setDocs] = useState([]);
  const [active, setActive] = useState(null);
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [contentMap, setContentMap] = useState({});
  const pendingScrollRef = useRef(null);
  const hashResolvedRef = useRef(false);

  useEffect(() => {
    getMe().then(setMe).catch(() => setMe(null));
  }, []);

  useEffect(() => {
    fetch("/api/docs")
      .then((r) => r.json())
      .then((list) => {
        setDocs(list);
        if (list.length) setActive(list[0]);
        list.forEach((d) => {
          fetch(`/api/docs/${encodeURIComponent(d.filename)}`)
            .then((r) => r.text())
            .then((md) => setContentMap((prev) => ({ ...prev, [d.filename]: md })))
            .catch(() => {});
        });
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!active) return;
    if (contentMap[active.filename]) {
      setContent(contentMap[active.filename]);
      return;
    }
    setLoading(true);
    fetch(`/api/docs/${encodeURIComponent(active.filename)}`)
      .then((r) => r.text())
      .then((md) => {
        setContentMap((prev) => ({ ...prev, [active.filename]: md }));
        setContent(md);
        setLoading(false);
      })
      .catch(() => {
        setContent("Failed to load document.");
        setLoading(false);
      });
  }, [active]);

  // Resolve a URL hash (e.g. /docs#installing-the-browser-extension) once doc
  // contents are loaded: pick the doc containing that heading and scroll to it.
  useEffect(() => {
    if (hashResolvedRef.current) return;
    const id = window.location.hash.replace(/^#/, "");
    if (!id) { hashResolvedRef.current = true; return; }
    const match = docs.find((d) =>
      contentMap[d.filename] && extractH1s(contentMap[d.filename]).some((h) => h.id === id)
    );
    if (!match) return;
    hashResolvedRef.current = true;
    if (active?.filename === match.filename) {
      const el = document.getElementById(id);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
      else pendingScrollRef.current = id;
    } else {
      pendingScrollRef.current = id;
      setActive(match);
    }
  }, [docs, contentMap]);

  useEffect(() => {
    if (!pendingScrollRef.current || loading) return;
    const el = document.getElementById(pendingScrollRef.current);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
      pendingScrollRef.current = null;
    }
  }, [content, loading]);

  function handleDocClick(doc) {
    setActive(doc);
    pendingScrollRef.current = null;
  }

  function handleHeadingClick(doc, headingId) {
    if (active?.filename === doc.filename) {
      const el = document.getElementById(headingId);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    } else {
      pendingScrollRef.current = headingId;
      setActive(doc);
    }
  }

  const headingComponents = {
    h1: ({ children, node: _node, ...props }) => {
      const text = Array.isArray(children)
        ? children.map((c) => (typeof c === "string" ? c : "")).join("")
        : String(children ?? "");
      return <h1 id={slugify(text)} {...props}>{children}</h1>;
    },
  };

  return (
    <div className="min-h-screen bg-[#0f0f1a] text-space-text">
      <Navbar me={me} />
      <div className="max-w-5xl mx-auto p-6">
        <div className="flex gap-8 h-[calc(100vh-4rem)]">
          <nav className="w-64 shrink-0 sticky top-6 self-start overflow-y-auto max-h-[calc(100vh-5rem)]">
            <ul className="space-y-3">
              {docs.map((d) => {
                const h1s = contentMap[d.filename] ? extractH1s(contentMap[d.filename]) : [];
                const isActive = d.filename === active?.filename;
                return (
                  <li key={d.filename}>
                    <button
                      onClick={() => handleDocClick(d)}
                      className={`w-full text-left text-base font-semibold transition-colors ${
                        isActive ? "text-space-text" : "text-space-dim hover:text-space-text"
                      }`}
                    >
                      {d.title}
                    </button>
                    {isActive && h1s.length > 0 && (
                      <ul className="mt-1 ml-3 space-y-1 border-l border-space-border pl-3">
                        {h1s.map((h) => (
                          <li key={h.id}>
                            <button
                              onClick={() => handleHeadingClick(d, h.id)}
                              className="w-full text-left text-sm text-space-dim hover:text-space-text transition-colors"
                            >
                              {h.text}
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                );
              })}
            </ul>
          </nav>

          <article className="prose prose-invert prose-headings:text-space-text prose-p:text-space-dim prose-li:text-space-dim prose-a:text-violet-400 hover:prose-a:text-violet-300 flex-1 min-w-0 overflow-y-auto">
            {loading ? (
              <p className="text-space-dim text-sm">Loading…</p>
            ) : (
              <ReactMarkdown components={headingComponents} rehypePlugins={[rehypeRaw]}>{content}</ReactMarkdown>
            )}
          </article>
        </div>
      </div>
    </div>
  );
}
