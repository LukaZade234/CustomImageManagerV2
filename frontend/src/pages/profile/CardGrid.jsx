import { Link } from 'react-router-dom'
import { Button } from '../../components/ui'

/**
 * The card grid every profile list uses, in one of two arrangements.
 *
 * `uniform` is for lists of characters. Every portrait is the same 9:14, so
 * these are a plain grid of equal cards — including the last row, which keeps
 * the size of the rows above it instead of stretching one lonely character
 * across the full width of a phone.
 *
 * The other is justified rows, the same arrangement the character gallery uses:
 * each card's flex-basis and flex-grow are both proportional to its image's
 * shape, so a row ends flush at a common height and nothing is cropped. That is
 * for hidden and removed, which hold custom images — whatever shape they were
 * drawn in, which is the point of them.
 */

/** Without these, flex-grow stretches a lone trailing card across the full width. */
const FILLERS = Object.freeze(['a', 'b', 'c', 'd', 'e', 'f'])

/** Width per unit height. Clamped so one panorama cannot flatten a whole row. */
export function cardRatio(width, height, fallback = 0.643) {
  if (!width || !height) return fallback
  return Math.min(1.9, Math.max(0.4, width / height))
}

export default function CardGrid({ items, height = 210, uniform = false }) {
  return (
    <div
      className={`profile-grid${uniform ? ' profile-grid--uniform' : ''}`}
      style={{ '--card-height': `${height}px` }}
    >
      {items.map((item) => (
        <article key={item.key} className="profile-card" style={{ '--ratio': item.ratio ?? 0.643 }}>
          <Link className="profile-card__link" to={item.href}>
            {item.image ? (
              <img
                className="profile-card__image"
                src={item.image}
                alt=""
                loading="lazy"
                decoding="async"
              />
            ) : (
              <span className="profile-card__image profile-card__image--empty" aria-hidden />
            )}
            <span className="profile-card__body">
              <span className="profile-card__title">{item.title}</span>
              {item.subtitle && <span className="profile-card__meta">{item.subtitle}</span>}
            </span>
          </Link>
          {item.action && (
            <Button
              size="sm"
              className="profile-card__action"
              disabled={item.busy}
              onClick={item.onAction}
            >
              {item.busy ? '…' : item.action}
            </Button>
          )}
        </article>
      ))}
      {/* A grid has no rows to level, so it needs none of these. */}
      {!uniform &&
        items.length > 0 &&
        FILLERS.map((id) => (
          <span key={`filler-${id}`} className="profile-grid__filler" aria-hidden="true" />
        ))}
    </div>
  )
}
