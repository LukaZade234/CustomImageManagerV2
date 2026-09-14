import { useInfiniteQuery } from '@tanstack/react-query'
import { apiClient } from '../api'
import { useDebouncedValue } from './useDebouncedValue'

/**
 * Server-side search with paging.
 *
 * The roster is no longer downloaded, so the page asks the server for one page
 * at a time, and "Show more" walks the pages with `useInfiniteQuery` — each
 * page is cached by the inputs that produced it, so returning to a query you
 * already ran is instant. Typing is debounced; paging is not.
 */
const PAGE_SIZE = 60

export { PAGE_SIZE as SEARCH_PAGE_SIZE }

export function useCatalogSearch({ query, mode, sort, order, delay = 250 }) {
  const q = (query || '').trim()
  const debouncedQuery = useDebouncedValue(q, delay)
  // Rank 1 is the best rank, so the direction that reads best-first is the
  // descending one; the server sorts literally. The customs list makes the
  // same swap, so both read the same way.
  const apiOrder = sort === 'rank' ? (order === 'desc' ? 'asc' : 'desc') : order

  const { data, isPending, isFetching, fetchNextPage, hasNextPage } = useInfiniteQuery({
    queryKey: ['catalog-search', { query: debouncedQuery, mode, sort, order: apiOrder }],
    queryFn: ({ pageParam }) =>
      apiClient.searchCharacters({
        q: debouncedQuery,
        by: mode,
        sort,
        order: apiOrder,
        page: pageParam,
        perPage: PAGE_SIZE,
      }),
    initialPageParam: 1,
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.reduce((n, page) => n + (page?.items?.length ?? 0), 0)
      const total = lastPage?.total ?? 0
      return loaded < total ? allPages.length + 1 : undefined
    },
    enabled: Boolean(debouncedQuery),
  })

  const items = data?.pages.flatMap((page) => page?.items ?? []) ?? []
  const total = data?.pages[0]?.total ?? 0

  return {
    items,
    total,
    loading: Boolean(debouncedQuery) && (isPending || isFetching),
    showMore: () => {
      if (hasNextPage) fetchNextPage()
    },
    hasMore: Boolean(hasNextPage),
  }
}
