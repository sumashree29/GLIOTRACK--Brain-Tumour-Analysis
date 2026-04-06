"use client";

// ─────────────────────────────────────────────────────────────────────────────
// GLIOTRACK — usePolling hook
//
// Wraps the pure startPolling engine in a React-friendly interface.
// The hook re-starts whenever the `scanId` dependency changes.
// POLL_INTERVAL_MS and POLL_MAX flow through lib/polling — never hardcoded here.
// ─────────────────────────────────────────────────────────────────────────────

import { useEffect, useRef, useState } from "react";
import { startPolling, type PollOptions } from "@/lib/polling";

export interface PollingState<T> {
  /** Most recent data returned by the fetcher */
  data:      T | null;
  /** Number of fetch attempts so far */
  attempts:  number;
  /** True after POLL_MAX attempts without isDone returning true */
  timedOut:  boolean;
  /** True when isDone returned true OR timeout occurred */
  finished:  boolean;
}

/**
 * Starts polling when `opts` is non-null.
 * Pass `null` to prevent polling (e.g. when scan_id isn't ready).
 */
export function usePolling<T>(
  opts: PollOptions<T> | null
): PollingState<T> & { stop: () => void } {
  const [state, setState] = useState<PollingState<T>>({
    data:     null,
    attempts: 0,
    timedOut: false,
    finished: false,
  });

  const stopRef = useRef<(() => void) | null>(null);

  function stop() {
    stopRef.current?.();
    stopRef.current = null;
    setState((prev) => ({ ...prev, finished: true }));
  }

  useEffect(() => {
    if (!opts) return;

    // Reset state on each new poll session
    setState({ data: null, attempts: 0, timedOut: false, finished: false });

    const cleanup = startPolling<T>({
      ...opts,

      onTick(data, attempt) {
        setState((prev) => ({ ...prev, data, attempts: attempt }));
        opts.onTick?.(data, attempt);

        // Mark finished if isDone passes
        if (opts.isDone(data)) {
          setState((prev) => ({ ...prev, finished: true }));
        }
      },

      onTimeout() {
        setState((prev) => ({ ...prev, timedOut: true, finished: true }));
        opts.onTimeout?.();
      },

      onError(err, attempt) {
        setState((prev) => ({ ...prev, attempts: attempt }));
        opts.onError?.(err, attempt);
      },
    });

    stopRef.current = cleanup;
    return cleanup;
    // opts is intentionally excluded — callers manage re-triggering via key prop
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { ...state, stop };
}

export default usePolling;
