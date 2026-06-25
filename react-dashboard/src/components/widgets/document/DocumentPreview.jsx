// Read-only PDF preview: embeds the real generated PDF from the existing
// endpoint. `version` is a cache-busting counter — bumping it (after a save
// re-renders the PDF) changes the src so the browser refetches the fresh file.
export default function DocumentPreview({ jobKey, docType, version, refreshing }) {
  const src = `/api/jobs/${jobKey}/${docType}?v=${version}`
  return (
    <div className="relative w-full h-full">
      <iframe
        title="PDF preview"
        src={src}
        className="w-full h-full rounded border border-space-border bg-white"
      />
      {refreshing && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/30 rounded">
          <span className="text-xs text-white bg-black/60 px-2 py-1 rounded">Refreshing…</span>
        </div>
      )}
    </div>
  )
}
