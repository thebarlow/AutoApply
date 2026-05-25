import { useState } from "react";
import StepLLM from "./StepLLM";
import StepResume from "./StepResume";
import { ensureProfileWithProvider } from "../../api";

export default function Wizard({ onFinish, onSkip }) {
  const [step, setStep] = useState(1);
  const [profileName, setProfileName] = useState("Master");
  // Stored after StepLLM succeeds so StepResume and skip can use them.
  const [llmInfo, setLlmInfo] = useState(null); // { providerType, model, apiKey }

  const handleSkip = async () => {
    // If the user configured an LLM but didn't finish the resume step, still
    // create the profile so the app is usable without a resume.
    if (llmInfo) {
      try {
        await ensureProfileWithProvider(profileName, llmInfo);
      } catch (e) {
        console.error("Skip-time profile creation failed:", e);
      }
    }
    onSkip();
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center">
      <div className="bg-[#0f0f1a] border border-space-border rounded-xl shadow-2xl w-[600px] max-w-[90vw] p-6 text-space-text">
        <div className="flex justify-between items-center mb-4">
          <div className="text-sm text-space-dim">Step {step} of 2</div>
          <button
            onClick={handleSkip}
            className="text-sm text-space-dim hover:text-space-text transition-colors hover:underline"
          >
            Skip for now
          </button>
        </div>
        {step === 1 && (
          <StepLLM
            onNext={(info) => {
              setLlmInfo(info);
              setStep(2);
            }}
          />
        )}
        {step === 2 && (
          <StepResume
            onBack={() => setStep(1)}
            onFinish={onFinish}
            profileName={profileName}
            setProfileName={setProfileName}
            llmInfo={llmInfo}
          />
        )}
      </div>
    </div>
  );
}
