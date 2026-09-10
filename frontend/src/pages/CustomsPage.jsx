import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiClient, getImageUrl } from '../api'
import { Badge, Button, Card, EmptyState, Input, SegmentedControl, Select } from '../components/ui'

const PAGE_SIZE = 20

const SORT_OPTIONS = [
  { value: 'recent', label: 'Most Recent' },
  { value: 'rank_asc', label: 'Rank (High-Low)' },
  { value: 'name_asc', label: 'Name (A-Z)' },
  { value: 'name_desc', label: 'Name (Z-A)' },
  { value: 'series_asc', label: 'Series (A-Z)' },
  { value: 'count_desc', label: 'Most Images' },
  { value: 'count_asc', label: 'Fewest Images' },
]

export default function CustomsPage() {
  const [search, setSearch] = useState('')
  const [searchMode, setSearchMode] = useState('name')
  const [sort, setSort] = useState('recent')
  const [page, setPage] = useState(1)
  const [pageJumpEditing, setPageJumpEditing] = useState(false)
  const [pageJumpValue, setPageJumpValue] = useState('1')
  const pageJumpInputRef = useRef(null)

  // Searching, sorting and paging all happen in SQL now. The page used to pull
  // the entire library into memory and do the work here, which cost ~475 KB on
  // every visit and would stop working outright once the roster grows.
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Debounced so typing does not fire a request per keystroke.
  const [debouncedSearch, setDebouncedSearch] = useState('')
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search.trim()), 250)
    return () => clearTimeout(timer)
  }, [search])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    apiClient
      .listCustoms({ page, perPage: PAGE_SIZE, q: debouncedSearch, by: searchMode, sort })
      .then((data) => {
        if (cancelled) return
        setResult(data)
        setError(null)
      })
      .catch((e) => {
        if (!cancelled) setError(e.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [page, debouncedSearch, searchMode, sort])

  const items = result?.items ?? []
  const total = result?.total ?? 0
  const totalPages = result?.total_pages ?? 1
  const hasSearch = Boolean(debouncedSearch)
  // Only meaningful once a response has arrived; before that the page is loading,
  // not empty.
  const emptySearchNoMatches = Boolean(result) && hasSearch && total === 0
  const totalGlobalEmpty = Boolean(result) && !hasSearch && total === 0

  // A shrinking result set can leave you past the last page.
  useEffect(() => {
    setPage((p) => Math.min(p, totalPages))
  }, [totalPages])

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

  const resetToPage1 = () => setPage(1)

  const clearSearch = () => {
    setSearch('')
    resetToPage1()
  }

  const commitPageJump = () => {
    const raw = pageJumpValue.trim()
    if (!raw) {
      setPageJumpValue(String(page))
      setPageJumpEditing(false)
      return
    }
    const n = parseInt(raw, 10)
    if (Number.isFinite(n) && n >= 1 && n <= totalPages) {
      setPage(n)
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
        <div className="search-field">
          <Input
            type="search"
            aria-label={searchMode === 'name' ? 'Search by character name' : 'Search by series'}
            placeholder={searchMode === 'name' ? 'Search by name...' : 'Search by series...'}
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              resetToPage1()
            }}
            autoComplete="off"
          />
          <SegmentedControl
            name="customs-search-mode"
            label="Search by"
            value={searchMode}
            onChange={(v) => {
              setSearchMode(v)
              resetToPage1()
            }}
            options={[
              { value: 'name', label: 'Name' },
              { value: 'series', label: 'Series' },
            ]}
          />
        </div>
        <div className="customs-sort-field">
          <label htmlFor="customsSort" className="customs-sort-label">
            Sort by
          </label>
          <Select
            id="customsSort"
            className="customs-sort-select"
            value={sort}
            onChange={(e) => {
              setSort(e.target.value)
              resetToPage1()
            }}
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {error && (
        <EmptyState
          title="Could not load the list"
          description={error}
          action={<Button onClick={() => setPage((p) => p)}>Try again</Button>}
        />
      )}

      {loading && !result && (
        <div className="customs-list" aria-busy="true" aria-live="polite">
          <p className="sr-only">Loading customs…</p>
          {Array.from({ length: 6 }, (_, i) => i).map((i) => (
            <div key={i} className="customs-skeleton-row">
              <div className="skeleton-line skeleton-line--title" />
              <div className="skeleton-line skeleton-line--body" />
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
        <div className={loading ? 'is-refetching' : undefined}>
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
                  <img src={getImageUrl(c.image)} alt="" className="search-result-img" />
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
                    {c.previews.map((url) => (
                      <img
                        key={url}
                        src={getImageUrl(url)}
                        alt=""
                        className="customs-preview-thumb"
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
            onClick={() => setPage(1)}
            disabled={page <= 1}
          >
            «
          </Button>
          <Button
            variant="secondary"
            aria-label="Previous page"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
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
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
          >
            ›
          </Button>
          <Button
            variant="secondary"
            aria-label="Last page"
            onClick={() => setPage(totalPages)}
            disabled={page >= totalPages}
          >
            »
          </Button>
        </div>
      )}
    </Card>
  )
}
