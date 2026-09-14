/**
 * Small preferences that outlive a page visit, kept in localStorage.
 *
 * The theme has its own module because it also touches the DOM; these are the
 * filter choices — which field to search by, how to sort — where the only
 * requirement is that the last thing you picked is what you find next time.
 * The failure mode to protect against is the same one theme guards: storage can
 * throw (private mode, a blocked origin), and a preference is never worth
 * breaking the page over, so both ends swallow that and fall back.
 */

/** Namespaced so a stray key from another app on the origin cannot collide. */
export const SEARCH_MODE_KEY = 'impeccable:search-mode'
export const SEARCH_SORT_KEY = 'impeccable:search-sort'
/**
 * `-v2` because the meaning of the value changed: the search order is now the
 * UI direction the sort menu shows (rank descending reads best-first), swapped
 * for the server's literal order on the way out. A stored `-v1` value would
 * invert rank results, so it is discarded rather than migrated.
 */
export const SEARCH_ORDER_KEY = 'impeccable:search-order-v2'
export const CUSTOMS_SORT_KEY = 'impeccable:customs-sort'
export const CUSTOMS_ORDER_KEY = 'impeccable:customs-order'

export function readStored(key, fallback) {
  try {
    const value = localStorage.getItem(key)
    return value === null ? fallback : value
  } catch {
    return fallback
  }
}

export function writeStored(key, value) {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* private mode / blocked storage */
  }
}
