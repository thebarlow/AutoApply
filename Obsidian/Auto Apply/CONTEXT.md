This is a structured repository of documentation and developer notes for enabling smart context retrieval for CLAUDE and savvy users.

### Routing

| Folder / File | Contents | Entry Point |
|---|---|---|
| `Docs/` | User-facing docs served via the dashboard (Getting Started, Making a Good Master Resume, Browser Extension) | `Docs/Getting Started.md` |
| `Notes/` | Developer reference notes (Architecture, dev server, FastAPI, React) | `Notes/Architecture.md` |
| `Excalidraw/` | Storage of all Excalidraw diagrams referenced within the vault | None |
| `_templates/` | Obsidian note templates (untracked; not served) | None |
| `Misc Notes.md` | Scratchpad for ad-hoc developer notes | None |
| `Overview.canvas` | Obsidian canvas overview of the vault | None |


### Doc tier-gating

`Docs/*.md` frontmatter may carry an optional `tiers:` key (comma-separated, e.g.
`tiers: friends_family, beta`). `web/routers/docs_router.py` filters gated docs from the
Docs list and 403s on direct fetch unless the caller's account tier matches (admins bypass);
docs with no `tiers:` key are public. `Browser Extension.md` is gated to `friends_family, beta`
(the extension isn't public yet); `Getting Started.md` covers the tier-agnostic manual-upload path.
An `order:` frontmatter key controls sort order.

### Interacting with the files


