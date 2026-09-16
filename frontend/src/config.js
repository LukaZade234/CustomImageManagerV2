/**
 * Deployment configuration.
 *
 * In development the Vite dev server proxies /api and /character_images to
 * Flask, so everything is same-origin and these stay empty. In production the
 * SPA is served by Cloudflare Pages and the API lives on a different origin
 * behind a Cloudflare Tunnel, so both must be set at build time.
 *
 * Vite inlines import.meta.env.* at build time — these are baked into the
 * bundle, so they must not contain anything secret.
 */

/** Origin of the Flask API, e.g. https://api.example.com. Empty = same origin. */
export const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

/**
 * Where the default character images live, i.e. the R2 bucket's custom domain.
 * Empty means same origin. The committed copies are gone from the repo; the
 * working rows now carry catalog `mudae.net` URLs and their R2 WebP mirrors, so
 * this only matters as the fallback that `imageUrl` appends `/character_images/`
 * to for a stored bare filename — of which there should be none left.
 */
export const IMAGE_BASE = (import.meta.env.VITE_IMAGE_BASE_URL || '').replace(/\/$/, '')

/** True once the API is on a different origin from the page. */
export const IS_CROSS_ORIGIN = API_BASE !== ''

/**
 * Always 'include' rather than 'same-origin'.
 *
 * Once the SPA is on Pages and the API is elsewhere, 'same-origin' silently
 * stops sending cookies — which would break the Phase 6 identity cookie in a way
 * that looks like "everyone is a new person on every request" rather than like
 * an error. 'include' behaves identically for same-origin requests, so there is
 * no reason to branch.
 *
 * This obliges the API to send Access-Control-Allow-Credentials and to name an
 * exact origin: browsers reject credentialed requests against a wildcard.
 */
export const CREDENTIALS = 'include'

/** Absolute URL for an API path. */
export function apiUrl(path) {
  return `${API_BASE}${path}`
}

/**
 * Where to show a gallery thumbnail.
 *
 * The server sends one of two forms. A mirrored thumbnail is the R2 key
 * ("thumbs/…", no leading slash) and loads from the image origin; an unmirrored
 * one is the API path ("/thumbs/…") that renders and mirrors it on the way
 * through. The leading slash is the signal. With no image origin (dev) even a
 * mirrored key resolves through the API, which serves the same bytes from its
 * local cache.
 */
export function thumbUrl(thumb) {
  if (!thumb) return ''
  if (thumb.startsWith('/')) return apiUrl(thumb)
  return `${IMAGE_BASE || API_BASE}/${thumb.replace(/^\/+/, '')}`
}

/** Absolute URL for a character image, given a stored filename or full URL. */
export function imageUrl(imagePath) {
  if (!imagePath) return ''
  if (imagePath.startsWith('http') || imagePath.startsWith('//')) return imagePath
  const base = IMAGE_BASE || ''
  return `${base}/character_images/${imagePath}`
}

/**
 * Where to show a character portrait: the mirrored WebP on the CDN when the
 * server says one exists, otherwise the stored original.
 *
 * The original may be a Mudae hotlink, an ImgChest upload, or a committed file;
 * `imageUrl` already handles all three. The mirror only applies where an image
 * base is configured — a production build. In development the mirror key has no
 * host to resolve on, so the original is used and the app keeps working against
 * the local library.
 */
export function portraitUrl(imagePath, thumbPath) {
  if (thumbPath && IMAGE_BASE) return `${IMAGE_BASE}/${thumbPath.replace(/^\/+/, '')}`
  return imageUrl(imagePath)
}

/**
 * Discord sign-in is a full-page redirect, not a fetch: the browser has to visit
 * Discord and be sent back. `next` returns you to the page you left, and the
 * server restricts it to a path on this site.
 */
export function signInUrl(nextPath = '/') {
  return `${API_BASE}/api/auth/discord/start?next=${encodeURIComponent(nextPath)}`
}
