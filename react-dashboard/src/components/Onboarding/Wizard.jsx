import { useState } from "react";
import StepResume from "./StepResume";

const TABS = [
  {
    key: "resume",
    label: "Use existing Resume",
    blurb: "We'll parse your résumé into structured profile fields you can edit afterwards.",
  },
  {
    key: "manual",
    label: "Manual Entry",
    blurb: "Skip the upload and fill in your profile fields yourself in the profile editor.",
  },
];

export default function Wizard({ onFinish, onSkip, onManual }) {
  const [tab, setTab] = useState("resume");
  const active = TABS.find((t) => t.key === tab);

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center">
      <div className="bg-[#0f0f1a] border border-space-border rounded-xl shadow-2xl w-[600px] max-w-[90vw] p-6 text-space-text">
        <div className="mb-4 text-center">
          <h1 className="text-2xl font-bold text-white">Create your User Profile</h1>
          <p className="text-sm text-space-dim mt-1">
            Upload your master résumé to auto-fill your profile, or enter your details manually.
          </p>
        </div>

        <div className="flex justify-end items-center mb-4">
          <button
            onClick={onSkip}
            className="text-sm text-space-dim hover:text-space-text transition-colors hover:underline"
          >
            Skip for now
          </button>
        </div>

        {/* Tab switcher */}
        <div className="flex gap-1.5 mb-3">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-3 py-1 rounded text-xs font-semibold transition-colors
                ${tab === t.key ? "bg-purple-600 text-white" : "text-space-dim hover:text-space-text border border-space-border"}`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <p className="text-xs text-space-dim mb-4">{active.blurb}</p>

        {/* Tab body */}
        {tab === "resume" ? (
          <StepResume onFinish={onFinish} />
        ) : (
          <div className="flex justify-end">
            <button
              onClick={onManual}
              className="text-sm text-purple-300 hover:text-purple-200 transition-colors hover:underline"
            >
              Try it out
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
