import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'

/**
 * A fresh query client per test, with retries off.
 *
 * Retrying is right in the app and wrong in a test: a mock that rejects would
 * otherwise burn three attempts with real backoff before the assertion runs,
 * and a cache shared between tests would leak one test's data into the next.
 */
export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      // No retry (a rejecting mock would burn attempts before the assertion),
      // no GC and no staleness, so a seeded query is served as-is and an
      // unseeded one still fetches exactly once.
      queries: {
        retry: false,
        gcTime: Number.POSITIVE_INFINITY,
        staleTime: Number.POSITIVE_INFINITY,
      },
    },
  })
}

export function renderWithQueryClient(
  ui,
  { client = createTestQueryClient(), queries = [], ...options } = {},
) {
  // Seed before render so the first paint already sees the data, the way the
  // store used to be seeded by `setState` in a test. `undefined` is skipped so
  // a caller can pass an optional seed without materialising a fake one.
  for (const [key, data] of queries) {
    if (data !== undefined) client.setQueryData(key, data)
  }
  return {
    client,
    ...render(ui, {
      wrapper: ({ children }) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      ),
      ...options,
    }),
  }
}
