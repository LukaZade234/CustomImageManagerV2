import { getImageUrl } from '../api'
import { apiUrl } from '../config'
import { FILLERS, ratioFor } from '../utils/galleryRatios'

/**
 * The grid of a character's custom images.
 *
 * Laid out as justified rows: each item's flex-basis and flex-grow are both
 * proportional to its aspect ratio, so every image in a row ends at the same
 * height with nothing cropped. `--ratio` carries the measured shape into CSS,
 * which is the one thing the stylesheet cannot work out for itself.
 */

function attributionFor(row) {
  if (row.is_mine) return 'Added by you'
  return row.owner ? `Added by ${row.owner}` : 'Added before ownership was tracked'
}

export default function CustomImageGallery({
  rows,
  ratios,
  modes,
  selectedUrls,
  reorder,
  onToggleSelect,
  onOpenImage,
  onImageLoad,
  onDragOver,
}) {
  const { ai, remove, download, reorder: reordering } = modes
  const selecting = ai || remove || download || reordering

  return (
    <div
      className={`custom-images-gallery ${reorder.isDragging ? 'reorder-drag-active' : ''}`}
      onDragOver={onDragOver}
    >
      {rows.map((row, index) => {
        const isDropTarget = reordering && reorder.dropTargetIndex === index
        const isDragSource = reordering && reorder.dragIndices?.includes(index)
        const classes = [
          'gallery-item-wrapper',
          ai && 'ai-mode',
          remove && 'delete-mode',
          download && 'download-mode',
          reordering && 'reorder-mode',
          selectedUrls.includes(row.url) && 'selected',
          isDropTarget && 'reorder-drop-target',
          isDragSource && 'reorder-drag-source',
          row.is_mine && 'is-mine',
          row.hidden && 'is-hidden',
        ]
          .filter(Boolean)
          .join(' ')

        return (
          <div
            key={row.url}
            data-reorder-slot={index}
            style={{ '--ratio': ratioFor(row, ratios[row.id]) }}
            className={classes}
            title={attributionFor(row)}
            onClick={() => {
              // A drag ends with a synthetic click on whatever the pointer was
              // over; that must not toggle a selection.
              if (reorder.consumeClickAfterDrag()) return
              if (selecting) onToggleSelect(row.url)
            }}
            {...reorder.itemProps(index)}
            role={reordering ? 'button' : undefined}
            tabIndex={reordering ? 0 : undefined}
          >
            <img
              /*
                The grid renders a small WebP; `row.url` stays the canonical
                ImgChest PNG and is what the lightbox, the download and every $ai
                command use, because Mudae accepts nothing else. GIFs are not
                thumbnailed and fall back to the original.
              */
              src={row.thumb ? apiUrl(row.thumb) : getImageUrl(row.url)}
              alt=""
              draggable={false}
              className="custom-image-full"
              /* A character can hold hundreds of images at ~1.9 MB each, so
                 fetching them all at once is untenable on a slow connection. The
                 row is already the right shape from the stored dimensions, so
                 nothing moves when one arrives. */
              loading="lazy"
              decoding="async"
              width={row.width || undefined}
              height={row.height || undefined}
              onLoad={(e) => onImageLoad(row.id, e.currentTarget)}
              onClick={() => !selecting && onOpenImage(index)}
            />
            {remove && (
              <span className={`gallery-owner-tag ${row.is_mine ? 'is-mine' : ''}`}>
                {row.is_mine ? 'Yours' : row.owner || 'No owner'}
              </span>
            )}
            {row.hidden && <span className="gallery-owner-tag is-hidden">Hidden</span>}
            {isDropTarget && (
              <span className="reorder-drop-label" aria-hidden>
                Drop here
              </span>
            )}
          </div>
        )
      })}
      {/*
        Absorb the leftover space on the last row. Without these, flex-grow
        stretches a single trailing image across the full width, which reads as a
        bug rather than a layout. Zero height and no reorder slot, so they are
        inert to both layout and hit-testing.
      */}
      {rows.length > 0 &&
        FILLERS.map((id) => (
          <span key={`filler-${id}`} className="gallery-filler" aria-hidden="true" />
        ))}
    </div>
  )
}
