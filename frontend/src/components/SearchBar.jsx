import { useEffect } from 'react'
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

export default function SearchBar() {
  const searchQuery = useStore((s) => s.searchQuery)
  const setSearchQuery = useStore((s) => s.setSearchQuery)
  const mode = useStore((s) => s.searchMode)
  const setMode = useStore((s) => s.setSearchMode)
  const sort = useStore((s) => s.searchSort)
  const setSort = useStore((s) => s.setSearchSort)

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
    </div>
  )
}
