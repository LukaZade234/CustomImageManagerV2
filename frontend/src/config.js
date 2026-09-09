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
 * Where the ~1000 default character images live. Empty means same origin, i.e.
 * Flask serving them off local disk, which is what production did in v1 and what
 * moving them to R2 fixes.
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

/** Absolute URL for a character image, given a stored filename or full URL. */
export function imageUrl(imagePath) {
  if (!imagePath) return ''
  if (imagePath.startsWith('http') || imagePath.startsWith('//')) return imagePath
  const base = IMAGE_BASE || ''
  return `${base}/character_images/${imagePath}`
}

/**
 * Discord sign-in is a full-page redirect, not a fetch: the browser has to visit
 * Discord and be sent back. `next` returns you to the page you left, and the
 * server restricts it to a path on this site.
 */
export function signInUrl(nextPath = '/') {
  return `${API_BASE}/api/auth/discord/start?next=${encodeURIComponent(nextPath)}`
}
