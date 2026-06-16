import StepResume from "./StepResume";

export default function Wizard({ onFinish, onSkip }) {
  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center">
      <div className="bg-[#0f0f1a] border border-space-border rounded-xl shadow-2xl w-[600px] max-w-[90vw] p-6 text-space-text">
        <div className="mb-4 text-center">
          <h1 className="text-2xl font-bold text-white">Upload Master Resume</h1>
          <p className="text-sm text-space-dim mt-1">
            We'll parse it into your profile to get you started.
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
        <StepResume onFinish={onFinish} />
      </div>
    </div>
  );
}
