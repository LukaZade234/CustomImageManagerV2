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
 * @param {boolean} [props.compact]  fold the sort control down to its arrow
 */
export default function SearchBar({ compact = false }) {
  const searchQuery = useStore((s) => s.searchQuery)
  const setSearchQuery = useStore((s) => s.setSearchQuery)
  const mode = useStore((s) => s.searchMode)
  const setMode = useStore((s) => s.setSearchMode)
  const sort = useStore((s) => s.searchSort)
  const setSort = useStore((s) => s.setSearchSort)

  /**
   * The sort control, folded.
   *
   * At 160px wide it was the widest thing in a navbar that had no width to
   * spare, and it spends its life showing an answer you already chose. Folded
   * it is an arrow; opening it expands the real <select> and asks the platform
   * for its own picker, so choosing is still one tap and the list is still the
   * one the phone draws rather than one imitated in a div.
   */
  const [sortOpen, setSortOpen] = useState(false)
  const sortRef = useRef(null)
  const sortFolded = compact && !sortOpen

  useEffect(() => {
    if (!sortOpen) return
    const select = sortRef.current
    if (!select) return
    try {
      // Chrome and Safari can open the native picker directly. Where they
      // cannot, the expanded select is now on screen and one tap away.
      select.showPicker?.()
    } catch {
      select.focus()
    }
  }, [sortOpen])

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

  return (
    <div className="search-bar-cluster">
      <div className="search-field">
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
      {sortFolded ? (
        <button
          type="button"
          className="ui-btn ui-btn--secondary ui-btn--md navbar-sort-toggle"
          aria-label={`Sort: ${SORT_OPTIONS.find((o) => o.value === sort)?.label}. Change.`}
          onClick={() => setSortOpen(true)}
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
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>
      ) : (
        <Select
          ref={sortRef}
          className="navbar-sort-select"
          value={sort}
          onChange={(e) => {
            setSort(e.target.value)
            setSortOpen(false)
          }}
          onBlur={() => setSortOpen(false)}
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
