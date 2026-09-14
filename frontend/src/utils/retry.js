/**
 * Transient browser / gateway failures worth retrying.
 *
 * A 4xx is the server saying the request will never work, so retrying it only
 * delays the error. A dropped connection, a proxy 502, or a timeout is the
 * infrastructure having a moment, so it is worth another go. This was written
 * twice — once in the store for the gallery fetch and once in `api.js` for
 * uploads — and now backs the query client's retry policy too.
 */
export function isTransientError(e) {
  if (e instanceof TypeError) return true
  const m = e?.message || ''
  if (m.startsWith('Network error:')) return true
  if (/could not complete the request/i.test(m)) return true
  if (/Gateway|502|503|504/i.test(m)) return true
  return false
}

/** Exponential backoff with jitter, in milliseconds. */
export function backoffDelay(attempt, base = 400) {
  return base * 2 ** attempt + Math.random() * 200
}
