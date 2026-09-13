import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getImageUrl } from '../api'
import { Button, Card } from '../components/ui'
import { useStore } from '../store/useStore'

// A one-letter query can match the whole roster. Rendering every hit eager was
// fine at 1,700 characters and is not at the tens of thousands the library is
// meant to reach, so the list grows on demand instead.
const PAGE_SIZE = 60

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
  // Keyed by the query, so moving to a new search starts from the first page
  // again without an effect that would run a render behind.
  const queryKey = `${searchQuery}\u0000${mode}`
  const [more, setMore] = useState({ key: queryKey, count: PAGE_SIZE })
  if (more.key !== queryKey) setMore({ key: queryKey, count: PAGE_SIZE })
  const visibleCount = more.count

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
      if (sort === 'rank') {
        // Rank 1 is the top rank, so the comparison is inverted: ascending
        // (lowest rank first) means the numerically largest ranks lead, and
        // descending reads best-first.
        rank = (parseInt(b.rank, 10) || 9999) - (parseInt(a.rank, 10) || 9999)
      } else if (sort === 'alphabet') rank = (a.name || '').localeCompare(b.name || '')
      else if (sort === 'count') rank = (a.custom_count || 0) - (b.custom_count || 0)
      return rank * direction
    })
    return sorted
  }, [searchQuery, mode, sort, order, characters])

  const shown = matches.slice(0, visibleCount)

  if (loading && characters.length === 0) {
    return (
      <Card as="section" padding="lg" className="page-loading-shell" aria-busy="true">
        <h1 className="page-title">Search Results</h1>
        <p className="text-meta page-loading-lead search-skeleton-note">Fetching character list…</p>
        <div className="search-results-list" aria-hidden>
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="search-result-item">
              <span className="skeleton-circle search-result-img" />
              <div className="search-result-info">
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
        {shown.map((c) => (
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
            <img
              src={getImageUrl(c.image)}
              alt=""
              className="search-result-img"
              width="80"
              height="80"
              loading="lazy"
              decoding="async"
            />
            <div className="search-result-info">
              <h3>{c.name}</h3>
              {c.series && <p>{c.series}</p>}
              {c.rank && <p>Rank: {c.rank}</p>}
            </div>
          </Link>
        ))}
      </div>
      {visibleCount < matches.length && (
        <div className="search-results-more">
          <Button
            variant="secondary"
            onClick={() => setMore((m) => ({ ...m, count: m.count + PAGE_SIZE }))}
          >
            Show {Math.min(PAGE_SIZE, matches.length - visibleCount)} more
          </Button>
        </div>
      )}
    </Card>
  )
}
