import { Link } from 'react-router-dom'
import { Button } from '../../components/ui'

/**
 * The card grid every profile list uses.
 *
 * Justified rows, the same arrangement the character gallery uses: each card's
 * flex-basis and flex-grow are both proportional to its image's shape, so a row
 * ends flush at a common height and nothing is cropped or stretched. The card
 * follows the image rather than the image being squeezed into the card.
 *
 * For saved and history that produces a tidy uniform grid on its own, because
 * every character portrait is the same 9:14. For hidden and removed it produces
 * genuinely ragged rows, because custom images are whatever shape they were
 * drawn in — which is the point.
 */

/** Without these, flex-grow stretches a lone trailing card across the full width. */
const FILLERS = Object.freeze(['a', 'b', 'c', 'd', 'e', 'f'])

/** Width per unit height. Clamped so one panorama cannot flatten a whole row. */
export function cardRatio(width, height, fallback = 0.643) {
  if (!width || !height) return fallback
  return Math.min(1.9, Math.max(0.4, width / height))
}

export default function CardGrid({ items, height = 210 }) {
  return (
    <div className="profile-grid" style={{ '--card-height': `${height}px` }}>
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
      {items.length > 0 &&
        FILLERS.map((id) => (
          <span key={`filler-${id}`} className="profile-grid__filler" aria-hidden="true" />
        ))}
    </div>
  )
}
