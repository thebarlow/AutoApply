import { useState } from "react";
import StepLLM from "./StepLLM";
import StepResume from "./StepResume"; // Created in Task 7

export default function Wizard({ onFinish, onSkip }) {
  const [step, setStep] = useState(1);
  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center">
      <div className="bg-[#0f0f1a] border border-space-border rounded-xl shadow-2xl w-[600px] max-w-[90vw] p-6 text-space-text">
        <div className="flex justify-between items-center mb-4">
          <div className="text-sm text-space-dim">Step {step} of 2</div>
          <button
            onClick={onSkip}
            className="text-sm text-space-dim hover:text-space-text transition-colors hover:underline"
          >
            Skip for now
          </button>
        </div>
        {step === 1 && <StepLLM onNext={() => setStep(2)} />}
        {step === 2 && <StepResume onBack={() => setStep(1)} onFinish={onFinish} />}
      </div>
    </div>
  );
}
