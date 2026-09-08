import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useStore } from '../store/useStore'
import { getImageUrl } from '../api'

export default function SearchResultsPage() {
  const searchQuery = useStore((s) => s.searchQuery)
  const setSearchQuery = useStore((s) => s.setSearchQuery)
  const mode = useStore((s) => s.searchMode)
  const sort = useStore((s) => s.searchSort)
  const characters = useStore((s) => s.characters)
  const loading = useStore((s) => s.loading)
  const navigate = useNavigate()

  const matches = useMemo(() => {
    if (!searchQuery.trim()) return []
    const q = searchQuery.trim().toLowerCase()
    const filtered = characters.filter((c) => {
      const field = mode === 'name' ? c.name : (c.series || '')
      return field.toLowerCase().includes(q)
    })
    const sorted = [...filtered].sort((a, b) => {
      if (sort === 'rank') return (parseInt(a.rank) || 9999) - (parseInt(b.rank) || 9999)
      if (sort === 'name') return (a.name || '').localeCompare(b.name || '')
      if (sort === 'series') return (a.series || '').localeCompare(b.series || '')
      return 0
    })
    return sorted
  }, [searchQuery, mode, sort, characters])

  const handleSelect = (char) => {
    setSearchQuery('')
    navigate(`/character/${encodeURIComponent(char.name)}`)
  }

  if (!searchQuery.trim()) return null

  if (loading && characters.length === 0) {
    return (
      <div id="searchPage" className="search-results-page page-loading-shell" aria-busy="true">
        <h2 className="page-title">Search Results</h2>
        <p className="text-meta page-loading-lead" style={{ textAlign: 'left', marginBottom: '1rem' }}>
          Fetching character list…
        </p>
        <div className="search-skeleton-list" aria-hidden>
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="search-skeleton-row">
              <div className="skeleton-circle search-skeleton-thumb" />
              <div className="search-skeleton-text">
                <div className="skeleton-line skeleton-line--title" style={{ marginBottom: 8 }} />
                <div className="skeleton-line skeleton-line--body" style={{ width: '40%' }} />
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div id="searchPage" className="search-results-page">
      <h2 className="page-title">Search Results</h2>
      <p className="search-results-count text-meta">
        {matches.length === 0
          ? 'No characters found'
          : `${matches.length} ${matches.length === 1 ? 'character' : 'characters'} found`}
      </p>
      <div className="search-results-list">
        {matches.map((c) => (
          <div
            key={c.name}
            className="search-result-item"
            onClick={() => handleSelect(c)}
            onKeyDown={(e) => e.key === 'Enter' && handleSelect(c)}
            role="button"
            tabIndex={0}
          >
            <img src={getImageUrl(c.image)} alt="" className="search-result-img" />
            <div className="search-result-info">
              <h3>{c.name}</h3>
              {c.series && <p>{c.series}</p>}
              {c.rank && <p>Rank: {c.rank}</p>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
