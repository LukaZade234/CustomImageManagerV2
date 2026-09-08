import { useState, useRef, useEffect } from 'react'
import { useStore } from '../store/useStore'

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
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef(null)

  const sortLabel = SORT_OPTIONS.find((o) => o.value === sort)?.label || sort

  useEffect(() => {
    const h = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) setDropdownOpen(false)
    }
    document.addEventListener('click', h)
    return () => document.removeEventListener('click', h)
  }, [])

  const handleSortSelect = (value) => {
    setSort(value)
    setDropdownOpen(false)
  }

  return (
    <div className="search-bar-cluster">
      <div className="search-input-wrapper">
        <input
          type="text"
          className="char-search-input"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder={mode === 'name' ? 'Search by name...' : 'Search by series...'}
          autoComplete="off"
        />
        <div className="search-toggle-wrapper search-toggle-visible">
          <span
            className={`toggle-label toggle-option ${mode === 'name' ? 'active' : ''}`}
            onClick={() => setMode('name')}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === 'Enter' && setMode('name')}
          >
            Name
          </span>
          <span
            className={`toggle-label toggle-option ${mode === 'series' ? 'active' : ''}`}
            onClick={() => setMode('series')}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === 'Enter' && setMode('series')}
          >
            Series
          </span>
        </div>
      </div>
      <div
        className={`custom-dropdown navbar-sort-dropdown ${dropdownOpen ? 'active' : ''}`}
        ref={dropdownRef}
      >
        <div
          className="dropdown-selected"
          onClick={() => setDropdownOpen(!dropdownOpen)}
          role="button"
          tabIndex={0}
          aria-label={`Sort by: ${sortLabel}`}
          aria-expanded={dropdownOpen}
          aria-haspopup="listbox"
          title={`Sort: ${sortLabel}`}
          onKeyDown={(e) => e.key === 'Enter' && setDropdownOpen(!dropdownOpen)}
        >
          <span className="selected-text">{sortLabel}</span>
          <svg className="dropdown-arrow" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </div>
        <div
          className={`dropdown-options ${dropdownOpen ? 'show' : ''}`}
          style={{ display: dropdownOpen ? 'block' : 'none' }}
          role="listbox"
          aria-label="Sort options"
        >
          {SORT_OPTIONS.map((o) => (
            <div
              key={o.value}
              className={`dropdown-option ${sort === o.value ? 'selected' : ''}`}
              onClick={() => handleSortSelect(o.value)}
              role="option"
              tabIndex={0}
              aria-selected={sort === o.value}
              onKeyDown={(e) => e.key === 'Enter' && handleSortSelect(o.value)}
            >
              {o.label}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
