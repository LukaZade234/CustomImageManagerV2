import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { apiClient, getImageUrl, getPortraitUrl } from '../api'
import FilterBar from '../components/FilterBar'
import { Badge, Button, Card, EmptyState } from '../components/ui'
import { thumbUrl } from '../config'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { useStore } from '../store/useStore'

const PAGE_SIZE = 20

const SORT_OPTIONS = [
  { value: 'recent', label: 'Most recent' },
  { value: 'rank', label: 'Rank' },
  { value: 'alphabet', label: 'Alphabet' },
  { value: 'count', label: 'Image count' },
]

/** Direction each sort reads best in when it is first chosen. */
const SORT_DEFAULT_ORDER = { recent: 'desc', rank: 'desc', alphabet: 'asc', count: 'desc' }

/**
 * The server whitelists whole ORDER BY fragments, so build the key from them.
 *
 * Rank is inverted: 1 is the *top* rank, so "Descending" (highest rank first)
 * is what reads best-first, and "Ascending" means the lowest-ranked characters
 * lead. The SQL keys name the numeric order, hence the swap.
 */
function customsSortKey(sort, order) {
  if (sort === 'alphabet') return order === 'desc' ? 'name_desc' : 'name_asc'
  if (sort === 'count') return order === 'desc' ? 'count_desc' : 'count_asc'
  if (sort === 'rank') return order === 'desc' ? 'rank_asc' : 'rank_desc'
  return order === 'asc' ? 'recent_asc' : 'recent'
}

export default function CustomsPage() {
  // Remembered across visits, and shared with the navbar's search: both ask
  // the same name-or-series question. The sort and direction are their own.
  const searchMode = useStore((s) => s.searchMode)
  const setSearchMode = useStore((s) => s.setSearchMode)
  const sort = useStore((s) => s.customsSort)
  const setSort = useStore((s) => s.setCustomsSort)
  const order = useStore((s) => s.customsOrder)
  const setOrder = useStore((s) => s.setCustomsOrder)
  const sortKey = customsSortKey(sort, order)

  // The query and the page live in the URL rather than in state: the back
  // button then steps through what you actually looked at — the previous page,
  // or the unfiltered list before a search — instead of leaving Browse Customs
  // for whatever route came before it. It also makes both linkable.
  const [params, setParams] = useSearchParams()
  const search = params.get('q') ?? ''
  const parsedPage = Number.parseInt(params.get('page') ?? '1', 10)
  const page = Number.isFinite(parsedPage) && parsedPage > 0 ? parsedPage : 1
  const changePage = useCallback(
    (next, { replace = false } = {}) => {
      setParams(
        (prev) => {
          const nextParams = new URLSearchParams(prev)
          // Page one is the absence of the parameter, so the common URL stays
          // /customs rather than /customs?page=1.
          if (next <= 1) nextParams.delete('page')
          else nextParams.set('page', String(next))
          return nextParams
        },
        { replace },
      )
    },
    [setParams],
  )
  const updateSearch = useCallback(
    (value) => {
      setParams(
        (prev) => {
          const nextParams = new URLSearchParams(prev)
          if (value) nextParams.set('q', value)
          else nextParams.delete('q')
          // A different query is a different first page.
          nextParams.delete('page')
          return nextParams
        },
        // The first keystroke of a search is a place to come back to; refining
        // it, or clearing it, is not — otherwise every letter would litter the
        // history.
        { replace: Boolean(params.get('q')) },
      )
    },
    [setParams, params],
  )

  const [pageJumpEditing, setPageJumpEditing] = useState(false)
  const [pageJumpValue, setPageJumpValue] = useState('1')
  const pageJumpInputRef = useRef(null)

  // Debounced so typing does not fire a request per keystroke. Seeded from the
  // URL query, so arriving on a linked or restored search fetches it at once
  // rather than flashing the unfiltered list first.
  const debouncedSearch = useDebouncedValue(search.trim(), 250)

  // Searching, sorting and paging all happen in SQL now. The page used to pull
  // the entire library into memory and do the work here, which cost ~475 KB on
  // every visit and would stop working outright once the roster grows.
  //
  // This is server state rather than a hand-rolled effect, so "Try again" is a
  // refetch instead of a bespoke counter, and the query takes part in the app's
  // invalidation. keepPreviousData holds the current page on screen while the
  // next one loads, which is what the `is-refetching` dimming relies on.
  const {
    data: result,
    isPending,
    isFetching,
    error,
    refetch,
  } = useQuery({
    queryKey: ['customs', page, debouncedSearch, searchMode, sortKey],
    queryFn: () =>
      apiClient.listCustoms({
        page,
        perPage: PAGE_SIZE,
        q: debouncedSearch,
        by: searchMode,
        sort: sortKey,
      }),
    placeholderData: keepPreviousData,
    // The list changes whenever anyone uploads, so revalidate on every mount
    // rather than trusting the app's 30s window. Cached data still paints
    // instantly on a back-navigation; this just refreshes it underneath.
    staleTime: 0,
  })
  const errorMessage = error?.message

  const items = result?.items ?? []
  const total = result?.total ?? 0
  const totalPages = result?.total_pages ?? 1
  const hasSearch = Boolean(debouncedSearch)
  // Only meaningful once a response has arrived; before that the page is loading,
  // not empty.
  const emptySearchNoMatches = Boolean(result) && hasSearch && total === 0
  const totalGlobalEmpty = Boolean(result) && !hasSearch && total === 0

  // A shrinking result set can leave you past the last page. Replaced rather
  // than pushed: correcting an impossible page is not a place to go back to.
  // Guarded on `result`: before the first response `totalPages` is a
  // placeholder 1, and clamping against it rewrote a restored `?page=2` to page
  // one before the page-2 fetch could land — which made the back button from a
  // character page land on page one.
  useEffect(() => {
    if (result && page > totalPages) changePage(totalPages, { replace: true })
  }, [result, page, totalPages, changePage])

  // Every page move — by the arrows, the jump, or the browser's back button —
  // starts the reader at the top of the new page rather than at the pager they
  // left. Skipped on the first render so an arriving visitor is not scrolled.
  const skipFirstScroll = useRef(true)
  // The page is the trigger, not an input: the body scrolls on every change.
  // biome-ignore lint/correctness/useExhaustiveDependencies: trigger, not an input
  useEffect(() => {
    if (skipFirstScroll.current) {
      skipFirstScroll.current = false
      return
    }
    window.scrollTo(0, 0)
  }, [page])

  // totalPages is the trigger, not an input. The click-to-jump input has to close
  // when the result set changes underneath it — a page number typed against the
  // old total is meaningless. Biome wants the dependency gone because the body
  // does not read it, which would turn this into a mount-only effect and leave
  // the input open.
  // biome-ignore lint/correctness/useExhaustiveDependencies: trigger, not an input
  useEffect(() => {
    setPageJumpEditing(false)
  }, [totalPages])

  useEffect(() => {
    if (!pageJumpEditing) setPageJumpValue(String(page))
  }, [page, pageJumpEditing])

  // A filter change is not a page the reader chose to visit, so it corrects the
  // page in place rather than adding a history entry.
  const resetToPage1 = useCallback(() => changePage(1, { replace: true }), [changePage])

  const clearSearch = () => updateSearch('')

  /**
   * Move to another page of results. Pushed, not replaced, so the browser's
   * back button steps through the pages you actually visited; the scroll to the
   * top is handled by the effect on `page`, which covers the back button too.
   */
  const goToPage = (next) => changePage(next)

  const commitPageJump = () => {
    const raw = pageJumpValue.trim()
    if (!raw) {
      setPageJumpValue(String(page))
      setPageJumpEditing(false)
      return
    }
    const n = parseInt(raw, 10)
    if (Number.isFinite(n) && n >= 1 && n <= totalPages) {
      goToPage(n)
    } else {
      setPageJumpValue(String(page))
    }
    setPageJumpEditing(false)
  }

  const startPageJump = () => {
    setPageJumpValue(String(page))
    setPageJumpEditing(true)
    setTimeout(() => pageJumpInputRef.current?.focus(), 0)
  }

  return (
    <Card as="section" padding="lg">
      <h1 className="page-title">Browse Customs</h1>
      <div className="customs-controls">
        <FilterBar
          query={search}
          onQuery={updateSearch}
          placeholder={searchMode === 'name' ? 'Search by name...' : 'Search by series...'}
          ariaLabel={searchMode === 'name' ? 'Search by character name' : 'Search by series'}
          mode={searchMode}
          onMode={(value) => {
            setSearchMode(value)
            resetToPage1()
          }}
          sortOptions={SORT_OPTIONS}
          sort={sort}
          onSort={(value) => {
            setSort(value)
            setOrder(SORT_DEFAULT_ORDER[value] ?? 'asc')
            resetToPage1()
          }}
          order={order}
          onOrder={(value) => {
            setOrder(value)
            resetToPage1()
          }}
        />
      </div>

      {errorMessage && (
        <EmptyState
          title="Could not load the list"
          description={errorMessage}
          action={<Button onClick={() => refetch()}>Try again</Button>}
        />
      )}

      {isPending && !result && (
        <div className="customs-list" aria-busy="true" aria-live="polite">
          <p className="sr-only">Loading customs…</p>
          {Array.from({ length: 6 }, (_, i) => i).map((i) => (
            <div key={i} className="customs-item-with-preview customs-item--skeleton" aria-hidden>
              <div className="customs-item-top">
                <span className="skeleton-tile skeleton-thumb" />
                <div className="search-result-info">
                  <div className="skeleton-line skeleton-line--title" />
                  <div className="skeleton-line skeleton-line--body" />
                </div>
              </div>
              <div className="customs-preview-row">
                {[0, 1, 2].map((j) => (
                  <span key={j} className="skeleton-tile skeleton-thumb skeleton-thumb--sm" />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {totalGlobalEmpty && (
        <EmptyState
          title="No custom images yet"
          description="Upload custom images from any character page and they will appear here."
        />
      )}

      {emptySearchNoMatches && (
        <EmptyState
          title="No matches"
          description={`Nothing matches "${search.trim()}" in ${
            searchMode === 'name' ? 'character names' : 'series'
          }.`}
          action={<Button onClick={clearSearch}>Clear search</Button>}
        />
      )}

      {result && !totalGlobalEmpty && !emptySearchNoMatches && (
        <div className={isFetching ? 'is-refetching' : undefined}>
          <p id="customsCount" className="text-meta customs-count-line">
            {total} characters with custom images. Showing page {page} of {totalPages}.
          </p>
          <div className="customs-list">
            {items.map((c) => (
              <Link
                key={c.name}
                to={`/character/${encodeURIComponent(c.name)}`}
                className="customs-item-with-preview"
              >
                <div className="customs-item-top">
                  <img
                    src={getPortraitUrl(c.image, c.image_thumb)}
                    alt=""
                    className="search-result-img"
                  />
                  <div className="search-result-info">
                    <h3>{c.name}</h3>
                    {c.series && <p>{c.series}</p>}
                    <p>
                      <Badge>{c.count} images</Badge>
                    </p>
                  </div>
                </div>
                {c.previews?.length > 0 && (
                  <div className="customs-preview-row">
                    {c.previews.map((p) => (
                      <img
                        key={p.id ?? p.url}
                        src={p.thumb ? thumbUrl(p.thumb) : getImageUrl(p.url)}
                        alt=""
                        className="customs-preview-thumb"
                        width="80"
                        height="80"
                        loading="lazy"
                        decoding="async"
                      />
                    ))}
                  </div>
                )}
              </Link>
            ))}
          </div>
        </div>
      )}
      {!totalGlobalEmpty && !emptySearchNoMatches && totalPages > 1 && (
        <div className="customs-pagination">
          <Button
            variant="secondary"
            aria-label="First page"
            onClick={() => goToPage(1)}
            disabled={page <= 1}
          >
            «
          </Button>
          <Button
            variant="secondary"
            aria-label="Previous page"
            onClick={() => goToPage(Math.max(1, page - 1))}
            disabled={page <= 1}
          >
            ‹
          </Button>
          <span className="pagination-info">
            {pageJumpEditing ? (
              <>
                Page{' '}
                <input
                  ref={pageJumpInputRef}
                  type="text"
                  inputMode="numeric"
                  className="customs-page-jump-input"
                  value={pageJumpValue}
                  onChange={(e) => setPageJumpValue(e.target.value.replace(/\D/g, ''))}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') commitPageJump()
                    if (e.key === 'Escape') {
                      setPageJumpValue(String(page))
                      setPageJumpEditing(false)
                    }
                  }}
                  onBlur={commitPageJump}
                  aria-label="Page number"
                />{' '}
                of {totalPages}
              </>
            ) : (
              <Button
                variant="ghost"
                size="sm"
                className="pagination-page-indicator"
                onClick={startPageJump}
                title="Click to jump to a page"
              >
                Page {page} of {totalPages}
              </Button>
            )}
          </span>
          <Button
            variant="secondary"
            aria-label="Next page"
            onClick={() => goToPage(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages}
          >
            ›
          </Button>
          <Button
            variant="secondary"
            aria-label="Last page"
            onClick={() => goToPage(totalPages)}
            disabled={page >= totalPages}
          >
            »
          </Button>
        </div>
      )}
    </Card>
  )
}
