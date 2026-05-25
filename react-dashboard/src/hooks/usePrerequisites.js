import { useCallback, useEffect, useState } from "react";
import { getSetupStatus } from "../api";

export function usePrerequisites() {
  const [state, setState] = useState({
    llmReady: false,
    resumeReady: false,
    loaded: false,
    error: null,
  });

  const refresh = useCallback(async () => {
    try {
      const data = await getSetupStatus();
      setState({
        llmReady: !!data.llm_configured,
        resumeReady: !!data.resume_parsed,
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

  const isFirstRun = state.loaded && !state.error && !state.llmReady && !state.resumeReady;

  return { ...state, isFirstRun, refresh };
}
