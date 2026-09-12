import { useEffect, useRef, useState } from 'react'
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
 * @param {boolean} [props.compact]    fold the sort control down to its arrow
 * @param {boolean} [props.collapsed]  something else has the width: show the
 *                                     magnifier alone
 * @param {() => void} [props.onExpand] asked for the field back
 */
export default function SearchBar({ compact = false, collapsed = false, onExpand }) {
  const searchQuery = useStore((s) => s.searchQuery)
  const setSearchQuery = useStore((s) => s.setSearchQuery)
  const mode = useStore((s) => s.searchMode)
  const setMode = useStore((s) => s.setSearchMode)
  const sort = useStore((s) => s.searchSort)
  const setSort = useStore((s) => s.setSearchSort)

  /**
   * Collapsed, the whole cluster is one magnifier.
   *
   * On a 390px screen the open menu, the home link and the sort control leave
   * about 30px, and a 30px text field is not a text field — it is an overflow
   * waiting to happen. Tapping the magnifier gives the width back, and only
   * that tap moves focus: the menu also closes on navigation, and popping the
   * keyboard up every time someone follows a link would be its own bug.
   */
  const inputRef = useRef(null)
  const [wantFocus, setWantFocus] = useState(false)
  /**
   * The sort menu borrows the field's width while it is open.
   *
   * There is no room for both at 360px: the expanded control is its label plus
   * its arrow, and a field squeezed into what is left would be narrower than
   * the Name/Series switch sitting inside it. So the field steps aside to its
   * magnifier, the same way it does for the navigation menu, and a choice puts
   * it straight back.
   */
  const [sortOpen, setSortOpen] = useState(false)

  useEffect(() => {
    if (collapsed || !wantFocus) return
    setWantFocus(false)
    inputRef.current?.focus()
  }, [collapsed, wantFocus])

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

  const magnifier = (onClick) => (
    <button
      type="button"
      className="ui-btn ui-btn--secondary ui-btn--md search-collapsed"
      aria-label="Search"
      onClick={onClick}
    >
      <svg
        aria-hidden="true"
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      >
        <circle cx="11" cy="11" r="7" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>
    </button>
  )

  // The navigation menu takes the whole cluster; the sort menu takes only the
  // field, since its own control has to stay on screen.
  if (collapsed) {
    return (
      <div className="search-bar-cluster search-bar-cluster--collapsed">
        {magnifier(() => {
          setWantFocus(true)
          onExpand?.()
        })}
      </div>
    )
  }

  /* Shortened to initials once there is something to read in the field. The
     switch is 116px of a 200px field, and the thing you are typing matters more
     than the two words beside it — which stay in the accessible name. */
  const short = searchQuery.length > 0

  return (
    <div className="search-bar-cluster">
      {compact && sortOpen ? (
        magnifier(() => {
          setWantFocus(true)
          setSortOpen(false)
        })
      ) : (
        <div className={`search-field${short ? ' is-short' : ''}`}>
          <Input
            ref={inputRef}
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
          {/* Positioned inside the field, so it needs the field to have a width.
            An absolutely positioned pill does not shrink with its container —
            it hangs out of the end of the bar — which is why the field
            collapses to its icon rather than being squeezed. */}
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
      )}
      {/*
        Wide: a native <select>, which brings arrow keys, Escape and a click
        outside without any of it being written by hand. Narrow: a menu under
        the arrow, because the platform's own picker opens as a sheet in the
        middle of the screen, detached from the control that asked for it —
        see SortMenu, which owes the native control everything it gave up.
      */}
      {compact ? (
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
