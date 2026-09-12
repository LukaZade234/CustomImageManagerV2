import { useEffect, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useStore } from '../store/useStore'
import { SortMenu } from './SortMenu'
import { Input, SegmentedControl, Select } from './ui'

const SORT_OPTIONS = [
  { value: 'rank', label: 'Rank (High-Low)' },
  { value: 'name', label: 'Name (A-Z)' },
  { value: 'series', label: 'Series (A-Z)' },
]

export function searchPath(query, mode) {
  return `/search?q=${encodeURIComponent(query)}&by=${mode}`
}

/**
 * @param {object} props
 * @param {boolean} [props.compact]  fold the sort control down to its arrow
 * @param {boolean} [props.minimal]  the navigation menu has the bar: the sort
 *                                   control steps out, the field stays
 */
export default function SearchBar({ compact = false, minimal = false }) {
  const searchQuery = useStore((s) => s.searchQuery)
  const setSearchQuery = useStore((s) => s.setSearchQuery)
  const mode = useStore((s) => s.searchMode)
  const setMode = useStore((s) => s.setSearchMode)
  const sort = useStore((s) => s.searchSort)
  const setSort = useStore((s) => s.setSearchSort)

  /**
   * The field never folds away; it only gives ground.
   *
   * It used to collapse to a magnifier whenever something else wanted the bar,
   * which answered the wrong question: the problem was never that a search
   * field cannot be small, it was that this one could not shrink. The switch
   * inside it is positioned rather than laid out, so it held the field open at
   * its full width and pushed everything else off the screen.
   *
   * So the field flexes down to a pill and the switch gets out of its way — by
   * initials once there is something to read, and entirely when the field is
   * too narrow to hold both. A container query decides that, since the answer
   * depends on the field's own width rather than the window's.
   */
  const [sortOpen, setSortOpen] = useState(false)

  const navigate = useNavigate()
  const location = useLocation()
  const [params] = useSearchParams()

  const onSearchRoute = location.pathname === '/search'
  const urlQuery = onSearchRoute ? params.get('q') || '' : ''
  const urlMode = params.get('by') === 'series' ? 'series' : 'name'

  // The URL is the source of truth for what is being searched. This adopts it
  // on any navigation — a shared link, the back button, or leaving the results
  // page, which is what clears the field.
  useEffect(() => {
    setSearchQuery(urlQuery)
  }, [urlQuery, setSearchQuery])

  useEffect(() => {
    if (onSearchRoute) setMode(urlMode)
  }, [onSearchRoute, urlMode, setMode])

  const go = (query, nextMode) => {
    if (!query) {
      if (onSearchRoute) navigate('/', { replace: true })
      return
    }
    // Replace while already searching, so a search does not leave one history
    // entry per keystroke behind it.
    navigate(searchPath(query, nextMode), { replace: onSearchRoute })
  }

  /* Shortened to initials once there is something to read in the field. The
     switch is 116px of a 200px field, and the thing you are typing matters more
     than the two words beside it — which stay in the accessible name. */
  const short = searchQuery.length > 0

  return (
    <div className="search-bar-cluster">
      <div className={`search-field${short ? ' is-short' : ''}`}>
        <Input
          type="search"
          value={searchQuery}
          onChange={(e) => {
            setSearchQuery(e.target.value)
            go(e.target.value, mode)
          }}
          placeholder={mode === 'name' ? 'Search by name...' : 'Search by series...'}
          aria-label={mode === 'name' ? 'Search by character name' : 'Search by series'}
          autoComplete="off"
        />
        {/* Positioned inside the field rather than laid out in it, so it does
            not shrink when the field does. It gives way in two steps instead:
            initials while you type, and gone once the field is too narrow to
            hold both — see the container query in pages.css. */}
        <SegmentedControl
          name="search-mode"
          label="Search by"
          value={mode}
          onChange={(v) => {
            setMode(v)
            go(searchQuery, v)
          }}
          options={[
            { value: 'name', label: 'Name', short: short ? 'N' : undefined },
            { value: 'series', label: 'Series', short: short ? 'S' : undefined },
          ]}
        />
      </div>
      {/*
        Wide: a native <select>, which brings arrow keys, Escape and a click
        outside without any of it being written by hand. Narrow: a menu under
        the arrow, because the platform's own picker opens as a sheet in the
        middle of the screen, detached from the control that asked for it —
        see SortMenu, which owes the native control everything it gave up.
      */}
      {/* While the navigation menu is out, the bar is its. Four links, a home
          button and a menu button leave the field barely a pill as it is. */}
      {minimal ? null : compact ? (
        <SortMenu
          options={SORT_OPTIONS}
          value={sort}
          open={sortOpen}
          onOpenChange={setSortOpen}
          onChange={setSort}
        />
      ) : (
        <Select
          className="navbar-sort-select"
          value={sort}
          onChange={(e) => setSort(e.target.value)}
          aria-label="Sort results"
        >
          {SORT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </Select>
      )}
    </div>
  )
}
