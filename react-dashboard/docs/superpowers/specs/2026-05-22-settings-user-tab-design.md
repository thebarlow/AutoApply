# Settings Widget — User Tab Redesign

**Date:** 2026-05-22
**Status:** Approved

---

## Overview

Redesign the User tab of the Settings widget to expose all profile fields through a structured, accordion-based read-only view with per-section and per-item editing via modals/overlays.

---

## Accordion Sections

Eight sections in the following order:

| # | Section | Type | Edit Interaction |
|---|---|---|---|
| 1 | Identity | Non-list | Edit button → modal (subsections: Personal, Contact, Socials) |
| 2 | Skills | List of strings | Item chips with Remove; Add New → mini overlay |
| 3 | Experience | List of objects | Item cards with Edit; Add New → mini overlay |
| 4 | Education | List of objects | Item cards with Edit; Add New → mini overlay |
| 5 | Projects | List of objects | Item cards with Edit; Add New → mini overlay |
| 6 | Job Preferences | Non-list | Edit button → modal |
| 7 | Prompts | Non-list | Edit button → modal |
| 8 | LLM Config | Non-list | Edit button → modal |

### Section field details

**Identity modal** — three labeled subsections within one modal:
- Personal: `first_name`, `last_name`, `hero` (professional tagline), `location`
- Contact: `email`, `phone`
- Socials: `linkedin`, `github`, `website`

**Skills** — list of strings. Each chip has a Remove (×) button. Add New opens a mini overlay with a single text input.

**Experience** — each item: `company`, `title`, `start`, `end`, `summary` (textarea)

**Education** — each item: `institution`, `degree`, `field`, `graduated`, `gpa` (number)

**Projects** — each item: `name`, `description` (textarea), `url`, `technologies` (tag input — comma-separated strings)

**Job Preferences modal**: `target_roles` (tag input), `target_salary_min`, `target_salary_max`

**Prompts modal** — five prompts, each with a textarea and a "Reset to Default" button:
- `prompt_scoring`
- `prompt_resume`
- `prompt_cover`
- `prompt_extraction`
- `prompt_intake`

Default strings are frontend constants. Reset to Default populates the textarea but does not auto-save.

**LLM Config modal**: `llm_provider_type` (dropdown: openrouter, anthropic, openai, gemini), `llm_model` (text input, e.g. "gpt-4o"), `llm_api_key` (password field — see error handling below)

---

## Component Architecture

### File structure

Extract all profile detail UI into a new file:

```
src/components/widgets/ProfileDetail.jsx
```

`Settings.jsx` imports and renders `ProfileDetailView` from this file. No other changes to `Settings.jsx`.

### Component tree

```
ProfileDetailView
  ├── AccordionSection            shared — title, optional Edit button, collapsible body
  ├── ItemOverlay                 shared — modal shell: title, content slot, Save/Cancel
  │
  ├── IdentitySection             → IdentityModal
  ├── SkillsSection               → SkillOverlay
  ├── ExperienceSection           → ExperienceOverlay
  ├── EducationSection            → EducationOverlay
  ├── ProjectsSection             → ProjectOverlay
  ├── JobPrefsSection             → JobPrefsModal
  ├── PromptsSection              → PromptsModal
  └── LlmSection                  → LlmModal
```

### State flow

- `ProfileDetailView` fetches the profile on mount and holds the full profile as `profileState`
- Each section receives its slice of `profileState` as props
- Each modal/overlay receives an `onSave(patch)` callback
- On successful API PUT, the callback merges `patch` into `profileState` (optimistic local update, no re-fetch)
- The PUT sends the full profile blob with the patched section merged in — uses the existing `PUT /api/config/profiles/{id}` endpoint

---

## Backend Model Changes

The following fields must be added to `core/user.py` (`_hydrate` and `_to_dict`) and are not currently present:

| Field | Type | Notes |
|---|---|---|
| `website` | `str` | Personal/portfolio URL |
| `prompt_scoring` | `str` | Custom scoring system prompt |
| `prompt_resume` | `str` | Custom resume generation system prompt |
| `prompt_cover` | `str` | Custom cover letter generation system prompt |
| `prompt_extraction` | `str` | Custom description extraction system prompt |
| `prompt_intake` | `str` | Custom intake system prompt |

All existing model fields (`hero`, `linkedin`, `github`, `projects`, `target_roles`, `target_salary_min/max`) are already in the model but not yet surfaced in the UI — no model change needed for those.

---

## Error Handling

- **Modal save failure**: show inline error within the modal, keep it open, do not update `profileState`
- **Missing prompt fields on load**: if any prompt field is `null`/missing, the UI displays the default constant string in the accordion preview. The user must open and save the Prompts modal to persist them.
- **Skills deduplication**: duplicate skill strings are silently ignored on add (frontend check before pushing)
- **LLM API key — key exists**: field displays `"••••••••"` as the value when `has_llm_key: true`. Focusing the field clears it so the user can type a replacement. Submitting blank does not overwrite the existing key.
- **LLM API key — no key**: field is empty with placeholder "Enter API key"

---

## Out of Scope

- Profile switching / active profile selection (already implemented in `ProfileCards`)
- Profile creation (already implemented in `CreateProfile`)
- Profile deletion (already implemented in the API, not yet in UI — separate task)
- Resume upload / parse from PDF (already implemented in the API — separate task)
