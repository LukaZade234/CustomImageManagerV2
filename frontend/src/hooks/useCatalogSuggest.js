import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../api'
import { useDebouncedValue } from './useDebouncedValue'

/**
 * Debounced catalog lookups for the Add flow.
 *
 * Both hooks read the imported catalog (plus the working set) over the API,
 * never Discord, so typing in the form costs no Mudae requests. The debounce is
 * what keeps a fast typist to a handful of calls rather than one per keystroke,
 * and react-query caches each settled query so a repeated prefix is free.
 */

/**
 * Suggestions for a combobox. `kind` is 'characters' or 'series'.
 *
 * `series` (characters only) is the connected-series hint: while the query is
 * empty, the characters of that exact series are offered instead of the generic
 * list. If the series matches nothing, it falls back to the generic list so an
 * unrecognised series still gives useful suggestions. Once the visitor types,
 * the series hint is dropped and the query is what drives the list.
 *
 * `pools` (characters only) narrows to characters carrying every named pool
 * facet; empty means no filter.
 */
export function useCatalogSuggest(
  query,
  { kind = 'characters', limit = 10, delay = 250, series = '', pools = [] } = {},
) {
  const q = (query || '').trim()
  const debouncedQuery = useDebouncedValue(q, delay)
  // Joined so the key depends on the contents rather than a new array each
  // render.
  const poolsKey = pools.join(',')
  const poolList = poolsKey ? poolsKey.split(',') : []
  const seriesHint = debouncedQuery || kind !== 'characters' ? '' : (series || '').trim()

  const { data } = useQuery({
    queryKey: [
      'catalog-suggest',
      { kind, query: debouncedQuery, limit, series: seriesHint, pools: poolsKey },
    ],
    queryFn: async () => {
      if (seriesHint) {
        const filtered = await apiClient.suggestCharacters('', limit, seriesHint, poolList)
        if (filtered?.items?.length) return filtered.items
      }
      const response =
        kind === 'series'
          ? await apiClient.suggestSeries(debouncedQuery, limit)
          : await apiClient.suggestCharacters(debouncedQuery, limit, seriesHint, poolList)
      return response?.items || []
    },
  })

  return data ?? []
}

/** The library's record for a typed name, or null. Used to offer/validate its series. */
export function useCatalogMatch(name, delay = 300) {
  const q = (name || '').trim()
  const debouncedName = useDebouncedValue(q, delay)
  const { data } = useQuery({
    queryKey: ['catalog-match', debouncedName],
    queryFn: () => apiClient.findCatalogCharacter(debouncedName),
    enabled: Boolean(debouncedName),
  })
  return data?.found ? data.character : null
}
