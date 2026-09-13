import { useState } from 'react'
import { useMediaQuery } from '../hooks/useMediaQuery'
import { SortMenu } from './SortMenu'
import { Input } from './ui'

/**
 * The one search bar: a capsule holding the field, and a filter that opens one
 * panel over it.
 *
 * The same bar sits in the navbar, above Browse Customs and above every profile
 * list. What changes per page is the sort set and whether a Name/Series choice
 * is offered; the shape, the ordering control and the way the choice is read
 * back do not. On a wide bar the closed filter states itself ("Rank asc."), and
 * on a phone there is no room for both, so it is the arrow alone.
 */

/** Same fold point as the bar in the navbar. */
const COMPACT = '(max-width: 960px)'

export const MODE_OPTIONS = [
  { value: 'name', label: 'Name' },
  { value: 'series', label: 'Series' },
]

export const ORDER_OPTIONS = [
  { value: 'asc', label: 'Ascending' },
  { value: 'desc', label: 'Descending' },
]

export default function FilterBar({
  query,
  onQuery,
  placeholder,
  ariaLabel,
  mode,
  onMode,
  modeOptions = MODE_OPTIONS,
  sortOptions,
  sort,
  onSort,
  order,
  onOrder,
  trailing,
  filterHidden = false,
}) {
  const compact = useMediaQuery(COMPACT)
  const [open, setOpen] = useState(false)

  const sortLabel = sortOptions.find((option) => option.value === sort)?.label ?? ''
  const summary = order ? `${sortLabel} ${order === 'desc' ? 'desc.' : 'asc.'}` : sortLabel

  const before =
    mode === undefined
      ? []
      : [{ label: 'Search by', value: mode, options: modeOptions, onChange: onMode }]
  const after =
    order === undefined
      ? []
      : [{ label: 'Order', value: order, options: ORDER_OPTIONS, onChange: onOrder }]

  return (
    <>
      <div className="filter-bar">
        <div className="search-field">
          <Input
            type="search"
            value={query}
            onChange={(e) => onQuery(e.target.value)}
            placeholder={placeholder}
            aria-label={ariaLabel}
            autoComplete="off"
          />
        </div>
        {!filterHidden && (
          <SortMenu
            options={sortOptions}
            value={sort}
            open={open}
            onOpenChange={setOpen}
            onChange={onSort}
            summary={compact ? undefined : summary}
            before={before}
            after={after}
          />
        )}
      </div>
      {trailing}
    </>
  )
}
