import { useEffect, useState } from 'react'
import { apiClient } from '../api'

/**
 * Debounced catalog lookups for the Add flow.
 *
 * Both hooks read the imported catalog (plus the working set) over the API,
 * never Discord, so typing in the form costs no Mudae requests. The debounce is
 * what keeps a fast typist to a handful of calls rather than one per keystroke.
 */

/**
 * Suggestions for a combobox. `kind` is 'characters' or 'series'.
 *
 * `series` (characters only) is the connected-series hint: while the query is
 * empty, the characters of that exact series are offered instead of the generic
 * list. If the series matches nothing, it falls back to the generic list so an
 * unrecognised series still gives useful suggestions. Once the visitor types,
 * the series hint is dropped and the query is what drives the list.
 */
export function useCatalogSuggest(
  query,
  { kind = 'characters', limit = 10, delay = 250, series = '' } = {},
) {
  const [items, setItems] = useState([])

  useEffect(() => {
    const q = (query || '').trim()
    const seriesHint = q || kind !== 'characters' ? '' : (series || '').trim()
    let cancelled = false
    const timer = setTimeout(() => {
      const run = async () => {
        if (seriesHint) {
          const filtered = await apiClient.suggestCharacters('', limit, seriesHint)
          if (filtered?.items?.length) return filtered.items
        }
        const response =
          kind === 'series'
            ? await apiClient.suggestSeries(q, limit)
            : await apiClient.suggestCharacters(q, limit, seriesHint)
        return response?.items || []
      }
      run()
        .then((next) => {
          if (!cancelled) setItems(next)
        })
        .catch(() => {
          if (!cancelled) setItems([])
        })
    }, delay)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [query, kind, limit, delay, series])

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
