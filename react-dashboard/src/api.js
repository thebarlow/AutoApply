const BASE = ''

async function _fetch(url, options) {
  const res = await fetch(BASE + url, options)
  if (!res.ok) throw new Error(`${options?.method ?? 'GET'} ${url} → ${res.status}`)
  if (res.status === 204) return null
  const ct = res.headers.get('content-type')
  return ct && ct.includes('application/json') ? res.json() : null
}

export const getJobs = () => _fetch('/api/jobs')

export const getProfiles = () => _fetch('/api/config/profiles')

export const createProfile = (name) =>
  _fetch('/api/config/profiles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })

export const getProviders = () => _fetch('/api/config/providers')

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

export const uploadPromptFile = (file) => {
  const form = new FormData()
  form.append('file', file)
  return _fetch('/api/prompts/upload', { method: 'POST', body: form })
}
