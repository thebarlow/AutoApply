# Profile UI Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the User Profile section of `config.html` so the list row is simplified (name + edit + delete), and "Add User" immediately opens the modal on the Upload tab.

**Architecture:** All changes are isolated to `web/static/config.html`. The modal gains an Upload tab (split out from the Edit tab), a Profile Name field, and close-with-delete logic for unsaved new profiles. The list row loses the drop zone and name input, gaining a read-only name label instead.

**Tech Stack:** Vanilla JS, HTML, existing FastAPI endpoints (`/api/config/profile/upload`, `/api/config/profile/parse`, `/api/config/profiles/{id}`)

---

## File Map

- **Modify:** `web/static/config.html`
  - HTML: profile list section, modal tab bar, modal tab panels
  - JS: `buildProfileRow`, `openProfileModal`, `closeProfileModal`, `loadModalContent`, `save-profile-modal` handler, `btn-add-profile` handler, `save-profile` handler, `btn-parse-profile` handler, `profile-file` change handler

---

### Task 1: Simplify the profile list row HTML and JS

The current `buildProfileRow` builds a row with a name text input, a drop zone, edit button, and delete button. Replace it with: radio | name label (`<span>`) | Edit button | Delete button. Remove `initDropZoneProfile` calls from here — file paths will live in modal state only.

**Files:**
- Modify: `web/static/config.html` — `buildProfileRow` function (~line 488) and `loadProfiles` function (~line 545)

- [ ] **Step 1: Replace `buildProfileRow`**

Find and replace the entire `buildProfileRow` function with:

```javascript
function buildProfileRow(profile, isActive) {
  const row = document.createElement('div');
  row.className = 'llm-row';
  row.dataset.id = profile.id;

  row.innerHTML = `
    <input type="radio" name="profile-active" value="${profile.id}"${isActive ? ' checked' : ''}>
    <span class="profile-name-label">${profile.name || 'New Profile'}</span>
    <button class="btn-edit-profile btn btn-secondary" type="button" title="Edit profile">Edit</button>
    <button class="btn-remove-llm" type="button" title="Delete profile">✕</button>
  `;

  row.querySelector('input[type=radio]').addEventListener('change', function () {
    _selectedProfileId = profile.id;
  });

  row.querySelector('.btn-edit-profile').addEventListener('click', function () {
    _selectedProfileId = profile.id;
    row.querySelector('input[type=radio]').checked = true;
    openProfileModal(profile.id, false);
  });

  row.querySelector('.btn-remove-llm').addEventListener('click', async function () {
    const resp = await fetch('/api/config/profiles/' + profile.id, { method: 'DELETE' });
    if (!resp.ok) { showStatus('status-profile', 'Delete failed', true); return; }
    row.remove();
    if (_selectedProfileId === profile.id) _selectedProfileId = null;
  });

  return row;
}
```

- [ ] **Step 2: Update `loadProfiles` to use simplified row**

Find `loadProfiles` (~line 545). Replace the `meta.profiles.forEach` block:

```javascript
meta.profiles.forEach(function(p, i) {
  const detail = details[i];
  const row = buildProfileRow(
    { id: p.id, name: p.name },
    p.id === meta.active_id
  );
  list.appendChild(row);
});
```

- [ ] **Step 3: Manual smoke test**

Start the server (`uvicorn web.main:app --reload` from project root), open `/config`, expand User Profile. Verify existing profiles show as: radio | name text | Edit button | ✕ button. No drop zone visible.

- [ ] **Step 4: Commit**

```bash
git add web/static/config.html
git commit -m "[refactor] Simplify profile list row to radio/name/edit/delete"
```

---

### Task 2: Add modal state variables and split Upload tab into its own tab

Currently "Upload Resume" is a section inside the Edit tab panel. Move it to its own tab panel `tab-panel-upload`. Add the modal state object for file paths.

**Files:**
- Modify: `web/static/config.html` — modal HTML (~line 155) and JS modal state (~line 635)

- [ ] **Step 1: Update modal tab bar HTML**

Find the `<div class="profile-tab-bar" ...>` block and replace it:

```html
<div class="profile-tab-bar" id="profile-tab-bar">
  <button class="profile-tab-btn active" id="tab-btn-upload" data-tab="upload">Upload</button>
  <button class="profile-tab-btn" id="tab-btn-pdf" data-tab="pdf">PDF</button>
  <button class="profile-tab-btn" id="tab-btn-md" data-tab="md">Markdown</button>
  <button class="profile-tab-btn" id="tab-btn-edit" data-tab="edit">Edit</button>
</div>
```

- [ ] **Step 2: Add Upload tab panel HTML and clean up Edit tab panel**

After the closing `</div>` of `tab-panel-md`, insert the new Upload tab panel. Then remove the "Upload Resume" section from `tab-panel-edit`, and add a Profile Name field at the top of the Edit tab. Replace everything from `<!-- PDF tab -->` through `</div>\n\n</div>` (end of modal panel) with:

```html
    <!-- Upload tab -->
    <div class="profile-tab-panel active" id="tab-panel-upload">
      <h2 style="font-size:0.8rem;font-weight:700;color:#888;text-transform:uppercase;letter-spacing:0.06em;margin:0 0 0.5rem">Upload Resume</h2>
      <div class="config-row">
        <input type="file" id="profile-file" accept=".pdf,.md">
        <button class="btn btn-secondary" id="btn-parse-profile" type="button" disabled style="margin-top:0">Parse</button>
      </div>
    </div>

    <!-- PDF tab -->
    <div class="profile-tab-panel" id="tab-panel-pdf">
      <iframe class="profile-pdf-frame" id="profile-pdf-frame" src="about:blank"></iframe>
    </div>

    <!-- Markdown tab -->
    <div class="profile-tab-panel" id="tab-panel-md">
      <textarea class="profile-md-viewer" id="profile-md-viewer" readonly></textarea>
    </div>

    <!-- Edit tab -->
    <div class="profile-tab-panel" id="tab-panel-edit">
      <h2 style="font-size:0.8rem;font-weight:700;color:#888;text-transform:uppercase;letter-spacing:0.06em;margin:0 0 0.5rem">Profile</h2>
      <label class="config-label">Profile Name</label>
      <input class="config-input" type="text" id="profile-modal-name">

      <h2 style="font-size:0.8rem;font-weight:700;color:#888;text-transform:uppercase;letter-spacing:0.06em;margin:1.25rem 0 0.5rem">Details</h2>
      <label class="config-label">Full Name</label>
      <input class="config-input" type="text" id="profile-name">
      <label class="config-label">Email</label>
      <input class="config-input" type="text" id="profile-email">
      <label class="config-label">Phone</label>
      <input class="config-input" type="text" id="profile-phone">
      <label class="config-label">Location</label>
      <input class="config-input" type="text" id="profile-location">
      <label class="config-label">Skills (comma-separated)</label>
      <input class="config-input" type="text" id="profile-skills">

      <h2 style="font-size:0.8rem;font-weight:700;color:#888;text-transform:uppercase;letter-spacing:0.06em;margin:1.25rem 0 0.5rem">Work History</h2>
      <div id="work-history-list"></div>
      <button class="btn btn-secondary" id="btn-add-work" type="button">+ Add Work History</button>

      <h2 style="font-size:0.8rem;font-weight:700;color:#888;text-transform:uppercase;letter-spacing:0.06em;margin:1.25rem 0 0.5rem">Education</h2>
      <div id="education-list"></div>
      <button class="btn btn-secondary" id="btn-add-education" type="button">+ Add Education</button>

      <div class="config-actions" style="margin-top:1rem">
        <button class="btn btn-save" id="save-profile-modal">Save</button>
        <span class="save-status" id="status-profile-modal"></span>
      </div>
    </div>
```

- [ ] **Step 3: Add `_modalFilePaths` and `_modalIsNew` to JS modal state**

Find `let _modalProfileId = null;` (~line 635) and replace with:

```javascript
let _modalProfileId = null;
let _modalIsNew = false;
let _modalFilePaths = { resume_path: '', md_path: '' };
```

- [ ] **Step 4: Commit**

```bash
git add web/static/config.html
git commit -m "[refactor] Split Upload into own modal tab, add modal state vars"
```

---

### Task 3: Update `openProfileModal` and `closeProfileModal`

`openProfileModal` now takes an `isNew` parameter. `closeProfileModal` deletes the profile if `_modalIsNew` is still true.

**Files:**
- Modify: `web/static/config.html` — `openProfileModal` and `closeProfileModal` functions (~line 637)

- [ ] **Step 1: Replace `openProfileModal`**

```javascript
function openProfileModal(id, isNew) {
  _modalProfileId = id;
  _modalIsNew = isNew;
  _modalFilePaths = { resume_path: '', md_path: '' };
  document.getElementById('profile-modal-backdrop').classList.add('is-open');
  loadModalContent(id, isNew);
}
```

- [ ] **Step 2: Replace `closeProfileModal`**

```javascript
async function closeProfileModal() {
  if (_modalIsNew) {
    await fetch('/api/config/profiles/' + _modalProfileId, { method: 'DELETE' });
    const row = document.querySelector('#profile-list .llm-row[data-id="' + _modalProfileId + '"]');
    if (row) row.remove();
    if (_selectedProfileId === _modalProfileId) _selectedProfileId = null;
  }
  _modalProfileId = null;
  _modalIsNew = false;
  _modalFilePaths = { resume_path: '', md_path: '' };
  document.getElementById('profile-modal-backdrop').classList.remove('is-open');
  document.getElementById('profile-pdf-frame').src = 'about:blank';
  document.getElementById('profile-md-viewer').value = '';
}
```

- [ ] **Step 3: Commit**

```bash
git add web/static/config.html
git commit -m "[refactor] Update openProfileModal/closeProfileModal with isNew logic"
```

---

### Task 4: Update `loadModalContent` to handle Upload-first and populate `_modalFilePaths`

When `isNew` is true, land on the Upload tab. When editing an existing profile, land on Edit tab and populate `_modalFilePaths` from the DB data.

**Files:**
- Modify: `web/static/config.html` — `loadModalContent` function (~line 651)

- [ ] **Step 1: Replace `loadModalContent`**

```javascript
async function loadModalContent(id, isNew) {
  // Reset all tabs
  document.querySelectorAll('.profile-tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.profile-tab-panel').forEach(p => p.classList.remove('active'));

  // Reset file input and parse button
  const fileInput = document.getElementById('profile-file');
  fileInput.value = '';
  document.getElementById('btn-parse-profile').disabled = true;

  if (isNew) {
    document.getElementById('tab-btn-upload').classList.add('active');
    document.getElementById('tab-panel-upload').classList.add('active');
    document.getElementById('profile-modal-title').textContent = 'New Profile';
    document.getElementById('profile-modal-name').value = '';
    document.getElementById('tab-btn-pdf').style.display = 'none';
    document.getElementById('tab-btn-md').style.display = 'none';
    populateEditForm({});
    return;
  }

  // Editing existing — land on Edit tab
  document.getElementById('tab-btn-edit').classList.add('active');
  document.getElementById('tab-panel-edit').classList.add('active');

  try {
    const resp = await fetch('/api/config/profiles/' + id);
    if (!resp.ok) return;
    const profile = await resp.json();

    document.getElementById('profile-modal-title').textContent = profile.name || 'Profile';
    document.getElementById('profile-modal-name').value = profile.name || '';
    populateEditForm(Object.assign({ name: profile.name }, profile.data));

    _modalFilePaths.resume_path = profile.data.resume_path || '';
    _modalFilePaths.md_path = profile.data.md_path || '';

    const resumePath = _modalFilePaths.resume_path;
    const hasPdf = resumePath.toLowerCase().endsWith('.pdf');
    document.getElementById('tab-btn-pdf').style.display = hasPdf ? '' : 'none';
    if (hasPdf) {
      document.getElementById('profile-pdf-frame').src = '/api/config/profiles/' + id + '/file?type=pdf';
    }

    const mdPath = _modalFilePaths.md_path;
    const hasMd = !!mdPath;
    document.getElementById('tab-btn-md').style.display = hasMd ? '' : 'none';
    if (hasMd) {
      fetch('/api/config/profiles/' + id + '/file?type=md')
        .then(r => r.text())
        .then(text => { document.getElementById('profile-md-viewer').value = text; })
        .catch(() => { document.getElementById('profile-md-viewer').value = '(Failed to load)'; });
    }
  } catch (e) {
    showStatus('status-profile-modal', 'Failed to load profile', true);
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add web/static/config.html
git commit -m "[refactor] Update loadModalContent for Upload-first new profile flow"
```

---

### Task 5: Update the Upload tab JS (file select, upload, parse)

Wire up the `profile-file` input and `btn-parse-profile` button to upload the file, store the path in `_modalFilePaths`, and auto-switch to Edit tab on parse.

**Files:**
- Modify: `web/static/config.html` — `profile-file` change handler and `btn-parse-profile` click handler (~line 743)

- [ ] **Step 1: Replace `profile-file` change handler**

Find and replace:

```javascript
document.getElementById('profile-file').addEventListener('change', function(e) {
  document.getElementById('btn-parse-profile').disabled = !e.target.files.length;
});
```

with:

```javascript
document.getElementById('profile-file').addEventListener('change', async function(e) {
  const file = e.target.files[0];
  if (!file) {
    document.getElementById('btn-parse-profile').disabled = true;
    return;
  }
  const form = new FormData();
  form.append('file', file);
  try {
    const resp = await fetch('/api/config/profile/upload', { method: 'POST', body: form });
    if (!resp.ok) { showStatus('status-profile-modal', 'Upload failed', true); return; }
    const result = await resp.json();
    if (file.name.toLowerCase().endsWith('.pdf')) {
      _modalFilePaths.resume_path = result.path;
      _modalFilePaths.md_path = '';
    } else {
      _modalFilePaths.md_path = result.path;
      _modalFilePaths.resume_path = '';
    }
    document.getElementById('btn-parse-profile').disabled = false;
  } catch (err) {
    showStatus('status-profile-modal', 'Upload error: ' + err.message, true);
  }
});
```

- [ ] **Step 2: Replace `btn-parse-profile` click handler**

Find and replace the entire `btn-parse-profile` addEventListener block:

```javascript
document.getElementById('btn-parse-profile').addEventListener('click', async function() {
  const file = document.getElementById('profile-file').files[0];
  if (!file) return;
  const form = new FormData();
  form.append('file', file);
  try {
    const resp = await fetch('/api/config/profile/parse', { method: 'POST', body: form });
    if (!resp.ok) { showStatus('status-profile-modal', 'Parse failed', true); return; }
    const data = await resp.json();
    document.getElementById('profile-modal-name').value = data.name || '';
    populateEditForm(Object.assign({ name: data.name }, data));
    // Switch to Edit tab
    document.querySelectorAll('.profile-tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.profile-tab-panel').forEach(p => p.classList.remove('active'));
    document.getElementById('tab-btn-edit').classList.add('active');
    document.getElementById('tab-panel-edit').classList.add('active');
  } catch (e) {
    showStatus('status-profile-modal', 'Parse error', true);
  }
});
```

- [ ] **Step 3: Commit**

```bash
git add web/static/config.html
git commit -m "[refactor] Wire Upload tab file input to upload endpoint and auto-switch on parse"
```

---

### Task 6: Update modal Save handler and "Add User" button

Save reads name from `#profile-modal-name` and file paths from `_modalFilePaths`. "Add User" creates the profile then opens the modal with `isNew=true`.

**Files:**
- Modify: `web/static/config.html` — `save-profile-modal` handler (~line 692) and `btn-add-profile` handler (~line 568)

- [ ] **Step 1: Replace `save-profile-modal` handler**

```javascript
document.getElementById('save-profile-modal').addEventListener('click', async function() {
  if (!_modalProfileId) return;
  const profileName = document.getElementById('profile-modal-name').value.trim() || 'New Profile';
  const body = collectEditForm(profileName);
  body.data.resume_path = _modalFilePaths.resume_path;
  body.data.md_path = _modalFilePaths.md_path;
  try {
    const resp = await fetch('/api/config/profiles/' + _modalProfileId, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (resp.ok) {
      _modalIsNew = false;
      document.getElementById('profile-modal-title').textContent = profileName;
      const row = document.querySelector('#profile-list .llm-row[data-id="' + _modalProfileId + '"]');
      if (row) row.querySelector('.profile-name-label').textContent = profileName;
      showStatus('status-profile-modal', 'Saved ✓', false);
    } else {
      showStatus('status-profile-modal', 'Error saving', true);
    }
  } catch (e) {
    showStatus('status-profile-modal', 'Error saving', true);
  }
});
```

- [ ] **Step 2: Replace `btn-add-profile` handler**

```javascript
document.getElementById('btn-add-profile').addEventListener('click', async function() {
  try {
    const resp = await fetch('/api/config/profiles', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'New Profile' }),
    });
    if (!resp.ok) { showStatus('status-profile', 'Failed to create profile', true); return; }
    const profile = await resp.json();
    const row = buildProfileRow({ id: profile.id, name: profile.name }, false);
    document.getElementById('profile-list').appendChild(row);
    _selectedProfileId = profile.id;
    openProfileModal(profile.id, true);
  } catch (e) {
    showStatus('status-profile', 'Error creating profile', true);
  }
});
```

- [ ] **Step 3: Commit**

```bash
git add web/static/config.html
git commit -m "[refactor] Update Add User and modal Save for new profile flow"
```

---

### Task 7: Update outer Save button and remove dead code

The outer `#save-profile` button now only sets the active profile. Remove the dead `initDropZoneProfile` function and the old name-input / drop-zone references in the save handler.

**Files:**
- Modify: `web/static/config.html` — `save-profile` handler (~line 586), `initDropZoneProfile` function (~line 302)

- [ ] **Step 1: Replace `save-profile` handler**

```javascript
document.getElementById('save-profile').addEventListener('click', async function() {
  const activeRadio = document.querySelector('input[name="profile-active"]:checked');
  if (!activeRadio) { showStatus('status-profile', 'Select a profile first', true); return; }
  const activeId = parseInt(activeRadio.value);
  try {
    const resp = await fetch('/api/config/profiles/active', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active_id: activeId }),
    });
    if (resp.ok) {
      _selectedProfileId = activeId;
      showStatus('status-profile', 'Active profile set ✓', false);
    } else {
      showStatus('status-profile', 'Error setting active profile', true);
    }
  } catch (e) {
    showStatus('status-profile', 'Error setting active profile', true);
  }
});
```

- [ ] **Step 2: Delete `initDropZoneProfile`**

Remove the entire `initDropZoneProfile` function (from `function initDropZoneProfile(` through its closing `}`). It is no longer called anywhere.

- [ ] **Step 3: Delete `selectProfile` function**

Remove the now-unused `selectProfile` function:

```javascript
async function selectProfile(id) {
  _selectedProfileId = id;
}
```

- [ ] **Step 4: Commit**

```bash
git add web/static/config.html
git commit -m "[refactor] Slim outer Save to active-only, remove dead initDropZoneProfile"
```

---

### Task 8: End-to-end manual test

No automated tests exist for this UI. Verify the full flow manually.

- [ ] **Step 1: Test "Add User" → close without saving**

1. Click "+ Add User". Modal opens on Upload tab.
2. Click ✕ (close). Profile row disappears from list. Verify with `GET /api/config/profiles` that it was deleted.

- [ ] **Step 2: Test "Add User" → upload + parse → save**

1. Click "+ Add User". Modal opens on Upload tab.
2. Select a `.pdf` or `.md` resume file. File uploads immediately; Parse enables.
3. Click Parse. Edit tab activates with fields populated. Profile Name field populated.
4. Edit the Profile Name if desired. Click Save. Row name label updates. Modal stays open (not new anymore).
5. Click ✕. Modal closes. Row remains with correct name.

- [ ] **Step 3: Test Edit existing profile**

1. Click Edit on an existing profile row. Modal opens on Edit tab with fields populated.
2. Change the Profile Name. Click Save. Row label updates.
3. Click ✕. Modal closes. Row still shows updated name.

- [ ] **Step 4: Test PDF/MD tabs on existing profile with files**

1. Open Edit on a profile that has `resume_path` set to a valid `.pdf`. PDF tab is visible; click it. PDF loads in iframe.
2. Open Edit on a profile with `md_path` set. MD tab is visible; click it. Markdown text loads.

- [ ] **Step 5: Test active profile save**

1. Select a radio on a profile row. Click the outer Save button. Status shows "Active profile set ✓".

- [ ] **Step 6: Commit if any fixes were needed**

```bash
git add web/static/config.html
git commit -m "[fix] Post-refactor corrections from manual test"
```
