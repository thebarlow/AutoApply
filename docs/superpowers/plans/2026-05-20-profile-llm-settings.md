# Profile & LLM Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show profile cards on the User tab, add a profile detail view with personal fields and per-profile LLM provider config (stored in `.env`), and remove the Advanced tab.

**Architecture:** Backend extends the existing profile GET/PUT endpoints to expose and accept LLM provider fields (`llm_provider_type`, `llm_model` in profile data JSON; `llm_api_key` written to `.env` as `LLM_KEY_PROFILE_{id}`). Frontend rewrites the User tab into a profile card list and adds a detail view that replaces the Advanced tab.

**Tech Stack:** Python / FastAPI / SQLAlchemy (backend), React + Framer Motion (frontend), pytest / FastAPI TestClient (tests)

---

## File Map

| File | Change |
|---|---|
| `web/routers/config.py` | Extend `get_profile` response; add `llm_api_key` field to `ProfileBody` and write to `.env` in `update_profile` |
| `tests/web/test_profile_api.py` | Add tests for new LLM fields on GET and PUT |
| `react-dashboard/src/api.js` | Add `getProfile(id)` and `updateProfile(id, body)` |
| `react-dashboard/src/components/widgets/Settings.jsx` | Remove Advanced tab; rewrite UserTab as profile cards; add ProfileDetailView |

---

### Task 1: Extend GET `/api/config/profiles/{id}` to return LLM fields

**Files:**
- Modify: `web/routers/config.py` (function `get_profile`, ~line 649)
- Test: `tests/web/test_profile_api.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/web/test_profile_api.py`:

```python
def test_get_profile_includes_llm_fields(client, db_session):
    from core.user import User as UserProfileModel
    import json
    data = {
        "email": "", "phone": "", "location": "", "skills": [],
        "work_history": [], "education": [], "target_salary_min": None,
        "target_salary_max": None, "target_roles": [], "resume_path": "",
        "llm_provider_type": "openrouter", "llm_model": "gpt-4o",
    }
    row = UserProfileModel(name="Test", data=json.dumps(data))
    db_session.add(row)
    db_session.commit()

    resp = client.get(f"/api/config/profiles/{row.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["llm_provider_type"] == "openrouter"
    assert body["llm_model"] == "gpt-4o"
    assert body["has_llm_key"] is False


def test_get_profile_has_llm_key_true(client, db_session, monkeypatch, tmp_path):
    import web.routers.config as config_mod
    import json
    from pathlib import Path
    from core.user import User as UserProfileModel

    env_file = tmp_path / ".env"
    monkeypatch.setattr(config_mod, "_ENV_PATH", env_file)

    data = {"email": "", "phone": "", "location": "", "skills": [],
            "work_history": [], "education": [], "target_salary_min": None,
            "target_salary_max": None, "target_roles": [], "resume_path": "",
            "llm_provider_type": "anthropic", "llm_model": "claude-3-5-sonnet"}
    row = UserProfileModel(name="Test", data=json.dumps(data))
    db_session.add(row)
    db_session.commit()

    env_file.write_text(f"LLM_KEY_PROFILE_{row.id}=sk-test-key\n")

    resp = client.get(f"/api/config/profiles/{row.id}")
    assert resp.status_code == 200
    assert resp.json()["has_llm_key"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/web/test_profile_api.py::test_get_profile_includes_llm_fields tests/web/test_profile_api.py::test_get_profile_has_llm_key_true -v
```

Expected: FAIL — response does not include `llm_provider_type`, `llm_model`, or `has_llm_key`.

- [ ] **Step 3: Implement — extend `get_profile` in `web/routers/config.py`**

Replace the existing `get_profile` function body:

```python
@router.get("/api/config/profiles/{profile_id}")
def get_profile(profile_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.query(User).filter_by(id=profile_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    data = json.loads(row.data) if row.data else {}
    env = _read_env()
    has_llm_key = bool(env.get(f"LLM_KEY_PROFILE_{profile_id}"))
    return {
        "id": row.id,
        "name": row.name,
        "data": data,
        "llm_provider_type": data.get("llm_provider_type", ""),
        "llm_model": data.get("llm_model", ""),
        "has_llm_key": has_llm_key,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/web/test_profile_api.py::test_get_profile_includes_llm_fields tests/web/test_profile_api.py::test_get_profile_has_llm_key_true -v
```

Expected: PASS

- [ ] **Step 5: Run the full profile test suite to check for regressions**

```
pytest tests/web/test_profile_api.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```
git add web/routers/config.py tests/web/test_profile_api.py
git commit -m "[feat] Return llm_provider_type, llm_model, has_llm_key from GET profile/{id}"
```

---

### Task 2: Extend PUT `/api/config/profiles/{id}` to write LLM API key to `.env`

**Files:**
- Modify: `web/routers/config.py` (`ProfileBody` class, `update_profile` function, ~line 657)
- Test: `tests/web/test_profile_api.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/web/test_profile_api.py`:

```python
def test_put_profile_writes_llm_key_to_env(client, db_session, monkeypatch, tmp_path):
    import web.routers.config as config_mod
    import json
    from core.user import User as UserProfileModel

    env_file = tmp_path / ".env"
    env_file.write_text("")
    monkeypatch.setattr(config_mod, "_ENV_PATH", env_file)

    row = UserProfileModel(name="Test", data=json.dumps({
        "email": "", "phone": "", "location": "", "skills": [],
        "work_history": [], "education": [], "target_salary_min": None,
        "target_salary_max": None, "target_roles": [], "resume_path": "",
    }))
    db_session.add(row)
    db_session.commit()

    body = {
        "name": "Test",
        "data": {"email": "a@b.com", "llm_provider_type": "openai", "llm_model": "gpt-4o"},
        "llm_api_key": "sk-secret-123",
    }
    resp = client.put(f"/api/config/profiles/{row.id}", json=body)
    assert resp.status_code == 200

    env_content = env_file.read_text()
    assert f"LLM_KEY_PROFILE_{row.id}=sk-secret-123" in env_content


def test_put_profile_empty_llm_key_does_not_write_env(client, db_session, monkeypatch, tmp_path):
    import web.routers.config as config_mod
    import json
    from core.user import User as UserProfileModel

    env_file = tmp_path / ".env"
    env_file.write_text("")
    monkeypatch.setattr(config_mod, "_ENV_PATH", env_file)

    row = UserProfileModel(name="Test", data=json.dumps({
        "email": "", "phone": "", "location": "", "skills": [],
        "work_history": [], "education": [], "target_salary_min": None,
        "target_salary_max": None, "target_roles": [], "resume_path": "",
    }))
    db_session.add(row)
    db_session.commit()

    body = {"name": "Test", "data": {"llm_provider_type": "openai"}, "llm_api_key": ""}
    resp = client.put(f"/api/config/profiles/{row.id}", json=body)
    assert resp.status_code == 200
    assert env_file.read_text() == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/web/test_profile_api.py::test_put_profile_writes_llm_key_to_env tests/web/test_profile_api.py::test_put_profile_empty_llm_key_does_not_write_env -v
```

Expected: FAIL — `ProfileBody` has no `llm_api_key` field.

- [ ] **Step 3: Implement — update `ProfileBody` and `update_profile`**

In `web/routers/config.py`, update `ProfileBody`:

```python
class ProfileBody(BaseModel):
    name: str
    data: dict
    llm_api_key: str = ""
```

Replace the `update_profile` function body:

```python
@router.put("/api/config/profiles/{profile_id}")
def update_profile(profile_id: int, body: ProfileBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.query(User).filter_by(id=profile_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    data = body.data
    if not data.get("name"):
        first = data.get("first_name", "")
        last = data.get("last_name", "")
        data["name"] = f"{first} {last}".strip()
    row.name = body.name
    row.data = json.dumps(data)
    db.commit()
    if body.llm_api_key:
        env = _read_env()
        env[f"LLM_KEY_PROFILE_{profile_id}"] = body.llm_api_key
        _write_env(env)
    return {"id": row.id, "name": row.name, "data": data}
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/web/test_profile_api.py::test_put_profile_writes_llm_key_to_env tests/web/test_profile_api.py::test_put_profile_empty_llm_key_does_not_write_env -v
```

Expected: PASS

- [ ] **Step 5: Run the full profile test suite**

```
pytest tests/web/test_profile_api.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```
git add web/routers/config.py tests/web/test_profile_api.py
git commit -m "[feat] Accept llm_api_key on PUT profile/{id}, write to .env"
```

---

### Task 3: Add `getProfile` and `updateProfile` to `api.js`

**Files:**
- Modify: `react-dashboard/src/api.js`

- [ ] **Step 1: Add the two new exports**

In `react-dashboard/src/api.js`, append after the existing `saveProvider` export:

```js
export const getProfile = (id) => _fetch(`/api/config/profiles/${id}`)

export const updateProfile = (id, body) =>
  _fetch(`/api/config/profiles/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
```

- [ ] **Step 2: Verify the dev server starts without errors**

```
cd react-dashboard && npm run dev
```

Expected: Vite starts, no compile errors in the terminal.

- [ ] **Step 3: Commit**

```
git add react-dashboard/src/api.js
git commit -m "[feat] Add getProfile and updateProfile to api.js"
```

---

### Task 4: Rewrite Settings.jsx — profile cards, detail view, remove Advanced tab

**Files:**
- Modify: `react-dashboard/src/components/widgets/Settings.jsx`

This task rewrites the `UserTab`, adds `ProfileCards`, adds `ProfileDetailView`, removes `Advanced` from `TABS`, and wires the new view states into the `Settings` root component.

- [ ] **Step 1: Update imports at the top of Settings.jsx**

The import line currently reads:
```js
import { getProfiles, createProfile, getProviders, saveProvider } from '../../api'
```

Replace with:
```js
import { getProfiles, createProfile, getProfile, updateProfile } from '../../api'
```

- [ ] **Step 2: Replace `UserTab` and remove `AdvancedTab`**

Delete the entire `UserTab` function (lines ~235–246) and the entire `AdvancedTab` function (lines ~250–320).

Replace both with the following three components. Insert them in place of the deleted code, before the `// ─── Root ───` comment:

```jsx
// ─── User tab — profile cards ─────────────────────────────────────────────────

function ProfileCards({ onSelect, onCreateProfile }) {
  const [profiles, setProfiles] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getProfiles()
      .then((data) => {
        setProfiles(data.profiles ?? [])
        setActiveId(data.active_id ?? null)
      })
      .catch(() => setError('Failed to load profiles'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p className="text-xs text-space-dim">Loading…</p>
  if (error) return <p className="text-xs text-red-400">{error}</p>

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        {profiles.length === 0 && (
          <p className="text-xs text-space-dim">No profiles yet.</p>
        )}
        {profiles.map((profile) => (
          <button
            key={profile.id}
            onClick={() => onSelect(profile.id)}
            className={`flex flex-col gap-0.5 rounded-lg px-3 py-2.5 text-left transition-colors
              bg-white/[0.03] border hover:border-purple-500/50
              ${activeId === profile.id ? 'border-l-2 border-purple-500' : 'border-white/5'}`}
          >
            <p className="text-sm font-medium text-space-text">{profile.name || 'Unnamed'}</p>
            {(profile.first_name || profile.last_name) && (
              <p className="text-xs text-space-dim">
                {[profile.first_name, profile.last_name].filter(Boolean).join(' ')}
              </p>
            )}
          </button>
        ))}
      </div>
      <button
        onClick={onCreateProfile}
        className="w-full py-2 rounded-lg border border-space-border hover:border-purple-500/50 text-sm text-space-dim hover:text-space-text transition-colors"
      >
        + Create Profile
      </button>
    </div>
  )
}

// ─── Profile detail view ──────────────────────────────────────────────────────

const PROVIDER_TYPES = ['openrouter', 'anthropic', 'openai', 'gemini']

function ProfileDetailView({ profileId }) {
  const [form, setForm] = useState(null)
  const [llmProviderType, setLlmProviderType] = useState('')
  const [llmModel, setLlmModel] = useState('')
  const [llmApiKey, setLlmApiKey] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState(null)
  const timerRef = useRef(null)

  useEffect(() => {
    setLoading(true)
    getProfile(profileId)
      .then((data) => {
        setForm({
          name: data.name || '',
          first_name: data.data?.first_name || '',
          last_name: data.data?.last_name || '',
          email: data.data?.email || '',
          phone: data.data?.phone || '',
          location: data.data?.location || '',
          _raw: data.data || {},
        })
        setLlmProviderType(data.llm_provider_type || '')
        setLlmModel(data.llm_model || '')
        setLlmApiKey('')
      })
      .catch(() => setStatus('Failed to load profile'))
      .finally(() => setLoading(false))
    return () => clearTimeout(timerRef.current)
  }, [profileId])

  const handleSave = async () => {
    if (!form) return
    setSaving(true)
    try {
      const firstName = form.first_name.trim()
      const lastName = form.last_name.trim()
      await updateProfile(profileId, {
        name: form.name || `${firstName} ${lastName}`.trim() || 'Unnamed',
        data: {
          ...form._raw,
          first_name: firstName,
          last_name: lastName,
          email: form.email.trim(),
          phone: form.phone.trim(),
          location: form.location.trim(),
          llm_provider_type: llmProviderType,
          llm_model: llmModel.trim(),
        },
        llm_api_key: llmApiKey,
      })
      setStatus('Saved ✓')
    } catch {
      setStatus('Save failed')
    } finally {
      setSaving(false)
      clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => setStatus(null), 2500)
    }
  }

  const field = (label, key, type = 'text') => (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-space-dim">{label}</label>
      <input
        type={type}
        className={inputClass}
        value={form?.[key] ?? ''}
        onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
      />
    </div>
  )

  if (loading) return <p className="text-xs text-space-dim">Loading…</p>

  return (
    <div className="flex flex-col gap-4">
      {field('First Name', 'first_name')}
      {field('Last Name', 'last_name')}
      {field('Email', 'email')}
      {field('Phone', 'phone')}
      {field('Location', 'location')}

      <hr className="border-space-border" />
      <p className="text-xs font-semibold uppercase tracking-widest text-space-dim">LLM Provider</p>

      <div className="flex flex-col gap-1">
        <label className="text-xs text-space-dim">Provider</label>
        <select
          className={inputClass}
          value={llmProviderType}
          onChange={(e) => setLlmProviderType(e.target.value)}
        >
          <option value="">— select —</option>
          {PROVIDER_TYPES.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs text-space-dim">Model</label>
        <input
          className={inputClass}
          value={llmModel}
          onChange={(e) => setLlmModel(e.target.value)}
          placeholder="e.g. gpt-4o"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs text-space-dim">API Key</label>
        <input
          type="password"
          className={inputClass}
          value={llmApiKey}
          onChange={(e) => setLlmApiKey(e.target.value)}
          placeholder="Enter new key to replace existing"
        />
      </div>

      <button
        onClick={handleSave}
        disabled={saving}
        className="w-full py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-sm font-semibold transition-colors"
      >
        {saving ? 'Saving…' : 'Save'}
      </button>

      {status && (
        <p className={`text-xs text-center ${status.includes('failed') ? 'text-red-400' : 'text-green-400'}`}>
          {status}
        </p>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Update `TABS` and the `Settings` root component**

Replace:
```js
const TABS = ['User', 'Tasks', 'Advanced', 'Preview']
```
With:
```js
const TABS = ['User', 'Tasks', 'Preview']
```

Replace the `Settings` function signature and state:
```js
export default function Settings({ selectedJob, activeTab, onTabChange, jobs, processingKeys }) {
  const [view, setView] = useState('main') // 'main' | 'profiles' | 'createProfile'
```
With:
```js
export default function Settings({ selectedJob, activeTab, onTabChange, jobs, processingKeys }) {
  const [view, setView] = useState('main') // 'main' | 'createProfile' | 'profileDetail'
  const [detailProfileId, setDetailProfileId] = useState(null)
```

Replace the `handleTabClick` function:
```js
  const handleTabClick = (tab) => {
    if (tab === 'Preview' && isPreviewDisabled) return
    onTabChange(tab)
    setView('main')
  }
```
(No change needed — keep as-is.)

In the header section, replace the sub-view header `<span>` content:
```jsx
          <span className="text-xs font-semibold uppercase tracking-widest text-space-dim">
            {view === 'profiles' ? 'Profile Settings' : 'Create Profile'}
          </span>
```
With:
```jsx
          <span className="text-xs font-semibold uppercase tracking-widest text-space-dim">
            {view === 'createProfile' ? 'Create Profile' : 'Edit Profile'}
          </span>
```

Replace the back button's `onClick` (back button always returns to `'main'` since the User tab itself shows the profile card list):
```jsx
            onClick={() => setView(view === 'createProfile' ? 'profiles' : 'main')}
```
With:
```jsx
            onClick={() => setView('main')}
```

In the content section, replace:
```jsx
            {view === 'main' && activeTab === 'User' && (
              <UserTab onProfileSettings={() => setView('profiles')} />
            )}
            {view === 'main' && activeTab === 'Tasks' && (
              <TasksTab jobs={jobs} processingKeys={processingKeys} />
            )}
            {view === 'main' && activeTab === 'Advanced' && <AdvancedTab />}
            {view === 'main' && activeTab === 'Preview' && (
              <PreviewTab job={selectedJob} />
            )}
            {view === 'profiles' && (
              <ProfileList
                onCreateProfile={() => setView('createProfile')}
              />
            )}
            {view === 'createProfile' && (
              <CreateProfile
                onBack={() => setView('profiles')}
                onCreated={() => setView('profiles')}
              />
            )}
```
With:
```jsx
            {view === 'main' && activeTab === 'User' && (
              <ProfileCards
                onSelect={(id) => { setDetailProfileId(id); setView('profileDetail') }}
                onCreateProfile={() => setView('createProfile')}
              />
            )}
            {view === 'main' && activeTab === 'Tasks' && (
              <TasksTab jobs={jobs} processingKeys={processingKeys} />
            )}
            {view === 'main' && activeTab === 'Preview' && (
              <PreviewTab job={selectedJob} />
            )}
            {view === 'createProfile' && (
              <CreateProfile
                onBack={() => setView('main')}
                onCreated={() => setView('main')}
              />
            )}
            {view === 'profileDetail' && detailProfileId != null && (
              <ProfileDetailView profileId={detailProfileId} />
            )}
```

- [ ] **Step 4: Start the dev server and verify visually**

```
cd react-dashboard && npm run dev
```

Open `http://localhost:5173` in a browser.

Check:
1. Settings widget shows tabs: User, Tasks, Preview (no Advanced)
2. User tab shows profile cards (or "No profiles yet." if none exist)
3. Clicking a card pushes the detail view with personal fields and LLM Provider section
4. Back button returns to the profile card list
5. "+ Create Profile" button opens the create form

- [ ] **Step 5: Commit**

```
git add react-dashboard/src/components/widgets/Settings.jsx
git commit -m "[feat] Rewrite User tab with profile cards and LLM provider detail view"
```

---

### Task 5: Verify the `ProfileCards` component surfaces first/last name correctly

The `GET /api/config/profiles` list endpoint returns profile summaries, but `first_name` and `last_name` are nested inside the `data` JSON blob. The list endpoint does not currently expose them.

**Files:**
- Modify: `web/routers/config.py` (`get_profiles` function, ~line 607)
- Test: `tests/web/test_profile_api.py`

- [ ] **Step 1: Check what `GET /api/config/profiles` currently returns for each profile**

Run the server and hit the endpoint:

```
curl http://localhost:8000/api/config/profiles
```

If `first_name` and `last_name` are absent from each profile entry, continue. If already present, skip to Task commit.

- [ ] **Step 2: Write the failing test**

Add to `tests/web/test_profile_api.py`:

```python
def test_get_profiles_includes_first_last_name(client, db_session):
    import json
    from core.user import User as UserProfileModel
    data = {
        "email": "", "phone": "", "location": "", "skills": [],
        "work_history": [], "education": [], "target_salary_min": None,
        "target_salary_max": None, "target_roles": [], "resume_path": "",
        "first_name": "Jane", "last_name": "Doe",
    }
    row = UserProfileModel(name="Software Engineer", data=json.dumps(data))
    db_session.add(row)
    db_session.commit()

    resp = client.get("/api/config/profiles")
    assert resp.status_code == 200
    profiles = resp.json()["profiles"]
    assert len(profiles) == 1
    assert profiles[0]["first_name"] == "Jane"
    assert profiles[0]["last_name"] == "Doe"
```

- [ ] **Step 3: Run test to verify it fails**

```
pytest tests/web/test_profile_api.py::test_get_profiles_includes_first_last_name -v
```

Expected: FAIL — `first_name` / `last_name` not in response.

- [ ] **Step 4: Extend `get_profiles` to include first/last name**

In `web/routers/config.py`, in the `get_profiles` function, update the profile dict construction inside the for loop. Find:

```python
        profiles.append({
            "id": r.id,
            "name": r.name,
            "has_resume": bool(data.get("resume_path") or data.get("md_path")),
            "has_cover": bool(data.get("cover_letter_path")),
            "resume_path": data.get("resume_path", ""),
            "cover_letter_path": data.get("cover_letter_path", ""),
            "resume_uploaded_at": data.get("resume_uploaded_at", ""),
            "cover_uploaded_at": data.get("cover_uploaded_at", ""),
            "resume_filename": data.get("resume_filename", ""),
            "cover_filename": data.get("cover_filename", ""),
        })
```

Replace with:

```python
        profiles.append({
            "id": r.id,
            "name": r.name,
            "first_name": data.get("first_name", ""),
            "last_name": data.get("last_name", ""),
            "has_resume": bool(data.get("resume_path") or data.get("md_path")),
            "has_cover": bool(data.get("cover_letter_path")),
            "resume_path": data.get("resume_path", ""),
            "cover_letter_path": data.get("cover_letter_path", ""),
            "resume_uploaded_at": data.get("resume_uploaded_at", ""),
            "cover_uploaded_at": data.get("cover_uploaded_at", ""),
            "resume_filename": data.get("resume_filename", ""),
            "cover_filename": data.get("cover_filename", ""),
        })
```

- [ ] **Step 5: Run test to verify it passes**

```
pytest tests/web/test_profile_api.py::test_get_profiles_includes_first_last_name -v
```

Expected: PASS

- [ ] **Step 6: Run full profile test suite**

```
pytest tests/web/test_profile_api.py -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```
git add web/routers/config.py tests/web/test_profile_api.py
git commit -m "[feat] Include first_name and last_name in GET /api/config/profiles list"
```
