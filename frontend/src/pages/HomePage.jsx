import { useEffect, useRef } from 'react'
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

/** One thumbnail in the "Just added" strip; a clone repeats it for a seamless loop. */
function RecentCard({ row, clone = false }) {
  return (
    <li className={clone ? 'home-recent__clone' : undefined} aria-hidden={clone || undefined}>
      <Link
        className="home-recent__item"
        to={characterHref(row.character)}
        tabIndex={clone ? -1 : undefined}
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
  )
}

/** The list is rendered twice, so the second half covers the first as it wraps. */
function stripRows(recent) {
  return (
    <>
      {recent.map((row) => (
        <RecentCard key={row.id} row={row} />
      ))}
      {recent.map((row) => (
        <RecentCard key={`clone-${row.id}`} row={row} clone />
      ))}
    </>
  )
}

// Slow enough to read the incoming character, fast enough to feel alive.
const TICKER_SPEED = 36

/**
 * "Just added" drifts left continuously and loops without a seam: the strip is
 * doubled and advances to the first clone, then wraps.
 *
 * The drift is a `transform`, not a scroll offset. A scroll container snaps
 * `scrollLeft` to whole pixels, so a slow drift or a slow-down is visibly
 * stepped; a composited translate positions the layer at sub-pixel offsets and
 * stays smooth. That means the drag is ours to implement too: a pointer pull
 * moves the same offset, and a release throws it.
 *
 * It pauses while hovered, focused, or scrolled off screen. The loop is
 * nonessential, so reduced-motion visitors (and engines without a
 * ResizeObserver/IntersectionObserver) get one static, natively scrollable set
 * with no duplicate cards.
 */
function RecentTicker({ recent }) {
  const viewportRef = useRef(null)
  const trackRef = useRef(null)
  useEffect(() => {
    const viewport = viewportRef.current
    const track = trackRef.current
    if (!viewport || !track) return
    const reduced =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    // Static, natively scrollable strip where the loop cannot run.
    if (typeof IntersectionObserver === 'undefined' || reduced) {
      viewport.classList.add('is-static')
      return () => viewport.classList.remove('is-static')
    }

    // Hovering eases the drift down over a slightly longer beat, then cuts the
    // tail: holding a hover is a wish to stop, so once the strip has visibly
    // slowed it is dropped rather than left creeping the last few pixels.
    // Leaving is a request to move again and restarts at once. A drag is not a
    // hover: releasing a throw seeds the speed from the last frames of the drag
    // and then decays fast, so a flick is a hard strike that bleeds off within
    // about a second rather than a long glide.
    const HOVER_STOP_DECAY = 1.1
    const HOVER_STOP_FLOOR = 0.35
    const HOVER_RESUME_RATE = 10
    const COAST_DECAY = 7
    const MOMENTUM_CAP = 50
    const FLICK_MIN = 0.15
    const SLOP_PX = 6

    let raf
    let last = performance.now()
    let onscreen = true
    let hovering = false
    let velocity = 1
    let offset = 0
    let period = 0
    let prevOffset = 0
    let dragVelocity = 0
    let dragging = false
    let wasDragging = false
    let coasting = false
    let dragStartX = 0
    let dragStartOffset = 0
    let dragged = false

    // The loop distance is the gap between the first card and its clone, read
    // off the DOM so the seam does not depend on the flex gap arithmetic.
    const measure = () => {
      const first = track.firstElementChild
      const clone = track.querySelector('.home-recent__clone')
      period = clone && first ? clone.offsetLeft - first.offsetLeft : track.scrollWidth / 2
    }
    measure()
    let ro = null
    if (typeof ResizeObserver !== 'undefined') {
      ro = new ResizeObserver(measure)
      ro.observe(track)
    }

    const apply = () => {
      if (period > 0) {
        const x = ((offset % period) + period) % period
        track.style.transform = `translate3d(${-x}px, 0, 0)`
      }
    }
    apply()

    const io = new IntersectionObserver(([entry]) => {
      onscreen = entry.isIntersecting
    })
    io.observe(viewport)

    const hold = () => {
      hovering = true
    }
    const release = () => {
      hovering = false
      // Leaving means move again: jump straight back to the jog rather than
      // ramping up, so the restart is immediate.
      if (velocity < 1) velocity = 1
    }

    const swallowClick = (event) => {
      event.preventDefault()
      event.stopPropagation()
    }
    const onPointerDown = (event) => {
      if (event.pointerType === 'mouse' && event.button !== 0) return
      dragging = true
      dragged = false
      coasting = false
      dragVelocity = 0
      dragStartX = event.clientX
      dragStartOffset = offset
      prevOffset = offset
      viewport.classList.add('is-dragging')
      window.addEventListener('pointermove', onPointerMove, { passive: false })
      window.addEventListener('pointerup', onPointerUp)
      window.addEventListener('pointercancel', onPointerUp)
    }
    const onPointerMove = (event) => {
      if (!dragging) return
      const dx = event.clientX - dragStartX
      if (!dragged && Math.abs(dx) < SLOP_PX) return
      dragged = true
      offset = dragStartOffset - dx
      if (event.cancelable) event.preventDefault()
    }
    const onPointerUp = () => {
      if (!dragging) return
      dragging = false
      viewport.classList.remove('is-dragging')
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerup', onPointerUp)
      window.removeEventListener('pointercancel', onPointerUp)
      if (dragged) {
        // The pull is about to produce a click on whichever card it ended over;
        // swallow exactly that one.
        window.addEventListener('click', swallowClick, { capture: true, once: true })
        setTimeout(() => window.removeEventListener('click', swallowClick, { capture: true }), 0)
      }
    }
    const onWheel = (event) => {
      const dx = event.shiftKey ? event.deltaY : event.deltaX
      if (!dx) return
      offset += dx
      apply()
      if (event.cancelable) event.preventDefault()
    }
    const preventDrag = (event) => event.preventDefault()

    viewport.addEventListener('pointerdown', onPointerDown)
    viewport.addEventListener('pointerenter', hold)
    viewport.addEventListener('pointerleave', release)
    viewport.addEventListener('focusin', hold)
    viewport.addEventListener('focusout', release)
    viewport.addEventListener('wheel', onWheel, { passive: false })
    viewport.addEventListener('dragstart', preventDrag)

    const step = (now) => {
      const dt = Math.min(64, now - last) / 1000
      last = now
      if (dragging) {
        // Smoothed so the seed on release is the throw's speed, not whatever
        // the final, jittery frame happened to measure.
        const instant = (offset - prevOffset) / Math.max(dt, 0.001)
        dragVelocity += (instant - dragVelocity) * Math.min(1, dt * 12)
        coasting = false
      } else if (wasDragging) {
        const throwRatio = dragVelocity / TICKER_SPEED
        if (Math.abs(throwRatio) > FLICK_MIN) {
          velocity = Math.max(-MOMENTUM_CAP, Math.min(MOMENTUM_CAP, throwRatio))
          coasting = true
        } else {
          velocity = 1
        }
        dragVelocity = 0
      }
      prevOffset = offset
      wasDragging = dragging
      if (!dragging) {
        if (coasting) {
          velocity += (1 - velocity) * Math.min(1, dt * COAST_DECAY)
          if (Math.abs(velocity - 1) < 0.1) {
            velocity = 1
            coasting = false
          }
        } else {
          const target = hovering ? 0 : 1
          velocity +=
            (target - velocity) *
            Math.min(1, dt * (hovering ? HOVER_STOP_DECAY : HOVER_RESUME_RATE))
          if (hovering && velocity < HOVER_STOP_FLOOR) velocity = 0
          else if (!hovering && velocity > 0.999) velocity = 1
        }
        if (onscreen && !document.hidden) offset += TICKER_SPEED * velocity * dt
      }
      apply()
      raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)

    return () => {
      cancelAnimationFrame(raf)
      io.disconnect()
      ro?.disconnect()
      viewport.removeEventListener('pointerdown', onPointerDown)
      viewport.removeEventListener('pointerenter', hold)
      viewport.removeEventListener('pointerleave', release)
      viewport.removeEventListener('focusin', hold)
      viewport.removeEventListener('focusout', release)
      viewport.removeEventListener('wheel', onWheel)
      viewport.removeEventListener('dragstart', preventDrag)
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerup', onPointerUp)
      window.removeEventListener('pointercancel', onPointerUp)
      window.removeEventListener('click', swallowClick, { capture: true })
      track.style.transform = ''
    }
  }, [])
  return (
    <div className="home-recent-viewport" ref={viewportRef}>
      <ul className="home-recent home-recent--ticker" ref={trackRef}>
        {stripRows(recent)}
      </ul>
    </div>
  )
}

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
  const maxSeriesCharacters = Math.max(1, ...topSeries.map((s) => s.characters))
  // Empty until the view log has something in it, which is why the section
  // hides rather than rendering an authoritative-looking blank.
  const mostViewed = stats?.most_viewed ?? []
  // One name is a fact about a person, not a ranking. The section earns its
  // place only once there is something to compare.
  const contributors = (stats?.contributors ?? []).length > 1 ? stats.contributors : []
  // Where the caller sits, even when outside the ranked few. The server only
  // sends it for a signed-in identity that has not hidden itself.
  const standing = stats?.you ?? null
  // Nothing to add when the caller is already one of the rows above.
  const standingIsBelow = standing && standing.rank > contributors.length ? standing : null

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
            <RecentTicker recent={recent} />
          </Section>
        </Card>
      )}

      {/*
        Everything below the hero and "Just added" shares one region. The three
        library sections stay the page's spine in a slimmer left column; the
        contributor ranking is the leaderboard in the right column, where a
        ranked list belongs and where it can run the full height of the stack
        beside it. Without enough contributors to be a ranking at all, there is
        no right column and the spine keeps the full width.
      */}
      <div className={`home-lower${contributors.length > 0 ? ' home-lower--split' : ''}`}>
        <div className="home-lower__main">
          {mostViewed.length > 0 && (
            <Card as="section" padding="lg">
              <Section title="Most visited this week">
                {/* biome-ignore format: kept on one line so live's text verification finds it whole */}
                <p className="text-meta home-note">
                  Ranked by how many different people looked, not by how many visits - one enthusiast refreshing cannot move it.
                </p>
                {/*
                  A contact strip: the eight frames butt together into one band
                  with hairline dividers, which is how a proof sheet reads — and
                  this page is a proof sheet of the library. It was eight
                  bordered tiles, a card inside a card repeated, with the
                  pictures reduced to 40px afterthoughts beside the names.
                */}
                <ol className="home-strip" {...dragScroll}>
                  {mostViewed.map((c, i) => (
                    <li key={c.name}>
                      <Link className="home-strip__item" to={characterHref(c.name)}>
                        {c.image ? (
                          <img
                            className="home-strip__shot"
                            src={getImageUrl(c.image)}
                            alt=""
                            loading="lazy"
                            decoding="async"
                          />
                        ) : (
                          <span className="home-strip__shot" aria-hidden />
                        )}
                        <span className="home-strip__caption">
                          <span className="home-strip__rank tabular">{i + 1}</span>
                          <span className="home-strip__name">{c.name}</span>
                          {c.series && <span className="home-strip__series">{c.series}</span>}
                        </span>
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
                <ol className="home-strip" {...dragScroll}>
                  {bestCovered.map((c) => (
                    <li key={c.name}>
                      <Link className="home-strip__item" to={characterHref(c.name)}>
                        {c.image ? (
                          <img
                            className="home-strip__shot"
                            src={getImageUrl(c.image)}
                            alt=""
                            loading="lazy"
                            decoding="async"
                          />
                        ) : (
                          <span className="home-strip__shot" aria-hidden />
                        )}
                        <span className="home-strip__caption">
                          <span className="home-strip__rank tabular">{c.images}</span>
                          <span className="home-strip__name">{c.name}</span>
                          {c.series && <span className="home-strip__series">{c.series}</span>}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ol>
              </Section>
            </Card>
          )}
        </div>

        {contributors.length > 0 && (
          <aside className="home-lower__aside">
            <Card as="section" padding="lg" className="home-leaderboard">
              <header className="home-leaderboard__head">
                <h2 className="section-heading home-leaderboard__title">Top contributors</h2>
                <p className="home-leaderboard__note">
                  Counts images added by people signed in with Discord. Anonymous uploads are not
                  ranked.
                </p>
              </header>
              <ol className="home-leaderboard__list">
                {contributors.map((c, i) => (
                  <li key={c.handle} className={`home-leaderboard__row${i < 3 ? ' is-lead' : ''}`}>
                    <span
                      className={`home-leaderboard__rank${i < 3 ? ` home-leaderboard__rank--${i + 1}` : ''}`}
                      aria-hidden
                    >
                      {i + 1}
                    </span>
                    <span className="home-leaderboard__name">{c.handle}</span>
                    <span className="home-leaderboard__count">{c.images.toLocaleString()}</span>
                  </li>
                ))}
              </ol>
              {standingIsBelow && (
                <p className="home-leaderboard__you">
                  You are <strong>#{standingIsBelow.rank}</strong> with{' '}
                  {standingIsBelow.images.toLocaleString()}{' '}
                  {standingIsBelow.images === 1 ? 'image' : 'images'}
                </p>
              )}
            </Card>
          </aside>
        )}
      </div>

      {topSeries.length > 0 && (
        /*
          The series ranking sits below the split rather than inside the spine.

          It used to be the spine's third card, which forced the contributor
          leaderboard on the right to stretch the full height of three cards to
          stay level with it. The series list is the only wide thing in the
          region, so giving it the whole measure both shortens the leaderboard
          back to the two cards it is actually paired with and opens a right
          column inside the row: the character that carries each series and how
          many images that is. The bar still measures a series against its
          peers, so the two readings stay independent.
        */
        <Card as="section" padding="lg">
          <Section title="Most popular series">
            <div
              className={`home-series-ledger${contributors.length > 0 ? ' home-series-ledger--split' : ''}`}
            >
              <div className="home-series-ledger__head" aria-hidden="true">
                <span>Series</span>
                <span>Images · Characters</span>
                <span>Most represented</span>
              </div>
              <ul className="home-series-ledger__list">
                {topSeries.map((s) => (
                  <li key={s.series}>
                    <Link className="home-series-ledger__row" to={seriesHref(s.series)}>
                      <span className="home-series-ledger__series">
                        <span className="home-series-ledger__name">{s.series}</span>
                        <span className="home-series-ledger__bar" aria-hidden="true">
                          <span
                            className="home-series-ledger__fill"
                            style={{ '--share': s.characters / maxSeriesCharacters }}
                          />
                        </span>
                      </span>
                      <span className="home-series-ledger__meta tabular" aria-hidden="true">
                        {s.images.toLocaleString()} · {s.characters}
                      </span>
                      <span className="home-series-ledger__lead">
                        <span className="home-series-ledger__leadname">{s.top_character}</span>
                        <span className="home-series-ledger__leadcount tabular">
                          {s.top_character_images.toLocaleString()}
                        </span>
                      </span>
                      <span className="sr-only">
                        {s.series}: {s.images.toLocaleString()} images across {s.characters}{' '}
                        {s.characters === 1 ? 'character' : 'characters'}. Most represented:{' '}
                        {s.top_character} with {s.top_character_images.toLocaleString()} images.
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          </Section>
        </Card>
      )}
    </div>
  )
}
