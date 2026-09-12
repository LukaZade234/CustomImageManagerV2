import { Card } from './ui'

/**
 * Shown while the app fetches characters / initial collection data on Home.
 * Uses the same Card as HomePage so the frame does not appear only once the
 * data lands.
 */
export default function HomeLoadingState() {
  return (
    <Card
      as="section"
      padding="lg"
      className="page-loading-shell"
      aria-busy="true"
      aria-live="polite"
    >
      <p className="text-meta page-loading-lead">Fetching characters and your collection…</p>
      <div className="skeleton-hero" aria-hidden>
        <div className="skeleton-hero__identity">
          <div className="skeleton-line skeleton-line--lg" />
          <div className="skeleton-line skeleton-line--body" />
        </div>
        <div className="skeleton-hero__figures">
          <div className="skeleton-line skeleton-line--body" />
          <div className="skeleton-line skeleton-line--body" />
          <div className="skeleton-line skeleton-line--body" />
        </div>
      </div>
    </Card>
  )
}
