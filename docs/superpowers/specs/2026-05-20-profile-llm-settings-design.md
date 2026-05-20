# Profile & LLM Settings Design

**Date:** 2026-05-20  
**Status:** Approved

## Problem

After the React migration, the Settings widget's User tab shows only a "Profile Settings" button (no profile data), and the Advanced tab reads from the wrong endpoint (`/api/config/providers` — named providers) instead of the active LLM config (`/api/config/llm`). Previously-configured user profiles and LLM providers are invisible.

## Solution

Redesign the User tab to show profile cards, add a profile detail view that includes LLM provider config, and remove the Advanced tab.

---

## Data Model

Per-profile LLM config is split across two stores:

- **Non-secret fields** (`llm_provider_type`, `llm_model`) stored inside the profile's `data` JSON blob in SQLite. No schema change — the PUT endpoint already accepts arbitrary `data`.
- **API key** stored in `.env` under `LLM_KEY_PROFILE_{profile_id}`. Same pattern as the existing named providers system.

The profile belongs to the user; the LLM provider belongs to the profile.

---

## Backend Changes (`web/routers/config.py`)

### GET `/api/config/profiles/{profile_id}`

Extend response to include:
- `llm_provider_type` — read from `data["llm_provider_type"]` (default `""`)
- `llm_model` — read from `data["llm_model"]` (default `""`)
- `has_llm_key` — bool, checks `.env` for `LLM_KEY_PROFILE_{profile_id}`

### PUT `/api/config/profiles/{profile_id}`

`ProfileBody` gains `llm_api_key: str = ""`. If non-empty, written to `.env` under `LLM_KEY_PROFILE_{profile_id}`. The `llm_provider_type` and `llm_model` fields ride inside `body.data` as usual.

No new endpoints. No scorer wiring (follow-up task).

---

## Frontend Changes

### `api.js`

Add two functions:
- `getProfile(id)` — GET `/api/config/profiles/{id}`
- `updateProfile(id, body)` — PUT `/api/config/profiles/{id}` with `{ name, data, llm_api_key }`

### `Settings.jsx` — Tab changes

- Remove `Advanced` from the `TABS` array.
- User tab content is replaced entirely (see below).

### User tab — Profile card list

Fetches `GET /api/config/profiles` on mount. Renders:
- One card per profile showing:
  - Profile role name (e.g. "Software Engineer")
  - User's first + last name from `data.first_name` / `data.last_name`
  - Active profile indicated by a purple left-border
- "+ Create Profile" button below the list

Clicking a card pushes view state to `{ type: 'profileDetail', profileId }`.

### Profile detail view

Triggered by clicking a profile card. Fetches `GET /api/config/profiles/{id}` on mount.

Layout (single scrollable view):
1. Back button → returns to profile card list
2. Personal fields: First Name, Last Name, Email, Phone, Location
3. Horizontal divider + "LLM Provider" heading
4. Provider type — `<select>` with options: openrouter, anthropic, openai, gemini
5. Model — text input
6. API Key — password input, placeholder "Enter new key to replace existing"
7. Save button at the bottom

On save: PUT `/api/config/profiles/{id}` with merged `data` (including `llm_provider_type` and `llm_model`) and `llm_api_key` if the field is non-empty.

### View state

Extend the existing `view` state in `Settings`:

| Value | Renders |
|---|---|
| `main` | Tab bar + tab content |
| `profiles` | Profile card list (replaces old ProfileList) |
| `createProfile` | Create profile form |
| `profileDetail` | Profile detail + LLM provider form |

`profileDetail` needs the selected profile ID — store as a sibling state variable `detailProfileId`.

---

## Out of Scope

- Wiring per-profile LLM provider into scorer/generator (follow-up)
- Profile deletion UI
- Resume/cover letter upload in the detail view
