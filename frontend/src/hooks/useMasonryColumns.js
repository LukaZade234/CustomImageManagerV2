import { useCallback, useLayoutEffect, useRef, useState } from 'react'

/**
 * Row spans for a uniform-column gallery.
 *
 * CSS grid can lay images out in columns of equal width and unequal height —
 * the phone photo-grid shape — but only if it is told how many row tracks each
 * one occupies, and it cannot work that out from an aspect ratio on its own.
 * So the track is 1px tall with no row gap, the visible gap is each item's own
 * margin, and this counts the tracks.
 *
 * Everything it needs is already known: the ratio comes from the stored image
 * dimensions, so a span can be computed before the image has loaded and nothing
 * moves when it arrives. The one measured value is the container's width, taken
 * in a layout effect so the first paint is already correct.
 */

/** Wider than this in one column would be a letterbox slice, so it takes both. */
export const WIDE_RATIO = 1.6
/** Must match the `--space-2` gap the stylesheet puts between items. */
const GAP_PX = 8
const COLUMNS = 2

export function useMasonryColumns(enabled) {
  const ref = useRef(null)
  const [width, setWidth] = useState(0)

  useLayoutEffect(() => {
    if (!enabled) {
      setWidth(0)
      return undefined
    }
    const element = ref.current
    if (!element) return undefined

    // Measured before paint, so the grid is never briefly wrong.
    setWidth(element.getBoundingClientRect().width)
    if (typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver((entries) => {
      const next = entries[0]?.contentRect.width
      if (next) setWidth(next)
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [enabled])

  /**
   * What to put on one item: how many row tracks it spans, and whether it is
   * one of the wide ones that takes the full width.
   *
   * Returns nothing until the width is known — a span guessed from a container
   * of zero width would collapse every image to a sliver for one frame.
   */
  const itemProps = useCallback(
    (ratio) => {
      if (!enabled || !width) return {}
      const wide = ratio >= WIDE_RATIO
      const columnWidth = wide ? width : (width - GAP_PX * (COLUMNS - 1)) / COLUMNS
      const height = columnWidth / ratio
      return {
        className: wide ? 'is-wide' : undefined,
        style: { gridRowEnd: `span ${Math.max(1, Math.ceil(height + GAP_PX))}` },
      }
    },
    [enabled, width],
  )

  return { ref, itemProps, ready: !enabled || width > 0 }
}
