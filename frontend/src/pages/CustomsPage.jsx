import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { getImageUrl } from '../api'
import { Badge, Button, Card, EmptyState, Input, SegmentedControl, Select } from '../components/ui'
import { useStore } from '../store/useStore'

const PAGE_SIZE = 20
const PREVIEW_COUNT = 3

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
  const characters = useStore((s) => s.characters)
  const customImages = useStore((s) => s.customImages)
  const loadCustomImages = useStore((s) => s.loadCustomImages)
  /** Unix seconds per character — updated when customs change (server `last_updated`). */
  const lastUpdated = useStore((s) => s.lastUpdated)
  const [search, setSearch] = useState('')
  const [searchMode, setSearchMode] = useState('name')
  const [sort, setSort] = useState('recent')
  const [page, setPage] = useState(1)
  const [pageJumpEditing, setPageJumpEditing] = useState(false)
  const [pageJumpValue, setPageJumpValue] = useState('1')
  const pageJumpInputRef = useRef(null)

  useEffect(() => {
    loadCustomImages()
  }, [loadCustomImages])

  const baseCustomsList = useMemo(() => {
    const entries = Object.entries(customImages).filter(([, urls]) => urls?.length > 0)
    return entries.map(([name, urls]) => {
      const char = characters.find((c) => c.name === name) || { name, series: '', rank: '' }
      const ts = lastUpdated[name]
      const lastModified = typeof ts === 'number' && Number.isFinite(ts) ? ts : 0
      return { ...char, customCount: urls.length, customUrls: urls, lastModified }
    })
  }, [customImages, characters, lastUpdated])

  const searchFiltered = useMemo(() => {
    if (!search.trim()) return baseCustomsList
    const q = search.trim().toLowerCase()
    if (searchMode === 'name') {
      return baseCustomsList.filter((c) => c.name.toLowerCase().includes(q))
    }
    return baseCustomsList.filter((c) => (c.series || '').toLowerCase().includes(q))
  }, [baseCustomsList, search, searchMode])

  const customsList = useMemo(() => {
    const filtered = [...searchFiltered]
    if (sort === 'recent') filtered.sort((a, b) => (b.lastModified || 0) - (a.lastModified || 0))
    if (sort === 'rank_asc')
      filtered.sort((a, b) => (parseInt(a.rank) || 9999) - (parseInt(b.rank) || 9999))
    if (sort === 'name_asc') filtered.sort((a, b) => (a.name || '').localeCompare(b.name || ''))
    if (sort === 'name_desc') filtered.sort((a, b) => (b.name || '').localeCompare(a.name || ''))
    if (sort === 'series_asc')
      filtered.sort((a, b) => (a.series || '').localeCompare(b.series || ''))
    if (sort === 'count_desc') filtered.sort((a, b) => b.customCount - a.customCount)
    if (sort === 'count_asc') filtered.sort((a, b) => a.customCount - b.customCount)
    return filtered
  }, [searchFiltered, sort])

  const hasSearch = Boolean(search.trim())
  const emptySearchNoMatches = hasSearch && customsList.length === 0 && baseCustomsList.length > 0
  const totalGlobalEmpty = baseCustomsList.length === 0

  const totalPages = Math.ceil(customsList.length / PAGE_SIZE) || 1

  useEffect(() => {
    setPage((p) => Math.min(p, totalPages))
  }, [totalPages])

  useEffect(() => {
    setPageJumpEditing(false)
  }, [totalPages])

  useEffect(() => {
    if (!pageJumpEditing) setPageJumpValue(String(page))
  }, [page, pageJumpEditing])
  const paginatedList = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE
    return customsList.slice(start, start + PAGE_SIZE)
  }, [customsList, page])

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
    <Card as="section" padding="lg" className="customs-page">
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

      {!totalGlobalEmpty && !emptySearchNoMatches && (
        <>
          <p id="customsCount" className="text-meta customs-count-line">
            {customsList.length} characters with custom images. Showing page {page} of {totalPages}.
          </p>
          <div className="customs-list">
            {paginatedList.map((c) => (
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
                      <Badge>{c.customCount} images</Badge>
                    </p>
                  </div>
                </div>
                {c.customUrls?.length > 0 && (
                  <div className="customs-preview-row">
                    {c.customUrls.slice(0, PREVIEW_COUNT).map((url) => (
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
        </>
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
