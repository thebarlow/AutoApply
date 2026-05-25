import ReactMarkdown from "react-markdown";

const docs = import.meta.glob("../docs-content/*.md", { query: "?raw", import: "default", eager: true });

function getDocs() {
  return Object.entries(docs).map(([path, content]) => {
    const slug = path.split("/").pop().replace(".md", "");
    return { slug, content };
  });
}

export default function Docs({ slug, onClose }) {
  const all = getDocs();
  const current = slug ? all.find((d) => d.slug === slug) : all[0];

  return (
    <div className="fixed inset-0 z-40 bg-[#0f0f1a] overflow-auto text-space-text">
      <div className="max-w-3xl mx-auto p-6">
        <div className="flex justify-between items-center mb-4">
          <h1 className="text-xl font-bold">Documentation</h1>
          <button onClick={onClose} className="text-space-dim hover:text-space-text hover:underline transition-colors">
            Close
          </button>
        </div>
        <div className="flex gap-6">
          <nav className="w-48 shrink-0">
            <ul className="space-y-1 text-sm">
              {all.map((d) => (
                <li key={d.slug}>
                  <a
                    href={`#/docs/${d.slug}`}
                    className={
                      d.slug === current?.slug
                        ? "font-semibold text-space-text"
                        : "text-space-dim hover:text-space-text"
                    }
                  >
                    {d.slug.replace(/-/g, " ")}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
          <article className="prose prose-invert flex-1">
            {current ? <ReactMarkdown>{current.content}</ReactMarkdown> : <div>Not found</div>}
          </article>
        </div>
      </div>
    </div>
  );
}
