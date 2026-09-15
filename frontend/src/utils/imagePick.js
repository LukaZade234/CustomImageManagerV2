/**
 * Where a click landed inside an image's own pixels.
 *
 * The element box is rarely the image's own shape: the gallery fills its tile
 * with `object-fit: cover` (cropping) and the portrait uses `contain`
 * (letterboxing). The point is mapped through whichever fit is in use, so the
 * result is the pixel actually under the cursor rather than its position in the
 * box — which is what the server needs to sample the same spot.
 */

const clamp01 = (n) => (n < 0 ? 0 : n > 1 ? 1 : n)

/** A point in 0..1 within the natural image, from a point within its painted box. */
export function naturalPoint({
  x,
  y,
  rectWidth,
  rectHeight,
  naturalWidth,
  naturalHeight,
  fit = 'fill',
}) {
  if (!naturalWidth || !naturalHeight || !rectWidth || !rectHeight) {
    return { u: 0, v: 0 }
  }
  if (fit !== 'cover' && fit !== 'contain') {
    // fill (the default) stretches to the box; none is not used on these images.
    return { u: clamp01(x / rectWidth), v: clamp01(y / rectHeight) }
  }
  const scale =
    fit === 'cover'
      ? Math.max(rectWidth / naturalWidth, rectHeight / naturalHeight)
      : Math.min(rectWidth / naturalWidth, rectHeight / naturalHeight)
  const offsetX = (rectWidth - naturalWidth * scale) / 2
  const offsetY = (rectHeight - naturalHeight * scale) / 2
  return {
    u: clamp01((x - offsetX) / scale / naturalWidth),
    v: clamp01((y - offsetY) / scale / naturalHeight),
  }
}

/** The same point, from a click event whose target is (or contains) an <img>. */
export function pickPixel(imgEl, clientX, clientY) {
  if (!imgEl) return { u: 0, v: 0 }
  const rect = imgEl.getBoundingClientRect()
  const fit = getComputedStyle(imgEl).objectFit || 'fill'
  return naturalPoint({
    x: clientX - rect.left,
    y: clientY - rect.top,
    rectWidth: rect.width,
    rectHeight: rect.height,
    naturalWidth: imgEl.naturalWidth,
    naturalHeight: imgEl.naturalHeight,
    fit,
  })
}
