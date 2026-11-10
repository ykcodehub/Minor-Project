import { useEffect, useState } from "react";
/** Bounded automatic polling. A pause is never presented as a server-side failure. */
export function useProcessingPoll(key: string, timeoutMs = 10 * 60 * 1000) {
  const [paused, setPaused] = useState(false);
  const [generation, setGeneration] = useState(0);
  useEffect(() => {
    setPaused(false);
    const timer = window.setTimeout(() => setPaused(true), timeoutMs);
    return () => window.clearTimeout(timer);
  }, [key, generation, timeoutMs]);
  return {
    paused,
    resume: () => {
      setPaused(false);
      setGeneration((value) => value + 1);
    },
  };
}
