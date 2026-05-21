const BASE = ''

async function _fetch(url, options) {
  const res = await fetch(BASE + url, options)
  if (!res.ok) throw new Error(`${options?.method ?? 'GET'} ${url} → ${res.status}`)
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
