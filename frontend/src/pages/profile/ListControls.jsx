import { Input, Select } from '../../components/ui'

/**
 * The search field and sort control above each of the profile's lists.
 *
 * `count` is shown rather than implied: once a search is narrowing a list, "12
 * of 340" is the difference between trusting the list and wondering what is
 * missing from it.
 */
export default function ListControls({
  label,
  query,
  onQuery,
  sort,
  onSort,
  options,
  shown,
  total,
}) {
  const id = `${label.toLowerCase().replace(/\s+/g, '-')}-search`
  return (
    <div className="profile-controls">
      <div className="profile-controls__search">
        <label className="sr-only" htmlFor={id}>
          {label}
        </label>
        <Input
          id={id}
          type="search"
          value={query}
          placeholder={label}
          onChange={(e) => onQuery(e.target.value)}
        />
      </div>
      <Select value={sort} onChange={(e) => onSort(e.target.value)} aria-label="Sort by">
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </Select>
      <span className="profile-controls__count text-meta tabular">
        {shown === total ? `${total}` : `${shown} of ${total}`}
      </span>
    </div>
  )
}
