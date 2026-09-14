import { useEffect, useState } from 'react'
import { apiClient } from '../api'

/**
 * Server-side search with paging.
 *
 * The roster is no longer downloaded, so the page asks the server for one page
 * at a time. Typing is debounced; moving to the next page is not. Results
 * accumulate across pages, and a change to the query, mode, sort or order
 * starts again from page one.
 */
const PAGE_SIZE = 60

export { PAGE_SIZE as SEARCH_PAGE_SIZE }

export function useCatalogSearch({ query, mode, sort, order, delay = 250 }) {
  const [state, setState] = useState({ items: [], total: 0, loading: false })
  // Keyed by the inputs, so changing any of them resets to page one during the
  // render rather than in an effect that would race the fetch.
  const key = `${query}\u0000${mode}\u0000${sort}\u0000${order}`
  const [page, setPage] = useState({ key, n: 1 })
  if (page.key !== key) setPage({ key, n: 1 })
  const pageNumber = page.n

  useEffect(() => {
    const q = (query || '').trim()
    if (!q) {
      setState({ items: [], total: 0, loading: false })
      return undefined
    }
    let cancelled = false
    setState((s) => ({ ...s, loading: true }))
    // Rank 1 is the best rank, so the direction that reads best-first is the
    // descending one; the server sorts literally. The customs list makes the
    // same swap, so both read the same way.
    const apiOrder = sort === 'rank' ? (order === 'desc' ? 'asc' : 'desc') : order
    const run = async () => {
      try {
        const res = await apiClient.searchCharacters({
          q,
          by: mode,
          sort,
          order: apiOrder,
          page: pageNumber,
          perPage: PAGE_SIZE,
        })
        if (cancelled) return
        const items = res?.items || []
        setState((s) => ({
          items: pageNumber === 1 ? items : [...s.items, ...items],
          total: res?.total ?? 0,
          loading: false,
        }))
      } catch {
        if (!cancelled) {
          setState((s) =>
            pageNumber === 1 ? { items: [], total: 0, loading: false } : { ...s, loading: false },
          )
        }
      }
    }
    // Debounce typing on page one; a "Show more" request is immediate.
    const timer = setTimeout(run, pageNumber === 1 ? delay : 0)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [query, mode, sort, order, pageNumber, delay])

  return {
    items: state.items,
    total: state.total,
    loading: state.loading,
    showMore: () => setPage((p) => ({ ...p, n: p.n + 1 })),
    hasMore: state.items.length < state.total,
  }
}
