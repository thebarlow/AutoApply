import { useState } from "react";
import { testLlmConnection, createProvider } from "../../api";
import HelpIcon from "../shared/HelpIcon";

const PROVIDERS = [
  {
    value: "anthropic",
    label: "Anthropic",
    defaultModel: "claude-sonnet-4-6",
    models: [
      "claude-opus-4-7",
      "claude-sonnet-4-6",
      "claude-haiku-4-5-20251001",
      "claude-3-7-sonnet-latest",
      "claude-3-5-haiku-latest",
    ],
  },
  {
    value: "openai",
    label: "OpenAI",
    defaultModel: "gpt-4o-mini",
    models: ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
  },
  {
    value: "openrouter",
    label: "OpenRouter",
    defaultModel: "openrouter/auto:free",
    models: [
      "openrouter/auto",
      "openrouter/auto:free",
      "anthropic/claude-3.5-sonnet",
      "openai/gpt-4o-mini",
      "meta-llama/llama-3.1-8b-instruct:free",
    ],
  },
  {
    value: "gemini",
    label: "Gemini",
    defaultModel: "gemini-1.5-flash",
    models: [
      "gemini-2.0-flash",
      "gemini-1.5-pro",
      "gemini-1.5-flash",
      "gemini-1.5-flash-8b",
    ],
  },
  {
    value: "custom",
    label: "Custom (OpenAI-compatible)",
    defaultModel: "",
    models: [],
    requiresBaseUrl: true,
  },
];

const inputClass =
  "w-full bg-white/5 border border-space-border rounded-lg px-3 py-2 text-sm text-space-text placeholder-space-dim focus:outline-none focus:border-purple-500 transition-colors";

/** Maps raw error strings to user-friendly messages. */
function mapError(raw) {
  if (!raw) return "Connection failed";
  const lower = raw.toLowerCase();
  if (
    lower.includes("auth") ||
    lower.includes("401") ||
    lower.includes("invalid api key") ||
    lower.includes("incorrect api key")
  ) {
    return "Invalid API key";
  }
  if (lower.includes("model") && (lower.includes("not found") || lower.includes("does not exist"))) {
    return "Invalid model";
  }
  return raw.length > 120 ? raw.slice(0, 117) + "…" : raw;
}

/** Simple combobox: text input + filtered dropdown. Allows free-text. */
function ModelCombobox({ value, onChange, models, disabled }) {
  const [open, setOpen] = useState(false);
  const filtered = value
    ? models.filter((m) => m.toLowerCase().includes(value.toLowerCase()))
    : models;

  return (
    <div className="relative">
      <input
        type="text"
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        disabled={disabled}
        placeholder="e.g. gpt-4o-mini"
        className={inputClass}
      />
      {open && filtered.length > 0 && (
        <ul className="absolute z-10 mt-1 w-full max-h-48 overflow-auto bg-white text-black border border-space-border rounded shadow-lg">
          {filtered.map((m) => (
            <li
              key={m}
              onMouseDown={(e) => {
                e.preventDefault();
                onChange(m);
                setOpen(false);
              }}
              className="px-2 py-1 hover:bg-gray-200 cursor-pointer text-sm"
            >
              {m}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function StepLLM({ onNext }) {
  const [provider, setProvider] = useState("anthropic");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState(PROVIDERS[0].defaultModel);
  const [baseUrl, setBaseUrl] = useState("");
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState("");

  const providerDef = PROVIDERS.find((p) => p.value === provider);
  const isCustom = provider === "custom";

  const onProviderChange = (v) => {
    setProvider(v);
    const p = PROVIDERS.find((x) => x.value === v);
    if (p) setModel(p.defaultModel);
    setError("");
  };

  const onNextClick = async () => {
    if (!apiKey.trim()) {
      setError("API key is required");
      return;
    }
    if (isCustom && !baseUrl.trim()) {
      setError("Base URL is required for custom providers");
      return;
    }

    setTesting(true);
    setError("");

    // Test connection
    try {
      const payload = { provider_type: provider, api_key: apiKey, model };
      if (isCustom && baseUrl.trim()) payload.base_url = baseUrl.trim();

      const r = await testLlmConnection(payload);
      if (!r || !r.ok) {
        setError(mapError((r && r.error) || ""));
        setTesting(false);
        return;
      }
    } catch (e) {
      setError(mapError(e.message));
      setTesting(false);
      return;
    }

    // Save provider
    try {
      const label = providerDef?.label ?? provider;
      const createPayload = {
        name: label,
        provider_type: provider,
        default_model: model,
        api_key: apiKey,
      };
      if (isCustom && baseUrl.trim()) createPayload.base_url = baseUrl.trim();

      await createProvider(createPayload);
      onNext({
        providerType: provider,
        model,
        apiKey,
        ...(isCustom && baseUrl.trim() ? { baseUrl: baseUrl.trim() } : {}),
      });
    } catch (e) {
      setError("Failed to save: " + e.message);
      setTesting(false);
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
        <label className="text-xs text-space-dim flex items-center">
          Provider
          <HelpIcon
            text="Which LLM service to use. Anthropic and OpenAI are well-supported; pick Custom for any OpenAI-compatible endpoint."
            docHref="#/docs/llm-providers"
          />
        </label>
        <select
          className={`${inputClass} text-space-text bg-space-card`}
          value={provider}
          onChange={(e) => onProviderChange(e.target.value)}
        >
          {PROVIDERS.map((p) => (
            <option key={p.value} value={p.value} className="text-black bg-white">
              {p.label}
            </option>
          ))}
        </select>
      </div>

      {/* Base URL (custom only) */}
      {isCustom && (
        <div className="flex flex-col gap-1 mb-3">
          <label className="text-xs text-space-dim">
            Base URL <span className="text-red-400">*</span>
          </label>
          <input
            type="text"
            className={inputClass}
            value={baseUrl}
            onChange={(e) => { setBaseUrl(e.target.value); setError(""); }}
            placeholder="https://..."
            autoComplete="off"
          />
        </div>
      )}

      {/* API Key */}
      <div className="flex flex-col gap-1 mb-3">
        <label className="text-xs text-space-dim flex items-center">
          API Key <span className="text-red-400 ml-1">*</span>
          <HelpIcon
            text="Your provider's secret API key. The app uses this to call the LLM on your behalf."
            docHref="#/docs/llm-providers"
          />
        </label>
        <input
          type="password"
          className={inputClass}
          value={apiKey}
          onChange={(e) => { setApiKey(e.target.value); setError(""); }}
          placeholder="Paste your API key here"
          autoComplete="off"
        />
      </div>

      {/* Model */}
      <div className="flex flex-col gap-1 mb-5">
        <label className="text-xs text-space-dim flex items-center">
          Model
          <HelpIcon
            text="The specific model to use. Smaller models are cheaper; larger ones produce better results."
            docHref="#/docs/llm-providers"
          />
        </label>
        {isCustom ? (
          <input
            type="text"
            className={inputClass}
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="e.g. my-model-name"
          />
        ) : (
          <ModelCombobox
            value={model}
            onChange={(v) => setModel(v)}
            models={providerDef?.models ?? []}
            disabled={testing}
          />
        )}
      </div>

      {/* Error */}
      {error && (
        <p className="text-sm text-red-400 mb-3">{error}</p>
      )}

      {/* Next (merged with test) */}
      <button
        onClick={onNextClick}
        disabled={testing || !apiKey.trim()}
        className="w-full py-2.5 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors"
      >
        {testing ? "Testing…" : "Next →"}
      </button>
    </div>
  );
}
