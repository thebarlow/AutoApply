const BASE = ''

async function _fetch(url, options) {
  const res = await fetch(BASE + url, options)
  if (!res.ok) {
    // Out-of-credits: surface a non-silent, app-wide signal (App.jsx toasts it)
    // and prompt a balance refresh. Still throw so callers' catch paths run.
    if (res.status === 402) {
      let body = null
      try { body = await res.clone().json() } catch { /* non-JSON body */ }
      if (body?.error === 'insufficient_credits') {
        window.dispatchEvent(new CustomEvent('auto-apply:credits-error', { detail: body }))
        window.dispatchEvent(new Event('auto-apply:credits-stale'))
      }
    }
    throw new Error(`${options?.method ?? 'GET'} ${url} → ${res.status}`)
  }
  if (res.status === 204) return null
  const ct = res.headers.get('content-type')
  return ct && ct.includes('application/json') ? res.json() : null
}

export const getJobs = () => _fetch('/api/jobs')

export const resumeCompare = (jobKey) =>
  _fetch(`/api/dev/resume-compare/${jobKey}`, { method: 'POST' })

export const deleteJob = (jobKey) =>
  _fetch(`/api/jobs/${jobKey}`, { method: 'DELETE' })

export const updateJobState = (jobKey, state) =>
  _fetch(`/api/jobs/${jobKey}/state`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ state }),
  })

export const getProfiles = () => _fetch('/api/config/profiles')

export const createProfile = (name) =>
  _fetch('/api/config/profiles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })

export const getProviders = () => _fetch('/api/config/providers')

export const createProvider = (body) =>
  _fetch('/api/config/providers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

export const saveProvider = (id, body) =>
  _fetch(`/api/config/providers/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

export const getProfile = (id) => _fetch(`/api/config/profiles/${id}`)

export const updateProfile = (id, body) =>
  _fetch(`/api/config/profiles/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

export const getProfileTree = (id) =>
  _fetch(`/api/config/profiles/${id}/tree`)

export const getOutputFormats = () => _fetch('/api/output-formats')

export const getThemes = () => _fetch('/api/themes')

export const putProfileTree = (id, tree) =>
  _fetch(`/api/config/profiles/${id}/tree`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tree }),
  })

export const deleteProfile = (id) =>
  _fetch(`/api/config/profiles/${id}`, { method: 'DELETE' })

export const resetProfile = (id) =>
  _fetch(`/api/config/profiles/${id}/reset`, { method: 'POST' })

export const setActiveProfile = (id) =>
  _fetch('/api/config/profiles/active', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ active_id: id }),
  })

export const getActivePromptStatus = () =>
  _fetch('/api/config/profiles/active/prompt-status')

export const getDefaultPrompt = (typeKey) => _fetch(`/api/prompts/defaults/${typeKey}`)

export const getPrompt = (profileId, typeKey) =>
  _fetch(`/api/prompts/${profileId}/${typeKey}`)

export const putPrompt = (profileId, typeKey, { content, model }) =>
  _fetch(`/api/prompts/${profileId}/${typeKey}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, model }),
  })

export const resetPrompt = (profileId, typeKey) =>
  _fetch(`/api/prompts/${profileId}/${typeKey}/reset`, { method: 'POST' })

export const uploadProfileResume = (file) => {
  const form = new FormData()
  form.append('file', file)
  return _fetch('/api/config/profile/upload', { method: 'POST', body: form })
}

export const parseProfileResume = (profileId) =>
  _fetch(`/api/config/profiles/${profileId}/parse`, { method: 'POST' })

export const markJobSeen = (jobKey) =>
  _fetch(`/api/jobs/${jobKey}/seen`, { method: 'POST' })

export const markJobActionSeen = (jobKey, action) =>
  _fetch(`/api/jobs/${jobKey}/seen/${action}`, { method: 'POST' })

export const getLlmStatus = () => _fetch('/api/llm-status')

export const getStats = (timeWindow) => _fetch(`/api/stats?window=${timeWindow}`)

export const getSkillFrequency = () => _fetch('/api/skill-frequency')

export const getJobsForSkill = (skill) =>
  _fetch('/api/skill-frequency/jobs?' + new URLSearchParams({ skill }))

export const getSetupStatus = () => _fetch('/api/setup-status')

export const setTourState = (state) =>
  _fetch('/api/onboarding/tour', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ state }),
  })

export const testLlmConnection = (body) =>
  _fetch('/api/llm/test-connection', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

/**
 * Ensures a profile named `name` exists, with the given LLM provider linked,
 * and sets it as the active profile.
 *
 * If a profile with that name already exists, it reuses it and updates the
 * LLM link. Otherwise creates a new profile.
 *
 * @param {string} name - Profile display name (e.g. "Master")
 * @param {{ providerType: string, model: string, apiKey: string, baseUrl?: string }} llm
 * @returns {Promise<{ id: number, name: string }>}
 */
export async function ensureProfileWithProvider(name, llm) {
  const { profiles, active_id } = await getProfiles()

  // Find existing profile by name (case-insensitive), or the active one.
  let profile = profiles.find((p) => p.name.toLowerCase() === name.toLowerCase())

  if (!profile) {
    profile = await createProfile(name)
  }

  // Link the LLM provider onto the profile row.
  const existingData = profile.data || {}
  const llmData = {
    llm_provider_type: llm.providerType,
    llm_model: llm.model,
  }
  if (llm.baseUrl) llmData.llm_base_url = llm.baseUrl
  await updateProfile(profile.id, {
    name: profile.name || name,
    data: {
      ...existingData,
      ...llmData,
    },
    llm_api_key: llm.apiKey,
  })

  // Make it the active profile.
  await setActiveProfile(profile.id)

  return { id: profile.id, name: profile.name || name }
}

export const getSkillAliases = () => _fetch('/api/skills/aliases')

export const searchSkillAliases = (q) =>
  _fetch('/api/skills/aliases/search?' + new URLSearchParams({ q }))

export const assignSkillAlias = (skill, canonical) =>
  _fetch('/api/skills/aliases/assign', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ skill, canonical }),
  })

export const removeSkillAliasMember = (skill) =>
  _fetch('/api/skills/aliases/member', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ skill }),
  })

export const addProfileSkill = (skill) =>
  _fetch('/api/skills/profile', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ skill }),
  })

export const removeProfileSkill = (skill) =>
  _fetch('/api/skills/profile', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ skill }),
  })

export const getOwnedSkills = (skills, jobKey = null) =>
  _fetch('/api/skills/owned', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ skills, job_key: jobKey }),
  })

export const rematchSkills = (jobKey) =>
  _fetch(`/api/jobs/${encodeURIComponent(jobKey)}/rematch-skills`, { method: 'POST' })

export const uploadJob = (fields) => {
  const uuid = crypto.randomUUID()
  const body = {
    source: 'manual',
    job_key: `manual_${uuid}`,
    title: fields.title,
    description: fields.description,
    company: fields.company || '',
    location: fields.location || '',
    salary: fields.salary || '',
    url: fields.url?.trim() || `manual://${uuid}`,
  }
  return _fetch('/api/scraper/stage-job', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export const updateJobFields = (jobKey, fields) =>
  _fetch(`/api/jobs/${jobKey}/fields`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  })

export const getDocument = (jobKey, docType) =>
  _fetch(`/api/jobs/${jobKey}/${docType}/document`)

export const putDocument = (jobKey, docType, doc) =>
  _fetch(`/api/jobs/${jobKey}/${docType}/document`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(doc),
  })

export const submitFeedback = (jobKey, docType, notes) =>
  _fetch(`/api/jobs/${jobKey}/${docType}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ notes }),
  })

export const flagJob = (jobKey, flagged) =>
  _fetch(`/api/jobs/${jobKey}/flag`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ flagged }),
  })

export async function getMe() {
  const res = await fetch('/api/me')
  if (res.status === 401) return null
  if (!res.ok) throw new Error(`GET /api/me → ${res.status}`)
  return res.json()
}

export const getCredits = () => _fetch('/api/credits')

export const getPacks = () => _fetch('/api/payments/packs')

export const getPurchaseHistory = () => _fetch('/api/payments/history')

export const startCheckout = (priceId) =>
  _fetch('/api/payments/checkout', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ price_id: priceId }),
  })

export const verifyPurchase = (sessionId) =>
  _fetch(`/api/payments/verify?session_id=${encodeURIComponent(sessionId)}`)

export const getSystemBalance = () => _fetch('/api/admin/system-balance')

export const inviteUser = (email, tier = 'standard', is_admin = false) =>
  _fetch('/api/admin/invite', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, tier, is_admin }),
  })

export const getInvites = () => _fetch('/api/admin/invites')

export const getUsers = () => _fetch('/api/admin/users')

export const getUserPurchases = (profileId) =>
  _fetch(`/api/admin/users/${profileId}/purchases`)

export const startImpersonation = (profileId) =>
  _fetch('/api/admin/impersonate/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile_id: profileId }),
  })

export const stopImpersonation = () =>
  _fetch('/api/admin/impersonate/stop', { method: 'POST' })

export const setUserAccess = (profileId, banned) =>
  _fetch(`/api/admin/users/${profileId}/access`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ banned }),
  })

export const getGrantBudget = () => _fetch('/api/admin/grant-budget')

export const grantCredits = (profileId, amount) =>
  _fetch(`/api/admin/users/${profileId}/grant`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ amount }),
  })

export const logout = () =>
  fetch('/auth/logout', { method: 'POST' }).then(() => { window.location.href = '/' })

export const proposeParse = (profileId) =>
  _fetch(`/api/config/profiles/${profileId}/parse/propose`, { method: 'POST' })

export const applyParse = (profileId, proposal) =>
  _fetch(`/api/config/profiles/${profileId}/parse/apply`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(proposal),
  })

// profileId kept for signature symmetry with proposeParse/applyParse; endpoint
// resolves the caller's profile from the session — it is not in the URL.
export const draftSectionPrompt = (_profileId, body) =>
  _fetch(`/api/config/section-prompt/draft`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
