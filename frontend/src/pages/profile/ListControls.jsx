import FilterBar from '../../components/FilterBar'

/**
 * The filter row above each of the profile's lists.
 *
 * It is the navbar's bar: the same capsule, the same one-panel filter, the same
 * search-by, sort and order. What differs is only the sort set and whether the
 * list has a name/series choice to make; the count rides to the right, because
 * once a search is narrowing a list "12 of 340" is the difference between
 * trusting the list and wondering what is missing from it.
 */
export default function ListControls({
  label,
  query,
  onQuery,
  sort,
  onSort,
  order,
  onOrder,
  options,
  mode,
  onMode,
  modeOptions,
  shown,
  total,
}) {
  const placeholder =
    mode === undefined ? label : mode === 'series' ? 'Search by series...' : 'Search by name...'

  return (
    <div className="profile-controls">
      <FilterBar
        query={query}
        onQuery={onQuery}
        placeholder={placeholder}
        ariaLabel={label}
        mode={mode}
        onMode={onMode}
        modeOptions={modeOptions}
        sortOptions={options}
        sort={sort}
        onSort={onSort}
        order={order}
        onOrder={onOrder}
        trailing={
          <span className="profile-controls__count text-meta tabular">
            {shown === total ? `${total}` : `${shown} of ${total}`}
          </span>
        }
      />
    </div>
  )
}
