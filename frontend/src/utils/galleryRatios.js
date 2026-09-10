/**
 * Aspect ratios for justified gallery rows.
 *
 * A justified row needs each image's shape before it can decide how wide to
 * make it, and the server does not store image dimensions — the library is 8,547
 * ImgChest URLs and nothing else. So the browser measures them as they load.
 */

/** Portrait, because almost all character art is. Used until an image loads. */
export const DEFAULT_RATIO = 2 / 3

/**
 * Degenerate shapes ruin a row: a 10:1 banner would flatten its whole row to a
 * sliver, and a 1:10 strip would make one absurdly tall. Clamping costs those
 * two extremes a small crop and protects everything else.
 */
export const MIN_RATIO = 0.4
export const MAX_RATIO = 2.5

export function clampRatio(ratio) {
  if (!Number.isFinite(ratio) || ratio <= 0) return DEFAULT_RATIO
  return Math.min(MAX_RATIO, Math.max(MIN_RATIO, ratio))
}

/** Ratio of a loaded <img>, or null if it has no intrinsic size yet. */
export function ratioOf(image) {
  if (!image?.naturalWidth || !image?.naturalHeight) return null
  return clampRatio(image.naturalWidth / image.naturalHeight)
}

/**
 * The ratio to lay a row out with, preferring what the server already knows.
 *
 * Stored dimensions are the whole point: with them the row is correct on first
 * paint and nothing moves. `measured` is the fallback for the handful of images
 * the backfill could not read, and `DEFAULT_RATIO` the fallback for those until
 * they load.
 */
export function ratioFor(row, measured) {
  if (row?.width > 0 && row?.height > 0) return clampRatio(row.width / row.height)
  return clampRatio(measured ?? DEFAULT_RATIO)
}

/**
 * How many invisible fillers the last row needs.
 *
 * Without them flex-grow stretches a lone trailing image across the full width,
 * which looks like a bug. The fillers absorb that space instead. They carry no
 * height and no reorder slot, so they are inert to layout and to hit-testing.
 */
export const FILLERS = Object.freeze(['a', 'b', 'c', 'd', 'e', 'f'])
