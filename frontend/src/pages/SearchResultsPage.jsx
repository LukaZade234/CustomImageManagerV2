import { Link, useSearchParams } from 'react-router-dom'
import { getImageUrl } from '../api'
import { Button, Card } from '../components/ui'
import { SEARCH_PAGE_SIZE, useCatalogSearch } from '../hooks/useCatalogSearch'
import { useStore } from '../store/useStore'

export default function SearchResultsPage() {
  // Read from the URL, not the store, so a result page is linkable and the
  // back button works.
  const [params] = useSearchParams()
  const searchQuery = params.get('q') || ''
  const mode = params.get('by') === 'series' ? 'series' : 'name'
  const sort = useStore((s) => s.searchSort)
  const order = useStore((s) => s.searchOrder)

  // Matching, sorting and paging happen on the server over the catalog and the
  // working set together, so the whole roster is never downloaded.
  const { items, total, loading, showMore, hasMore } = useCatalogSearch({
    query: searchQuery,
    mode,
    sort,
    order,
  })
  const remaining = total - items.length

  if (loading && items.length === 0) {
    return (
      <Card as="section" padding="lg" className="page-loading-shell" aria-busy="true">
        <h1 className="page-title">Search Results</h1>
        <p className="text-meta page-loading-lead search-skeleton-note">Searching…</p>
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
        {total === 0
          ? 'No characters found'
          : `${total} ${total === 1 ? 'character' : 'characters'} found`}
      </p>
      <div className="search-results-list">
        {items.map((c) => (
          /*
            A link, not a div with role="button". Clicking a result navigates, so
            saying so is what makes middle-click, "open in new tab" and "copy link
            address" work -- none of which the click handler offered -- and it is
            also the only version a keyboard can reach. A <button> would not do:
            its content model is phrasing content, and these results contain a
            heading.

            A catalog-only name has no page to manage yet, so it goes to the Add
            form with the name filled in instead.
          */
          <Link
            key={c.name}
            className="search-result-item"
            to={
              c.in_library
                ? `/character/${encodeURIComponent(c.name)}`
                : `/add?name=${encodeURIComponent(c.name)}`
            }
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
              {!c.in_library && (
                <p className="search-result-hint text-meta">Not in your library — add it</p>
              )}
            </div>
          </Link>
        ))}
      </div>
      {hasMore && (
        <div className="search-results-more">
          <Button variant="secondary" onClick={showMore} disabled={loading}>
            Show {Math.min(SEARCH_PAGE_SIZE, remaining)} more
          </Button>
        </div>
      )}
    </Card>
  )
}
