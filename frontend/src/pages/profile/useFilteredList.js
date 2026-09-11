import { useMemo, useState } from 'react'

/**
 * Search and sort for the profile's list tabs.
 *
 * All four lists — saved, history, hidden, removed — are the same shape of
 * problem: a personal list that grows until you cannot find anything in it. The
 * filtering is identical in each, so it lives here rather than four times.
 *
 * Everything is done in memory on purpose. These are *your* lists, bounded by
 * what one person has done rather than by the size of the library, so the whole
 * list is already on the client and a round trip per keystroke would buy
 * nothing. The customs page is the opposite case and is filtered server-side.
 *
 * @param items    the rows to filter, or null while loading
 * @param fields   which keys the search term is matched against
 * @param sorts    {value: {label, compare}} — the first key is the default
 */
export function useFilteredList(items, fields, sorts) {
  const sortKeys = Object.keys(sorts)
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState(sortKeys[0])

  const filtered = useMemo(() => {
    if (!items) return null
    const needle = query.trim().toLowerCase()
    const matched = needle
      ? items.filter((item) =>
          fields.some((f) =>
            String(item[f] ?? '')
              .toLowerCase()
              .includes(needle),
          ),
        )
      : items
    const compare = sorts[sort]?.compare
    // Sorting copies: the caller's array is state somewhere and must not move
    // under it.
    return compare ? [...matched].sort(compare) : matched
  }, [items, query, sort, fields, sorts])

  return {
    query,
    setQuery,
    sort,
    setSort,
    options: sortKeys.map((value) => ({ value, label: sorts[value].label })),
    items: filtered,
    /** True when a search is hiding everything, as opposed to having nothing. */
    filteredToNothing: Boolean(items?.length) && filtered?.length === 0,
  }
}

/** Case-insensitive compare on a string field, for building `sorts`. */
export const byText = (field) => (a, b) =>
  String(a[field] ?? '').localeCompare(String(b[field] ?? ''), undefined, { sensitivity: 'base' })

/** Descending compare on a number or ISO date field. */
export const byDesc = (field) => (a, b) => {
  const left = a[field] ?? ''
  const right = b[field] ?? ''
  if (typeof left === 'number' || typeof right === 'number') return (right || 0) - (left || 0)
  return String(right).localeCompare(String(left))
}
