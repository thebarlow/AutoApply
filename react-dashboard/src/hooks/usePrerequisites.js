import { useCallback, useEffect, useState } from "react";
import { getSetupStatus } from "../api";

export function usePrerequisites() {
  const [state, setState] = useState({
    llmReady: false,
    resumeReady: false,
    onboardingTour: 'unstarted',
    loaded: false,
    error: null,
  });

  const refresh = useCallback(async () => {
    try {
      const data = await getSetupStatus();
      setState({
        llmReady: !!data.llm_configured,
        resumeReady: !!data.resume_parsed,
        onboardingTour: data.onboarding_tour || 'unstarted',
        loaded: true,
        error: null,
      });
    } catch (e) {
      setState((s) => ({ ...s, loaded: true, error: e.message }));
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // The platform owns the LLM key, so onboarding keys only on a missing résumé.
  const isFirstRun = state.loaded && !state.error && !state.resumeReady;

  return { ...state, isFirstRun, refresh };
}
