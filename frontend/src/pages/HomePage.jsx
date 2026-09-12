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
 * There is deliberately no visitor count: an identity row is created per cookie,
 * so the honest number is either 1 or 4, and neither is worth printing.
 *
 * Every section below hides itself when it has nothing to show, so the page
 * degrades to the parts that are true rather than displaying empty furniture.
 */

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
  // Empty until the view log has something in it, which is why the section
  // hides rather than rendering an authoritative-looking blank.
  const mostViewed = stats?.most_viewed ?? []
  // One name is a fact about a person, not a ranking. The section earns its
  // place only once there is something to compare.
  const contributors = (stats?.contributors ?? []).length > 1 ? stats.contributors : []

  return (
    <div className="home">
      {/*
        Identity on one side, what is in the library on the other.

        It was a page title over three cards of icon-plus-number-plus-label,
        which is a card inside a card and the laziest container there is. The
        figures are a definition list now — they are definitions — so they read
        as a table of contents for the library rather than as three badges.
      */}
      <Card as="section" padding="lg">
        <div className="home-hero">
          <div>
            <h1 className="page-title home-hero__title">ImgManager</h1>
            <p className="home-hero__subtitle">
              Custom character images for Mudae - organised, deduplicated, and ready to paste.
            </p>
          </div>
          <dl className="home-hero__figures">
            <div className="home-hero__figure">
              <dt>Custom images</dt>
              <dd>{images.toLocaleString()}</dd>
            </div>
            <div className="home-hero__figure">
              <dt>Characters covered</dt>
              <dd>{characters.toLocaleString()}</dd>
            </div>
            <div className="home-hero__figure">
              <dt>Series</dt>
              <dd>{seriesCount.toLocaleString()}</dd>
            </div>
          </dl>
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

      {mostViewed.length > 0 && (
        <Card as="section" padding="lg">
          <Section title="Most visited this week">
            {/* biome-ignore format: kept on one line so live's text verification finds it whole */}
            <p className="text-meta home-note">
              Ranked by how many different people looked, not by how many visits - one enthusiast refreshing cannot move it.
            </p>
            <ol className="home-ranked">
              {mostViewed.map((c, i) => (
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
                    <span className="home-ranked__count tabular">{c.viewers.toLocaleString()}</span>
                  </Link>
                </li>
              ))}
            </ol>
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
