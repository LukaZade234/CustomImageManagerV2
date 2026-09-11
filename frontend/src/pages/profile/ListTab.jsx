import { Card, EmptyState } from '../../components/ui'
import ListControls from './ListControls'

/**
 * The shell every profile list shares: heading, blurb, controls, and the three
 * states a personal list can be in.
 *
 * Those three states are the reason this exists rather than each tab rolling
 * its own. "Nothing here yet" and "your search matched nothing" are different
 * situations needing different words, and the loading state must not be
 * mistaken for either — a list that says "nothing saved" for half a second
 * while it loads is actively misleading.
 */
export default function ListTab({
  title,
  blurb,
  searchLabel,
  filter,
  total,
  emptyTitle,
  emptyBody,
  children,
}) {
  const { items } = filter

  return (
    <Card as="section" padding="lg">
      <h2 className="section-heading">{title}</h2>
      {blurb && <p className="text-meta profile-lead">{blurb}</p>}

      {total > 0 && (
        <ListControls
          label={searchLabel}
          query={filter.query}
          onQuery={filter.setQuery}
          sort={filter.sort}
          onSort={filter.setSort}
          options={filter.options}
          shown={items?.length ?? 0}
          total={total}
        />
      )}

      {items === null ? (
        <p className="text-meta" role="status">
          Loading…
        </p>
      ) : filter.filteredToNothing ? (
        <EmptyState
          title="Nothing matches that"
          description={`No results for “${filter.query}”. Clear the search to see all ${total}.`}
        />
      ) : items.length === 0 ? (
        <EmptyState title={emptyTitle} description={emptyBody} />
      ) : (
        children(items)
      )}
    </Card>
  )
}
