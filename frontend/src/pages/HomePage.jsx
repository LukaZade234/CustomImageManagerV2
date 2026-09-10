import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getImageUrl } from '../api'
import HomeLoadingState from '../components/HomeLoadingState'
import { Card } from '../components/ui'
import { apiUrl } from '../config'
import { useDragScroll } from '../hooks/useDragScroll'
import { useStore } from '../store/useStore'

/**
 * The landing page.
 *
 * It used to be two stat cards above a bullet list explaining the site to
 * people already using it. Everything here now comes out of the library itself,
 * because the library is the only thing that can make the page look inhabited.
 *
 * Two things were deliberately left out. There is no visitor count: an identity
 * row is created per cookie, so the honest number is either 1 or 4 and neither
 * is worth printing. There is no most-visited section: nothing records page
 * views yet, and ranking by the copy-command events that do exist would measure
 * something else while looking authoritative.
 *
 * Every section below hides itself when it has nothing to show, so the page
 * degrades to the parts that are true rather than displaying empty furniture.
 */

function Stat({ value, label, children }) {
  return (
    <div className="stat-card">
      <div className="stat-icon" aria-hidden>
        {children}
      </div>
      <div className="stat-info">
        <span className="stat-value tabular">{value.toLocaleString()}</span>
        <span className="stat-label">{label}</span>
      </div>
    </div>
  )
}

function Section({ title, action, children }) {
  return (
    <section className="home-section">
      <div className="home-section__head">
        <h2 className="section-heading">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  )
}

/** Landscape and portrait both look deliberate; a missing size falls back to 3:4. */
function ratioOf(width, height) {
  if (!width || !height) return 0.75
  return Math.min(2, Math.max(0.45, width / height))
}

const characterHref = (name) => `/character/${encodeURIComponent(name)}`
const seriesHref = (series) => `/search?q=${encodeURIComponent(series)}&by=series`

export default function HomePage() {
  const stats = useStore((s) => s.stats)
  const loading = useStore((s) => s.loading)
  const error = useStore((s) => s.error)
  const loadStats = useStore((s) => s.loadStats)
  // Above the early returns: hooks must run in the same order every render.
  const dragScroll = useDragScroll()

  useEffect(() => {
    loadStats()
  }, [loadStats])

  if (loading) return <HomeLoadingState />
  if (error) return <div className="loading loading-error">Failed to load: {error}</div>

  const images = stats?.custom_images ?? 0
  const characters = stats?.characters_with_customs ?? 0
  const seriesCount = stats?.series_count ?? 0
  const recent = stats?.recent ?? []
  const bestCovered = stats?.best_covered ?? []
  const topSeries = stats?.top_series ?? []
  // One name is a fact about a person, not a ranking. The section earns its
  // place only once there is something to compare.
  const contributors = (stats?.contributors ?? []).length > 1 ? stats.contributors : []

  return (
    <div className="home">
      <Card as="section" padding="lg">
        <h1 className="page-title">ImgManager</h1>
        <p className="page-subtitle">
          Custom character images for Mudae — organised, deduplicated, and ready to paste.
        </p>
        <div className="stats-dashboard">
          <Stat value={images} label="Custom images">
            <svg
              aria-hidden="true"
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
              <circle cx="8.5" cy="8.5" r="1.5" />
              <polyline points="21 15 16 10 5 21" />
            </svg>
          </Stat>
          <Stat value={characters} label="Characters covered">
            <svg
              aria-hidden="true"
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
              <circle cx="12" cy="7" r="4" />
            </svg>
          </Stat>
          <Stat value={seriesCount} label="Series">
            <svg
              aria-hidden="true"
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
            </svg>
          </Stat>
        </div>
      </Card>

      {recent.length > 0 && (
        <Card as="section" padding="lg">
          <Section
            title="Just added"
            action={
              <Link className="home-section__link" to="/customs">
                Browse everything
              </Link>
            }
          >
            <ul className="home-recent" {...dragScroll}>
              {recent.map((row) => (
                <li key={row.id}>
                  <Link
                    className="home-recent__item"
                    to={characterHref(row.character)}
                    style={{ '--ratio': ratioOf(row.width, row.height) }}
                  >
                    <img
                      className="home-recent__thumb"
                      src={row.thumb ? apiUrl(row.thumb) : getImageUrl(row.url)}
                      alt=""
                      loading="lazy"
                      decoding="async"
                      width={row.width || undefined}
                      height={row.height || undefined}
                    />
                    <span className="home-recent__name">{row.character}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </Section>
        </Card>
      )}

      {bestCovered.length > 0 && (
        <Card as="section" padding="lg">
          <Section title="Most popular characters">
            <ol className="home-ranked">
              {bestCovered.map((c, i) => (
                <li key={c.name}>
                  <Link className="home-ranked__item" to={characterHref(c.name)}>
                    <span className="home-ranked__rank tabular" aria-hidden>
                      {i + 1}
                    </span>
                    {c.image ? (
                      <img
                        className="home-ranked__thumb"
                        src={getImageUrl(c.image)}
                        alt=""
                        loading="lazy"
                        decoding="async"
                      />
                    ) : (
                      <span className="home-ranked__thumb home-ranked__thumb--empty" aria-hidden />
                    )}
                    <span className="home-ranked__text">
                      <span className="home-ranked__title">{c.name}</span>
                      {c.series && <span className="home-ranked__meta">{c.series}</span>}
                    </span>
                    <span className="home-ranked__count tabular">{c.images}</span>
                  </Link>
                </li>
              ))}
            </ol>
          </Section>
        </Card>
      )}

      {topSeries.length > 0 && (
        <Card as="section" padding="lg">
          <Section title="Most popular series">
            <ul className="home-series">
              {topSeries.map((s) => (
                <li key={s.series}>
                  <Link className="home-series__item" to={seriesHref(s.series)}>
                    <span className="home-series__name">{s.series}</span>
                    <span className="home-series__meta tabular">
                      {s.images.toLocaleString()} images · {s.characters}{' '}
                      {s.characters === 1 ? 'character' : 'characters'}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </Section>
        </Card>
      )}

      {contributors.length > 0 && (
        <Card as="section" padding="lg">
          <Section title="Top contributors">
            <p className="text-meta home-note">
              Counts images added by people signed in with Discord. Anonymous uploads are not
              ranked.
            </p>
            <ol className="home-ranked">
              {contributors.map((c, i) => (
                <li key={c.handle}>
                  <div className="home-ranked__item">
                    <span className="home-ranked__rank tabular" aria-hidden>
                      {i + 1}
                    </span>
                    <span className="home-ranked__text">
                      <span className="home-ranked__title">{c.handle}</span>
                    </span>
                    <span className="home-ranked__count tabular">{c.images}</span>
                  </div>
                </li>
              ))}
            </ol>
          </Section>
        </Card>
      )}
    </div>
  )
}
