import { useState, useMemo, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useStore } from '../store/useStore'
import { getImageUrl } from '../api'

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
    if (sort === 'rank_asc') filtered.sort((a, b) => (parseInt(a.rank) || 9999) - (parseInt(b.rank) || 9999))
    if (sort === 'name_asc') filtered.sort((a, b) => (a.name || '').localeCompare(b.name || ''))
    if (sort === 'name_desc') filtered.sort((a, b) => (b.name || '').localeCompare(a.name || ''))
    if (sort === 'series_asc') filtered.sort((a, b) => (a.series || '').localeCompare(b.series || ''))
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
    <div id="customsPage" className="customs-page">
      <h2 className="page-title">Browse Customs</h2>
      <div className="customs-controls">
        <div className="search-input-wrapper customs-search-wrap">
          <input
            type="text"
            className="char-search-input"
            placeholder={searchMode === 'name' ? 'Search by name...' : 'Search by series...'}
            value={search}
            onChange={(e) => { setSearch(e.target.value); resetToPage1() }}
            autoComplete="off"
          />
          <div className="search-toggle-wrapper search-toggle-visible">
            <span
              className={`toggle-label toggle-option ${searchMode === 'name' ? 'active' : ''}`}
              onClick={() => { setSearchMode('name'); resetToPage1() }}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && setSearchMode('name')}
            >
              Name
            </span>
            <span
              className={`toggle-label toggle-option ${searchMode === 'series' ? 'active' : ''}`}
              onClick={() => { setSearchMode('series'); resetToPage1() }}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && setSearchMode('series')}
            >
              Series
            </span>
          </div>
        </div>
        <div className="customs-sort-field">
          <label htmlFor="customsSort" className="customs-sort-label">Sort by</label>
          <select
            id="customsSort"
            className="customs-sort-select"
            value={sort}
            onChange={(e) => { setSort(e.target.value); resetToPage1() }}
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
      </div>

      {totalGlobalEmpty && (
        <div className="empty-state">
          <p className="empty-state-title">No custom images yet</p>
          <p className="text-meta">Upload custom images from any character page, then they will appear here.</p>
        </div>
      )}

      {emptySearchNoMatches && (
        <div className="empty-state empty-state--search">
          <p className="empty-state-title">No matches</p>
          <p className="text-meta">
            Nothing matches &quot;{search.trim()}&quot; in {searchMode === 'name' ? 'character names' : 'series'}.
          </p>
          <button type="button" className="action-btn empty-state-clear" onClick={clearSearch}>
            Clear search
          </button>
        </div>
      )}

      {!totalGlobalEmpty && !emptySearchNoMatches && (
        <>
          <p id="customsCount" className="text-meta customs-count-line">
            {customsList.length} characters with custom images. Showing page {page} of {totalPages}.
          </p>
          <div id="customsList" className="search-result-list">
            {paginatedList.map((c) => (
              <Link key={c.name} to={`/character/${encodeURIComponent(c.name)}`} className="customs-item-with-preview">
                <div className="customs-item-top">
                  <img src={getImageUrl(c.image)} alt="" className="search-result-img" />
                  <div className="search-result-info" style={{ flex: 1 }}>
                    <h3>{c.name}</h3>
                    {c.series && <p>{c.series}</p>}
                    <p>
                      <span className="badge" style={{ display: 'inline-block', marginLeft: '8px', padding: '2px 8px', background: '#e9ecef', borderRadius: '4px', fontSize: '0.8rem' }}>
                        {c.customCount} images
                      </span>
                    </p>
                  </div>
                </div>
                {c.customUrls?.length > 0 && (
                  <div className="customs-preview-row">
                    {c.customUrls.slice(0, PREVIEW_COUNT).map((url) => (
                      <img key={url} src={getImageUrl(url)} alt="" className="customs-preview-thumb" />
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
          <button
            type="button"
            className="action-btn customs-page-btn"
            aria-label="First page"
            onClick={() => setPage(1)}
            disabled={page <= 1}
          >
            «
          </button>
          <button
            type="button"
            className="action-btn customs-page-btn"
            aria-label="Previous page"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
          >
            ‹
          </button>
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
              <button
                type="button"
                className="pagination-page-indicator"
                onClick={startPageJump}
                title="Click to jump to a page"
              >
                Page {page} of {totalPages}
              </button>
            )}
          </span>
          <button
            type="button"
            className="action-btn customs-page-btn"
            aria-label="Next page"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
          >
            ›
          </button>
          <button
            type="button"
            className="action-btn customs-page-btn"
            aria-label="Last page"
            onClick={() => setPage(totalPages)}
            disabled={page >= totalPages}
          >
            »
          </button>
        </div>
      )}
    </div>
  )
}
