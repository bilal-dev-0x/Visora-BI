import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api/client";

interface AsyncState<T> {
  data: T | undefined;
  error: ApiError | undefined;
  loading: boolean;
}

/**
 * Minimal async data hook: loading / error / success with stale-response
 * protection and a manual reload trigger.
 */
export function useAsync<T>(
  factory: () => Promise<T>,
  deps: unknown[],
  options: { enabled?: boolean } = {},
): AsyncState<T> & { reload: () => void } {
  const enabled = options.enabled ?? true;
  const [nonce, setNonce] = useState(0);
  const [state, setState] = useState<AsyncState<T>>({
    data: undefined,
    error: undefined,
    loading: enabled,
  });
  const factoryRef = useRef(factory);
  factoryRef.current = factory;

  useEffect(() => {
    if (!enabled) {
      setState({ data: undefined, error: undefined, loading: false });
      return;
    }
    let cancelled = false;
    setState((prev) => ({ ...prev, loading: true, error: undefined }));
    factoryRef
      .current()
      .then((data) => {
        if (!cancelled) setState({ data, error: undefined, loading: false });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        const apiError =
          error instanceof ApiError
            ? error
            : new ApiError(0, "unexpected_error", "Something went wrong while loading this view.");
        setState({ data: undefined, error: apiError, loading: false });
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce, enabled]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);
  return { ...state, reload };
}

/** Tracks an in-flight imperative action (analyze, delete, upload...). */
export function useAction<Args extends unknown[], R>(
  action: (...args: Args) => Promise<R>,
): {
  run: (...args: Args) => Promise<R | undefined>;
  loading: boolean;
  error: ApiError | null;
  reset: () => void;
} {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const actionRef = useRef(action);
  actionRef.current = action;

  const run = async (...args: Args): Promise<R | undefined> => {
    setLoading(true);
    setError(null);
    try {
      return await actionRef.current(...args);
    } catch (caught) {
      const apiError =
        caught instanceof ApiError
          ? caught
          : new ApiError(0, "unexpected_error", "Something went wrong. Please try again.");
      setError(apiError);
      return undefined;
    } finally {
      setLoading(false);
    }
  };

  return { run, loading, error, reset: () => setError(null) };
}
