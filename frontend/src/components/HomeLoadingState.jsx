import { Card } from './ui'

const STRIP = [0, 1, 2, 3, 4, 5, 6, 7]
const ROWS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

/** A row of poster-shaped frames, standing in for a ranked strip or ticker. */
function Strip() {
  return (
    <div className="skeleton-strip" aria-hidden>
      {STRIP.map((i) => (
        <span key={i} className="skeleton-tile" />
      ))}
    </div>
  )
}

/**
 * Shown while the library loads on Home.
 *
 * It mirrors the real page's sections -- hero, the "Just added" strip, the two
 * ranked strips beside the contributor leaderboard, and the series ledger -- so
 * the frame keeps the page's shape instead of collapsing to the hero and then
 * jumping when ten sections land at once.
 */
export default function HomeLoadingState() {
  return (
    <div className="home" aria-busy="true" aria-live="polite">
      <p className="sr-only">Loading the library…</p>
      <Card as="section" padding="lg" className="page-loading-shell">
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

      <Card as="section" padding="lg" className="page-loading-shell">
        <div className="skeleton-line skeleton-line--title" aria-hidden />
        <Strip />
      </Card>

      <div className="home-lower home-lower--split">
        <div className="home-lower__main">
          <Card as="section" padding="lg" className="page-loading-shell">
            <div className="skeleton-line skeleton-line--title" aria-hidden />
            <Strip />
          </Card>
          <Card as="section" padding="lg" className="page-loading-shell">
            <div className="skeleton-line skeleton-line--title" aria-hidden />
            <Strip />
          </Card>
        </div>
        <aside className="home-lower__aside">
          <Card as="section" padding="lg" className="page-loading-shell home-leaderboard">
            <div className="skeleton-line skeleton-line--title" aria-hidden />
            <div className="skeleton-rows" aria-hidden>
              {ROWS.map((i) => (
                <div key={i} className="skeleton-line skeleton-line--body" />
              ))}
            </div>
          </Card>
        </aside>
      </div>

      <Card as="section" padding="lg" className="page-loading-shell">
        <div className="skeleton-line skeleton-line--title" aria-hidden />
        <div className="skeleton-rows" aria-hidden>
          {ROWS.map((i) => (
            <div key={i} className="skeleton-line skeleton-line--body" />
          ))}
        </div>
      </Card>
    </div>
  )
}
