import { usePrerequisites } from "../../hooks/usePrerequisites";

const RULES = {
  score:        ({ llmReady })              => llmReady ? null : "Requires LLM provider — configure in Settings",
  generate:     ({ llmReady, resumeReady }) => !llmReady ? "Requires LLM provider — configure in Settings"
                                              : !resumeReady ? "Requires a parsed resume — set up in Profile"
                                              : null,
  parse_resume: ({ llmReady })              => llmReady ? null : "Requires LLM provider — configure in Settings",
};

export default function GatedButton({ action, onClick, children, className = "", disabled: disabledProp, ...rest }) {
  const prereqs = usePrerequisites();
  const rule = RULES[action];
  const reason = rule ? rule(prereqs) : null;
  const disabled = reason !== null || disabledProp;

  return (
    <button
      type="button"
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      title={reason || undefined}
      className={`${className} ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
      {...rest}
    >
      {children}
    </button>
  );
}
