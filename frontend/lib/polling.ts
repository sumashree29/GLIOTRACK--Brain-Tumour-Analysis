// ─────────────────────────────────────────────────────────────────────────────
// GLIOTRACK — Polling engine
//
// POLL_INTERVAL_MS (15s) and POLL_MAX (80) are imported from constants.
// They must never be overridden inline — pass them through opts only in tests.
// ─────────────────────────────────────────────────────────────────────────────

import { POLL_INTERVAL_MS, POLL_MAX } from "@/lib/constants";

export interface PollOptions<T> {
  /** Async function called on every tick to get current state */
  fetcher: () => Promise<T>;
  /** Return true to stop polling (success condition) */
  isDone: (data: T) => boolean;
  /** Called on every successful fetch */
  onTick?: (data: T, attempt: number) => void;
  /** Called when POLL_MAX attempts are exhausted */
  onTimeout?: () => void;
  /** Called when fetcher throws — polling continues */
  onError?: (err: unknown, attempt: number) => void;
  /** Test-only: override interval in ms */
  _intervalMs?: number;
  /** Test-only: override max attempts */
  _maxAttempts?: number;
}

/**
 * Starts a polling loop. Returns a `stop()` function.
 *
 * First tick fires immediately (0 ms delay), subsequent ticks
 * fire after POLL_INTERVAL_MS.
 */
export function startPolling<T>(opts: PollOptions<T>): () => void {
  const intervalMs  = opts._intervalMs  ?? POLL_INTERVAL_MS;
  const maxAttempts = opts._maxAttempts ?? POLL_MAX;

  let attempts = 0;
  let stopped  = false;
  let timerId: ReturnType<typeof setTimeout> | null = null;

  async function tick() {
    if (stopped) return;

    attempts++;

    try {
      const data = await opts.fetcher();

      if (!stopped) {
        opts.onTick?.(data, attempts);

        if (opts.isDone(data)) {
          stopped = true;
          return;
        }
      }
    } catch (err) {
      if (!stopped) opts.onError?.(err, attempts);
    }

    if (stopped) return;

    if (attempts >= maxAttempts) {
      opts.onTimeout?.();
      stopped = true;
      return;
    }

    timerId = setTimeout(tick, intervalMs);
  }

  // Fire first tick immediately
  timerId = setTimeout(tick, 0);

  return function stop() {
    stopped = true;
    if (timerId !== null) {
      clearTimeout(timerId);
      timerId = null;
    }
  };
}
