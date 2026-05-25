import { useState } from "react";
import { testLlmConnection, createProvider } from "../../api";

const PROVIDERS = [
  { value: "anthropic", label: "Anthropic", defaultModel: "claude-haiku-4-5-20251001" },
  { value: "openai", label: "OpenAI", defaultModel: "gpt-4o-mini" },
  { value: "openrouter", label: "OpenRouter", defaultModel: "openai/gpt-4o-mini" },
  { value: "gemini", label: "Gemini", defaultModel: "gemini-1.5-flash" },
];

const inputClass =
  "w-full bg-white/5 border border-space-border rounded-lg px-3 py-2 text-sm text-space-text placeholder-space-dim focus:outline-none focus:border-purple-500 transition-colors";

export default function StepLLM({ onNext }) {
  const [provider, setProvider] = useState("anthropic");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState(PROVIDERS[0].defaultModel);
  const [status, setStatus] = useState(null); // null | "testing" | "ok" | "error"
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const onProviderChange = (v) => {
    setProvider(v);
    const p = PROVIDERS.find((x) => x.value === v);
    if (p) setModel(p.defaultModel);
    setStatus(null);
    setError("");
  };

  const onTest = async () => {
    if (!apiKey.trim()) {
      setStatus("error");
      setError("API key is required");
      return;
    }
    setStatus("testing");
    setError("");
    try {
      const r = await testLlmConnection({ provider_type: provider, api_key: apiKey, model });
      if (r && r.ok) {
        setStatus("ok");
      } else {
        setStatus("error");
        setError((r && r.error) || "Connection failed");
      }
    } catch (e) {
      setStatus("error");
      setError(e.message || "Connection failed");
    }
  };

  const onNextClick = async () => {
    setSaving(true);
    setError("");
    try {
      // POST to /api/config/providers — creates a named provider with the API key.
      // This is what makes /api/setup-status return llm_configured: true.
      const label = PROVIDERS.find((p) => p.value === provider)?.label ?? provider;
      await createProvider({
        name: label,
        provider_type: provider,
        default_model: model,
        api_key: apiKey,
      });
      onNext();
    } catch (e) {
      setError("Failed to save: " + e.message);
      setStatus("error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <h2 className="text-lg font-semibold mb-2">Set up your LLM provider</h2>
      <p className="text-sm text-space-dim mb-5">
        The app uses an LLM to score jobs and tailor your resume. Pick a provider and paste your API key.
      </p>

      {/* Provider */}
      <div className="flex flex-col gap-1 mb-3">
        <label className="text-xs text-space-dim">Provider</label>
        <select
          className={inputClass}
          value={provider}
          onChange={(e) => onProviderChange(e.target.value)}
        >
          {PROVIDERS.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </select>
      </div>

      {/* API Key */}
      <div className="flex flex-col gap-1 mb-3">
        <label className="text-xs text-space-dim">
          API Key <span className="text-red-400">*</span>
        </label>
        <input
          type="password"
          className={inputClass}
          value={apiKey}
          onChange={(e) => { setApiKey(e.target.value); setStatus(null); setError(""); }}
          placeholder="Paste your API key here"
          autoComplete="off"
        />
      </div>

      {/* Model */}
      <div className="flex flex-col gap-1 mb-5">
        <label className="text-xs text-space-dim">Model</label>
        <input
          className={inputClass}
          value={model}
          onChange={(e) => { setModel(e.target.value); setStatus(null); }}
          placeholder="e.g. gpt-4o-mini"
        />
      </div>

      {/* Test connection */}
      <div className="flex items-center gap-3 mb-5">
        <button
          onClick={onTest}
          disabled={status === "testing" || !apiKey.trim()}
          className="px-4 py-2 rounded-lg border border-space-border text-sm text-space-dim hover:text-space-text hover:border-purple-500/50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {status === "testing" ? "Testing…" : "Test connection"}
        </button>
        {status === "ok" && (
          <span className="text-sm text-emerald-400 font-medium">✓ Connected</span>
        )}
        {status === "error" && (
          <span className="text-sm text-red-400">{error || "Connection failed"}</span>
        )}
      </div>

      {/* Next */}
      <button
        onClick={onNextClick}
        disabled={status !== "ok" || saving}
        className="w-full py-2.5 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors"
      >
        {saving ? "Saving…" : "Next →"}
      </button>
      {status !== "ok" && !saving && (
        <p className="text-xs text-space-dim mt-2 text-center">
          Test the connection first to continue.
        </p>
      )}
    </div>
  );
}
