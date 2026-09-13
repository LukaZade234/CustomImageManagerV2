import { useEffect } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useStore } from '../store/useStore'
import FilterBar from './FilterBar'

const SORT_OPTIONS = [
  { value: 'rank', label: 'Rank' },
  { value: 'alphabet', label: 'Alphabet' },
  { value: 'count', label: 'Image count' },
]

/**
 * The direction each sort opens in when it is chosen. Rank and image count read
 * best from the top down, so they default to descending; A–Z reads upward.
 * Rank is inverted because 1 is the top rank (see SearchResultsPage).
 */
const SORT_DEFAULT_ORDER = { rank: 'desc', alphabet: 'asc', count: 'desc' }

export function searchPath(query, mode) {
  return `/search?q=${encodeURIComponent(query)}&by=${mode}`
}

/**
 * @param {object} props
 * @param {boolean} [props.minimal]  the navigation menu has the bar: the filter
 *                                   steps out, the field stays
 */
export default function SearchBar({ minimal = false }) {
  const searchQuery = useStore((s) => s.searchQuery)
  const setSearchQuery = useStore((s) => s.setSearchQuery)
  const mode = useStore((s) => s.searchMode)
  const setMode = useStore((s) => s.setSearchMode)
  const sort = useStore((s) => s.searchSort)
  const setSort = useStore((s) => s.setSearchSort)
  const order = useStore((s) => s.searchOrder)
  const setOrder = useStore((s) => s.setSearchOrder)

  const navigate = useNavigate()
  const location = useLocation()
  const [params] = useSearchParams()

  const onSearchRoute = location.pathname === '/search'
  const urlQuery = onSearchRoute ? params.get('q') || '' : ''
  // Only an explicit `by` overrides the remembered choice. Treating its
  // absence as "name" reset the field to the default on every visit to a
  // results page that did not spell the mode out.
  const byParam = params.get('by')
  const urlMode = byParam === 'series' ? 'series' : byParam === 'name' ? 'name' : null

  // The URL is the source of truth for what is being searched. This adopts it
  // on any navigation — a shared link, the back button, or leaving the results
  // page, which is what clears the field.
  useEffect(() => {
    setSearchQuery(urlQuery)
  }, [urlQuery, setSearchQuery])

  useEffect(() => {
    if (onSearchRoute && urlMode) setMode(urlMode)
  }, [onSearchRoute, urlMode, setMode])

  /**
   * Leaving the results by emptying the field should return the reader to the
   * page they were searching from, not force them home. Going back is that page
   * when the search was reached from the app; a results URL opened directly (or
   * reloaded) has nothing useful behind it, so that case falls back to home
   * rather than out of the site.
   */
  const leaveSearch = () => {
    if (location.key && location.key !== 'default') navigate(-1)
    else navigate('/', { replace: true })
  }

  const go = (query, nextMode) => {
    if (!query) {
      if (onSearchRoute) leaveSearch()
      return
    }
    // Replace while already searching, so a search does not leave one history
    // entry per keystroke behind it.
    navigate(searchPath(query, nextMode), { replace: onSearchRoute })
  }

  return (
    <FilterBar
      query={searchQuery}
      onQuery={(value) => {
        setSearchQuery(value)
        go(value, mode)
      }}
      placeholder={mode === 'name' ? 'Search by name...' : 'Search by series...'}
      ariaLabel={mode === 'name' ? 'Search by character name' : 'Search by series'}
      mode={mode}
      onMode={(value) => {
        setMode(value)
        go(searchQuery, value)
      }}
      sortOptions={SORT_OPTIONS}
      sort={sort}
      onSort={(value) => {
        setSort(value)
        setOrder(SORT_DEFAULT_ORDER[value] ?? 'asc')
      }}
      order={order}
      onOrder={setOrder}
      filterHidden={minimal}
    />
  )
}
