import { useStore } from '../store/useStore'
import { Input, SegmentedControl, Select } from './ui'

const SORT_OPTIONS = [
  { value: 'rank', label: 'Rank (High-Low)' },
  { value: 'name', label: 'Name (A-Z)' },
  { value: 'series', label: 'Series (A-Z)' },
]

export default function SearchBar() {
  const searchQuery = useStore((s) => s.searchQuery)
  const setSearchQuery = useStore((s) => s.setSearchQuery)
  const mode = useStore((s) => s.searchMode)
  const setMode = useStore((s) => s.setSearchMode)
  const sort = useStore((s) => s.searchSort)
  const setSort = useStore((s) => s.setSearchSort)

  return (
    <div className="search-bar-cluster">
      <div className="search-input-wrapper">
        <Input
          type="search"
          className="char-search-input"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder={mode === 'name' ? 'Search by name...' : 'Search by series...'}
          aria-label={mode === 'name' ? 'Search by character name' : 'Search by series'}
          autoComplete="off"
        />
        <SegmentedControl
          className="search-toggle-wrapper"
          name="search-mode"
          label="Search by"
          value={mode}
          onChange={setMode}
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
