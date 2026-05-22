# Settings User Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Settings widget User tab into an accordion-based read-only profile view with per-section modals and per-item overlays for editing.

**Architecture:** `ProfileDetailView` and all section sub-components are extracted into a new `ProfileDetail.jsx` file. `ProfileDetailView` holds the full profile as local state, fetches on mount, and provides `onSave(patch)` and `onSaveLlm(...)` callbacks that merge patches optimistically. The existing `PUT /api/config/profiles/{id}` endpoint handles all saves.

**Tech Stack:** React 18, Framer Motion, Tailwind CSS (space-* theme), FastAPI backend, SQLAlchemy User model.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `core/user.py` | Modify | Add 6 new profile fields to `_hydrate` and `_to_dict` |
| `tests/core/test_user.py` | Modify | Tests for new fields |
| `react-dashboard/src/components/widgets/ProfileDetail.jsx` | Create | All profile detail UI (AccordionSection, ItemOverlay, all sections) |
| `react-dashboard/src/components/widgets/Settings.jsx` | Modify | Replace inline `ProfileDetailView` with import from ProfileDetail.jsx |

---

## Task 1: Backend — add new profile fields

**Files:**
- Modify: `core/user.py`
- Modify: `tests/core/test_user.py`

New fields: `website` (string), `prompt_scoring`, `prompt_resume`, `prompt_cover`, `prompt_extraction`, `prompt_intake` (all strings).

- [ ] **Step 1: Write failing tests**

Add to `tests/core/test_user.py`:

```python
def test_user_hydrates_new_fields_from_data(db_session):
    from core.user import User
    data = {
        **SAMPLE_DATA,
        "website": "https://example.com",
        "prompt_scoring": "custom scoring prompt",
        "prompt_resume": "custom resume prompt",
        "prompt_cover": "custom cover prompt",
        "prompt_extraction": "custom extraction prompt",
        "prompt_intake": "custom intake prompt",
    }
    db_session.add(User(name="Matt", data=json.dumps(data)))
    db_session.commit()
    user = User.load(db_session)
    assert user.website == "https://example.com"
    assert user.prompt_scoring == "custom scoring prompt"
    assert user.prompt_resume == "custom resume prompt"
    assert user.prompt_cover == "custom cover prompt"
    assert user.prompt_extraction == "custom extraction prompt"
    assert user.prompt_intake == "custom intake prompt"


def test_user_hydrates_new_fields_default_to_empty(db_session):
    from core.user import User
    db_session.add(User(name="Matt", data=json.dumps(SAMPLE_DATA)))
    db_session.commit()
    user = User.load(db_session)
    assert user.website == ""
    assert user.prompt_scoring == ""
    assert user.prompt_resume == ""
    assert user.prompt_cover == ""
    assert user.prompt_extraction == ""
    assert user.prompt_intake == ""


def test_user_to_dict_includes_new_fields(db_session):
    from core.user import User
    data = {**SAMPLE_DATA, "website": "https://portfolio.dev", "prompt_resume": "my prompt"}
    db_session.add(User(name="Matt", data=json.dumps(data)))
    db_session.commit()
    user = User.load(db_session)
    serialized = user._to_dict()
    assert serialized["website"] == "https://portfolio.dev"
    assert serialized["prompt_resume"] == "my prompt"
    assert "prompt_scoring" in serialized
    assert "prompt_cover" in serialized
    assert "prompt_extraction" in serialized
    assert "prompt_intake" in serialized
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd C:\Users\barlo\Projects\auto_apply
python -m pytest tests/core/test_user.py::test_user_hydrates_new_fields_from_data tests/core/test_user.py::test_user_hydrates_new_fields_default_to_empty tests/core/test_user.py::test_user_to_dict_includes_new_fields -v
```

Expected: 3 FAILED (AttributeError: 'User' object has no attribute 'website')

- [ ] **Step 3: Add fields to `_hydrate` and `_to_dict` in `core/user.py`**

In `_hydrate`, after the `self.github = ...` line, add:

```python
        self.website = raw.get("website", "")
        self.prompt_scoring = raw.get("prompt_scoring", "")
        self.prompt_resume = raw.get("prompt_resume", "")
        self.prompt_cover = raw.get("prompt_cover", "")
        self.prompt_extraction = raw.get("prompt_extraction", "")
        self.prompt_intake = raw.get("prompt_intake", "")
```

In `_to_dict`, after the `"github": self.github,` line, add:

```python
            "website": self.website,
            "prompt_scoring": self.prompt_scoring,
            "prompt_resume": self.prompt_resume,
            "prompt_cover": self.prompt_cover,
            "prompt_extraction": self.prompt_extraction,
            "prompt_intake": self.prompt_intake,
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/core/test_user.py::test_user_hydrates_new_fields_from_data tests/core/test_user.py::test_user_hydrates_new_fields_default_to_empty tests/core/test_user.py::test_user_to_dict_includes_new_fields -v
```

Expected: 3 PASSED

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
python -m pytest tests/ -v
```

Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add core/user.py tests/core/test_user.py
git commit -m "[feat] Add website and prompt fields to User profile model"
```

---

## Task 2: Scaffold ProfileDetail.jsx

**Files:**
- Create: `react-dashboard/src/components/widgets/ProfileDetail.jsx`
- Modify: `react-dashboard/src/components/widgets/Settings.jsx`

This task creates the file skeleton: shared primitives, `ProfileDetailView` with fetch/state, and wires it into Settings.jsx replacing the existing inline `ProfileDetailView`.

- [ ] **Step 1: Create `react-dashboard/src/components/widgets/ProfileDetail.jsx`**

```jsx
import { useState, useEffect, useRef } from 'react'
import { getProfile, updateProfile } from '../../api'

// ─── Shared ────────────────────────────────────────────────────────────────────

export const inputClass =
  'w-full bg-white/5 border border-space-border rounded-lg px-3 py-2 text-sm text-space-text placeholder-space-dim focus:outline-none focus:border-purple-500 transition-colors'

const PROVIDER_TYPES = ['openrouter', 'anthropic', 'openai', 'gemini']

function ChevronDown({ open }) {
  return (
    <svg
      width="12" height="12" viewBox="0 0 12 12" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      style={{ transform: open ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}
    >
      <path d="M2 4l4 4 4-4" />
    </svg>
  )
}

// ─── AccordionSection ──────────────────────────────────────────────────────────

function AccordionSection({ title, editButton, children }) {
  const [open, setOpen] = useState(true)
  return (
    <div className="border border-space-border rounded-lg overflow-hidden">
      <div
        className="flex items-center justify-between px-3 py-2.5 bg-white/[0.03] cursor-pointer select-none"
        onClick={() => setOpen(o => !o)}
      >
        <span className="text-xs font-semibold uppercase tracking-widest text-space-dim">{title}</span>
        <div className="flex items-center gap-2" onClick={e => e.stopPropagation()}>
          {editButton}
          <span className="text-space-dim pointer-events-none">
            <ChevronDown open={open} />
          </span>
        </div>
      </div>
      {open && <div className="p-3">{children}</div>}
    </div>
  )
}

// ─── ItemOverlay ───────────────────────────────────────────────────────────────

function ItemOverlay({ title, onClose, onSave, saving, error, children }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#0f0f1a] border border-space-border rounded-xl w-[90%] max-w-md max-h-[80vh] flex flex-col shadow-2xl">
        <div className="flex items-center justify-between px-4 py-3 border-b border-space-border shrink-0">
          <span className="text-sm font-semibold text-space-text">{title}</span>
          <button onClick={onClose} className="text-space-dim hover:text-space-text text-lg leading-none">×</button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3">{children}</div>
        <div className="px-4 py-3 border-t border-space-border shrink-0 flex flex-col gap-2">
          {error && <p className="text-xs text-red-400">{error}</p>}
          <div className="flex gap-2">
            <button
              onClick={onSave}
              disabled={saving}
              className="flex-1 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-sm font-semibold transition-colors"
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-lg border border-space-border text-sm text-space-dim hover:text-space-text transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function EditBtn({ onClick }) {
  return (
    <button
      onClick={onClick}
      className="px-2 py-0.5 rounded text-xs text-space-dim border border-space-border hover:text-space-text hover:border-purple-500/50 transition-colors"
    >
      Edit
    </button>
  )
}

function Field({ label, value }) {
  if (!value) return null
  return (
    <div>
      <p className="text-xs text-space-dim">{label}</p>
      <p className="text-xs text-space-text">{value}</p>
    </div>
  )
}

// ─── Placeholder section components (filled in subsequent tasks) ───────────────

function IdentitySection({ data, onSave }) { return null }
function SkillsSection({ data, onSave }) { return null }
function ExperienceSection({ data, onSave }) { return null }
function EducationSection({ data, onSave }) { return null }
function ProjectsSection({ data, onSave }) { return null }
function JobPrefsSection({ data, onSave }) { return null }
function PromptsSection({ data, onSave }) { return null }
function LlmSection({ profile, onSave }) { return null }

// ─── ProfileDetailView ─────────────────────────────────────────────────────────

const PROFILE_DATA_DEFAULTS = {
  first_name: '', last_name: '', hero: '', email: '', phone: '',
  location: '', linkedin: '', github: '', website: '',
  skills: [], work_history: [], education: [], projects: [],
  target_roles: [], target_salary_min: null, target_salary_max: null,
  prompt_scoring: '', prompt_resume: '', prompt_cover: '',
  prompt_extraction: '', prompt_intake: '',
}

export default function ProfileDetailView({ profileId }) {
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    getProfile(profileId)
      .then(raw => setProfile({ ...raw, data: { ...PROFILE_DATA_DEFAULTS, ...raw.data } }))
      .catch(() => setError('Failed to load profile'))
      .finally(() => setLoading(false))
  }, [profileId])

  const handleSave = async (patch) => {
    const newData = { ...profile.data, ...patch }
    await updateProfile(profileId, { name: profile.name, data: newData })
    setProfile(p => ({ ...p, data: newData }))
  }

  const handleSaveLlm = async ({ providerType, model, apiKey }) => {
    const newData = { ...profile.data, llm_provider_type: providerType, llm_model: model }
    const body = { name: profile.name, data: newData }
    if (apiKey) body.llm_api_key = apiKey
    await updateProfile(profileId, body)
    setProfile(p => ({ ...p, data: newData, llm_provider_type: providerType, llm_model: model }))
  }

  if (loading) return <p className="text-xs text-space-dim">Loading…</p>
  if (error) return <p className="text-xs text-red-400">{error}</p>

  const d = profile.data

  return (
    <div className="flex flex-col gap-3">
      <IdentitySection data={d} onSave={handleSave} />
      <SkillsSection data={d} onSave={handleSave} />
      <ExperienceSection data={d} onSave={handleSave} />
      <EducationSection data={d} onSave={handleSave} />
      <ProjectsSection data={d} onSave={handleSave} />
      <JobPrefsSection data={d} onSave={handleSave} />
      <PromptsSection data={d} onSave={handleSave} />
      <LlmSection profile={profile} onSave={handleSaveLlm} />
    </div>
  )
}
```

- [ ] **Step 2: Update `Settings.jsx` — replace inline ProfileDetailView with import**

At the top of `Settings.jsx`, add the import after the existing imports:

```jsx
import ProfileDetailView from './ProfileDetail'
```

Find the `ProfileDetailView` function definition (starting around line 406) and delete it entirely (lines 406–544 in the current file). The component is now imported.

Also delete the `PROVIDER_TYPES` constant at line 404 — it moves to ProfileDetail.jsx.

- [ ] **Step 3: Verify the app still runs**

```bash
cd react-dashboard && npm run dev
```

Open the Settings widget → User tab → click a profile. Should load without errors (sections are all null/empty — this is expected). Check browser console for no import errors.

- [ ] **Step 4: Commit**

```bash
git add react-dashboard/src/components/widgets/ProfileDetail.jsx react-dashboard/src/components/widgets/Settings.jsx
git commit -m "[feat] Scaffold ProfileDetail.jsx, wire Settings.jsx to import it"
```

---

## Task 3: Identity section

**Files:**
- Modify: `react-dashboard/src/components/widgets/ProfileDetail.jsx`

Replace the stub `function IdentitySection` with the full implementation.

- [ ] **Step 1: Replace `function IdentitySection` stub in ProfileDetail.jsx**

```jsx
function IdentitySection({ data, onSave }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const openModal = () => {
    setForm({
      first_name: data.first_name || '',
      last_name: data.last_name || '',
      hero: data.hero || '',
      location: data.location || '',
      email: data.email || '',
      phone: data.phone || '',
      linkedin: data.linkedin || '',
      github: data.github || '',
      website: data.website || '',
    })
    setError(null)
    setOpen(true)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await onSave(form)
      setOpen(false)
    } catch {
      setError('Save failed')
    } finally {
      setSaving(false)
    }
  }

  const f = (label, key, type = 'text') => (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-space-dim">{label}</label>
      <input
        type={type}
        className={inputClass}
        value={form[key] ?? ''}
        onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
      />
    </div>
  )

  const fullName = [data.first_name, data.last_name].filter(Boolean).join(' ')

  return (
    <>
      <AccordionSection title="Identity" editButton={<EditBtn onClick={openModal} />}>
        <div className="flex flex-col gap-1.5">
          {fullName && <p className="text-sm font-medium text-space-text">{fullName}</p>}
          {data.hero && <p className="text-xs text-space-dim italic">{data.hero}</p>}
          <Field label="Email" value={data.email} />
          <Field label="Phone" value={data.phone} />
          <Field label="Location" value={data.location} />
          {data.linkedin && <Field label="LinkedIn" value={data.linkedin} />}
          {data.github && <Field label="GitHub" value={data.github} />}
          {data.website && <Field label="Website" value={data.website} />}
          {!fullName && !data.email && <p className="text-xs text-space-dim">No identity info yet.</p>}
        </div>
      </AccordionSection>

      {open && (
        <ItemOverlay title="Edit Identity" onClose={() => setOpen(false)} onSave={handleSave} saving={saving} error={error}>
          <p className="text-xs font-semibold uppercase tracking-widest text-space-dim">Personal</p>
          {f('First Name', 'first_name')}
          {f('Last Name', 'last_name')}
          {f('Tagline / Hero', 'hero')}
          {f('Location', 'location')}
          <hr className="border-space-border" />
          <p className="text-xs font-semibold uppercase tracking-widest text-space-dim">Contact</p>
          {f('Email', 'email', 'email')}
          {f('Phone', 'phone', 'tel')}
          <hr className="border-space-border" />
          <p className="text-xs font-semibold uppercase tracking-widest text-space-dim">Socials</p>
          {f('LinkedIn URL', 'linkedin', 'url')}
          {f('GitHub URL', 'github', 'url')}
          {f('Website URL', 'website', 'url')}
        </ItemOverlay>
      )}
    </>
  )
}
```

- [ ] **Step 2: Verify in browser**

Open the User tab, click a profile, expand Identity. Should show existing profile data. Click Edit — modal opens with 3 subsections. Fill a field, click Save. Data should update in the accordion without re-fetching.

- [ ] **Step 3: Commit**

```bash
git add react-dashboard/src/components/widgets/ProfileDetail.jsx
git commit -m "[feat] Add Identity accordion section with edit modal"
```

---

## Task 4: Skills section

**Files:**
- Modify: `react-dashboard/src/components/widgets/ProfileDetail.jsx`

Replace the stub `function SkillsSection`.

- [ ] **Step 1: Replace `function SkillsSection` stub**

```jsx
function SkillsSection({ data, onSave }) {
  const [overlayOpen, setOverlayOpen] = useState(false)
  const [editingIndex, setEditingIndex] = useState(null)
  const [inputVal, setInputVal] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const skills = data.skills || []

  const openAdd = () => { setEditingIndex(null); setInputVal(''); setError(null); setOverlayOpen(true) }
  const openEdit = (i) => { setEditingIndex(i); setInputVal(skills[i]); setError(null); setOverlayOpen(true) }

  const handleSave = async () => {
    const val = inputVal.trim()
    if (!val) { setError('Skill cannot be empty'); return }
    let updated
    if (editingIndex === null) {
      if (skills.includes(val)) { setError('Skill already exists'); return }
      updated = [...skills, val]
    } else {
      updated = skills.map((s, i) => i === editingIndex ? val : s)
    }
    setSaving(true)
    try {
      await onSave({ skills: updated })
      setOverlayOpen(false)
    } catch {
      setError('Save failed')
    } finally {
      setSaving(false)
    }
  }

  const handleRemove = async (i) => {
    const updated = skills.filter((_, idx) => idx !== i)
    await onSave({ skills: updated })
  }

  return (
    <>
      <AccordionSection title="Skills">
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap gap-1.5">
            {skills.map((s, i) => (
              <div key={i} className="flex items-center gap-1 bg-white/5 border border-space-border rounded-full px-2.5 py-0.5">
                <button
                  onClick={() => openEdit(i)}
                  className="text-xs text-space-text hover:text-purple-400 transition-colors"
                >
                  {s}
                </button>
                <button
                  onClick={() => handleRemove(i)}
                  className="text-space-dim hover:text-red-400 text-xs leading-none transition-colors"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
          {skills.length === 0 && <p className="text-xs text-space-dim">No skills added yet.</p>}
          <button
            onClick={openAdd}
            className="self-start text-xs text-space-dim hover:text-space-text border border-space-border hover:border-purple-500/50 rounded px-2 py-1 transition-colors"
          >
            + Add Skill
          </button>
        </div>
      </AccordionSection>

      {overlayOpen && (
        <ItemOverlay
          title={editingIndex === null ? 'Add Skill' : 'Edit Skill'}
          onClose={() => setOverlayOpen(false)}
          onSave={handleSave}
          saving={saving}
          error={error}
        >
          <div className="flex flex-col gap-1">
            <label className="text-xs text-space-dim">Skill</label>
            <input
              autoFocus
              className={inputClass}
              value={inputVal}
              onChange={e => setInputVal(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSave()}
              placeholder="e.g. Python"
            />
          </div>
        </ItemOverlay>
      )}
    </>
  )
}
```

- [ ] **Step 2: Verify in browser**

Skills accordion shows chips. Click a chip name to edit, × to remove. "+ Add Skill" opens overlay. Duplicate check works.

- [ ] **Step 3: Commit**

```bash
git add react-dashboard/src/components/widgets/ProfileDetail.jsx
git commit -m "[feat] Add Skills accordion section"
```

---

## Task 5: Experience section

**Files:**
- Modify: `react-dashboard/src/components/widgets/ProfileDetail.jsx`

Replace the stub `function ExperienceSection`.

- [ ] **Step 1: Replace `function ExperienceSection` stub**

```jsx
const EMPTY_EXPERIENCE = { company: '', title: '', start: '', end: '', summary: '' }

function ExperienceSection({ data, onSave }) {
  const [overlayOpen, setOverlayOpen] = useState(false)
  const [editingIndex, setEditingIndex] = useState(null)
  const [form, setForm] = useState(EMPTY_EXPERIENCE)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const items = data.work_history || []

  const openAdd = () => { setEditingIndex(null); setForm(EMPTY_EXPERIENCE); setError(null); setOverlayOpen(true) }
  const openEdit = (i) => { setEditingIndex(i); setForm({ ...items[i] }); setError(null); setOverlayOpen(true) }

  const handleSave = async () => {
    if (!form.company.trim() || !form.title.trim()) { setError('Company and title are required'); return }
    const updated = editingIndex === null
      ? [...items, form]
      : items.map((item, i) => i === editingIndex ? form : item)
    setSaving(true)
    try {
      await onSave({ work_history: updated })
      setOverlayOpen(false)
    } catch {
      setError('Save failed')
    } finally {
      setSaving(false)
    }
  }

  const handleRemove = async (i) => {
    await onSave({ work_history: items.filter((_, idx) => idx !== i) })
  }

  const f = (label, key, multiline = false) => (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-space-dim">{label}</label>
      {multiline
        ? <textarea rows={3} className={inputClass + ' resize-none'} value={form[key] ?? ''} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} />
        : <input className={inputClass} value={form[key] ?? ''} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} />
      }
    </div>
  )

  return (
    <>
      <AccordionSection title="Experience">
        <div className="flex flex-col gap-2">
          {items.map((item, i) => (
            <div key={i} className="flex items-start justify-between gap-2 rounded-lg px-3 py-2.5 bg-white/[0.03] border border-white/5">
              <div className="min-w-0">
                <p className="text-sm font-medium text-space-text truncate">{item.title}</p>
                <p className="text-xs text-space-dim">{item.company} · {item.start}–{item.end}</p>
              </div>
              <div className="flex gap-1 shrink-0">
                <EditBtn onClick={() => openEdit(i)} />
                <button onClick={() => handleRemove(i)} className="px-2 py-0.5 rounded text-xs text-space-dim border border-space-border hover:text-red-400 transition-colors">✕</button>
              </div>
            </div>
          ))}
          {items.length === 0 && <p className="text-xs text-space-dim">No experience added yet.</p>}
          <button onClick={openAdd} className="self-start text-xs text-space-dim hover:text-space-text border border-space-border hover:border-purple-500/50 rounded px-2 py-1 transition-colors">
            + Add Experience
          </button>
        </div>
      </AccordionSection>

      {overlayOpen && (
        <ItemOverlay
          title={editingIndex === null ? 'Add Experience' : 'Edit Experience'}
          onClose={() => setOverlayOpen(false)}
          onSave={handleSave}
          saving={saving}
          error={error}
        >
          {f('Company', 'company')}
          {f('Title', 'title')}
          {f('Start (e.g. 2022-01)', 'start')}
          {f('End (e.g. Present)', 'end')}
          {f('Summary', 'summary', true)}
        </ItemOverlay>
      )}
    </>
  )
}
```

- [ ] **Step 2: Verify in browser**

Experience accordion shows work history cards. Add, edit, remove all work. Summary textarea renders correctly.

- [ ] **Step 3: Commit**

```bash
git add react-dashboard/src/components/widgets/ProfileDetail.jsx
git commit -m "[feat] Add Experience accordion section"
```

---

## Task 6: Education section

**Files:**
- Modify: `react-dashboard/src/components/widgets/ProfileDetail.jsx`

Replace the stub `function EducationSection`.

- [ ] **Step 1: Replace `function EducationSection` stub**

```jsx
const EMPTY_EDUCATION = { institution: '', degree: '', field: '', graduated: '', gpa: '' }

function EducationSection({ data, onSave }) {
  const [overlayOpen, setOverlayOpen] = useState(false)
  const [editingIndex, setEditingIndex] = useState(null)
  const [form, setForm] = useState(EMPTY_EDUCATION)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const items = data.education || []

  const openAdd = () => { setEditingIndex(null); setForm(EMPTY_EDUCATION); setError(null); setOverlayOpen(true) }
  const openEdit = (i) => { setEditingIndex(i); setForm({ ...items[i], gpa: String(items[i].gpa ?? '') }); setError(null); setOverlayOpen(true) }

  const handleSave = async () => {
    if (!form.institution.trim()) { setError('Institution is required'); return }
    const entry = { ...form, gpa: parseFloat(form.gpa) || 0 }
    const updated = editingIndex === null
      ? [...items, entry]
      : items.map((item, i) => i === editingIndex ? entry : item)
    setSaving(true)
    try {
      await onSave({ education: updated })
      setOverlayOpen(false)
    } catch {
      setError('Save failed')
    } finally {
      setSaving(false)
    }
  }

  const handleRemove = async (i) => {
    await onSave({ education: items.filter((_, idx) => idx !== i) })
  }

  const f = (label, key) => (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-space-dim">{label}</label>
      <input className={inputClass} value={form[key] ?? ''} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} />
    </div>
  )

  return (
    <>
      <AccordionSection title="Education">
        <div className="flex flex-col gap-2">
          {items.map((item, i) => (
            <div key={i} className="flex items-start justify-between gap-2 rounded-lg px-3 py-2.5 bg-white/[0.03] border border-white/5">
              <div className="min-w-0">
                <p className="text-sm font-medium text-space-text truncate">{item.degree} in {item.field}</p>
                <p className="text-xs text-space-dim">{item.institution} · {item.graduated}{item.gpa ? ` · GPA ${item.gpa}` : ''}</p>
              </div>
              <div className="flex gap-1 shrink-0">
                <EditBtn onClick={() => openEdit(i)} />
                <button onClick={() => handleRemove(i)} className="px-2 py-0.5 rounded text-xs text-space-dim border border-space-border hover:text-red-400 transition-colors">✕</button>
              </div>
            </div>
          ))}
          {items.length === 0 && <p className="text-xs text-space-dim">No education added yet.</p>}
          <button onClick={openAdd} className="self-start text-xs text-space-dim hover:text-space-text border border-space-border hover:border-purple-500/50 rounded px-2 py-1 transition-colors">
            + Add Education
          </button>
        </div>
      </AccordionSection>

      {overlayOpen && (
        <ItemOverlay
          title={editingIndex === null ? 'Add Education' : 'Edit Education'}
          onClose={() => setOverlayOpen(false)}
          onSave={handleSave}
          saving={saving}
          error={error}
        >
          {f('Institution', 'institution')}
          {f('Degree (e.g. B.S.)', 'degree')}
          {f('Field of Study', 'field')}
          {f('Graduated (e.g. 2018)', 'graduated')}
          {f('GPA', 'gpa')}
        </ItemOverlay>
      )}
    </>
  )
}
```

- [ ] **Step 2: Verify in browser**

Education cards show degree/field/institution. Add, edit, remove. GPA is stored as float but edited as string.

- [ ] **Step 3: Commit**

```bash
git add react-dashboard/src/components/widgets/ProfileDetail.jsx
git commit -m "[feat] Add Education accordion section"
```

---

## Task 7: Projects section

**Files:**
- Modify: `react-dashboard/src/components/widgets/ProfileDetail.jsx`

Replace the stub `function ProjectsSection`.

- [ ] **Step 1: Replace `function ProjectsSection` stub**

```jsx
const EMPTY_PROJECT = { name: '', description: '', url: '', technologies: [] }

function ProjectsSection({ data, onSave }) {
  const [overlayOpen, setOverlayOpen] = useState(false)
  const [editingIndex, setEditingIndex] = useState(null)
  const [form, setForm] = useState(EMPTY_PROJECT)
  const [techInput, setTechInput] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const items = data.projects || []

  const openAdd = () => {
    setEditingIndex(null); setForm(EMPTY_PROJECT)
    setTechInput(''); setError(null); setOverlayOpen(true)
  }
  const openEdit = (i) => {
    setEditingIndex(i)
    setForm({ ...items[i], technologies: [...(items[i].technologies || [])] })
    setTechInput((items[i].technologies || []).join(', '))
    setError(null); setOverlayOpen(true)
  }

  const handleSave = async () => {
    if (!form.name.trim()) { setError('Project name is required'); return }
    const technologies = techInput.split(',').map(t => t.trim()).filter(Boolean)
    const entry = { ...form, technologies }
    const updated = editingIndex === null
      ? [...items, entry]
      : items.map((item, i) => i === editingIndex ? entry : item)
    setSaving(true)
    try {
      await onSave({ projects: updated })
      setOverlayOpen(false)
    } catch {
      setError('Save failed')
    } finally {
      setSaving(false)
    }
  }

  const handleRemove = async (i) => {
    await onSave({ projects: items.filter((_, idx) => idx !== i) })
  }

  const f = (label, key, multiline = false) => (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-space-dim">{label}</label>
      {multiline
        ? <textarea rows={3} className={inputClass + ' resize-none'} value={form[key] ?? ''} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} />
        : <input className={inputClass} value={form[key] ?? ''} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} />
      }
    </div>
  )

  return (
    <>
      <AccordionSection title="Projects">
        <div className="flex flex-col gap-2">
          {items.map((item, i) => (
            <div key={i} className="flex items-start justify-between gap-2 rounded-lg px-3 py-2.5 bg-white/[0.03] border border-white/5">
              <div className="min-w-0">
                <p className="text-sm font-medium text-space-text truncate">{item.name}</p>
                {item.technologies?.length > 0 && (
                  <p className="text-xs text-space-dim truncate">{item.technologies.join(', ')}</p>
                )}
              </div>
              <div className="flex gap-1 shrink-0">
                <EditBtn onClick={() => openEdit(i)} />
                <button onClick={() => handleRemove(i)} className="px-2 py-0.5 rounded text-xs text-space-dim border border-space-border hover:text-red-400 transition-colors">✕</button>
              </div>
            </div>
          ))}
          {items.length === 0 && <p className="text-xs text-space-dim">No projects added yet.</p>}
          <button onClick={openAdd} className="self-start text-xs text-space-dim hover:text-space-text border border-space-border hover:border-purple-500/50 rounded px-2 py-1 transition-colors">
            + Add Project
          </button>
        </div>
      </AccordionSection>

      {overlayOpen && (
        <ItemOverlay
          title={editingIndex === null ? 'Add Project' : 'Edit Project'}
          onClose={() => setOverlayOpen(false)}
          onSave={handleSave}
          saving={saving}
          error={error}
        >
          {f('Project Name', 'name')}
          {f('Description', 'description', true)}
          {f('URL', 'url')}
          <div className="flex flex-col gap-1">
            <label className="text-xs text-space-dim">Technologies (comma-separated)</label>
            <input
              className={inputClass}
              value={techInput}
              onChange={e => setTechInput(e.target.value)}
              placeholder="e.g. Python, React, Docker"
            />
          </div>
        </ItemOverlay>
      )}
    </>
  )
}
```

- [ ] **Step 2: Verify in browser**

Projects cards show name + technologies. Technologies are comma-separated on input, stored as array. Add, edit, remove all work.

- [ ] **Step 3: Commit**

```bash
git add react-dashboard/src/components/widgets/ProfileDetail.jsx
git commit -m "[feat] Add Projects accordion section"
```

---

## Task 8: Job Preferences section

**Files:**
- Modify: `react-dashboard/src/components/widgets/ProfileDetail.jsx`

Replace the stub `function JobPrefsSection`.

- [ ] **Step 1: Replace `function JobPrefsSection` stub**

```jsx
function JobPrefsSection({ data, onSave }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({})
  const [rolesInput, setRolesInput] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const openModal = () => {
    setForm({
      target_salary_min: data.target_salary_min ?? '',
      target_salary_max: data.target_salary_max ?? '',
    })
    setRolesInput((data.target_roles || []).join(', '))
    setError(null)
    setOpen(true)
  }

  const handleSave = async () => {
    const target_roles = rolesInput.split(',').map(r => r.trim()).filter(Boolean)
    const patch = {
      target_roles,
      target_salary_min: form.target_salary_min !== '' ? Number(form.target_salary_min) : null,
      target_salary_max: form.target_salary_max !== '' ? Number(form.target_salary_max) : null,
    }
    setSaving(true)
    try {
      await onSave(patch)
      setOpen(false)
    } catch {
      setError('Save failed')
    } finally {
      setSaving(false)
    }
  }

  const salaryStr = data.target_salary_min != null && data.target_salary_max != null
    ? `$${data.target_salary_min.toLocaleString()} – $${data.target_salary_max.toLocaleString()}`
    : data.target_salary_min != null ? `From $${data.target_salary_min.toLocaleString()}` : null

  return (
    <>
      <AccordionSection title="Job Preferences" editButton={<EditBtn onClick={openModal} />}>
        <div className="flex flex-col gap-1.5">
          {(data.target_roles || []).length > 0 && (
            <Field label="Target Roles" value={data.target_roles.join(', ')} />
          )}
          {salaryStr && <Field label="Target Salary" value={salaryStr} />}
          {!(data.target_roles?.length) && !salaryStr && (
            <p className="text-xs text-space-dim">No preferences set yet.</p>
          )}
        </div>
      </AccordionSection>

      {open && (
        <ItemOverlay title="Job Preferences" onClose={() => setOpen(false)} onSave={handleSave} saving={saving} error={error}>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-space-dim">Target Roles (comma-separated)</label>
            <input
              className={inputClass}
              value={rolesInput}
              onChange={e => setRolesInput(e.target.value)}
              placeholder="e.g. Backend Engineer, Staff Engineer"
            />
          </div>
          <div className="flex gap-2">
            <div className="flex flex-col gap-1 flex-1">
              <label className="text-xs text-space-dim">Salary Min ($)</label>
              <input
                type="number"
                className={inputClass}
                value={form.target_salary_min ?? ''}
                onChange={e => setForm(f => ({ ...f, target_salary_min: e.target.value }))}
                placeholder="120000"
              />
            </div>
            <div className="flex flex-col gap-1 flex-1">
              <label className="text-xs text-space-dim">Salary Max ($)</label>
              <input
                type="number"
                className={inputClass}
                value={form.target_salary_max ?? ''}
                onChange={e => setForm(f => ({ ...f, target_salary_max: e.target.value }))}
                placeholder="160000"
              />
            </div>
          </div>
        </ItemOverlay>
      )}
    </>
  )
}
```

- [ ] **Step 2: Verify in browser**

Job Preferences accordion shows salary range and target roles. Edit modal shows comma-separated roles and min/max salary inputs.

- [ ] **Step 3: Commit**

```bash
git add react-dashboard/src/components/widgets/ProfileDetail.jsx
git commit -m "[feat] Add Job Preferences accordion section"
```

---

## Task 9: Prompts section

**Files:**
- Modify: `react-dashboard/src/components/widgets/ProfileDetail.jsx`

Replace the stub `function PromptsSection`. Add `DEFAULT_PROMPTS` constant above it.

- [ ] **Step 1: Add `DEFAULT_PROMPTS` constant and replace `function PromptsSection` stub**

Add `DEFAULT_PROMPTS` immediately above the `PromptsSection` function definition:

```jsx
const DEFAULT_PROMPTS = {
  prompt_scoring: `You are evaluating a job posting for a candidate. Score the job on two dimensions.

## Candidate Profile
Name: {user.first_name} {user.last_name}
Skills: {user.skills}
Target roles: {user.target_roles}
Target salary: ${'{'}user.target_salary_min{'}'} – ${'{'}user.target_salary_max{'}'}

Work History:
{user.work_history}

Education:
{user.education}

## Job Posting
Title: {job.title}
Company: {job.company}
Location: {job.location}
Salary: {job.salary}
Description:
{job.description}

## Instructions
Return ONLY a JSON object with exactly these four keys:
- desirability_score: float 0.0–1.0 (how much the candidate would want this job)
- fit_score: float 0.0–1.0 (how well the candidate matches the job requirements)
- desirability_justification: string (1–2 sentences explaining desirability score)
- fit_justification: string (1–2 sentences explaining fit score)

Consider for desirability: salary vs target, remote/location fit, role alignment, company quality.
Consider for fit: required skills vs candidate skills, experience level, education requirements.

Return only the JSON object, no other text.`,

  prompt_resume: `You are writing a tailored one-page resume in Markdown for a job application.

# Candidate Profile
{profile}

# Job Posting
{job}

# Instructions
- Output ONLY the resume Markdown body. No preamble, no explanation.
- Do NOT include a name or contact block — those are handled separately.
- Start directly with the first section header (e.g. ## Profile).
- Do not use \`---\` horizontal rules between sections.
- Do not invent experience or skills not in the candidate profile.
- Drop the Soft Skills section entirely.

## Profile
- Max 500 characters total.

## Education
- Always include all degrees exactly as written. No bullets.

## Experience
- Always include all entries.
- Max 2 bullets per entry, each bullet max 120 characters.
- Stress skills and responsibilities directly mentioned in the job description.

## Projects
- Reorder by relevance to this job. Drop least relevant project(s) if needed.
- Always include at least 2, max 4 projects.
- 1 bullet per project, max 120 characters.

## Skills
- Always include Python, Git, Docker, SQL regardless of job description.
- Include only categories that have 2 or more relevant skills for this job.
- Max 6 categories.`,

  prompt_cover: `You are writing a concise cover letter in Markdown for a job application.

# Candidate Profile
{profile}

# Job Posting
{job}

# Instructions
- Output ONLY the cover letter Markdown. No preamble, no explanation.
- Do not use \`---\` horizontal rules anywhere in the output.
- Exactly 3 paragraphs: (1) fit and interest, (2) specific value-add tied to the job description, (3) close.
- Address it to the hiring team at the company listed in the job posting.
- Do not include a sign-off, name, or contact information at the end — those are added automatically.
- Do not invent experience or skills not in the candidate profile.`,

  prompt_extraction: `Extract structured data from the job description.

Job Title: {job.title}
Company: {job.company}
Description:
{job.description}

Return ONLY a JSON object with these keys:
- seniority: string (Junior/Mid/Senior/Lead/Staff/Principal/Director/VP)
- role_type: string (e.g. Backend Engineer, Frontend Engineer, ML Engineer)
- domain: string (e.g. FinTech, HealthTech, SaaS)
- work_arrangement: string (Remote/Hybrid/On-site)
- employment_type: string (Full-time/Part-time/Contract)
- required_skills: array of strings
- preferred_skills: array of strings
- tech_stack: array of strings
- key_responsibilities: array of strings (max 5)
- company_signals: array of strings (culture, growth, red flags)

Return only the JSON object, no other text.`,

  prompt_intake: `Review the newly scraped job posting and determine if it should be queued for scoring.

Job Title: {job.title}
Company: {job.company}
Location: {job.location}
Description:
{job.description}

Return ONLY a JSON object:
- should_score: boolean (true if the job is worth scoring)
- reason: string (brief explanation)

Return only the JSON object, no other text.`,
}

const PROMPT_LABELS = {
  prompt_scoring: 'Scoring',
  prompt_resume: 'Resume Generation',
  prompt_cover: 'Cover Letter Generation',
  prompt_extraction: 'Description Extraction',
  prompt_intake: 'Intake',
}

function PromptsSection({ data, onSave }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const promptKeys = Object.keys(DEFAULT_PROMPTS)

  const openModal = () => {
    const initial = {}
    promptKeys.forEach(k => { initial[k] = data[k] || '' })
    setForm(initial)
    setError(null)
    setOpen(true)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await onSave(form)
      setOpen(false)
    } catch {
      setError('Save failed')
    } finally {
      setSaving(false)
    }
  }

  const configuredCount = promptKeys.filter(k => data[k]).length

  return (
    <>
      <AccordionSection title="Prompts" editButton={<EditBtn onClick={openModal} />}>
        <div className="flex flex-col gap-1">
          {promptKeys.map(k => (
            <div key={k} className="flex items-center justify-between">
              <span className="text-xs text-space-dim">{PROMPT_LABELS[k]}</span>
              <span className={`text-xs font-medium ${data[k] ? 'text-green-400' : 'text-space-dim/50'}`}>
                {data[k] ? 'Custom' : 'Default'}
              </span>
            </div>
          ))}
          {configuredCount === 0 && (
            <p className="text-xs text-space-dim mt-1">All prompts using system defaults.</p>
          )}
        </div>
      </AccordionSection>

      {open && (
        <ItemOverlay title="Edit Prompts" onClose={() => setOpen(false)} onSave={handleSave} saving={saving} error={error}>
          {promptKeys.map(k => (
            <div key={k} className="flex flex-col gap-1">
              <div className="flex items-center justify-between">
                <label className="text-xs text-space-dim">{PROMPT_LABELS[k]}</label>
                <button
                  onClick={() => setForm(f => ({ ...f, [k]: DEFAULT_PROMPTS[k] }))}
                  className="text-xs text-purple-400 hover:text-purple-300 transition-colors"
                >
                  Reset to Default
                </button>
              </div>
              <textarea
                rows={4}
                className={inputClass + ' resize-y font-mono text-xs'}
                value={form[k] ?? ''}
                onChange={e => setForm(f => ({ ...f, [k]: e.target.value }))}
                placeholder={DEFAULT_PROMPTS[k].slice(0, 80) + '…'}
              />
            </div>
          ))}
        </ItemOverlay>
      )}
    </>
  )
}
```

- [ ] **Step 2: Verify in browser**

Prompts accordion shows each prompt name with "Custom" or "Default" status. Edit modal has 5 textareas. "Reset to Default" populates the field. Save persists to the API.

- [ ] **Step 3: Commit**

```bash
git add react-dashboard/src/components/widgets/ProfileDetail.jsx
git commit -m "[feat] Add Prompts accordion section with defaults"
```

---

## Task 10: LLM Config section

**Files:**
- Modify: `react-dashboard/src/components/widgets/ProfileDetail.jsx`

Replace the stub `function LlmSection`.

- [ ] **Step 1: Replace `function LlmSection` stub**

```jsx
function LlmSection({ profile, onSave }) {
  const [open, setOpen] = useState(false)
  const [providerType, setProviderType] = useState('')
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [keyEdited, setKeyEdited] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const openModal = () => {
    setProviderType(profile.llm_provider_type || '')
    setModel(profile.llm_model || '')
    setApiKey('')
    setKeyEdited(false)
    setError(null)
    setOpen(true)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await onSave({
        providerType,
        model,
        apiKey: keyEdited ? apiKey : '',
      })
      setOpen(false)
    } catch {
      setError('Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <AccordionSection title="LLM Config" editButton={<EditBtn onClick={openModal} />}>
        <div className="flex flex-col gap-1.5">
          {profile.llm_provider_type
            ? <Field label="Provider" value={profile.llm_provider_type} />
            : <p className="text-xs text-space-dim">No LLM provider configured.</p>
          }
          {profile.llm_model && <Field label="Model" value={profile.llm_model} />}
          <div className="flex items-center justify-between">
            <span className="text-xs text-space-dim">API Key</span>
            <span className={`text-xs font-medium ${profile.has_llm_key ? 'text-green-400' : 'text-space-dim/50'}`}>
              {profile.has_llm_key ? 'Configured' : 'Not set'}
            </span>
          </div>
        </div>
      </AccordionSection>

      {open && (
        <ItemOverlay title="LLM Config" onClose={() => setOpen(false)} onSave={handleSave} saving={saving} error={error}>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-space-dim">Provider</label>
            <select
              className={inputClass}
              value={providerType}
              onChange={e => setProviderType(e.target.value)}
            >
              <option value="">— select —</option>
              {PROVIDER_TYPES.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-space-dim">Model</label>
            <input
              className={inputClass}
              value={model}
              onChange={e => setModel(e.target.value)}
              placeholder="e.g. gpt-4o"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-space-dim">API Key</label>
            <input
              type="password"
              className={inputClass}
              value={!keyEdited && profile.has_llm_key ? '••••••••' : apiKey}
              onFocus={() => { if (!keyEdited && profile.has_llm_key) { setKeyEdited(true); setApiKey('') } }}
              onChange={e => { setKeyEdited(true); setApiKey(e.target.value) }}
              placeholder={profile.has_llm_key ? '' : 'Enter API key'}
            />
            {profile.has_llm_key && !keyEdited && (
              <p className="text-xs text-space-dim">Click to replace existing key</p>
            )}
          </div>
        </ItemOverlay>
      )}
    </>
  )
}
```

- [ ] **Step 2: Verify in browser**

LLM Config accordion shows provider/model/key status. Edit modal: provider dropdown, model input, API key shows ●●●●●●●● when key exists, clears on focus. Saving with blank key after focus does not overwrite (because `keyEdited` is true but `apiKey` is empty — `onSave` sends empty string, backend ignores blank `llm_api_key`).

- [ ] **Step 3: Commit**

```bash
git add react-dashboard/src/components/widgets/ProfileDetail.jsx
git commit -m "[feat] Add LLM Config accordion section"
```
