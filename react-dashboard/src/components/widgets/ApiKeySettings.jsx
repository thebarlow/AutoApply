import { useState, useEffect, useCallback } from 'react'
import {
  getLlmKey, getLlmKeyModels, testLlmKey, saveLlmKey, setLlmDefaultModel, deleteLlmKey,
} from '../../api'
import { inputClass } from './ProfileDetail'

const KEY_LINKS = {
  openrouter: 'https://openrouter.ai/settings/keys',
  openai: 'https://platform.openai.com/api-keys',
  anthropic: 'https://console.anthropic.com/settings/keys',
  gemini: 'https://aistudio.google.com/apikey',
}

const notifyChanged = () => {
  window.dispatchEvent(new Event('auto-apply:credits-stale'))
  window.dispatchEvent(new Event('auto-apply:byok-changed'))
}

/** Searchable model picker. Lists can run to hundreds of entries (OpenRouter). */
function ModelPicker({ id, value, onChange, models }) {
  return (
    <>
      <input
        id={id}
        list={`${id}-list`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Type to search models"
        className={inputClass}
      />
      <datalist id={`${id}-list`}>
        {models.map((m) => <option key={m.id} value={m.id}>{m.name !== m.id ? m.name : null}</option>)}
      </datalist>
    </>
  )
}

/**
 * Bring-your-own-key settings. With a saved key every AI action runs on the
 * user's provider account and costs no credits. `compact` trims the intro copy
 * for use inside the onboarding modal.
 */
export default function ApiKeySettings({ compact = false, onSaved }) {
  const [state, setState] = useState(null)
  const [loadError, setLoadError] = useState('')
  const [provider, setProvider] = useState('openrouter')
  const [apiKey, setApiKey] = useState('')
  const [models, setModels] = useState(null)
  const [model, setModel] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(() => {
    getLlmKey()
      .then((s) => { setState(s); setLoadError('') })
      .catch((e) => setLoadError(e.status === 409 ? 'local' : 'Could not load your API key settings.'))
  }, [])

  useEffect(() => { load() }, [load])

  // With a saved key, fetch its models so the default can be changed.
  useEffect(() => {
    if (!state?.has_key) return
    setModel(state.default_model ?? '')
    getLlmKeyModels().then((d) => setModels(d.models)).catch(() => setModels([]))
  }, [state?.has_key, state?.default_model])

  const resetDraft = () => { setApiKey(''); setModels(null); setModel(''); setError('') }

  const check = async () => {
    setBusy(true); setError(''); setNotice('')
    const r = await testLlmKey(provider, apiKey.trim())
    setBusy(false)
    if (!r.ok) { setError(r.error); setModels(null); return }
    if (r.models.length === 0) { setError('This key works, but it has no text models available.'); return }
    setModels(r.models)
    setModel(r.models[0].id)
  }

  const save = async () => {
    setBusy(true); setError('')
    try {
      const s = await saveLlmKey(provider, apiKey.trim(), model)
      setState(s); resetDraft(); setNotice('Key saved. AI actions now run on your account and cost no credits.')
      notifyChanged()
      onSaved?.()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const changeModel = async () => {
    setBusy(true); setError(''); setNotice('')
    try {
      setState(await setLlmDefaultModel(model)); setNotice('Default model updated.')
    } catch {
      setError('Could not update the default model. Try again.')
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    setBusy(true); setError(''); setNotice('')
    try {
      setState(await deleteLlmKey()); resetDraft(); setNotice('Key removed. AI actions now use credits.')
      notifyChanged()
    } catch {
      setError('Could not remove the key. Try again.')
    } finally {
      setBusy(false)
    }
  }

  if (loadError === 'local') {
    return <p className="text-xs text-space-dim">Local install: set <code>LLM_API_KEY</code> in <code>.env</code> instead.</p>
  }
  if (loadError) return <p className="text-xs text-red-400">{loadError}</p>
  if (!state) return <p className="text-xs text-space-dim">Loading…</p>

  const btn = 'px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors disabled:opacity-50'

  return (
    <section className="flex flex-col gap-3" aria-labelledby="byok-heading">
      <div className="flex flex-col gap-1">
        <h3 id="byok-heading" className="text-xs uppercase tracking-widest text-space-dim">Your AI API key</h3>
        {!compact && (
          <p className="text-xs text-space-dim">
            Use your own OpenRouter, OpenAI, Anthropic or Gemini API key and AutoApply is free.
            Your provider bills you directly for what you use. Without a key, AI actions use credits.
          </p>
        )}
      </div>

      {state.has_key ? (
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg border border-space-border bg-white/5">
            <span className="text-sm text-space-text">{state.provider_label}</span>
            <span className="text-sm font-mono text-space-dim">{state.masked_key}</span>
          </div>
          <label htmlFor="byok-default-model" className="text-xs text-space-dim">Default model</label>
          <ModelPicker id="byok-default-model" value={model} onChange={setModel} models={models ?? []} />
          <div className="flex gap-2">
            <button type="button" onClick={changeModel} disabled={busy || !model || model === state.default_model}
              className={`${btn} bg-purple-600 hover:bg-purple-500 text-white`}>
              Update model
            </button>
            <button type="button" onClick={remove} disabled={busy}
              className={`${btn} border border-space-border text-space-dim hover:text-red-400 hover:border-red-400`}>
              Remove key
            </button>
          </div>
        </div>
      ) : !state.storage_available ? (
        <p className="text-xs text-space-dim">Saving your own key isn&apos;t available on this server yet.</p>
      ) : (
        <div className="flex flex-col gap-3">
          <label htmlFor="byok-provider" className="text-xs text-space-dim">Provider</label>
          <select id="byok-provider" value={provider}
            onChange={(e) => { setProvider(e.target.value); resetDraft() }} className={inputClass}>
            {state.providers.map((p) => (
              <option key={p.id} value={p.id} className="text-black">{p.label}</option>
            ))}
          </select>
          <label htmlFor="byok-key" className="text-xs text-space-dim">
            API key{' '}
            <a href={KEY_LINKS[provider]} target="_blank" rel="noreferrer" className="text-purple-400 hover:underline">
              (get one)
            </a>
          </label>
          <input id="byok-key" type="password" autoComplete="off" spellCheck={false} value={apiKey}
            onChange={(e) => { setApiKey(e.target.value); setModels(null) }}
            placeholder="Paste your API key" className={inputClass} />
          {models === null ? (
            <button type="button" onClick={check} disabled={busy || apiKey.trim().length < 8}
              className={`${btn} self-start bg-purple-600 hover:bg-purple-500 text-white`}>
              {busy ? 'Checking…' : 'Check key'}
            </button>
          ) : (
            <>
              <label htmlFor="byok-new-model" className="text-xs text-space-dim">
                Default model ({models.length} available)
              </label>
              <ModelPicker id="byok-new-model" value={model} onChange={setModel} models={models} />
              <button type="button" onClick={save} disabled={busy || !model}
                className={`${btn} self-start bg-purple-600 hover:bg-purple-500 text-white`}>
                {busy ? 'Saving…' : 'Save key'}
              </button>
            </>
          )}
          <p className="text-[11px] text-space-dim">
            Stored encrypted. It&apos;s never shown again after saving, only its last 4 characters.
          </p>
        </div>
      )}

      {error && <p role="alert" className="text-xs text-red-400">{error}</p>}
      {notice && <p role="status" className="text-xs text-green-400">{notice}</p>}
    </section>
  )
}
