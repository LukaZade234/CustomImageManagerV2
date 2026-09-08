/**
 * Shown while the app fetches characters / initial collection data on Home.
 */
export default function HomeLoadingState() {
  return (
    <div className="home-page page-loading-shell" aria-busy="true" aria-live="polite">
      <p className="text-meta page-loading-lead">Fetching characters and your collection…</p>
      <div className="skeleton-stats" aria-hidden>
        <div className="skeleton-stat-card">
          <div className="skeleton-circle" />
          <div className="skeleton-stat-text">
            <div className="skeleton-line skeleton-line--lg" />
            <div className="skeleton-line skeleton-line--sm" />
          </div>
        </div>
        <div className="skeleton-stat-card">
          <div className="skeleton-circle" />
          <div className="skeleton-stat-text">
            <div className="skeleton-line skeleton-line--lg" />
            <div className="skeleton-line skeleton-line--sm" />
          </div>
        </div>
      </div>
      <div className="skeleton-features" aria-hidden>
        <div className="skeleton-line skeleton-line--title" />
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="skeleton-line skeleton-line--body" />
        ))}
      </div>
    </div>
  )
}
