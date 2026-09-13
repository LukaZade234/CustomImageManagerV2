import { useEffect, useState } from 'react'
import { apiClient } from '../api'

/**
 * Debounced catalog lookups for the Add flow.
 *
 * Both hooks read the imported catalog (plus the working set) over the API,
 * never Discord, so typing in the form costs no Mudae requests. The debounce is
 * what keeps a fast typist to a handful of calls rather than one per keystroke.
 */

/** Suggestions for a combobox. `kind` is 'characters' or 'series'. */
export function useCatalogSuggest(query, { kind = 'characters', limit = 10, delay = 250 } = {}) {
  const [items, setItems] = useState([])

  useEffect(() => {
    const q = (query || '').trim()
    let cancelled = false
    const timer = setTimeout(() => {
      const fetch =
        kind === 'series'
          ? apiClient.suggestSeries(q, limit)
          : apiClient.suggestCharacters(q, limit)
      fetch
        .then((res) => {
          if (!cancelled) setItems(res?.items || [])
        })
        .catch(() => {
          if (!cancelled) setItems([])
        })
    }, delay)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [query, kind, limit, delay])

  return items
}

/** The library's record for a typed name, or null. Used to offer/validate its series. */
export function useCatalogMatch(name, delay = 300) {
  const [match, setMatch] = useState(null)

  useEffect(() => {
    const q = (name || '').trim()
    if (!q) {
      setMatch(null)
      return undefined
    }
    let cancelled = false
    const timer = setTimeout(() => {
      apiClient
        .findCatalogCharacter(q)
        .then((res) => {
          if (!cancelled) setMatch(res?.found ? res.character : null)
        })
        .catch(() => {
          if (!cancelled) setMatch(null)
        })
    }, delay)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [name, delay])

  return match
}
