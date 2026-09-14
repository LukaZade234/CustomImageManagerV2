import { QueryClient } from '@tanstack/react-query'
import { backoffDelay, isTransientError } from '../utils/retry'

/**
 * Retry only what is worth retrying: three attempts with backoff, and only for
 * transient failures. This replaces the retry loop the store hand-rolled for
 * the gallery fetch, so every query now gets the same policy for free.
 */
export function retryPolicy(failureCount, error) {
  return failureCount < 3 && isTransientError(error)
}

/**
 * The application's one server-state cache.
 *
 * A short stale window makes back-navigation instant without letting data go
 * meaningfully stale: every mutation invalidates the key it touched, so the
 * only way a query here is out of date is if the change came from elsewhere.
 * Refetching on window focus is off for the same reason it would be painful —
 * alt-tabbing back to a 256-image gallery should not re-download it.
 */
export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: retryPolicy,
        retryDelay: (attempt) => backoffDelay(attempt),
        staleTime: 30_000,
        refetchOnWindowFocus: false,
      },
    },
  })
}
