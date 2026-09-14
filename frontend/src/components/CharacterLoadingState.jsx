import { GallerySkeleton } from './CustomImageGallery'
import { Card } from './ui'

/**
 * Shown while the character library is still arriving.
 *
 * The character page used to render "Character not found" whenever its record
 * was missing, and the record is missing for as long as the ~1,700-row library
 * takes to load. So every refresh, every bookmark and every link pasted into
 * Discord opened with an error claiming the character did not exist. Shared
 * links are a primary way people arrive here, and that was the first thing they
 * saw.
 *
 * The shape mirrors the real page exactly -- portrait beside the title, the
 * save button under the picture, the actions under the identity, and the same
 * gallery grid below -- so nothing moves when the data lands.
 */
export default function CharacterLoadingState() {
  return (
    <Card as="article" padding="lg" className="character-page" aria-busy="true">
      <p className="sr-only" aria-live="polite">
        Loading character…
      </p>
      <div className="character-top-section" aria-hidden>
        <div className="char-image-section">
          <div className="skeleton-portrait" />
        </div>
        <div className="char-info-section">
          <div className="skeleton-line skeleton-line--lg" style={{ maxWidth: '14rem' }} />
          <div className="skeleton-line skeleton-line--body" style={{ maxWidth: '9rem' }} />
          <div className="skeleton-line skeleton-line--sm" style={{ maxWidth: '5rem' }} />
        </div>
        <div className="skeleton-line skeleton-line--body save-skeleton" />
        <div className="char-page-actions">
          <div className="skeleton-line skeleton-line--body" style={{ maxWidth: '11rem' }} />
          <div className="skeleton-line skeleton-line--body" style={{ maxWidth: '11rem' }} />
        </div>
      </div>
      <div className="custom-images-section" aria-hidden>
        <div className="skeleton-line skeleton-line--title" />
        <div className="custom-images-gallery">
          <GallerySkeleton />
        </div>
      </div>
    </Card>
  )
}
