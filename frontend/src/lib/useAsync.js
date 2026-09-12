import { useCallback, useState } from "react";

/** Runs an async action and tracks pending/error state, so every page handles both the same way. */
export function useAsync(action) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);

  const run = useCallback(
    async (...args) => {
      setPending(true);
      setError(null);
      try {
        return await action(...args);
      } catch (e) {
        setError(e.message);
        return undefined;
      } finally {
        setPending(false);
      }
    },
    [action],
  );

  return { run, pending, error, clearError: () => setError(null) };
}