const BASE = ''

async function _fetch(url, options) {
  const res = await fetch(BASE + url, options)
  if (!res.ok) throw new Error(`${options?.method ?? 'GET'} ${url} → ${res.status}`)
  if (res.status === 204) return null
  const ct = res.headers.get('content-type')
  return ct && ct.includes('application/json') ? res.json() : null
}

export const getJobs = () => _fetch('/api/jobs')

export const deleteJob = (jobKey) =>
  _fetch(`/api/jobs/${jobKey}`, { method: 'DELETE' })

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

export const deleteProfile = (id) =>
  _fetch(`/api/config/profiles/${id}`, { method: 'DELETE' })

export const setActiveProfile = (id) =>
  _fetch('/api/config/profiles/active', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ active_id: id }),
  })

export const getActivePromptStatus = () =>
  _fetch('/api/config/profiles/active/prompt-status')

export const listPrompts = () => _fetch('/api/prompts')

export const getPromptFile = (path) =>
  fetch('/api/prompts/file?' + new URLSearchParams({ path }))
    .then((r) => {
      if (!r.ok) throw new Error(`GET prompt file → ${r.status}`)
      return r.text()
    })

export const putPromptFile = (path, content) =>
  _fetch('/api/prompts/file?' + new URLSearchParams({ path }), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })

export const createPromptFile = (filename, content) =>
  _fetch('/api/prompts/file', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename, content }),
  })

export const uploadPromptFile = (file) => {
  const form = new FormData()
  form.append('file', file)
  return _fetch('/api/prompts/upload', { method: 'POST', body: form })
}

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

export const getSetupStatus = () => _fetch('/api/setup-status')

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
 * @param {{ providerType: string, model: string, apiKey: string }} llm
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
  await updateProfile(profile.id, {
    name: profile.name || name,
    data: {
      ...existingData,
      llm_provider_type: llm.providerType,
      llm_model: llm.model,
    },
    llm_api_key: llm.apiKey,
  })

  // Make it the active profile.
  await setActiveProfile(profile.id)

  return { id: profile.id, name: profile.name || name }
}
