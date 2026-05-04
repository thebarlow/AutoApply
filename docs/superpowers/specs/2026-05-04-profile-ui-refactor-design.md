# Design: User Profile UI Refactor

**Date:** 2026-05-04  
**Scope:** `web/static/config.html` — User Profile section and modal only

---

## Goal

Simplify the profile list row, move file upload into the modal, and make "Add User" immediately open the modal on the Upload tab.

---

## Profile List Row

**Before:** radio | name input | drop zone | edit button | delete button  
**After:** radio | name label (read-only) | Edit button | Delete button

- Name label is updated by the modal Save action.
- Radio selects active profile (unchanged).
- Delete button: DELETE endpoint, remove row (unchanged behavior).

---

## "Add User" Flow

1. POST `/api/config/profiles` → creates profile named "New Profile".
2. Append simplified row to `#profile-list`.
3. Immediately call `openProfileModal(id, isNew=true)`.

---

## Modal State

Two variables track modal context:
- `_modalProfileId` — ID of the profile being edited.
- `_modalIsNew` — `true` when opened from Add User, `false` when opened from Edit button. Set to `false` after first successful Save.

File paths are stored as properties on a modal-level state object (e.g., `_modalFilePaths = { resume_path: '', md_path: '' }`), cleared on open, populated from DB when editing an existing profile.

---

## Upload Tab

- File input + Parse button.
- Parse is disabled until a file is selected.
- On file select:
  - POST to `/api/config/profile/upload`.
  - Store returned absolute path in `_modalFilePaths`.
  - Enable Parse button.
- On Parse click:
  - POST to `/api/config/profile/parse` with the file.
  - Populate Edit tab fields with returned data.
  - Auto-switch to Edit tab.
- PDF and Markdown view tabs: shown only when `_modalFilePaths` has a value (same logic as current).

---

## Edit Tab

- **New:** "Profile Name" text input at the top (replaces the row name input as the canonical name field).
- Remaining fields unchanged: email, phone, location, skills, work history, education.

---

## Modal Save

1. Read name from modal name input.
2. Read file paths from `_modalFilePaths`.
3. Collect all form fields.
4. PUT `/api/config/profiles/{_modalProfileId}`.
5. On success:
   - Update the row's name label.
   - Set `_modalIsNew = false`.
   - Show "Saved ✓" status.

---

## Modal Close (✕, backdrop click, Escape)

- If `_modalIsNew === true`: DELETE `/api/config/profiles/{_modalProfileId}`, remove row, close.
- Otherwise: close only.

---

## Active Profile

- Radio selection on the list still controls active profile.
- The outer "Save" button (currently `#save-profile`) is removed or repurposed — profile data is now only saved via the modal. Active profile selection can be saved automatically on radio change, or the outer Save button can be kept solely for setting active. **Decision: keep outer Save button only for setting active profile.**

---

## Files Changed

- `web/static/config.html` — all changes are in this file (HTML structure + inline JS).
