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

/**
 * What the item's control is called, which depends on what activating it does.
 *
 * The images are interchangeable to a screen reader — they have no titles and
 * `alt` is empty because the picture *is* the content — so the position and the
 * attribution are the only things that distinguish one from another.
 */
function labelFor(row, index, selecting) {
  const what = `Image ${index + 1}, ${attributionFor(row).toLowerCase()}`
  return selecting ? `Select ${what}` : `Open ${what}`
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
    // A drop target for files dragged in from outside the page, which has no
    // keyboard equivalent to expose. The accessible route to the same outcome is
    // the toolbar's "Add Image" button, which opens a file picker.
    // biome-ignore lint/a11y/noStaticElementInteractions: file drop zone, see above
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
          /*
            One real <button> per image, rather than a click handler on the
            wrapper for selecting and a second one on the <img> for opening.
            Those were two overlapping mouse-only targets that no keyboard could
            reach, and the mode already decides which of the two a click means —
            so it is one control whose action depends on the mode, and saying so
            gets Enter, Space, focus and a name for free.
          */
          <button
            type="button"
            key={row.url}
            data-reorder-slot={index}
            style={{ '--ratio': ratioFor(row, ratios[row.id]) }}
            className={classes}
            title={attributionFor(row)}
            aria-label={labelFor(row, index, selecting)}
            aria-pressed={selecting ? selectedUrls.includes(row.url) : undefined}
            onClick={() => {
              // A drag ends with a synthetic click on whatever the pointer was
              // over; that must not toggle a selection.
              if (reorder.consumeClickAfterDrag()) return
              if (selecting) onToggleSelect(row.url)
              else onOpenImage(index)
            }}
            {...reorder.itemProps(index)}
            // Arrow keys move an item in reorder mode; the hook handles the
            // keydown, this just makes the announcement reachable.
            aria-describedby={reordering ? 'gallery-reorder-help' : undefined}
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
          </button>
        )
      })}
      {/*
        Absorb the leftover space on the last row. Without these, flex-grow
        stretches a single trailing image across the full width, which reads as a
        bug rather than a layout. Zero height and no reorder slot, so they are
        inert to both layout and hit-testing.
      */}
      {/* Pointer drags are visible; a key press is not, so it is announced. */}
      {reordering && (
        <>
          <span id="gallery-reorder-help" className="sr-only">
            Press the arrow keys to move this image.
          </span>
          <span className="sr-only" role="status">
            {reorder.announcement}
          </span>
        </>
      )}
      {rows.length > 0 &&
        FILLERS.map((id) => (
          <span key={`filler-${id}`} className="gallery-filler" aria-hidden="true" />
        ))}
    </div>
  )
}
