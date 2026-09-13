import { useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getImageUrl } from '../api'
import { Card } from '../components/ui'
import { useStore } from '../store/useStore'

export default function SearchResultsPage() {
  // Read from the URL, not the store, so a result page is linkable and the
  // back button works.
  const [params] = useSearchParams()
  const searchQuery = params.get('q') || ''
  const mode = params.get('by') === 'series' ? 'series' : 'name'
  const sort = useStore((s) => s.searchSort)
  const order = useStore((s) => s.searchOrder)
  const characters = useStore((s) => s.characters)
  const loading = useStore((s) => s.loading)

  const matches = useMemo(() => {
    if (!searchQuery.trim()) return []
    const q = searchQuery.trim().toLowerCase()
    const filtered = characters.filter((c) => {
      const field = mode === 'name' ? c.name : c.series || ''
      return field.toLowerCase().includes(q)
    })
    const direction = order === 'desc' ? -1 : 1
    const sorted = [...filtered].sort((a, b) => {
      let rank = 0
      if (sort === 'rank') rank = (parseInt(a.rank, 10) || 9999) - (parseInt(b.rank, 10) || 9999)
      else if (sort === 'alphabet') rank = (a.name || '').localeCompare(b.name || '')
      else if (sort === 'count') rank = (a.custom_count || 0) - (b.custom_count || 0)
      return rank * direction
    })
    return sorted
  }, [searchQuery, mode, sort, order, characters])

  if (loading && characters.length === 0) {
    return (
      <Card as="section" padding="lg" className="page-loading-shell" aria-busy="true">
        <h1 className="page-title">Search Results</h1>
        <p className="text-meta page-loading-lead search-skeleton-note">Fetching character list…</p>
        <div className="search-skeleton-list" aria-hidden>
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="search-skeleton-row">
              <div className="skeleton-circle search-skeleton-thumb" />
              <div className="search-skeleton-text">
                <div className="skeleton-line skeleton-line--title" />
                <div className="skeleton-line skeleton-line--body" />
              </div>
            </div>
          ))}
        </div>
      </Card>
    )
  }

  return (
    <Card as="section" padding="lg">
      <h1 className="page-title">Search Results</h1>
      <p className="search-results-count text-meta">
        {matches.length === 0
          ? 'No characters found'
          : `${matches.length} ${matches.length === 1 ? 'character' : 'characters'} found`}
      </p>
      <div className="search-results-list">
        {matches.map((c) => (
          /*
            A link, not a div with role="button". Clicking a result navigates, so
            saying so is what makes middle-click, "open in new tab" and "copy link
            address" work -- none of which the click handler offered -- and it is
            also the only version a keyboard can reach. A <button> would not do:
            its content model is phrasing content, and these results contain a
            heading.
          */
          <Link
            key={c.name}
            className="search-result-item"
            to={`/character/${encodeURIComponent(c.name)}`}
          >
            <img src={getImageUrl(c.image)} alt="" className="search-result-img" />
            <div className="search-result-info">
              <h3>{c.name}</h3>
              {c.series && <p>{c.series}</p>}
              {c.rank && <p>Rank: {c.rank}</p>}
            </div>
          </Link>
        ))}
      </div>
    </Card>
  )
}
