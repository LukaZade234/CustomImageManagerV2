import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useStore } from '../store/useStore'
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

  if (collapsed) {
    return (
      <div className="search-bar-cluster search-bar-cluster--collapsed">
        <button
          type="button"
          className="ui-btn ui-btn--secondary ui-btn--md search-collapsed"
          aria-label="Search"
          onClick={() => {
            setWantFocus(true)
            onExpand?.()
          }}
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
      </div>
    )
  }

  return (
    <div className="search-bar-cluster">
      <div className="search-field">
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
            { value: 'name', label: 'Name' },
            { value: 'series', label: 'Series' },
          ]}
        />
      </div>
      {/*
        Was a div-based listbox with a document-level click-outside listener, no
        arrow-key navigation and no Escape. A native select does all of that,
        and gets the platform's own picker on mobile.
      */}
      {compact ? (
        /*
          Folded to its arrow, with the real <select> lying invisibly over it.
          An expand-then-choose version of this got stuck open — nothing
          guarantees a change event or a blur when someone dismisses the
          platform's picker — and a control that can be left in the wrong state
          is worse than one that never changes state at all. Tapping the arrow
          is tapping the select, so the phone draws its own list and folds it
          away itself.
        */
        <span className="navbar-sort-compact">
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
            <polyline points="6 9 12 15 18 9" />
          </svg>
          <Select
            className="navbar-sort-compact__select"
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
        </span>
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
